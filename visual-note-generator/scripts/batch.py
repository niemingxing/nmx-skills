#!/usr/bin/env python3
"""
Visual Note Generator - Batch and parallel image generation.

Usage:
    python3 batch.py --input document.md --output output_dir/ [--workers 4]
    python3 batch.py --input document.md --output output_dir/ --style sketchnote
"""

import os
import sys
import re
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

# Optional analyzer for smart splitting
try:
    from analyzer import DocumentAnalyzer, DocumentSection
    ANALYZER_AVAILABLE = True
except ImportError:
    ANALYZER_AVAILABLE = False


@dataclass
class ContentChunk:
    """A chunk of content to generate an image from."""
    title: str
    content: str
    filename: str
    index: int


@dataclass
class GenerationResult:
    """Result of an image generation."""
    success: bool
    chunk: ContentChunk
    output_path: str
    error: Optional[str] = None
    duration: float = 0.0


class MarkdownParser:
    """Parse markdown documents into content chunks."""

    # Headers to split on (priority order)
    SPLIT_HEADERS = ['#', '##', '###']

    def __init__(self, max_chunk_size: int = 1000):
        """
        Args:
            max_chunk_size: Maximum characters per chunk (soft limit)
        """
        self.max_chunk_size = max_chunk_size

    def parse_file(self, file_path: str) -> List[ContentChunk]:
        """Parse a markdown file into content chunks."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return self.parse_content(content, source_file=file_path)

    def parse_content(self, content: str, source_file: str = "") -> List[ContentChunk]:
        """Parse markdown content into chunks based on headers."""
        chunks = []
        lines = content.split('\n')

        current_title = "Introduction"
        current_content = []
        current_level = 0
        chunk_index = 0

        for line in lines:
            # Check for headers
            header_match = re.match(r'^(#{1,3})\s+(.+)$', line)

            if header_match:
                level = len(header_match.group(1))
                title = header_match.group(2).strip()

                # Save previous chunk if exists
                if current_content:
                    chunks.append(ContentChunk(
                        title=current_title,
                        content='\n'.join(current_content).strip(),
                        filename=self._sanitize_filename(current_title, chunk_index),
                        index=chunk_index
                    ))
                    chunk_index += 1

                # Start new chunk
                current_title = title
                current_content = []
                current_level = level
            else:
                # Skip empty lines at start of content
                if line.strip() or current_content:
                    current_content.append(line)

                # Split if chunk gets too large
                if len('\n'.join(current_content)) > self.max_chunk_size:
                    # Try to split at a good break point
                    if self._split_chunk(chunks, current_content, current_title, chunk_index):
                        chunk_index += 1
                        current_content = []

        # Don't forget the last chunk
        if current_content:
            chunks.append(ContentChunk(
                title=current_title,
                content='\n'.join(current_content).strip(),
                filename=self._sanitize_filename(current_title, chunk_index),
                index=chunk_index
            ))

        return chunks

    def _split_chunk(self, chunks: List[ContentChunk],
                     content: List[str], title: str, index: int) -> bool:
        """Try to split a large chunk at a logical break point."""
        content_str = '\n'.join(content)

        # Look for good split points: empty lines followed by non-list content
        split_points = []
        for i, line in enumerate(content):
            if i > len(content) * 0.3:  # Only split after 30% into content
                if not line.strip() and i + 1 < len(content):
                    next_line = content[i + 1]
                    # Good split: not a list item, not a code block
                    if (not next_line.strip().startswith(('-', '*', '+', '>', '```'))
                            and not next_line.strip().startswith(('1.', '2.', '3.', '4.', '5.'))):
                        split_points.append(i)

        if split_points:
            split_at = split_points[0]
            chunks.append(ContentChunk(
                title=title,
                content='\n'.join(content[:split_at]).strip(),
                filename=self._sanitize_filename(f"{title}_part1", index),
                index=index
            ))
            content[:] = content[split_at:]
            return True

        return False

    def _sanitize_filename(self, title: str, index: int) -> str:
        """Create a safe filename from title."""
        # Remove/replace special characters
        safe = re.sub(r'[^\w\s-]', '', title)
        safe = re.sub(r'[-\s]+', '-', safe)
        safe = safe.strip('-').lower()

        # Add index prefix for ordering
        return f"{index:02d}_{safe}"[:50]  # Limit length


class ImageGenerator:
    """Generate images using API with parallel support."""

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
        title: str = None
    ) -> str:
        """Build a complete image generation prompt."""
        style_prefix = get_style_prompt(style)

        prompt = f"""
{style_prefix.strip()}

