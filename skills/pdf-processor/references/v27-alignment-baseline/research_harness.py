#!/usr/bin/env python3
"""
W2 research harness — compares layered-PDF alignment schemes.

Schemes:
- A: ocrmypdf closed-loop (Tesseract internal hOCR → PDF text layer)
- D-legacy: current pdf_ocr_layered.py path, fed by local tesseract TSV
            (proxy for an OCR API returning block-level polys)
- D-improved: same path but with proposed fixes (per-word boxes,
              font-fit by text bbox, no derotation for already-upright pages,
              robust scale inference)

Metrics per sample PDF:
- keyword_hit_rate : fraction of expected keywords found in extracted text
- CER              : char error rate vs reference text (whitespace-normalized)
- searchable_ratio : pages with >= 10 chars extracted (degenerate for 1-page)
- alignment_score  : fraction of text-layer words whose bbox contains a
                     high-ink-density region in the underlying page image
- runtime_sec      : wall-clock of the OCR step

Outputs JSON to /tmp/w2_research/results.json and prints a comparison table.
"""
import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import fitz
import numpy as np

RESEARCH_DIR = Path("/tmp/w2_research")
SAMPLES_DIR = RESEARCH_DIR / "samples"
RESULTS_DIR = RESEARCH_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
REFERENCE = (SAMPLES_DIR / "reference.txt").read_text(encoding="utf-8")
KEYWORDS = [k.strip() for k in (SAMPLES_DIR / "keywords.txt").read_text(encoding="utf-8").splitlines() if k.strip()]

# Add worktree scripts to import path
SCRIPTS_DIR = Path("/Users/maoking/Library/Application Support/maoscripts/skills/legal-skills/.claude/worktrees/tmux-feat-pdf-processor-layered-align/skills/pdf-processor/scripts")
sys.path.insert(0, str(SCRIPTS_DIR))

# ---------- text-normalization & CER ----------
def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")

def levenshtein(a: str, b: str) -> int:
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            ins = curr[j-1] + 1
            delete = prev[j] + 1
            repl = prev[j-1] + (0 if ca == cb else 1)
            curr.append(min(ins, delete, repl))
        prev = curr
    return prev[-1]

def cer(hyp: str, ref: str) -> float:
    hyp_n = normalize(hyp)
    ref_n = normalize(ref)
    if not ref_n: return 1.0
    return levenshtein(hyp_n, ref_n) / len(ref_n)

# ---------- PDF metric extraction ----------
def extract_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    parts = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts)

def keyword_hit_rate(text: str, kws: list[str]) -> tuple[int, int]:
    hit = sum(1 for k in kws if k in text)
    return hit, len(kws)

# ---------- alignment score ----------
def alignment_score(pdf_path: Path, ink_threshold: float = 0.10) -> dict:
    """For each word bbox in the text layer, check if the corresponding
    image region under it has dark-pixel density above threshold.

    Returns:
        {aligned_words, total_words, alignment_ratio,
         mean_iou_proxy, mean_center_distance_pts}
    """
    doc = fitz.open(str(pdf_path))
    aligned = 0
    total = 0
    center_dists = []
    iou_proxies = []
    for page in doc:
        words = page.get_text("words")  # list of (x0,y0,x1,y1, word, ...)
        if not words:
            continue
        # Render page at 2x for pixel-level analysis
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        # Convert to grayscale (0..255)
        gray = img.mean(axis=2)
        scale = 2.0  # 2x render
        for w in words:
            x0, y0, x1, y1 = w[:4]
            # Map PDF points → pixel coords
            px0 = max(0, int(x0 * scale))
            py0 = max(0, int(y0 * scale))
            px1 = min(pix.width, int(x1 * scale))
            py1 = min(pix.height, int(y1 * scale))
            if px1 <= px0 or py1 <= py0:
                continue
            region = gray[py0:py1, px0:px1]
            # Ink density: fraction of pixels darker than 200
            ink_density = float((region < 200).mean())
            total += 1
            if ink_density >= ink_threshold:
                aligned += 1
            # Compute IoU proxy between word bbox and ink bbox within a search band
            # For simplicity, take the ink bbox inside a slightly enlarged search rect
            margin = 5  # pixels
            sx0 = max(0, px0 - margin)
            sy0 = max(0, py0 - margin)
            sx1 = min(pix.width, px1 + margin)
            sy1 = min(pix.height, py1 + margin)
            search = gray[sy0:sy1, sx0:sx1]
            mask = search < 200
            if mask.any():
                ys, xs = np.where(mask)
                ix0, iy0, ix1, iy1 = xs.min(), ys.min(), xs.max(), ys.max()
                # Translate back to absolute pixel coords
                ix0a = sx0 + ix0
                iy0a = sy0 + iy0
                ix1a = sx0 + ix1
                iy1a = sy0 + iy1
                # IoU between (px0,py0,px1,py1) and (ix0a,iy0a,ix1a,iy1a)
                ix0i = max(px0, ix0a); iy0i = max(py0, iy0a)
                ix1i = min(px1, ix1a); iy1i = min(py1, iy1a)
                inter = max(0.0, ix1i - ix0i) * max(0.0, iy1i - iy0i)
                area_word = (px1 - px0) * (py1 - py0)
                area_ink = (ix1a - ix0a) * (iy1a - iy0a)
                union = area_word + area_ink - inter
                iou = inter / union if union > 0 else 0.0
                iou_proxies.append(iou)
                # Center distance in PDF points
                wcx = (px0 + px1) / 2 / scale
                wcy = (py0 + py1) / 2 / scale
                icx = (ix0a + ix1a) / 2 / scale
                icy = (iy0a + iy1a) / 2 / scale
                center_dists.append(((wcx - icx) ** 2 + (wcy - icy) ** 2) ** 0.5)
            else:
                iou_proxies.append(0.0)
                center_dists.append(99.0)
    doc.close()
    return {
        "aligned_words": aligned,
        "total_words": total,
        "alignment_ratio": (aligned / total) if total else 0.0,
        "mean_iou_proxy": (statistics.mean(iou_proxies) if iou_proxies else 0.0),
        "mean_center_distance_pts": (statistics.mean(center_dists) if center_dists else 0.0),
    }

