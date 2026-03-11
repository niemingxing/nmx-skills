#!/usr/bin/env python3
"""
Visual Note Generator - Batch image generation from pre-analyzed content.

This script accepts structured JSON data (from any AI model) and generates
visual note-style images using Google Gemini image generation API.

Input formats:
  - JSON file with sections array
  - Markdown file (simple header-based split)
  - JSON string via stdin

Usage:
    python3 batch.py --input data.json --output output_dir/
    echo '{"sections":[...]}' | python3 batch.py --output output_dir/
"""

import os
import sys
import json
import base64
import argparse
import time
import re
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


def sanitize_filename(title: str, index: int) -> str:
    """Create a safe filename from title."""
    safe = re.sub(r'[^\w\s-]', '', title)
    safe = re.sub(r'[-\s]+', '-', safe)
    safe = safe.strip('-').lower()
    return f"{index:02d}_{safe}"[:50]


def parse_json_input(data: dict) -> List[ContentChunk]:
    """Parse JSON input into ContentChunks.

    Expected format:
    {
        "style": "sketchnote",  // optional
        "aspect_ratio": "9:16",  // optional
        "brand": "Brand Name",   // optional
        "tagline": "Tagline",    // optional
        "sections": [
            {
                "title": "Section Title",
                "content": "Section content...",
                "visual_type": "list|timeline|comparison|process|diagram"
            }
        ]
    }
    """
    chunks = []
    sections = data.get("sections", [])

    for i, section in enumerate(sections):
        chunks.append(ContentChunk(
            title=section.get("title", f"Section {i+1}"),
            content=section.get("content", ""),
            filename=sanitize_filename(section.get("title", f"section_{i+1}"), i),
            index=i,
            visual_type=section.get("visual_type", "list")
        ))

    return chunks


def parse_markdown_input(content: str) -> List[ContentChunk]:
    """Simple markdown parser - splits by headers.

    This is a fallback for when no AI analysis is available.
    For best results, use pre-analyzed JSON input.
    """
    chunks = []
    lines = content.split('\n')

    current_title = "Introduction"
    current_content = []
    chunk_index = 0

    for line in lines:
        header_match = re.match(r'^(#{1,3})\s+(.+)$', line)

        if header_match:
            if current_content:
                chunks.append(ContentChunk(
                    title=current_title,
                    content='\n'.join(current_content).strip(),
                    filename=sanitize_filename(current_title, chunk_index),
                    index=chunk_index
                ))
                chunk_index += 1

            current_title = header_match.group(2).strip()
            current_content = []
        else:
            if line.strip() or current_content:
                current_content.append(line)

    # Last chunk
    if current_content:
        chunks.append(ContentChunk(
            title=current_title,
            content='\n'.join(current_content).strip(),
            filename=sanitize_filename(current_title, chunk_index),
            index=chunk_index
        ))

    return chunks


class ImageGenerator:
    """Generate images using Gemini API."""

    def __init__(self, api_key: str = None, model: str = "gemini-3.1-flash-image-preview"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError(
                "Google API key not found. "
                "Set GOOGLE_API_KEY environment variable or use --api-key."
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
        description="Generate visual note images from pre-analyzed content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Input formats:

1. JSON file (recommended - from any AI analysis):
   {
     "style": "sketchnote",
     "sections": [
       {"title": "Intro", "content": "...", "visual_type": "list"}
     ]
   }

2. Markdown file (simple header-based split)

3. JSON via stdin:
   echo '{"sections":[...]}' | python3 batch.py --output out/

Examples:
  # From JSON file
  python3 batch.py --input analysis.json --output output/

  # From markdown (simple split)
  python3 batch.py --input notes.md --output output/

  # From stdin
  cat data.json | python3 batch.py --output output/

  # With custom style and brand
  python3 batch.py --input data.json --output out/ --style minimalist --brand "MyBrand"

  # Preview only
  python3 batch.py --input data.json --output out/ --dry-run
        """
    )

    # Input options
    parser.add_argument("--input", "-i", help="Input file (JSON or markdown)")
    parser.add_argument("--output", "-o", required=True, help="Output directory")

    # Style options (can be overridden by JSON input)
    parser.add_argument("--style", "-s", default="sketchnote",
                       choices=list(STYLES.keys()),
                       help="Visual style (can be in JSON input)")
    parser.add_argument("--aspect-ratio", "-a", default="9:16",
                       choices=list(ASPECT_RATIOS.keys()),
                       help="Aspect ratio")

    # Brand options (can be overridden by JSON input)
    parser.add_argument("--brand", "-b", help="Brand name")
    parser.add_argument("--tagline", "-t", help="Brand tagline")

    # Performance options
    parser.add_argument("--workers", "-w", type=int, default=3,
                       help="Number of parallel workers")

    # API options
    parser.add_argument("--api-key", help="Google Gemini API key")
    parser.add_argument("--model", default="gemini-3.1-flash-image-preview",
                       help="Image generation model")

    # Other options
    parser.add_argument("--dry-run", action="store_true",
                       help="Preview without generating")

    args = parser.parse_args()

    # Parse input
    chunks = []
    json_config = {}

    # Try stdin first
    if not sys.stdin.isatty():
        try:
            stdin_data = json.load(sys.stdin)
            json_config = stdin_data
            chunks = parse_json_input(stdin_data)
            print(f"📥 Read {len(chunks)} sections from stdin")
        except json.JSONDecodeError:
            print("⚠️  Warning: stdin is not valid JSON")
            sys.exit(1)

    # Then try file input
    elif args.input:
        file_path = Path(args.input)

        if not file_path.exists():
            print(f"❌ Error: File not found: {args.input}")
            sys.exit(1)

        content = file_path.read_text(encoding='utf-8')

        # Try JSON first
        try:
            data = json.loads(content)
            json_config = data
            chunks = parse_json_input(data)
            print(f"📄 Parsed JSON file: {len(chunks)} sections")
        except json.JSONDecodeError:
            # Fall back to markdown
            print(f"📄 Parsing as markdown (JSON parse failed)")
            chunks = parse_markdown_input(content)

    else:
        print("❌ Error: No input provided. Use --input or pipe JSON via stdin.")
        sys.exit(1)

    if not chunks:
        print("❌ Error: No content sections found in input")
        sys.exit(1)

    # Apply JSON config overrides
    if json_config.get("style") and args.style == "sketchnote":
        args.style = json_config["style"]
    if json_config.get("aspect_ratio"):
        args.aspect_ratio = json_config["aspect_ratio"]
    if json_config.get("brand"):
        args.brand = json_config["brand"]
    if json_config.get("tagline"):
        args.tagline = json_config["tagline"]

    # Dry run
    if args.dry_run:
        print(f"\n{'='*50}")
        print("🔍 Dry run - images that will be generated:")
        print(f"{'='*50}\n")
        print(f"Style: {args.style} | Aspect Ratio: {args.aspect_ratio}")
        if args.brand:
            print(f"Brand: {args.brand}")
        print()
        for i, chunk in enumerate(chunks, 1):
            print(f"{i}. {chunk.filename}.png")
            print(f"   Title: {chunk.title}")
            print(f"   Type: {chunk.visual_type}")
            print(f"   Length: {len(chunk.content)} chars")
            preview = chunk.content[:80].replace('\n', ' ')
            print(f"   Preview: {preview}...")
            print()
        sys.exit(0)

    # Generate images
    try:
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

    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
