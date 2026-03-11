#!/usr/bin/env python3
"""
Visual Note Generator - Batch and parallel image generation with AI-powered smart splitting.

Usage:
    python3 batch.py --input document.md --output output_dir/ [--max-images 10] [--workers 4]
"""

import os
import sys
import json
import base64
import argparse
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Callable

try:
    import requests
except ImportError:
    print("Error: requests module not found. Install with: pip install requests")
    sys.exit(1)

from styles import STYLES, get_style_prompt, ASPECT_RATIOS


@dataclass
class ContentChunk:
    """A chunk of content to generate an image from."""
    title: str
    content: str
    filename: str
    index: int
    visual_type: str = "list"


@dataclass
class GenerationResult:
    """Result of an image generation."""
    success: bool
    chunk: ContentChunk
    output_path: str
    error: Optional[str] = None
    duration: float = 0.0


class DocumentAnalyzer:
    """AI-powered document analyzer for intelligent content splitting."""

    def __init__(self, api_key: str = None, model: str = "gemini-2.0-flash-exp"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError("API key required. Set GOOGLE_API_KEY or use --api-key")

    def analyze(self, content: str, max_images: int = 10) -> dict:
        """
        Analyze document and intelligently split into sections.

        Args:
            content: The document content to analyze
            max_images: Maximum number of images to generate

        Returns:
            Dict with analysis results including sections list
        """
        # Truncate content if too long
        max_content_length = 12000
        if len(content) > max_content_length:
            content = content[:max_content_length] + "\n...[content truncated]"

        prompt = f"""You are a document analyst for visual note generation. Analyze this document and suggest how to split it into {max_images} visual images.

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
  "overview": "Brief 2-3 sentence summary",
  "suggested_style": "sketchnote|minimalist|colorful|dark|retro",
  "sections": [
    {{
      "title": "Section title",
      "content": "Actual extracted/summarized content for this section (3-8 sentences)",
      "key_points": ["concept1", "concept2"],
      "visual_type": "timeline|comparison|list|process|diagram|other"
    }}
  ]
}}

IMPORTANT:
- Group by MEANING, not just by headers
- Each section should tell a complete mini-story
- Keep related points together even if they cross headers
- Maximum {max_images} sections
- Include actual CONTENT in each section, not just descriptions
"""

        response = self._call_api(prompt)
        return self._parse_json_response(response)

    def _call_api(self, prompt: str, temperature: float = 0.7) -> str:
        """Call the Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 8192
            }
        }

        response = requests.post(url, json=payload, timeout=120)
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

        raise ValueError(f"Could not parse JSON from response")


def sanitize_filename(title: str, index: int) -> str:
    """Create a safe filename from title."""
    import re
    safe = re.sub(r'[^\w\s-]', '', title)
    safe = re.sub(r'[-\s]+', '-', safe)
    safe = safe.strip('-').lower()
    return f"{index:02d}_{safe}"[:50]


class ImageGenerator:
    """Generate images using Gemini API."""

    def __init__(self, api_key: str = None, model: str = "gemini-3.1-flash-image-preview"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError(
                "Google API key not found. "
                "Set GOOGLE_API_KEY environment variable or provide --api-key."
            )

    def build_prompt(
        self,
        content: str,
        style: str = "sketchnote",
        aspect_ratio: str = "9:16",
        brand_name: str = None,
        brand_tagline: str = None,
        title: str = None,
        visual_type: str = "list"
    ) -> str:
        """Build a complete image generation prompt."""
        style_prefix = get_style_prompt(style)

        # Add visual type guidance
        visual_guidance = self._get_visual_guidance(visual_type)

        prompt = f"""
{style_prefix.strip()}

VERTICAL INFOGRAPHIC ({aspect_ratio} aspect ratio)

{visual_guidance}
"""

        # Add header
        if brand_name or title:
            prompt += "=== HEADER TOP ===\n"
            if brand_name:
                prompt += f"Top left: Large bold text \"{brand_name}\""
                if brand_tagline:
                    prompt += f" with subtitle \"{brand_tagline}\""
                prompt += "\n"
            if title:
                prompt += f"Title: \"{title}\"\n"
            prompt += "Add small doodle decorations around header\n\n"

        # Add main content
        prompt += f"""=== CONTENT ===
{content}

"""

        # Add footer
        if brand_name:
            prompt += f"""=== FOOTER BOTTOM ===
At the bottom: A horizontal banner with \"{brand_name}\""""
            if brand_tagline:
                prompt += f" | {brand_tagline}"
            prompt += f"""
Small text: "Made with {brand_name}"
Add small doodle decorations at bottom
"""

        return prompt.strip()

    def _get_visual_guidance(self, visual_type: str) -> str:
        """Get visual layout guidance based on type."""
        templates = {
            "timeline": "=== VISUAL LAYOUT: TIMELINE ===\nHorizontal or vertical timeline with key events. Use arrow connectors between events. Each event: date/time label + title + brief description.",
            "comparison": "=== VISUAL LAYOUT: COMPARISON ===\nSplit view with two columns. Left side: Topic A | Right side: Topic B. VS badge in center. Each side has 3-4 key points with icons.",
            "list": "=== VISUAL LAYOUT: NUMBERED LIST ===\nClean numbered list with icons. Each item: number + icon + title + brief text. Use visual hierarchy with size and color.",
            "process": "=== VISUAL LAYOUT: PROCESS FLOW ===\nCircular or linear flow diagram. Each step in a box/card connected by arrows. Number steps clearly. Include key action for each step.",
            "diagram": "=== VISUAL LAYOUT: DIAGRAM ===\nCentral concept in middle. Related concepts branching out. Use connecting lines with labels. Include key relationships.",
            "other": "=== VISUAL LAYOUT: FLEXIBLE ===\nOrganize content visually with clear visual hierarchy, grouped related items, visual connectors between concepts, and icons for key concepts."
        }
        return templates.get(visual_type, templates["list"])

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        timeout: int = 180
    ) -> tuple[bool, str]:
        """Generate a single image. Returns (success, error_message)."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8}
        }

        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            result = response.json()

            if "candidates" in result and len(result["candidates"]) > 0:
                parts = result["candidates"][0].get("content", {}).get("parts", [])

                for part in parts:
                    if "inlineData" in part:
                        img_data = part["inlineData"].get("data")
                        if img_data:
                            output_path = Path(output_path)
                            output_path.parent.mkdir(parents=True, exist_ok=True)

                            img_bytes = base64.b64decode(img_data)
                            with open(output_path, "wb") as f:
                                f.write(img_bytes)

                            return True, ""

            if "error" in result:
                error_msg = result['error'].get('message', 'Unknown error')
                return False, error_msg

            return False, "No image data in response"

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                return False, "Rate limited"
            elif e.response.status_code == 400:
                try:
                    detail = e.response.json().get('error', {}).get('message', 'Bad request')
                    return False, detail
                except:
                    return False, "Bad request"
            return False, f"HTTP error: {e}"
        except requests.exceptions.Timeout:
            return False, "Request timed out"
        except Exception as e:
            return False, str(e)


class BatchGenerator:
    """Batch and parallel image generation."""

    def __init__(
        self,
        api_key: str = None,
        style: str = "sketchnote",
        aspect_ratio: str = "9:16",
        brand_name: str = None,
        brand_tagline: str = None,
        workers: int = 3
    ):
        self.generator = ImageGenerator(api_key)
        self.style = style
        self.aspect_ratio = aspect_ratio
        self.brand_name = brand_name
        self.brand_tagline = brand_tagline
        self.workers = workers

    def generate(
        self,
        chunks: List[ContentChunk],
        output_dir: str,
        progress_callback: Callable[[GenerationResult], None] = None
    ) -> List[GenerationResult]:
        """Generate images for all chunks in parallel."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = []
        completed = 0
        total = len(chunks)

        print(f"\n🚀 Starting batch generation: {total} images")
        print(f"   Style: {self.style} | Aspect Ratio: {self.aspect_ratio}")
        print(f"   Workers: {self.workers} | Output: {output_dir}\n")

        def generate_with_retry(chunk: ContentChunk, max_retries: int = 2) -> GenerationResult:
            """Generate a single chunk with retry logic."""
            output_file = output_path / f"{chunk.filename}.png"

            for attempt in range(max_retries + 1):
                start_time = time.time()

                prompt = self.generator.build_prompt(
                    content=chunk.content,
                    style=self.style,
                    aspect_ratio=self.aspect_ratio,
                    brand_name=self.brand_name,
                    brand_tagline=self.brand_tagline,
                    title=chunk.title,
                    visual_type=chunk.visual_type
                )

                success, error = self.generator.generate_image(
                    prompt=str(prompt),
                    output_path=str(output_file)
                )

                duration = time.time() - start_time

                if success:
                    return GenerationResult(
                        success=True,
                        chunk=chunk,
                        output_path=str(output_file),
                        duration=duration
                    )
                elif "Rate limited" in error and attempt < max_retries:
                    wait_time = (attempt + 1) * 5
                    print(f"   ⏳ Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    return GenerationResult(
                        success=False,
                        chunk=chunk,
                        output_path=str(output_file),
                        error=error,
                        duration=duration
                    )

            return GenerationResult(
                success=False,
                chunk=chunk,
                output_path=str(output_file),
                error="Max retries exceeded",
                duration=0
            )

        # Parallel generation
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_chunk = {
                executor.submit(generate_with_retry, chunk): chunk
                for chunk in chunks
            }

            for future in as_completed(future_to_chunk):
                result = future.result()
                results.append(result)
                completed += 1

                status = "✅" if result.success else "❌"
                duration_str = f"{result.duration:.1f}s"
                print(f"   [{completed}/{total}] {status} {result.chunk.filename} ({duration_str})")

                if result.error:
                    print(f"      Error: {result.error}")

                if progress_callback:
                    progress_callback(result)

        # Summary
        success_count = sum(1 for r in results if r.success)
        total_duration = sum(r.duration for r in results)

        print(f"\n{'='*50}")
        print(f"✨ Batch generation complete!")
        print(f"   Success: {success_count}/{total}")
        print(f"   Failed: {total - success_count}")
        print(f"   Total time: {total_duration:.1f}s")
        if total > 1:
            print(f"   Average: {total_duration/total:.1f}s per image")
        print(f"{'='*50}\n")

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Batch generate visual note images from markdown using AI smart splitting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python3 batch.py --input notes.md --output output/

  # Specify max images
  python3 batch.py --input notes.md --output output/ --max-images 10

  # With brand and style
  python3 batch.py --input notes.md --output output/ --brand "MyBrand" --style minimalist

  # Parallel generation
  python3 batch.py --input notes.md --output output/ --workers 4

  # Preview first (dry run)
  python3 batch.py --input notes.md --output output/ --dry-run
        """
    )

    # Required
    parser.add_argument("--input", "-i", required=True, help="Input markdown file")
    parser.add_argument("--output", "-o", required=True, help="Output directory")

    # Content options
    parser.add_argument("--max-images", "-n", type=int, default=8,
                       help="Maximum number of images to generate (default: 8)")

    # Style options
    parser.add_argument("--style", "-s", default="sketchnote",
                       choices=list(STYLES.keys()),
                       help="Visual style (default: sketchnote, or let AI suggest)")
    parser.add_argument("--aspect-ratio", "-a", default="9:16",
                       choices=list(ASPECT_RATIOS.keys()),
                       help="Aspect ratio (default: 9:16)")

    # Brand options
    parser.add_argument("--brand", "-b", help="Brand name for header/footer")
    parser.add_argument("--tagline", "-t", help="Brand tagline")

    # Performance options
    parser.add_argument("--workers", "-w", type=int, default=3,
                       help="Number of parallel workers (default: 3)")

    # API options
    parser.add_argument("--api-key", help="Google API key")
    parser.add_argument("--model", default="gemini-3.1-flash-image-preview",
                       help="Image generation model (default: gemini-3.1-flash-image-preview)")

    # Other options
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview without generating images")

    args = parser.parse_args()

    # Read document
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: File not found: {args.input}")
        sys.exit(1)

    # Analyze document with AI
    print(f"\n🧠 Analyzing document with AI...")
    print(f"   Document: {args.input}")
    print(f"   Max images: {args.max_images}")
    print(f"   Please wait...\n")

    try:
        analyzer = DocumentAnalyzer(api_key=args.api_key)
        analysis = analyzer.analyze(content, max_images=args.max_images)
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        sys.exit(1)

    # Display analysis
    print(f"{'='*50}")
    print(f"📄 {analysis.get('title', 'Document Analysis')}")
    print(f"{'='*50}")
    print(f"\n{analysis.get('overview', '')}\n")

    suggested_style = analysis.get('suggested_style', 'sketchnote')
    if args.style == "sketchnote" and suggested_style in STYLES:
        args.style = suggested_style

    print(f"Suggested style: {suggested_style}")
    print(f"Using style: {args.style}")
    print(f"Sections to generate: {len(analysis.get('sections', []))}\n")

    # Convert to ContentChunks
    chunks = []
    for i, section_data in enumerate(analysis.get('sections', [])):
        chunks.append(ContentChunk(
            title=section_data.get('title', f'Section {i+1}'),
            content=section_data.get('content', ''),
            filename=sanitize_filename(section_data.get('title', f'section_{i+1}'), i),
            index=i,
            visual_type=section_data.get('visual_type', 'list')
        ))

    # Dry run mode
    if args.dry_run:
        print(f"{'='*50}")
        print("🔍 Dry run - images that will be generated:")
        print(f"{'='*50}\n")
        for i, chunk in enumerate(chunks, 1):
            print(f"{i}. {chunk.filename}.png")
            print(f"   Title: {chunk.title}")
            print(f"   Type: {chunk.visual_type}")
            print(f"   Length: {len(chunk.content)} chars")
            preview = chunk.content[:80].replace('\n', ' ')
            print(f"   Preview: {preview}...")
            print()
        print(f"Output directory: {args.output}")
        print(f"Style: {args.style} | Aspect Ratio: {args.aspect_ratio}")
        sys.exit(0)

    # Generate images
    batch_gen = BatchGenerator(
        api_key=args.api_key,
        style=args.style,
        aspect_ratio=args.aspect_ratio,
        brand_name=args.brand,
        brand_tagline=args.tagline,
        workers=args.workers
    )

    results = batch_gen.generate(chunks, args.output)

    if any(not r.success for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