# ---------- scheme runners ----------
def run_scheme_a_ocrmypdf(input_pdf: Path, output_pdf: Path) -> dict:
    """Scheme A: ocrmypdf closed-loop."""
    cmd = [
        "ocrmypdf",
        "--language", "chi_sim",
        "--output-type", "pdf",
        "--optimize", "0",
        "--skip-big", "50",
        "--mode", "skip",  # don't touch existing text layer on digital.pdf
        "--pdf-renderer", "hocr",
        "--deskew",
        "--rotate-pages",
        "--tesseract-timeout", "60",
        "-j", "1",
        str(input_pdf), str(output_pdf),
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    if proc.returncode != 0:
        # ocrmypdf returns 6 for "skip-text skipped the page" success in some cases
        if proc.returncode == 6:
            pass  # this is OK, means prior text layer is good
        else:
            return {"error": f"ocrmypdf rc={proc.returncode}", "stderr": (proc.stderr or b"")[-500:].decode("utf-8", errors="replace"), "runtime_sec": elapsed}
    return {"runtime_sec": elapsed, "stdout_tail": proc.stdout[-300:]}


def run_scheme_d_block(input_pdf: Path, output_pdf: Path, agg_level: int = 4) -> dict:
    """Scheme D-block: same as D-legacy but TSV aggregated to line/block level.
    Mimics PaddleOCR API which returns line/block-level polys (outer rect of a text line).
    """
    t0 = time.time()
    doc = fitz.open(str(input_pdf))
    page_entries = []
    for pno, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB, alpha=False)
        img_path = RESULTS_DIR / f"page_{pno}.png"
        img_path.write_bytes(pix.tobytes("png"))
        out_base = img_path.with_suffix("")
        tsv_path = out_base.parent / f"{out_base.name}.tsv"
        proc = subprocess.run([
            "tesseract", img_path.name, out_base.name,
            "-l", "chi_sim", "tsv",
        ], capture_output=True, text=False, cwd=str(img_path.parent))
        if proc.returncode != 0:
            return {"error": f"tesseract rc={proc.returncode}", "stderr": proc.stderr[-500:].decode("utf-8", errors="replace")}
        rows = parse_tsv(tsv_path, level=agg_level)
        page_entries.append({"rows": rows, "width": pix.width, "height": pix.height})
    doc.close()
    import argparse
    args = argparse.Namespace(
        input=str(input_pdf), output=str(output_pdf), mode="skip",
        paddle_skip_text_min_chars=10, paddle_min_score=0.0,
        no_paddle_cjk_space_normalize=False, quiet=True,
    )
    import pdf_ocr_layered
    ok = pdf_ocr_layered.apply_page_entries_as_layered_pdf(page_entries, args, source_name=f"D-block-L{agg_level}")
    return {"runtime_sec": time.time() - t0, "ok": ok}

