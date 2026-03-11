#!/usr/bin/env python3
"""
Visual Note Generator - Image generation script for skill
Usage: python3 generate.py --prompt "..." --output "path.png" [--api-key "..."]
"""

import os
import sys
import base64
import argparse
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests module not found. Install with: pip install requests")
    sys.exit(1)

from styles import STYLES, get_style_prompt


def generate_image(
    prompt: str,
    output_path: str,
    api_key: str = None,
    model: str = "gemini-3.1-flash-image-preview",
    max_retries: int = 3
) -> bool:
    """
    Generate an image using Google Gemini API.

    Args:
        prompt: The text prompt for image generation
        output_path: Where to save the generated image
        api_key: Google API key (or uses GOOGLE_API_KEY env var)
        model: Model name to use
        max_retries: Number of retry attempts

    Returns:
        True if successful, False otherwise
    """
    # Get API key from parameter or environment
    api_key = api_key or os.getenv("GOOGLE_API_KEY")

    if not api_key or api_key == "your-api-key-here":
        print("Error: Google API key not found.")
        print("Please set GOOGLE_API_KEY environment variable or provide --api-key argument.")
        return False

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "temperature": 0.8
        }
    }

    for attempt in range(max_retries):
        try:
            print(f"Generating image... (attempt {attempt + 1}/{max_retries})")

            response = requests.post(url, json=payload, timeout=180)
            response.raise_for_status()

            result = response.json()

            # Parse Gemini API response for image data
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

                            print(f"✅ Image saved: {output_path}")
                            return True

            # Check for error response
            if "error" in result:
                error_msg = result['error'].get('message', 'Unknown error')
                print(f"❌ API Error: {error_msg}")

                # Check for quota issues
                if "quota" in error_msg.lower():
                    print("💡 Tip: You may have exceeded your API quota.")
                    print("   Visit: https://aistudio.google.com/app/apikey")

                return False

            print(f"❌ Generation failed: No image data in response")
            print(f"   Response: {str(result)[:500]}")
            return False

        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP Error: {e}")
            if e.response.status_code == 429:
                print("💡 Rate limited. Waiting before retry...")
                time.sleep(5 ** attempt)  # Exponential backoff
                continue
            elif e.response.status_code == 400:
                try:
                    error_detail = e.response.json()
                    print(f"   Detail: {error_detail.get('error', {}).get('message', 'Unknown')}")
                except:
                    pass
                return False
            return False

        except requests.exceptions.Timeout:
            print(f"❌ Request timed out. Retrying...")
            time.sleep(2 ** attempt)
            continue

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False

    return False


def build_prompt(
    content: str,
    style: str = "sketchnote",
    aspect_ratio: str = "9:16",
    brand_name: str = None,
    brand_tagline: str = None,
    title: str = None
) -> str:
    """
    Build a complete image generation prompt.

    Args:
        content: The main content to visualize
        style: Visual style (sketchnote, minimalist, colorful, dark, retro)
        aspect_ratio: Image aspect ratio (9:16, 1:1, 16:9)
        brand_name: Optional brand name for header
        brand_tagline: Optional tagline
        title: Optional title for the image

    Returns:
        Complete prompt string
    """
    style_prefix = get_style_prompt(style)

    prompt = f"""
{style_prefix.strip()}

VERTICAL INFOGRAPHIC ({aspect_ratio} aspect ratio)

"""

    # Add header if brand provided
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

    # Add footer if brand provided
    if brand_name:
        prompt += f"""=== FOOTER BOTTOM ===
At the bottom: A horizontal banner with \"{brand_name}"
"""
        if brand_tagline:
            prompt += f"| {brand_tagline}"
        prompt += f"""\nSmall text: "Made with {brand_name}"
Add small doodle decorations at bottom
"""

    return prompt.strip()


def main():
    parser = argparse.ArgumentParser(description="Generate visual note images")
    parser.add_argument("--prompt", required=True, help="Image generation prompt")
    parser.add_argument("--content", help="Main content to visualize")
    parser.add_argument("--style", default="sketchnote",
                       choices=["sketchnote", "minimalist", "colorful", "dark", "retro"],
                       help="Visual style")
    parser.add_argument("--aspect-ratio", default="9:16",
                       choices=["9:16", "1:1", "16:9"],
                       help="Aspect ratio")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--api-key", help="Google API key")
    parser.add_argument("--brand", help="Brand name for header/footer")
    parser.add_argument("--tagline", help="Brand tagline")
    parser.add_argument("--title", help="Image title")

    args = parser.parse_args()

    # Build prompt from components if content provided
    if args.content:
        prompt = build_prompt(
            content=args.content,
            style=args.style,
            aspect_ratio=args.aspect_ratio,
            brand_name=args.brand,
            brand_tagline=args.tagline,
            title=args.title
        )
    else:
        prompt = args.prompt

    # Generate image
    success = generate_image(
        prompt=prompt,
        output_path=args.output,
        api_key=args.api_key
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
