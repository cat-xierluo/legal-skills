#!/usr/bin/env python3
"""Call SiliconFlow images/generations and download the first result."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Optional

from env_utils import load_env_file

try:
    import requests
except ImportError:
    print("Missing dependency: requests")
    print("Install it with: python3 -m pip install -r scripts/requirements.txt")
    raise SystemExit(1)


DEFAULT_ENDPOINT = "https://api.siliconflow.cn/v1/images/generations"


def to_data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def normalize_image(value: str) -> Optional[str]:
    if not value:
        return None
    if value.startswith(("http://", "https://", "data:image/")):
        return value
    path = Path(value)
    if path.exists():
        return to_data_url(path)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=str(Path(__file__).resolve().parents[1] / "secrets.env"))
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--endpoint", default=os.getenv("SILICONFLOW_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--model", default="Tongyi-MAI/Z-Image-Turbo")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="")
    parser.add_argument("--image", default="")
    parser.add_argument("--image2", default="")
    parser.add_argument("--image3", default="")
    parser.add_argument("--image-size", default="auto")
    parser.add_argument("--cfg", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    if args.env:
        load_env_file(args.env)

    api_key = args.api_key or os.getenv("SILICONFLOW_AK")
    if not api_key:
        raise SystemExit("Missing API key. Provide --api-key or set SILICONFLOW_AK")

    payload = {"model": args.model, "prompt": args.prompt}
    if args.negative:
        payload["negative_prompt"] = args.negative

    for payload_key, image_value in (("image", args.image), ("image2", args.image2), ("image3", args.image3)):
        normalized = normalize_image(image_value)
        if normalized:
            payload[payload_key] = normalized

    image_size = str(args.image_size or "").strip()
    if image_size.lower() == "auto":
        if "edit" in args.model.lower():
            image_size = ""
        elif "z-image" in args.model.lower():
            image_size = "2048x872"
        else:
            image_size = "1664x928"
    if image_size:
        payload["image_size"] = image_size
    if args.cfg:
        try:
            payload["cfg"] = float(args.cfg)
        except ValueError:
            raise SystemExit("--cfg must be a number, for example 4.0")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = requests.post(args.endpoint, headers=headers, data=json.dumps(payload), timeout=args.timeout)
    if not response.ok:
        raise SystemExit(f"HTTP {response.status_code}: {response.text}")

    data = response.json()
    try:
        image_url = data["images"][0]["url"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"Unexpected API response: {data}") from exc

    image_response = requests.get(image_url, timeout=args.timeout)
    if not image_response.ok:
        raise SystemExit(f"Image download failed: HTTP {image_response.status_code}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_response.content)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