def run_scheme_d_legacy(input_pdf: Path, output_pdf: Path) -> dict:
    """Scheme D-legacy: tesseract TSV → mimic API payload → apply_page_entries_as_layered_pdf.
    This isolates the current layered path with a deterministic OCR source.
    """
    t0 = time.time()
    # Step 1: render each page to PNG, run tesseract chi_sim to get TSV
    doc = fitz.open(str(input_pdf))
    page_entries = []
    tmp_imgs = []
    for pno, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB, alpha=False)
        img_path = RESULTS_DIR / f"page_{pno}.png"
        img_path.write_bytes(pix.tobytes("png"))
        tmp_imgs.append(img_path)
        # Run tesseract: writes <out_base>.tsv to disk.
        # NOTE: must set cwd to img dir — leptonica mishandles absolute paths
        # when the inherited cwd contains spaces/non-ASCII.
        out_base = img_path.with_suffix("")  # /.../page_0 (no extension)
        tsv_path = out_base.parent / f"{out_base.name}.tsv"
        proc = subprocess.run([
            "tesseract", img_path.name, out_base.name,
            "-l", "chi_sim", "tsv",
        ], capture_output=True, text=False, cwd=str(img_path.parent))
        if proc.returncode != 0:
            return {"error": f"tesseract rc={proc.returncode}", "stderr": proc.stderr[-500:].decode("utf-8", errors="replace")}
        # Parse TSV
        rows = parse_tsv(tsv_path, level=5)  # word-level
        page_entries.append({
            "rows": rows,
            "width": pix.width,
            "height": pix.height,
        })
    doc.close()
    # Step 2: build args namespace for apply_page_entries_as_layered_pdf
    import argparse
    args = argparse.Namespace(
        input=str(input_pdf),
        output=str(output_pdf),
        mode="skip",
        paddle_skip_text_min_chars=10,
        paddle_min_score=0.0,
        no_paddle_cjk_space_normalize=False,
        quiet=True,
    )
    import pdf_ocr_layered
    ok = pdf_ocr_layered.apply_page_entries_as_layered_pdf(page_entries, args, source_name="D-legacy")
    elapsed = time.time() - t0
    return {"runtime_sec": elapsed, "ok": ok}

def parse_tsv(tsv_path: Path, level: int = 5) -> list:
    """Parse tesseract TSV output to rows = [(text, score, poly4), ...].
    level: TSV level to aggregate to. 5=word, 4=line (block bbox of one line of text),
           3=paragraph, 2=block. Use 4 to mimic PaddleOCR API line-level polys.
    """
    if not tsv_path.exists():
        return []
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    cols = {name: i for i, name in enumerate(header)}
    # Group rows by (page, block, par, line) tuple at the chosen level
    groups = {}
    order = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            continue
        try:
            lvl = int(parts[cols["level"]])
            pn = int(parts[cols["page_num"]])
            bn = int(parts[cols["block_num"]])
            par = int(parts[cols["par_num"]])
            ln = int(parts[cols["line_num"]])
            wn = int(parts[cols["word_num"]])
        except (KeyError, ValueError):
            continue
        text = parts[cols["text"]]
        try:
            left = int(parts[cols["left"]])
            top = int(parts[cols["top"]])
            width = int(parts[cols["width"]])
            height = int(parts[cols["height"]])
            conf = float(parts[cols["conf"]])
        except (KeyError, ValueError):
            continue
        if lvl == 5 and conf < 0:
            continue
        if lvl < 5 and (not text or not text.strip()):
            continue
        # Build key at the chosen aggregation level
        if level >= 5:
            key = (pn, bn, par, ln, wn)
        elif level == 4:
            key = (pn, bn, par, ln)
        elif level == 3:
            key = (pn, bn, par)
        elif level == 2:
            key = (pn, bn)
        else:
            key = (pn,)
        if key not in groups:
            groups[key] = {"texts": [], "conf": [], "x0": [], "y0": [], "x1": [], "y1": []}
            order.append(key)
        g = groups[key]
        if lvl == 5:
            # Word: include only if text non-empty
            if text.strip():
                g["texts"].append(text)
                g["conf"].append(conf)
                g["x0"].append(left)
                g["y0"].append(top)
                g["x1"].append(left + width)
                g["y1"].append(top + height)
        else:
            # Higher-level entry itself carries bbox + text
            if text.strip():
                g["texts"].append(text)
            g["x0"].append(left)
            g["y0"].append(top)
            g["x1"].append(left + width)
            g["y1"].append(top + height)
            # we don't get per-line conf at level<5; default 1.0
    rows = []
    for k in order:
        g = groups[k]
        if not g["x0"]:
            continue
        text = " ".join(g["texts"]).strip()
        if not text:
            continue
        if g["conf"]:
            score = max(0.0, min(1.0, sum(g["conf"]) / len(g["conf"]) / 100.0))
        else:
            score = 1.0
        x0 = min(g["x0"]); y0 = min(g["y0"]); x1 = max(g["x1"]); y1 = max(g["y1"])
        poly4 = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        rows.append((text, score, poly4))
    return rows

