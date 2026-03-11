#!/usr/bin/env python3
"""
Visual style definitions for visual note generation.
Each style defines the visual aesthetic for generated infographics.
"""

STYLES = {
    "sketchnote": {
        "name": "Sketch Note",
        "description": "Hand-drawn doodle style with sticky notes and arrows",
        "colors": ["coral", "mint", "lavender", "mustard", "sky blue"],
        "background": "white",
        "elements": ["sticky notes", "arrow connectors", "icons", "doodles", "highlights"],
        "best_for": ["Educational content", "Training materials", "Tutorials"],
        "prompt": """
Visual note-taking infographic with hand-drawn sketchnote style.
Include: sticky notes, arrow connectors, icons, color-coded sections,
marker pen highlights, doodle elements, clean white background.
Use pastel colors: coral, mint, lavender, mustard, sky blue.
Professional yet friendly style with bilingual text support.
"""
    },

    "minimalist": {
        "name": "Minimalist",
        "description": "Clean, simple layout with lots of white space",
        "colors": ["black", "white", "gray", "one accent color"],
        "background": "white",
        "elements": ["simple shapes", "thin lines", "clear typography"],
        "best_for": ["Professional summaries", "Corporate content", "Reports"],
        "prompt": """
Clean minimalist infographic with ample white space.
Simple geometric shapes, thin lines, limited color palette (2-3 colors max).
Clear hierarchy, sans-serif typography, no decorative elements.
Professional corporate style with focus on readability.
"""
    },

    "colorful": {
        "name": "Colorful",
        "description": "Bold, vibrant colors with eye-catching graphics",
        "colors": ["electric blue", "hot pink", "lime green", "sunny yellow"],
        "background": "gradient or light",
        "elements": ["large icons", "bold typography", "gradients"],
        "best_for": ["Marketing content", "Social media", "Presentations"],
        "prompt": """
Bold vibrant infographic with eye-catching colors.
Gradient backgrounds, large typography, icon-heavy layout.
Bright accent colors: electric blue, hot pink, lime green, sunny yellow.
High contrast, energetic feel with modern design.
"""
    },

    "dark": {
        "name": "Dark Mode",
        "description": "Dark background with neon accents",
        "colors": ["cyan", "magenta", "lime", "amber"],
        "background": "#1a1a1a dark gray",
        "elements": ["glowing effects", "bright lines", "tech aesthetic"],
        "best_for": ["Tech content", "Developer docs", "Modern apps"],
        "prompt": """
Dark mode infographic with dark gray/black background (#1a1a1a).
Neon accent colors: cyan (#00d4ff), magenta (#ff00ff), lime (#00ff00), amber (#ffcc00).
Glowing effects, thin bright lines for contrast.
Modern tech aesthetic with futuristic feel.
"""
    },

    "retro": {
        "name": "Retro Vintage",
        "description": "Vintage paper texture with muted colors",
        "colors": ["sepia", "olive", "rust", "cream", "teal"],
        "background": "aged paper texture",
        "elements": ["imperfect lines", "classic typography", "paper texture"],
        "best_for": ["Nostalgic content", "Classic topics", "Artistic projects"],
        "prompt": """
Vintage-style infographic with paper texture background.
Muted earth tones: sepia, olive, rust, cream, teal.
Hand-drawn feel with slightly imperfect lines.
Classic typography, aged paper aesthetic with nostalgic charm.
"""
    }
}

ASPECT_RATIOS = {
    "9:16": {
        "name": "Vertical",
        "dimensions": "1080x1920",
        "best_for": ["Mobile", "Instagram Stories", "TikTok", "Phone viewing"]
    },
    "1:1": {
        "name": "Square",
        "dimensions": "1080x1080",
        "best_for": ["Instagram posts", "General use", "Thumbnails"]
    },
    "16:9": {
        "name": "Horizontal",
        "dimensions": "1920x1080",
        "best_for": ["Desktop", "Presentations", "YouTube", "Twitter"]
    }
}


def get_style_info(style_name: str) -> dict:
    """Get detailed information about a style."""
    return STYLES.get(style_name.lower(), STYLES["sketchnote"])


def get_style_prompt(style_name: str) -> str:
    """Get the prompt prefix for a style."""
    return get_style_info(style_name)["prompt"]


def list_styles():
    """Print all available styles."""
    print("\n" + "="*50)
    print("Available Visual Styles")
    print("="*50)
    for key, style in STYLES.items():
        print(f"\n[{key}] {style['name']}")
        print(f"    {style['description']}")
        print(f"    Best for: {', '.join(style['best_for'])}")
    print()


def list_aspect_ratios():
    """Print all available aspect ratios."""
    print("\n" + "="*50)
    print("Available Aspect Ratios")
    print("="*50)
    for key, ratio in ASPECT_RATIOS.items():
        print(f"\n[{key}] {ratio['name']} ({ratio['dimensions']})")
        print(f"    Best for: {', '.join(ratio['best_for'])}")
    print()


if __name__ == "__main__":
    list_styles()
    list_aspect_ratios()
