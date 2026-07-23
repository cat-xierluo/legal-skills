#!/usr/bin/env python3
"""Prepare WeChat article illustration prompts for ImageGen/built-in generation."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from env_utils import load_env_file


DEFAULT_EDIT_MODEL = "Qwen/Qwen-Image-Edit-2509"
DEFAULT_T2I_MODEL = "Tongyi-MAI/Z-Image-Turbo"
DEFAULT_T2I_IMAGE_SIZE = "auto"
DEFAULT_QWEN_T2I_IMAGE_SIZE = "1664x928"
DEFAULT_ZIMAGE_T2I_IMAGE_SIZE = "2048x872"


def require_pillow():
    try:
        from PIL import Image
    except ImportError:
        print("Missing dependency: pillow")
        print("Install it with: python3 -m pip install -r scripts/requirements.txt")
        raise SystemExit(1)
    return Image


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except ValueError as exc:
        raise SystemExit(f"Invalid size: {value}. Use WIDTHxHEIGHT, for example 2400x1024") from exc


def safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value).strip()
    value = re.sub(r"\s+", "_", value)
    return value[:80] or "illustration"


def resize_center_crop(in_path: Path, out_path: Path, target_w: int, target_h: int) -> None:
    Image = require_pillow()
    image = Image.open(in_path).convert("RGB")
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((int(round(image.width * scale)), int(round(image.height * scale))), Image.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    cropped = resized.crop((left, top, left + target_w, top + target_h))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_path, format="PNG", optimize=True)


def make_base_image(path: Path, size: str) -> None:
    Image = require_pillow()
    width, height = parse_size(size)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (250, 249, 245)).save(path)


def resolve_t2i_image_size(model: str, requested: str) -> str:
    raw = str(requested or "").strip()
    if raw and raw.lower() != "auto":
        return raw
    if "z-image" in str(model).lower():
        return DEFAULT_ZIMAGE_T2I_IMAGE_SIZE
    return DEFAULT_QWEN_T2I_IMAGE_SIZE


def run_generate_prompts(outline: Path, out_json: Path, config: str, theme: str = "") -> None:
    script = Path(__file__).parent / "generate_prompts.py"
    command = [sys.executable, str(script), "--outline", str(outline), "--out", str(out_json)]
    if config:
        command += ["--config", config]
    if theme:
        command += ["--theme", theme]
    subprocess.check_call(command)


def run_local_renderer(prompts_json: Path, outdir: Path, image_size: str, final_size: str, *, board: bool = True) -> None:
    script = Path(__file__).parent / "render_local_images.py"
    command = [
        sys.executable,
        str(script),
        "--prompts",
        str(prompts_json),
        "--outdir",
        str(outdir),
        "--size",
        resolve_t2i_image_size(DEFAULT_T2I_MODEL, image_size),
        "--final-size",
        final_size,
    ]
    if board:
        command.append("--board")
    subprocess.check_call(command)


def run_siliconflow(command_args: list[str], api_key: str) -> None:
    env = os.environ.copy()
    env["SILICONFLOW_AK"] = api_key
    script = Path(__file__).parent / "siliconflow_generate.py"
    subprocess.check_call([sys.executable, str(script), *command_args], env=env)


def generate_edit(
    *,
    item: dict,
    api_key: str,
    model: str,
    base_image: Path,
    out_path: Path,
    image2: str,
    image3: str,
) -> None:
    command = [
        "--model",
        model,
        "--prompt",
        item["prompt"],
        "--negative",
        item.get("negative_prompt", ""),
        "--image",
        str(base_image),
        "--out",
        str(out_path),
    ]
    if image2:
        command += ["--image2", image2]
    if image3:
        command += ["--image3", image3]
    run_siliconflow(command, api_key)


def build_guided_edit_prompt(item: dict) -> str:
    composition = json.dumps(item.get("composition_spec", {}), ensure_ascii=False)
    return (
        "Use the input image as a strict composition guide. Preserve the same canvas aspect ratio, "
        "main object type, object count, object placement, subject size, background mode, and accent-color placement. "
        "Preserve the input palette exactly: warm off-white paper, near-black ink, and the configured blue-gray accent only. "
        "Do not introduce tan, brown, orange, sepia, aged paper, watercolor wash, paper stains, mottled texture, or grunge texture. "
        "All blank rectangles, cards, sheets, nodes, and panels must remain flat off-white or the configured blue-gray; never recolor them as tan paper blocks. "
        "Do not invent new objects, words, UI labels, logos, panels, shadows, gradients, or decorative marks. "
        "Only restyle the guide into a more natural hand-inked editorial object-card illustration. "
        "Keep all document/interface contents abstract and non-readable. "
        f"Composition contract: {composition}. "
        f"Style and semantic brief: {item['prompt']}"
    )


def composition_guide_path(item: dict, guide_dir: Path) -> Path:
    item_id = safe_name(str(item.get("id") or "item"))
    title = safe_name(str(item.get("title") or item.get("target") or "image"))
    return guide_dir / f"{item_id}_{title}.png"


def generate_t2i(*, item: dict, api_key: str, model: str, image_size: str, cfg: float | None, out_path: Path) -> None:
    command = [
        "--model",
        model,
        "--prompt",
        item["prompt"],
        "--negative",
        item.get("negative_prompt", ""),
        "--image-size",
        resolve_t2i_image_size(model, item.get("image_size") or image_size),
        "--out",
        str(out_path),
    ]
    if cfg is not None:
        command += ["--cfg", str(cfg)]
    run_siliconflow(command, api_key)


def build_codex_prompt(item: dict) -> str:
    negative = str(item.get("negative_prompt", "")).strip()
    prompt = str(item.get("prompt", "")).strip()
    target = str(item.get("target") or "inline").strip()
    final_size = str(item.get("final_size") or "").strip()
    abstraction_strength = str(item.get("abstraction_strength") or "balanced").strip()
    abstraction_clause = str(item.get("codex_abstraction_clause") or "").strip()
    size_note = f"Target delivery size: {final_size}." if final_size else "Target delivery: wide inline article illustration."
    brief_parts = []
    labels = {
        "chapter_claim_en": "claim",
        "visual_thesis_en": "visual thesis",
        "main_relation_en": "main relation",
        "support_structure_en": "support structure",
    }
    for key, label in labels.items():
        value = str(item.get(key) or "").strip()
        if value:
            brief_parts.append(f"{label}: {value}")
    brief_note = " Semantic grounding only, do not render these words as text: " + " | ".join(brief_parts) + "." if brief_parts else ""
    return (
        f"{prompt}\n\n"
        "Generate a single clean editorial illustration from this prompt. "
        f"Abstraction strength setting: {abstraction_strength}. "
        f"{abstraction_clause} "
        "Keep the output text-free and object-only. Do not add captions, labels, logos, UI screenshots, or watermarks. "
        "Do not put checkmarks, person icons, avatars, stars, pencils, tools, app symbols, or familiar semantic icons inside the shapes; use only blank cards, dots, short strokes, and abstract blocks. "
        "Preserve the configured palette and hand-drawn object-card composition. "
        f"Target type: {target}. {size_note}{brief_note} "
        f"Negative constraints: {negative}"
    ).strip()


def write_codex_generation_queue(items: list[dict], outdir: Path, *, final_size: str) -> None:
    """Write an agent-consumable queue for Codex/ChatGPT built-in image generation.

    The built-in image tool is available to the Agent, not to this Python process.
    Therefore this mode deliberately writes prompts and target filenames, then stops.
    """
    queue: list[dict] = []
    lines = [
        "# Codex Image Generation Queue",
        "",
        "This queue is for the Agent's built-in Codex/ChatGPT image generation capability.",
        "The Python script does not call an external API and cannot invoke the built-in image tool by itself.",
        "Generate each item in order, save/export the returned image using the suggested filename when the host app provides a file handle, then build a board if needed.",
        "",
    ]
    for item in items:
        item_id = safe_name(str(item.get("id") or "item"))
        title = safe_name(str(item.get("title") or item.get("target") or "image"))
        output_file = f"{item_id}_{title}.png"
        item_final_size = str(item.get("final_size") or (final_size if item.get("target") == "cover" else "")).strip()
        final_output_file = f"{item_id}_{title}_{item_final_size}.png" if item_final_size else ""
        prompt = build_codex_prompt(item)
        queue.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "target": item.get("target", "inline"),
                "abstraction_strength": item.get("abstraction_strength", "balanced"),
                "codex_abstraction_clause": item.get("codex_abstraction_clause", ""),
                "background_mode": item.get("background_mode"),
                "image_size": item.get("image_size"),
                "final_size": item_final_size,
                "suggested_output_file": output_file,
                "suggested_final_output_file": final_output_file,
                "chapter_claim_en": item.get("chapter_claim_en", ""),
                "visual_thesis_en": item.get("visual_thesis_en", ""),
                "main_relation_en": item.get("main_relation_en", ""),
                "support_structure_en": item.get("support_structure_en", ""),
                "final_prompt_en": item.get("final_prompt_en", ""),
                "prompt": prompt,
                "negative_prompt": item.get("negative_prompt", ""),
                "composition_spec": item.get("composition_spec", {}),
            }
        )
        lines.extend(
            [
                f"## {item.get('id', item_id)} {item.get('title', title)}",
                "",
                f"- Target: `{item.get('target', 'inline')}`",
                f"- Abstraction strength: `{item.get('abstraction_strength', 'balanced')}`",
                f"- Suggested output: `{output_file}`",
                f"- Suggested final output: `{final_output_file or output_file}`",
                "",
                "```text",
                prompt,
                "```",
                "",
            ]
        )

    queue_path = outdir / "codex_generation_queue.json"
    markdown_path = outdir / "codex_generation_queue.md"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"wrote Codex generation queue: {queue_path}")
    print(f"wrote Codex generation notes: {markdown_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outline", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--env", default=str(Path(__file__).resolve().parents[1] / "config" / "secrets.env"))
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config" / "style.json"))
    parser.add_argument(
        "--theme",
        default="",
        help="主题包名（themes/ 下的目录名），透传给 generate_prompts.py；留空则由 config/style.json 的 active_theme 决定",
    )
    parser.add_argument(
        "--mode",
        choices=["codex", "local", "edit", "t2i", "guided-edit"],
        default="codex",
        help="codex writes the ImageGen/built-in generation queue; local is an explicit diagnostic sketch mode only; API modes require --allow-api.",
    )
    parser.add_argument(
        "--allow-api",
        action="store_true",
        help="Explicitly allow external image API calls for experimental modes.",
    )
    parser.add_argument("--prompts-only", action="store_true", help="Only write prompts.json; do not render images or call an image API")
    parser.add_argument("--edit-model", default=DEFAULT_EDIT_MODEL)
    parser.add_argument("--t2i-model", default=DEFAULT_T2I_MODEL)
    parser.add_argument("--image-size", default=DEFAULT_T2I_IMAGE_SIZE)
    parser.add_argument("--base-size", default=DEFAULT_T2I_IMAGE_SIZE)
    parser.add_argument("--base", default="")
    parser.add_argument("--image2", default="")
    parser.add_argument("--image3", default="")
    parser.add_argument("--cfg", type=float, default=4.0)
    parser.add_argument("--final-size", default="2400x1024")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    prompts_json = outdir / "prompts.json"
    run_generate_prompts(Path(args.outline), prompts_json, args.config, args.theme)
    items = json.loads(prompts_json.read_text(encoding="utf-8"))

    if args.prompts_only:
        print(f"wrote {prompts_json}")
        return

    if args.mode == "local":
        run_local_renderer(prompts_json, outdir, args.image_size, args.final_size)
        print(f"rendered local preview images in {outdir}")
        return

    if args.mode == "codex":
        write_codex_generation_queue(items, outdir, final_size=args.final_size)
        print("Codex mode wrote the ImageGen/built-in generation queue; now use the Agent's built-in image tool to generate the actual images.")
        return

    if not args.allow_api:
        raise SystemExit(
            "External image API modes are disabled by default. "
            "Use --mode codex for the standard ImageGen/built-in image queue. "
            "Use --mode local only when the user explicitly asks for diagnostic preview sketches. "
            "or add --allow-api only for explicit experiments."
        )

    if args.env:
        load_env_file(args.env)

    api_key = args.api_key or os.getenv("SILICONFLOW_AK")
    if not api_key:
        raise SystemExit("Missing API key. Provide --api-key or set SILICONFLOW_AK")

    guide_dir = outdir / "composition_guides"
    if args.mode == "guided-edit":
        run_local_renderer(prompts_json, guide_dir, args.image_size, args.final_size, board=True)

    base_image = Path(args.base) if args.base else outdir / "base_16x9_cream.png"
    if args.mode == "edit" and not base_image.exists():
        make_base_image(base_image, resolve_t2i_image_size(args.edit_model, args.base_size))

    for item in items:
        item_id = safe_name(str(item.get("id") or "item"))
        title = safe_name(str(item.get("title") or item.get("target") or "image"))
        out_path = outdir / f"{item_id}_{title}.png"
        if args.mode == "guided-edit":
            guide_image = composition_guide_path(item, guide_dir)
            if not guide_image.exists():
                raise SystemExit(f"Missing composition guide: {guide_image}")
            guided_item = item.copy()
            guided_item["prompt"] = build_guided_edit_prompt(item)
            generate_edit(
                item=guided_item,
                api_key=api_key,
                model=args.edit_model,
                base_image=guide_image,
                out_path=out_path,
                image2=args.image2,
                image3=args.image3,
            )
        elif args.mode == "edit":
            generate_edit(
                item=item,
                api_key=api_key,
                model=args.edit_model,
                base_image=base_image,
                out_path=out_path,
                image2=args.image2,
                image3=args.image3,
            )
        else:
            generate_t2i(
                item=item,
                api_key=api_key,
                model=args.t2i_model,
                image_size=args.image_size,
                cfg=args.cfg,
                out_path=out_path,
            )

        final_size = item.get("final_size") or (args.final_size if item.get("target") == "cover" else "")
        if final_size:
            target_w, target_h = parse_size(final_size)
            final_path = outdir / f"{item_id}_{title}_{final_size}.png"
            resize_center_crop(out_path, final_path, target_w, target_h)
            print(f"exported {final_path}")


if __name__ == "__main__":
    main()