def measure_sample(sample_path: Path, output_pdf: Path, scheme: str, runner) -> dict:
    """Run a scheme on a sample and measure quality."""
    out_path = RESULTS_DIR / f"{sample_path.stem}_{scheme}.pdf"
    if out_path.exists():
        out_path.unlink()
    run_result = runner(sample_path, out_path)
    result = {
        "sample": sample_path.name,
        "scheme": scheme,
        "output_pdf": str(out_path),
        "runner_result": run_result,
    }
    if "error" in run_result:
        result["status"] = "error"
        return result
    # Extract text from output
    text = extract_text(out_path)
    hits, total = keyword_hit_rate(text, KEYWORDS)
    cer_val = cer(text, REFERENCE)
    align = alignment_score(out_path)
    result.update({
        "status": "ok",
        "extracted_text_len": len(text),
        "keyword_hits": hits,
        "keyword_total": total,
        "keyword_hit_rate": hits / total,
        "cer": cer_val,
        "alignment": align,
        "output_size": out_path.stat().st_size,
        "input_size": sample_path.stat().st_size,
        "size_ratio": out_path.stat().st_size / sample_path.stat().st_size,
    })
    return result

def main():
    samples = [SAMPLES_DIR / "digital.pdf", SAMPLES_DIR / "scanned.pdf", SAMPLES_DIR / "skewed.pdf"]
    schemes = {
        "A_ocrmypdf": run_scheme_a_ocrmypdf,
        "D_legacy_word": run_scheme_d_legacy,
        "D_block_line": lambda i, o: run_scheme_d_block(i, o, agg_level=4),
        "D_block_para": lambda i, o: run_scheme_d_block(i, o, agg_level=3),
    }
    all_results = []
    for sample in samples:
        for scheme_name, runner in schemes.items():
            print(f"\n>>> {sample.name} / {scheme_name}", flush=True)
            r = measure_sample(sample, RESULTS_DIR / f"ignore_{sample.stem}_{scheme_name}.pdf", scheme_name, runner)
            print(f"    -> {r.get('status')}", flush=True)
            if r.get("status") == "ok":
                print(f"    keyword_hit_rate={r['keyword_hit_rate']:.2%} cer={r['cer']:.4f} "
                      f"align_ratio={r['alignment']['alignment_ratio']:.2%} "
                      f"mean_iou={r['alignment']['mean_iou_proxy']:.3f} "
                      f"center_dist={r['alignment']['mean_center_distance_pts']:.2f}pt "
                      f"runtime={r['runner_result']['runtime_sec']:.2f}s", flush=True)
            else:
                print(f"    ERROR: {r['runner_result'].get('error')}", flush=True)
            all_results.append(r)
    # Write JSON
    out_json = RESEARCH_DIR / "results_baseline.json"
    out_json.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults JSON: {out_json}")
    # Print summary table
    print("\n" + "=" * 100)
    print(f"{'sample':<15} {'scheme':<22} {'kw_hit':<10} {'CER':<8} {'align%':<10} {'IoU':<8} {'dist_pt':<10} {'runtime':<8}")
    print("-" * 100)
    for r in all_results:
        if r.get("status") != "ok":
            print(f"{r['sample']:<15} {r['scheme']:<22} ERROR: {r['runner_result'].get('error', '')[:60]}")
            continue
        a = r["alignment"]
        print(f"{r['sample']:<15} {r['scheme']:<22} "
              f"{r['keyword_hit_rate']:>5.0%}({r['keyword_hits']}/{r['keyword_total']}) "
              f"{r['cer']:.4f}   "
              f"{a['alignment_ratio']:>6.0%}     "
              f"{a['mean_iou_proxy']:.3f}   "
              f"{a['mean_center_distance_pts']:>6.2f}    "
              f"{r['runner_result']['runtime_sec']:>5.2f}s")
    print("=" * 100)

if __name__ == "__main__":
    main()
