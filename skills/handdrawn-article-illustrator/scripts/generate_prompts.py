#!/usr/bin/env python3
"""Generate hand-drawn WeChat article illustration prompts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = SKILL_ROOT / "config" / "style.json"
THEMES_DIR = SKILL_ROOT / "themes"
DEFAULT_THEME = "blue-gray"
# 主题包缺失或解析失败时回退用的中性色，仅作兜底，不应当作正式主题使用。
FALLBACK_THEME_COLORS = {
    "accent_name": "ink-black",
    "accent_color": "#2A2A28",
    "paper_background": "#FAF9F5",
    "paper_surface": "#F0EEE6",
    "ink_color": "#141413",
}

NEGATIVE_DEFAULT = (
    "readable text, letters, numbers, typography, headline, subtitle, label, watermark, logo, "
    "brand mark, AI assistant logo, company logo, UI screenshot, website screenshot, realistic photo, "
    "photorealism, 3d render, isometric 3d, glossy surface, strong shadow, gradient, neon color, "
    "complex background, dense infographic, chart labels, law court, gavel, scales of justice, "
    "aged paper, parchment, sepia, tan blocks, brown blocks, orange blocks, watercolor wash, paper stains, "
    "vintage texture, grunge texture, mottled background, heavy paper grain, "
    "smooth uniform rounded stroke, thin monoline icon, perfect vector geometry, sterile icon set, "
    "mechanical vector icon outline, CAD-straight geometry, ruler-straight edges, perfectly parallel sides, "
    "algorithmic uniform bezier curves, soft cartoon outline, evenly rounded corners, jittery random wobble, chaotic deformation, "
    "random ink blobs, lumpy contour noise, edge noise on every side, hand tremor effect, "
    "scribbly sketch lines, messy rough outline, noisy roughness, over-distorted hand-drawn line, "
    "tiny centered icon, miniature subject, small object lost in whitespace, excessive empty margins, "
    "visible words, pseudo text, fake UI labels, table words, document title, "
    "checkmark, tick mark, person icon, user avatar, profile icon, star icon, pencil icon, tool icon, familiar symbol"
)

# DEFAULT_STYLE 只保留与颜色无关的结构性配置；颜色字段（accent_name、accent_color、
# paper_background、paper_surface、ink_color）统一由主题文件 themes/<name>.json 提供，
# 缺失时用 FALLBACK_THEME_COLORS 兜底。这样换主题只需切换 theme.json，无需改这里的默认值。
DEFAULT_STYLE = {
    "accent_ratio": "8-15%",
    "cover_subject_scale": (
        "one large centered symbolic object occupying 60-72% of the canvas width and 55-68% of the canvas height, "
        "kept inside the center-safe crop area"
    ),
    "inline_subject_scale": (
        "one dominant main object occupying 55-68% of the canvas width or visual footprint, "
        "with up to two close supporting marks"
    ),
    "card_subject_scale": "centered symbolic object occupying about 68-76% of the square canvas",
    "background_mode_sequence": ["paper", "paper", "paper", "inverted"],
    "abstraction_strength": "balanced",
    "ink_variation": "natural_hand_inked",
    "line_style": (
        "Natural hand-inked editorial contour style: near-black filled ink paths that feel hand traced in one confident pass, "
        "not mechanically vectorized. Keep stable readable silhouettes, but allow subtle human asymmetry: slightly imperfect parallel edges, "
        "gently tapered stroke starts and ends, small pressure flattening at corners and overlaps, and a few heavier anchor points. "
        "Long edges should stay calm and mostly continuous with organic tapering, not ruler-straight and not randomly wavy. "
        "Internal detail lines should be thinner, slightly tapered, and hand-placed. Avoid mechanical vector icon outlines, "
        "CAD-straight geometry, perfectly parallel sides, random ink blobs, lumpy noise along every edge, jittery wobble, "
        "scribbly sketch lines, and over-rough contours."
    ),
}

ABSTRACTION_PROFILES = {
    "reference_card": {
        "prompt_clause": (
            "Abstraction strength: reference_card. Stay close to this skill's composition families: "
            "readable hand-drawn workflow objects, folder archive, nested frame, workflow book, orbit/ring table, map field, "
            "chain active block, accent rail blocks, and module puzzle chain. Keep the metaphor immediately legible and article-serving. "
            "Use cloud funnel or left-to-right transform only when the chapter is explicitly about compression or filtering. "
            "Avoid nameless abstract machines, soft shells, organic plumes, sealed chambers, oracle frames, and cryptic surreal mechanisms."
        ),
        "codex_clause": (
            "For built-in image generation, keep the composition close to the reference families: folder/archive, nested frame, "
            "workflow book, chain active block, accent rail blocks, module puzzle chain, orbit/ring table, map field, balance frame, "
            "or scaffold frame. Prefer readable text-free workflow objects over nameless machines. Do not default to a left-to-right "
            "input-transform-output layout."
        ),
    },
    "balanced": {
        "prompt_clause": (
            "Abstraction strength: balanced. Use this skill's composition families as the base, then abstract only enough "
            "to avoid literal document cards, UI panels, role icons, permission badges, and dashboard screenshots. The object must remain "
            "easy to explain through one reader takeaway."
        ),
        "codex_clause": (
            "For built-in image generation, balance readability and abstraction. Translate roles, permissions, tools, files, and workflows "
            "into blank slabs, rounded capsules, archive trays, nested frames, chain blocks, orbit tables, map fields, balance frames, "
            "scaffold frames, modular grids, or single rare-signal capsules, while keeping the article metaphor legible. Use funnel outputs, "
            "filter gates, threshold channels, pipelines, and left-to-right input/output layouts only when the chapter truly concerns "
            "compression, screening, or transformation; avoid repeating that layout across a series."
        ),
    },
    "high_abstract": {
        "prompt_clause": (
            "Abstraction strength: high_abstract. You may use a nameless abstract mechanism, soft slabs, rounded shells, slots, hinges, "
            "vessels, organic plumes, endpoint capsules, and thick connector bands, but the main relation must remain clear. Do not drift "
            "into faces, eyes, body parts, horror, mystical symbols, or unreadable surreal objects."
        ),
        "codex_clause": (
            "For built-in image generation, use a higher-abstraction object-card mechanism when helpful: nameless boundary mechanism, "
            "soft slabs, rounded shells, slots, hinges, vessels, organic plumes, capsules, hollow endpoints, and thick connector bands. "
            "Do not let the image become cryptic; preserve the reader takeaway."
        ),
    },
}

METAPHORS = {
    "network": "a nameless abstract boundary mechanism: one large off-white rounded shell with an accent-color hinge band, loose blank slabs on one side, and blank endpoint capsules on the other",
    "radar": "concentric radar rings with one highlighted risk signal",
    "gate": "an abstract access gate with one approved block passing through",
    "dashboard": "a quiet dashboard panel with indicator lights and a single trend stroke",
    "magnifier": "a floating magnifier over anonymous document blocks with no readable text",
    "bridge": "a simple bridge joining two abstract systems",
    "evidence_box": "an open evidence box containing connected blank cards and small marker dots",
    "building_blocks": "stacked rounded blocks forming a stable governance structure",
    "timeline": "a short segmented timeline with one emphasized checkpoint",
    "browser_window": "a blank browser window connected to tool nodes and an output block",
    "folder": "a folder-like object holding sorted blank sheets and one accent marker",
    "funnel": "a loose group of blank input scraps compressed through a flat funnel into a clean output path",
    "broadcast": "one source object sending an organic plume of blank cards toward several receiving nodes",
    "prism": "one input band entering a flat prism and leaving as three orderly output bands",
    "maze": "a simple labyrinth-like path with one clear exit and a highlighted route segment",
    "flywheel": "a broad circular operating loop with a few grouped stations and one active segment",
    "scaffold": "a temporary scaffold structure around a central capability block",
    "compass_map": "a folded map sheet with a compass needle and one marked future route",
    "sample_tray": "a shallow tray presenting a few abstract sample cards with one selected specimen",
    "balance": "a central pivot balancing two abstract sides with one prioritized side",
    "orbit_table": "an open circular table or ring with a calm empty center and blank cards arranged around it",
    "map_field": "a folded map-like field with a compass mark and a few detached path fragments",
    "tension_frame": "a suspended frame with two opposing blank forces held around a central pivot",
    "temporary_scaffold": "a half-built scaffold frame holding a few blank slabs without closing into a finished system",
    "rare_signal": "one small clear capsule or seed-like signal held inside a larger quiet structure",
}

TARGETS = {
    "cover": {
        "label": "WeChat article cover",
        "aspect": "16:9",
        "size": "auto",
        "final_size": "2400x1024",
        "opening": (
            "Wide WeChat article cover illustration, generated in 16:9 and center-safe for "
            "2400x1024 crop."
        ),
    },
    "inline": {
        "label": "inline section illustration",
        "aspect": "16:9",
        "size": "auto",
        "final_size": "",
        "opening": "16:9 horizontal editorial illustration for a WeChat article section.",
    },
    "card": {
        "label": "square sharing card",
        "aspect": "1:1",
        "size": "1024x1024",
        "final_size": "",
        "opening": "1:1 square object-card editorial illustration.",
    },
}


def load_theme(theme_name: str) -> dict:
    """读取主题文件 themes/<theme_name>.json，返回 colors 等元信息。

    主题文件不存在或解析失败时回退到 FALLBACK_THEME_COLORS，保证脚本不会因缺主题而崩溃。
    返回示例：{"colors": {...}, "theme_name": "blue-gray"}
    """
    theme_name = (theme_name or "").strip() or DEFAULT_THEME
    theme_path = THEMES_DIR / f"{theme_name}.json"
    if not theme_path.exists():
        return {
            "colors": dict(FALLBACK_THEME_COLORS),
            "theme_name": theme_name,
            "_fallback": True,
        }
    data = json.loads(theme_path.read_text(encoding="utf-8"))
    colors = data.get("colors") or {}
    # 合法性兜底：缺哪个色值就用 FALLBACK 补哪个，避免 KeyError。
    merged_colors = dict(FALLBACK_THEME_COLORS)
    merged_colors.update({k: v for k, v in colors.items() if v not in ("", None)})
    return {
        "colors": merged_colors,
        "theme_name": data.get("name", theme_name),
        "display_name": data.get("display_name", theme_name),
        "_fallback": False,
    }


def load_style_config(config_path: Path) -> dict:
    """读取 config/style.json，返回结构性配置（不含颜色，颜色由主题包提供）。

    config/style.json 现在是「激活主题指针 + 本地覆盖层」结构：
    - active_theme：默认激活的主题包名
    - overrides：对主题色值的本地微调（优先级高于主题包，低于 outline 与命令行）
    其余结构性字段（accent_ratio、subject_scale 等）保持原样。
    """
    config = DEFAULT_STYLE.copy()
    if config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        config.update({k: v for k, v in loaded.items() if v not in ("", None)})
    return config


def style_config_for(outline_style: dict, config_path: Path, theme_override: str = "") -> dict:
    """按优先级合并配置：DEFAULT_STYLE ← 主题包 colors ← config overrides ← outline style。

    优先级（高 → 低）：outline.style.<key> > config.overrides > theme.json.colors > DEFAULT_STYLE。
    theme_override 来自命令行 --theme；为空时读 outline.style.theme，再为空读 config.active_theme。
    """
    config = load_style_config(config_path)

    # 1. 解析要激活的主题包：命令行 > outline.style.theme > config.active_theme > DEFAULT_THEME
    theme_name = theme_override or str(outline_style.get("theme") or "").strip() or config.get("active_theme", "") or DEFAULT_THEME
    theme = load_theme(theme_name)
    config["active_theme"] = theme["theme_name"]

    # 2. 注入主题包颜色（作为基础色值层）
    config.update(theme["colors"])

    # 3. 应用 config 的 overrides（本地微调，优先级高于主题包）
    overrides = config.get("overrides") or {}
    for key, value in overrides.items():
        if value not in ("", None):
            config[key] = value

    # 4. 应用 outline.style 覆盖（最高优先级，兼容老的 style.accent_color 等字段）
    for key in (
        "accent_name",
        "accent_color",
        "paper_background",
        "paper_surface",
        "ink_color",
        "accent_ratio",
        "cover_subject_scale",
        "inline_subject_scale",
        "card_subject_scale",
        "background_mode_sequence",
        "abstraction_strength",
        "ink_variation",
        "line_style",
    ):
        if outline_style.get(key) not in ("", None):
            config[key] = outline_style[key]
    return config


def background_mode_for(item: dict, style: dict, config: dict, index: int) -> str:
    explicit = str(
        item.get("background_mode") or item.get("palette_mode") or item.get("palette") or ""
    ).lower().strip()
    if explicit in {"paper", "inverted"}:
        return explicit

    sequence = style.get("background_mode_sequence") or config.get("background_mode_sequence") or []
    if sequence:
        mode = str(sequence[index % len(sequence)]).lower().strip()
        if mode in {"paper", "inverted"}:
            return mode

    return "paper"


def abstraction_strength_for(item: dict, style: dict, config: dict) -> str:
    value = str(
        item.get("abstraction_strength")
        or item.get("abstract_strength")
        or style.get("abstraction_strength")
        or style.get("abstract_strength")
        or config.get("abstraction_strength")
        or "balanced"
    ).lower().strip()
    aliases = {
        "low": "reference_card",
        "reference": "reference_card",
        "reference-card": "reference_card",
        "classic": "reference_card",
        "old": "reference_card",
        "medium": "balanced",
        "default": "balanced",
        "high": "high_abstract",
        "high-abstract": "high_abstract",
        "abstract": "high_abstract",
    }
    value = aliases.get(value, value)
    if value not in ABSTRACTION_PROFILES:
        return "balanced"
    return value


def target_for(item: dict, outline_aspect: str) -> dict:
    key = str(item.get("target", "inline")).lower().strip()
    target = TARGETS.get(key, TARGETS["inline"]).copy()
    if key not in TARGETS and outline_aspect == "1:1":
        target = TARGETS["card"].copy()
    return target


def clean_sentence(value: str) -> str:
    return str(value).strip().rstrip(".。")


def visual_only_text(value: str) -> str:
    """Reduce source words that image models tend to render as visible text."""
    text = clean_sentence(value)
    replacements = (
        ("HTML tables", "complex merged-cell grids"),
        ("HTML table", "complex merged-cell grid"),
        ("HTML", "web markup"),
        ("Markdown", "plain structured documents"),
        ("Word export", "final document export"),
        ("Word", "final document"),
        ("rowspan", "merged rows"),
        ("colspan", "merged columns"),
        ("source code", "raw markup-like blocks"),
        ("PR", "development milestone"),
        ("pull requests", "development milestones"),
        ("pull request", "development milestone"),
        ("AI Agent", "automation node"),
        ("Agent", "automation node"),
        ("blank role cards", "blank relationship blocks"),
        ("blank role card", "blank relationship block"),
        ("central governance node", "central boundary block"),
        ("governance node", "boundary block"),
        ("role cards", "blank relationship blocks"),
        ("role card", "blank relationship block"),
        ("permission dots", "plain endpoint dots"),
        ("permission dot", "plain endpoint dot"),
        ("permissions", "boundary marks"),
        ("permission", "boundary mark"),
        ("roles", "blank lanes"),
        ("role", "blank lane"),
        ("Folia", "the lightweight reading tool"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def image_brief_clause(item: dict) -> str:
    fields = [
        ("chapter claim", item.get("chapter_claim_en") or ""),
        ("visual thesis", item.get("visual_thesis_en") or ""),
        ("main relation", item.get("main_relation_en") or ""),
        ("support structure", item.get("support_structure_en") or ""),
    ]
    parts = []
    for label, raw_value in fields:
        value = visual_only_text(raw_value)
        if value:
            parts.append(f"{label}: {value}")
    if not parts:
        return ""
    return "Semantic image brief: " + "; ".join(parts) + ". "


def build_prompt(*, title: str, item: dict, style: dict, config: dict, background_mode: str, target: dict) -> str:
    concept = clean_sentence(item.get("concept_en") or item.get("concept") or item.get("title_en") or item.get("title") or title)
    concept_visual = visual_only_text(concept)
    metaphor_key = str(item.get("metaphor", "network")).lower().strip()
    metaphor = METAPHORS.get(metaphor_key, metaphor_key.replace("_", " ") or METAPHORS["network"])
    accent = visual_only_text(item.get("accent", "the primary symbolic object"))
    accent_color = config["accent_color"]
    accent_name = config["accent_name"]
    accent_ratio = config["accent_ratio"]
    ink_color = config["ink_color"]
    line_style = config["line_style"]
    abstraction_strength = abstraction_strength_for(item, style, config)
    abstraction_clause = ABSTRACTION_PROFILES[abstraction_strength]["prompt_clause"]

    if target["aspect"] == "1:1":
        scale_clause = config["card_subject_scale"]
    elif item.get("target") == "cover":
        scale_clause = config["cover_subject_scale"]
    else:
        scale_clause = config["inline_subject_scale"]

    if background_mode == "inverted":
        color_clause = (
            f"Use a flat {accent_name} background ({accent_color}) as the only colored field. "
            f"Draw the main object with warm off-white surfaces ({config['paper_surface']}) and "
            f"near-black ink contours ({ink_color}). Do not add a second accent color."
        )
    else:
        color_clause = (
            f"Use a warm off-white paper background ({config['paper_background']}). "
            f"Use exactly one accent color, {accent_name} {accent_color}, placed on {accent}, "
            f"about {accent_ratio} of the image. Do not use other accent colors."
        )

    final_prompt = clean_sentence(item.get("final_prompt_en") or "")
    if final_prompt:
        visual_core = (
            f"Final visual composition: {visual_only_text(final_prompt)}. "
            f"{image_brief_clause(item)}"
        )
    else:
        visual_core = (
            f"Pure visual concept only, never render source words: {concept_visual}. "
            f"Visual metaphor: {metaphor}. "
        )

    return (
        f"{target['opening']} Hand-drawn editorial object-card style, not a copy of any "
        f"brand asset. {color_clause} {line_style} "
        f"{abstraction_clause} "
        f"{visual_core}All document or interface content must be non-readable blank strokes, empty cells, dots, and abstract blocks. "
        f"Composition: {scale_clause}, generous but not excessive negative space, "
        f"large readable object-card layout, quiet low-detail editorial layout. Use off-white inner surfaces and near-black filled ink outlines. No readable text, no "
        f"logo, no watermark, no gradients, no shadows, no 3D, no photorealism."
    )


def build_composition_spec(*, item: dict, config: dict, background_mode: str, target: dict, abstraction_strength: str) -> dict:
    metaphor_key = str(item.get("metaphor", "network")).lower().strip()
    if target["aspect"] == "1:1":
        scale_clause = config["card_subject_scale"]
    elif item.get("target") == "cover":
        scale_clause = config["cover_subject_scale"]
    else:
        scale_clause = config["inline_subject_scale"]
    return {
        "layout": "single centered object-card composition with low detail and controlled negative space",
        "metaphor_key": metaphor_key,
        "metaphor_visual": METAPHORS.get(metaphor_key, metaphor_key.replace("_", " ") or METAPHORS["network"]),
        "chapter_claim_en": item.get("chapter_claim_en", ""),
        "visual_thesis_en": item.get("visual_thesis_en", ""),
        "main_relation_en": item.get("main_relation_en", ""),
        "support_structure_en": item.get("support_structure_en", ""),
        "background_mode": background_mode,
        "abstraction_strength": abstraction_strength,
        "subject_scale": scale_clause,
        "accent_color": config["accent_color"],
        "lock_rules": [
            "keep one dominant main object",
            "keep supporting marks close to the main object",
            "do not add readable text or pseudo labels",
            "do not add extra decorative objects",
            "preserve the same background mode and accent-color placement",
            "keep blank rectangles, cards, sheets, nodes, and panels flat off-white unless they are the configured {accent_name} accent".format(accent_name=config["accent_name"]),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outline", required=True, help="Path to article outline JSON")
    parser.add_argument("--out", required=True, help="Output prompts JSON path")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Style config JSON path")
    parser.add_argument(
        "--theme",
        default="",
        help="主题包名（themes/ 下的目录名），优先级高于 config.active_theme 和 outline.style.theme；留空则按配置解析",
    )
    parser.add_argument("--negative", default=NEGATIVE_DEFAULT, help="Negative prompt")
    args = parser.parse_args()

    outline = json.loads(Path(args.outline).read_text(encoding="utf-8"))
    title = outline.get("title_en") or outline.get("title", "")
    style = outline.get("style", {})
    config = style_config_for(style, Path(args.config), theme_override=args.theme)
    outline_aspect = outline.get("aspect", "16:9")

    rows = []
    for index, item in enumerate(outline.get("illustrations", [])):
        target = target_for(item, outline_aspect)
        background_mode = background_mode_for(item, style, config, index)
        abstraction_strength = abstraction_strength_for(item, style, config)
        rows.append(
            {
                "id": item.get("id") or f"{index + 1:02d}",
                "position": item.get("position", ""),
                "target": item.get("target", "inline"),
                "title": item.get("title", ""),
                "concept": item.get("concept", ""),
                "title_en": item.get("title_en", ""),
                "concept_en": item.get("concept_en", ""),
                "chapter_claim_en": item.get("chapter_claim_en", ""),
                "visual_thesis_en": item.get("visual_thesis_en", ""),
                "main_relation_en": item.get("main_relation_en", ""),
                "support_structure_en": item.get("support_structure_en", ""),
                "final_prompt_en": item.get("final_prompt_en", ""),
                "metaphor": item.get("metaphor", ""),
                "abstraction_strength": abstraction_strength,
                "abstraction_prompt_clause": ABSTRACTION_PROFILES[abstraction_strength]["prompt_clause"],
                "codex_abstraction_clause": ABSTRACTION_PROFILES[abstraction_strength]["codex_clause"],
                "background_mode": background_mode,
                "accent_name": config["accent_name"],
                "accent_color": config["accent_color"],
                "aspect": target["aspect"],
                "image_size": target["size"],
                "final_size": target["final_size"],
                "composition_spec": build_composition_spec(
                    item=item,
                    config=config,
                    background_mode=background_mode,
                    target=target,
                    abstraction_strength=abstraction_strength,
                ),
                "prompt": build_prompt(
                    title=title,
                    item=item,
                    style=style,
                    config=config,
                    background_mode=background_mode,
                    target=target,
                ),
                "negative_prompt": args.negative,
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
