---
name: visual-note-generator
description: "Generate visual note-style infographics from markdown documents using AI image generation. Use this skill whenever the user wants to create visual notes, sketchnote-style images, infographics from documents, or convert text content into visual formats. This skill handles the entire workflow - document analysis, style selection, aspect ratio choice, API configuration, and image generation."
---

# Visual Note Generator

A skill for converting markdown documents into beautiful visual note-style infographics using AI image generation.

## How this skill works

1. **Analyze the input document** - Extract key topics, structure, and content
2. **Guide user through choices** - Style, aspect ratio, brand customization
3. **Configure API** - Set up Google Gemini API key
4. **Generate images** - Create visual note infographics (batch or single)
5. **Save and organize** - Output images to a designated folder

## Step 1: Get the document

First, ask the user for the markdown document they want to convert:
- What is the path to the markdown file?
- Or they can paste content directly

Read the document and analyze its structure. Identify:
- Main topics/chapters (each will become a separate image)
- Key concepts and relationships
- Important data points, formulas, or processes

## Step 2: Choose visual style

Present the user with style options and ask them to choose:

| Style | Description | Best For |
|-------|-------------|----------|
| **sketchnote** | Hand-drawn doodle style with sticky notes, arrows, icons, pastel colors | Educational content, training materials |
| **minimalist** | Clean, simple layout with lots of white space, minimal colors | Professional summaries, corporate content |
| **colorful** | Bold, vibrant colors with eye-catching graphics | Marketing content, social media |
| **dark** | Dark background with neon/bright accents | Modern tech content, developer docs |
| **retro** | Vintage/Paper texture with muted colors | Nostalgic themes, classic content |

Ask the user: **"Which visual style would you like? (sketchnote/minimalist/colorful/dark/retro)"**

## Step 3: Choose aspect ratio

Ask the user: **"What aspect ratio? (9:16 for mobile/story, 1:1 for square, 16:9 for desktop)"**

| Ratio | Dimensions | Use Case |
|-------|------------|----------|
| 9:16 | Vertical | Mobile, Instagram Stories, TikTok |
| 1:1 | Square | Instagram posts, general use |
| 16:9 | Horizontal | Desktop, presentations, YouTube |

## Step 4: Configure API key

Ask the user: **"Please provide your Google Gemini API key (or set GOOGLE_API_KEY environment variable)"**

If they don't have one, explain:
1. Go to https://aistudio.google.com/app/apikey
2. Create a new API key
3. Paste it here or set as environment variable

Store the API key in the script and ensure it's used for generation.

## Step 5: Brand customization (optional)

Ask: **"Do you want to add brand elements? If yes, provide:**
- Brand name (for headers)
- Tagline/subtitle (optional)
- Any specific colors or styling preferences**"

## Step 6: Generate images

For each main topic/chapter in the document:

1. Create a detailed prompt that includes:
   - The chosen style's visual characteristics
   - The aspect ratio specification
   - Brand elements (header/footer)
   - The actual content from that chapter

2. Call the generation script to create the image

3. Save to output directory with descriptive filename

4. Show progress and confirm before continuing to next image

## Generation script usage

The skill has a bundled Python script at `scripts/generate.py`. Use it like this:

```bash
python3 scripts/generate.py \
  --prompt "<detailed prompt>" \
  --output "output/image_01.png" \
  --api-key "$GOOGLE_API_KEY"
```

The script handles:
- API calls to Gemini 3.1 Flash Image Preview
- Base64 decoding and image saving
- Error handling and retry logic

## Batch Generation

For processing entire markdown documents, use the batch script:

```bash
python3 scripts/batch.py \
  --input document.md \
  --output output_folder/ \
  --style sketchnote \
  --workers 4
```

**Batch features:**
- **Automatic document splitting** - Divides markdown by headers (#, ##, ###)
- **Parallel generation** - Multiple workers generate images simultaneously
- **Progress tracking** - Real-time status updates
- **Error recovery** - Continues on failure, shows summary
- **Smart chunking** - Splits long sections at logical break points

**Batch options:**
| Option | Description | Default |
|--------|-------------|---------|
| `--input` / `-i` | Input markdown file | Required |
| `--output` / `-o` | Output directory | Required |
| `--style` / `-s` | Visual style | sketchnote |
| `--aspect-ratio` / `-a` | Aspect ratio | 9:16 |
| `--workers` / `-w` | Parallel workers | 3 |
| `--brand` / `-b` | Brand name | None |
| `--tagline` / `-t` | Brand tagline | None |
| `--max-chunk-size` | Max chars per chunk | 1000 |
| `--dry-run` | Preview without generating | - |
| `--list-chunks` | Show detected chunks | - |

**Preview before generating:**
```bash
# See what chunks will be generated
python3 scripts/batch.py --input doc.md --output out/ --list-chunks

# Dry run to verify settings
python3 scripts/batch.py --input doc.md --output out/ --dry-run
```

**Performance tips:**
- Use `--workers 3-5` for best balance (API rate limits apply)
- Higher workers = faster but more likely to hit rate limits
- For large documents, start with lower worker count

## Style definitions

Reference `scripts/styles.py` for detailed style prompts:

### Sketchnote
```
Visual note-taking infographic with hand-drawn sketchnote style.
Include: sticky notes, arrow connectors, icons, color-coded sections,
marker pen highlights, doodle elements, clean white background.
Use pastel colors: coral, mint, lavender, mustard, sky blue.
Chinese + English bilingual text. Professional yet friendly style.
```

### Minimalist
```
Clean minimalist infographic with ample white space.
Simple geometric shapes, thin lines, limited color palette (2-3 colors max).
Clear hierarchy, sans-serif typography, no decorative elements.
Professional corporate style.
```

### Colorful
```
Bold vibrant infographic with eye-catching colors.
Gradient backgrounds, large typography, icon-heavy layout.
Bright accent colors: electric blue, hot pink, lime green, sunny yellow.
High contrast, energetic feel.
```

### Dark
```
Dark mode infographic with dark gray/black background.
Neon accent colors: cyan, magenta, lime, amber.
Glowing effects, thin bright lines for contrast.
Modern tech aesthetic.
```

### Retro
```
Vintage-style infographic with paper texture background.
Muted earth tones: sepia, olive, rust, cream.
Hand-drawn feel with slightly imperfect lines.
Classic typography, aged paper aesthetic.
```

## Header and footer format

For branded images, include:

**Header:**
```
=== HEADER TOP ===
Top left: Brand name (bold, large)
Below brand: Subtitle/tagline
Title: [Image Title]
Add doodle decorations around header
```

**Footer:**
```
=== FOOTER BOTTOM ===
Horizontal banner: "Brand | Tagline"
Small text: "Made with [Brand]"
Add small doodle decorations
```

## Output organization

Create an output directory structure:
```
visual_notes/
├── 01_topic_name.png
├── 02_topic_name.png
├── 03_topic_name.png
└── ...
```

Filenames should be descriptive and numbered for ordering.

## Error handling

If generation fails:
1. Check API key validity
2. Verify internet connectivity
3. Check API quota limits
4. Retry with exponential backoff
5. Show user the error and suggest solutions

## User interaction flow

Always:
1. Confirm each step before proceeding
2. Show a preview/sample of the first image before generating all
3. Allow user to adjust settings between images
4. Provide progress updates during generation
5. Show final output location when done

## Example prompts

See `references/examples.md` for sample prompts in each style.

---

**Remember:** This skill is about transforming written content into visual formats. Guide users through each choice patiently, and generate images one at a time so they can review and adjust as needed.