VERTICAL INFOGRAPHIC ({aspect_ratio} aspect ratio)

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

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        timeout: int = 180
    ) -> tuple[bool, str]:
        """
        Generate a single image.

        Returns:
            (success, error_message)
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.8
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            result = response.json()

            # Parse response for image data
            if "candidates" in result and len(result["candidates"]) > 0:
                parts = result["candidates"][0].get("content", {}).get("parts", [])

                for part in parts:
                    if "inlineData" in part:
                        img_data = part["inlineData"].get("data")
                        if img_data:
                            # Ensure output directory exists
                            output_path = Path(output_path)
                            output_path.parent.mkdir(parents=True, exist_ok=True)

                            # Save image
                            img_bytes = base64.b64decode(img_data)
                            with open(output_path, "wb") as f:
                                f.write(img_bytes)

                            return True, ""

            # Check for error response
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
        """
        Generate images for all chunks in parallel.

        Args:
            chunks: List of content chunks to generate
            output_dir: Output directory for images
            progress_callback: Optional callback for progress updates

        Returns:
            List of generation results
        """
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

                # Build prompt
                prompt = self.generator.build_prompt(
                    content=chunk.content,
                    style=self.style,
                    aspect_ratio=self.aspect_ratio,
                    brand_name=self.brand_name,
                    brand_tagline=self.brand_tagline,
                    title=chunk.title
                )

                # Generate
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

                # Progress indicator
                status = "✅" if result.success else "❌"
                duration_str = f"{result.duration:.1f}s"
                print(f"   [{completed}/{total}] {status} {result.chunk.filename} ({duration_str})")

                if result.error:
                    print(f"      Error: {result.error}")

                # Call progress callback if provided
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
        description="Batch generate visual note images from markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate from markdown file
  python3 batch.py --input notes.md --output output/

  # With custom style and brand
  python3 batch.py --input notes.md --output output/ --style minimalist --brand "MyBrand"

  # Parallel with 4 workers
  python3 batch.py --input notes.md --output output/ --workers 4

  # Specify aspect ratio
  python3 batch.py --input notes.md --output output/ --aspect-ratio 16:9
        """
    )

    # Input options
    parser.add_argument("--input", "-i", required=True,
                       help="Input markdown file")
    parser.add_argument("--output", "-o", required=True,
                       help="Output directory for images")

    # Style options
    parser.add_argument("--style", "-s", default="sketchnote",
                       choices=list(STYLES.keys()),
                       help="Visual style")
    parser.add_argument("--aspect-ratio", "-a", default="9:16",
                       choices=list(ASPECT_RATIOS.keys()),
                       help="Aspect ratio")

    # Brand options
    parser.add_argument("--brand", "-b", help="Brand name for header/footer")
    parser.add_argument("--tagline", "-t", help="Brand tagline")

    # Performance options
    parser.add_argument("--workers", "-w", type=int, default=3,
                       help="Number of parallel workers (default: 3)")

    # Content options
    parser.add_argument("--max-chunk-size", type=int, default=1000,
                       help="Maximum characters per chunk for simple mode (default: 1000)")
    parser.add_argument("--smart-split", action="store_true",
                       help="Use AI to intelligently analyze and split the document")
    parser.add_argument("--max-images", type=int, default=8,
                       help="Maximum number of images to generate (smart mode, default: 8)")

    # API options
    parser.add_argument("--api-key", help="Google API key")
    parser.add_argument("--model", default="gemini-3.1-flash-image-preview",
                       help="Gemini model to use")

    # Other options
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be generated without calling API")
    parser.add_argument("--list-chunks", action="store_true",
                       help="List detected chunks and exit")

    args = parser.parse_args()

    # Check for smart split mode
    use_smart_split = args.smart_split

    if use_smart_split and not ANALYZER_AVAILABLE:
        print("⚠️  Smart split requested but analyzer module not available")
        print("   Falling back to simple parsing")
        use_smart_split = False

    # Parse input file
    if use_smart_split:
        # Smart AI-powered splitting
        print(f"\n🧠 Using AI-powered smart split (max {args.max_images} images)...")
        print("   This may take a minute as we analyze the document...\n")

        try:
            # Read content
            with open(args.input, 'r', encoding='utf-8') as f:
                content = f.read()

            # Analyze with AI
            analyzer = DocumentAnalyzer(api_key=args.api_key)
            analysis = analyzer.analyze(content, max_images=args.max_images)

            # Display analysis results
            print(f"{'='*50}")
            print(f"📄 {analysis.title}")
            print(f"{'='*50}")
            print(f"\n{analysis.overview}\n")
            print(f"Suggested style: {analysis.suggested_style}")
            print(f"Sections found: {len(analysis.sections)}")

            # Convert DocumentSections to ContentChunks
            chunks = []
            for i, section in enumerate(analysis.sections):
                chunks.append(ContentChunk(
                    title=section.title,
                    content=section.content,
                    filename=MarkdownParser._sanitize_filename(section.title, i),
                    index=i
                ))

            # Use suggested style if not overridden
            if args.style == "sketchnote" and analysis.suggested_style:
                suggested = analysis.suggested_style
                if suggested in STYLES:
                    args.style = suggested
                    print(f"Using suggested style: {suggested}")

        except Exception as e:
            print(f"❌ Smart split failed: {e}")
            print("   Falling back to simple parsing")
            use_smart_split = False

    if not use_smart_split:
        # Simple header-based parsing
        parser_obj = MarkdownParser(max_chunk_size=args.max_chunk_size)

        try:
            chunks = parser_obj.parse_file(args.input)
        except FileNotFoundError:
            print(f"❌ Error: File not found: {args.input}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error parsing file: {e}")
            sys.exit(1)

    if not chunks:
        print("❌ No content chunks found in input file")
        sys.exit(1)

    # List chunks mode
    if args.list_chunks:
        print(f"\n📋 Found {len(chunks)} content chunks:\n")
        for i, chunk in enumerate(chunks, 1):
            preview = chunk.content[:100].replace('\n', ' ')
            print(f"{i}. [{chunk.filename}]")
            print(f"   Title: {chunk.title}")
            print(f"   Content: {preview}...")
            print()
        sys.exit(0)

    # Dry run mode
    if args.dry_run:
        print(f"\n🔍 Dry run mode - showing {len(chunks)} images to generate:\n")
        for i, chunk in enumerate(chunks, 1):
            print(f"{i}. {chunk.filename}.png")
            print(f"   Title: {chunk.title}")
            print(f"   Length: {len(chunk.content)} chars")
        print(f"\nOutput directory: {args.output}")
        print(f"Style: {args.style} | Aspect Ratio: {args.aspect_ratio}")
        sys.exit(0)

    # Generate
    batch_gen = BatchGenerator(
        api_key=args.api_key,
        style=args.style,
        aspect_ratio=args.aspect_ratio,
        brand_name=args.brand,
        brand_tagline=args.tagline,
        workers=args.workers
    )

    results = batch_gen.generate(chunks, args.output)

    # Exit with error code if any failed
    if any(not r.success for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
