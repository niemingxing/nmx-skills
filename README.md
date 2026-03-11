# nmx-skills

Claude Code 技能集合 - 提升开发效率和内容创作能力

## Skills

### visual-note-generator

将 Markdown 文档转换为精美视觉笔记风格信息图的 AI 技能。

#### 功能特点

- **5 种视觉风格**：sketchnote（手绘）、minimalist（简约）、colorful（鲜艳）、dark（深色）、retro（复古）
- **3 种宽高比**：9:16（竖版）、1:1（方形）、16:9（横版）
- **6 种布局类型**：list、timeline、comparison、process、diagram、other
- **批量生成**：支持并行生成多张图片
- **品牌定制**：支持添加品牌名称和标语

#### 使用场景

| 场景 | 推荐风格 | 宽高比 |
|------|----------|--------|
| 教育培训 | sketchnote | 9:16 |
| 技术文档 | dark | 16:9 |
| 营销内容 | colorful | 1:1 |
| 专业报告 | minimalist | 16:9 |

#### 快速开始

```bash
# JSON 输入（推荐）
python3 scripts/batch.py --input analysis.json --output out/ --workers 4

# Markdown 输入
python3 scripts/batch.py --input doc.md --output out/

# 单图生成
python3 scripts/generate.py --prompt "..." --output image.png
```

#### JSON 输入格式

```json
{
  "style": "sketchnote",
  "aspect_ratio": "9:16",
  "brand": "Brand Name",
  "sections": [
    {
      "title": "Section Title",
      "content": "Content to visualize...",
      "visual_type": "list"
    }
  ]
}
```

#### 要求

- Python 3.7+
- Google Gemini API key
- `pip install requests`

---

## 安装

### 方式一：全局安装（推荐）

```bash
git clone https://github.com/niemingxing/nmx-skills.git
cp -r nmx-skills/visual-note-generator ~/.claude/skills/
```

### 方式二：项目内安装

```bash
cp -r nmx-skills/visual-note-generator .claude/skills/
```

---

## 配置

设置 Gemini API key：

```bash
export GOOGLE_API_KEY="your-api-key-here"
```

或在使用时通过 `--api-key` 参数传递。

---

## License

MIT
