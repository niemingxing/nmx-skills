#!/usr/bin/env python3
"""
AI-powered document analyzer for intelligent content splitting.

Uses LLM to analyze document structure and semantically group content
for better visual note generation.
"""

import os
import json
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


@dataclass
class DocumentSection:
    """A semantically coherent section of the document."""
    title: str
    content: str
    key_points: List[str]
    context_before: str = ""
    context_after: str = ""
    suggested_visual: str = ""  # Suggested visual layout type


@dataclass
class DocumentAnalysis:
    """Analysis result of a document."""
    title: str
    overview: str
    sections: List[DocumentSection]
    total_estimated_images: int
    suggested_style: str = ""
    metadata: dict = None


class DocumentAnalyzer:
    """AI-powered document analyzer."""

    def __init__(self, api_key: str = None, model: str = "gemini-2.0-flash-exp"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError("API key required for document analysis")

        if requests is None:
            raise ImportError("requests module required")

    def analyze(self, content: str, max_images: int = 10) -> DocumentAnalysis:
        """
        Analyze document and intelligently split into sections.

        Args:
            content: The document content to analyze
            max_images: Maximum number of images to generate

        Returns:
            DocumentAnalysis with semantically grouped sections
        """
        # First pass: Get overall structure
        structure_prompt = self._build_structure_prompt(content, max_images)
        structure_response = self._call_api(structure_prompt)

        # Parse structure response
        try:
            structure_data = self._parse_json_response(structure_response)
        except:
            # Fallback to simple parsing if JSON fails
            structure_data = self._fallback_structure(content, max_images)

        # Second pass: For each section, extract key points and visual suggestions
        sections = []
        for i, section_data in enumerate(structure_data.get("sections", [])):
            section = self._analyze_section(
                content,
                section_data,
                i,
                len(structure_data.get("sections", []))
            )
            sections.append(section)

        return DocumentAnalysis(
            title=structure_data.get("title", "Document"),
            overview=structure_data.get("overview", ""),
            sections=sections,
            total_estimated_images=len(sections),
            suggested_style=structure_data.get("suggested_style", "sketchnote"),
            metadata=structure_data.get("metadata", {})
        )

    def _build_structure_prompt(self, content: str, max_images: int) -> str:
        """Build prompt for document structure analysis."""
        # Truncate content if too long
        max_content_length = 8000
        if len(content) > max_content_length:
            content = content[:max_content_length] + "\n...[content truncated]"

        return f"""You are a document analyst for visual note generation. Analyze this document and suggest how to split it into {max_images} visual images.

DOCUMENT CONTENT:
```
{content}
```

Your task:
1. Identify the document's main topic and purpose
2. Group related content together semantically (don't just follow headers - think about flow!)
3. Each group should be:
   - Coherent and focused on ONE main idea
   - Small enough to fit on one visual image
   - Logically complete (don't cut off explanations)

Respond ONLY with valid JSON in this exact format:
{{
  "title": "Document main title",
  "overview": "Brief 2-3 sentence summary of what this document covers",
  "suggested_style": "sketchnote|minimalist|colorful|dark|retro",
  "sections": [
    {{
      "title": "Section title",
      "content_summary": "What this section covers",
      "key_concepts": ["concept1", "concept2"],
      "visual_type": "timeline|comparison|list|process|diagram|other",
      "content_range": "Approximate location (e.g., 'Introduction through Chapter 1')"
    }}
  ],
  "metadata": {{
    "total_topics": number,
    "target_audience": "who this is for",
    "difficulty_level": "beginner|intermediate|advanced"
  }}
}}

IMPORTANT:
- Group by MEANING, not just by headers
- Each section should tell a complete mini-story
- Keep related points together even if they cross headers
- Maximum {max_images} sections
"""

    def _analyze_section(
        self,
        full_content: str,
        section_data: dict,
        index: int,
        total: int
    ) -> DocumentSection:
        """Analyze a specific section in detail."""
        title = section_data.get("title", f"Section {index + 1}")
        content_summary = section_data.get("content_summary", "")

        # Build context-aware prompt for this section
        context_prompt = f"""You are extracting content for visual note generation.

SECTION TITLE: {title}
WHAT THIS COVERS: {content_summary}
POSITION: This is section {index + 1} of {total}

FULL DOCUMENT:
```
{full_content}
```

Extract the actual content for this section. Requirements:
1. Find and extract ALL relevant content for "{title}"
2. Include key points, explanations, examples
3. Keep it focused but complete
4. Format as a clean summary suitable for visual notes

Respond with JSON:
{{
  "content": "The actual extracted/summarized content",
  "key_points": ["point 1", "point 2", "point 3"],
  "suggested_visual": "timeline|comparison|list|process|diagram"
}}
"""

        response = self._call_api(context_prompt, temperature=0.3)

        try:
            result = self._parse_json_response(response)
        except:
            # Fallback
            result = {
                "content": content_summary,
                "key_points": section_data.get("key_concepts", []),
                "suggested_visual": section_data.get("visual_type", "list")
            }

        return DocumentSection(
            title=title,
            content=result.get("content", content_summary),
            key_points=result.get("key_points", []),
            suggested_visual=result.get("suggested_visual", "list")
        )

    def _call_api(self, prompt: str, temperature: float = 0.7) -> str:
        """Call the Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 4096
            }
        }

        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        if "candidates" in result and len(result["candidates"]) > 0:
            parts = result["candidates"][0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    return part["text"]

        raise ValueError("No text in API response")

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response (handles markdown code blocks)."""
        response = response.strip()

        # Try direct parse
        try:
            return json.loads(response)
        except:
            pass

        # Try extracting from markdown code block
        if "```" in response:
            # Find JSON block
            start = response.find("```json") + 7
            if start == 6:  # ```json not found
                start = response.find("```") + 3
            end = response.rfind("```")
            if start > 0 and end > start:
                json_str = response[start:end].strip()
                return json.loads(json_str)

        # Try finding first { and last }
        start = response.find("{")
        end = response.rfind("}")
        if start >= 0 and end > start:
            json_str = response[start:end + 1]
            return json.loads(json_str)

        raise ValueError(f"Could not parse JSON from response: {response[:200]}")

    def _fallback_structure(self, content: str, max_images: int) -> dict:
        """Fallback simple parsing when AI analysis fails."""
        lines = content.split('\n')

        sections = []
        current_section = {"title": "Introduction", "content": []}
        section_count = 0

        for line in lines:
            if line.startswith('#'):
                if current_section["content"]:
                    sections.append({
                        "title": current_section["title"],
                        "content_summary": '\n'.join(current_section["content"][-5:]),
                        "key_concepts": [],
                        "visual_type": "list"
                    })
                    section_count += 1
                    if section_count >= max_images:
                        break
                current_section = {
                    "title": line.lstrip('#').strip(),
                    "content": []
                }
            else:
                current_section["content"].append(line)

        # Add last section
        if current_section["content"] and section_count < max_images:
            sections.append({
                "title": current_section["title"],
                "content_summary": '\n'.join(current_section["content"][-5:]),
                "key_concepts": [],
                "visual_type": "list"
            })

        return {
            "title": "Document Analysis",
            "overview": "Analysis completed with fallback parsing",
            "suggested_style": "sketchnote",
            "sections": sections[:max_images],
            "metadata": {"analysis_method": "fallback"}
        }

    def get_visual_template(self, section: DocumentSection) -> str:
        """Get a visual template suggestion based on section type."""
        templates = {
            "timeline": """
=== VISUAL LAYOUT: TIMELINE ===
Horizontal or vertical timeline with key events.
Use arrow connectors between events.
Each event: date/time label + title + brief description.
""",
            "comparison": """
=== VISUAL LAYOUT: COMPARISON ===
Split view with two columns.
Left side: Topic A | Right side: Topic B
VS badge in center.
Each side has 3-4 key points with icons.
""",
            "list": """
=== VISUAL LAYOUT: NUMBERED LIST ===
Clean numbered list with icons.
Each item: number + icon + title + brief text.
Use visual hierarchy with size and color.
""",
            "process": """
=== VISUAL LAYOUT: PROCESS FLOW ===
Circular or linear flow diagram.
Each step in a box/card connected by arrows.
Number steps clearly.
Include key action for each step.
""",
            "diagram": """
=== VISUAL LAYOUT: DIAGRAM ===
Central concept in middle.
Related concepts branching out.
Use connecting lines with labels.
Include key relationships.
""",
            "other": """
=== VISUAL LAYOUT: FLEXIBLE ===
Organize content visually with:
- Clear visual hierarchy
- Grouped related items
- Visual connectors between concepts
- Icons for key concepts
"""
        }
        return templates.get(section.suggested_visual, templates["other"])


def main():
    """CLI for document analysis."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze document for smart splitting")
    parser.add_argument("--input", "-i", required=True, help="Input file")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--max-images", type=int, default=8,
                       help="Maximum number of images to generate")
    parser.add_argument("--api-key", help="Google API key")

    args = parser.parse_args()

    # Read content
    with open(args.input, 'r', encoding='utf-8') as f:
        content = f.read()

    # Analyze
    print(f"🔍 Analyzing document: {args.input}")
    analyzer = DocumentAnalyzer(api_key=args.api_key)

    result = analyzer.analyze(content, max_images=args.max_images)

    # Display results
    print(f"\n{'='*50}")
    print(f"📄 {result.title}")
    print(f"{'='*50}")
    print(f"\n{result.overview}\n")
    print(f"Suggested style: {result.suggested_style}")
    print(f"Images to generate: {result.total_estimated_images}")

    print(f"\n{'='*50}")
    print("📋 Sections:")
    print(f"{'='*50}\n")

    for i, section in enumerate(result.sections, 1):
        print(f"{i}. {section.title}")
        print(f"   Type: {section.suggested_visual}")
        print(f"   Key points: {', '.join(section.key_points[:3])}")
        preview = section.content[:100].replace('\n', ' ')
        print(f"   Content: {preview}...")
        print()

    # Save to JSON if requested
    if args.output:
        output_data = {
            "title": result.title,
            "overview": result.overview,
            "suggested_style": result.suggested_style,
            "sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "key_points": s.key_points,
                    "suggested_visual": s.suggested_visual
                }
                for s in result.sections
            ]
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved analysis to: {args.output}")


if __name__ == "__main__":
    main()
