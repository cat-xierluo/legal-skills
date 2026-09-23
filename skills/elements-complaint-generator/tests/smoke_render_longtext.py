#!/usr/bin/env python3
"""68 棵主文书长文本真实渲染矩阵与稳定性证据。

本入口面向发布级验证，不并入每次日常 E2E。它为每棵编号主文书生成
确定性压力输入，复用生产流水线的字体、页码、语义表头和版式门禁，
并可保留首轮 DOCX、PDF、关键页截图及三轮稳定指纹。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from fill_template import (  # noqa: E402
    RULE_BUILDERS,
    DocParts,
    apply_font_compatibility,
    apply_publication_mark_cleanup,
    apply_rules,
    apply_semantic_table_headers,
    fix_footers_and_pagination,
    load_text_parts,
    merge_sections_and_normalize,
    resolve_case,
    save_text_parts,
)
from generic_rules import generic_case_numbers, primary_tree_for  # noqa: E402
from layout_gate import (  # noqa: E402
    _find_soffice,
    _renderer_kind,
    _soffice_version,
    audit_docx,
    audit_pdf,
    audit_text_survival,
    load_policy,
    render_docx,
)
from pack_docx import pack_tree  # noqa: E402


RULE_PATH = re.compile(
    r"^(?:fill_after|replace|swap|insparas|amt|dint|damt)\[(.+)\]$"
)
REQUEST_WORDS = ("请求", "金额", "费用", "损失", "赔偿", "本金", "利息", "主文")
FACT_WORDS = (
    "事实", "理由", "经过", "内容", "依据", "情况", "说明", "证据", "范围",
)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _docx_content_sha256(path: Path) -> str:
    """忽略 ZIP 时间戳，对 DOCX 内部文件名与内容做确定性哈希。"""
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(archive.read(name))
    return digest.hexdigest()


def _set_path(root: dict[str, Any], path: str, value: Any) -> None:
    """按 fill_template._get_path 的点分语义构造嵌套输入。"""
    parts = path.split(".")
    cursor = root
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[parts[-1]] = value


def _request_text(seed: str) -> str:
    clauses = [
        f"第{i}项压力请求（{seed}）：请求依法判令履行给付、停止侵害并承担相应费用，"
        "金额、计算期间及履行方式均以最终查明事实为准。"
        for i in range(1, 7)
    ]
    return "".join(clauses)


def _fact_text(seed: str) -> str:
    clauses = [
        f"事实段{i}（{seed}）：双方围绕合同订立、履行、催告、异议和损失计算形成连续事实，"
        "相关时间、地点、人员、凭证与沟通记录均需在长文本换行和跨页后保持完整可读。"
        for i in range(1, 9)
    ]
    return "".join(clauses)


def _detail_text(seed: str) -> str:
    return (
        f"压力明细（{seed}）：本段用于验证长字段在表格单元格中的自动换行、行高增长、"
        "列边界守恒、跨页续接和字体存活；内容不代表任何真实案件事实。"
    ) * 2


def _value_for_path(path: str, seed: str) -> str:
    if any(word in path for word in REQUEST_WORDS):
        return _request_text(seed)
    if any(word in path for word in FACT_WORDS):
        return _fact_text(seed)
    return _detail_text(seed)


def _production_case_type(number: str) -> str:
    """优先选择与正式入口相同的精调 key，未精调编号才走通用级。"""
    return next((key for key in RULE_BUILDERS if key.startswith(f"{number}-")), number)


def build_stress_elements(
    tree_dir: Path, rules_builder=None,
) -> tuple[dict[str, Any], list[str]]:
    """生成确定性长文本输入，并返回自动推导出的填充路径。"""
    fixture = json.loads(
        (SKILL_DIR / "tests/fixtures/generic-smoke.json").read_text(encoding="utf-8")
    )
    elements = copy.deepcopy(fixture["elements"])
    seed = tree_dir.name[:2]

    people = elements["当事人"]
    people["原告"].update({
        "姓名": "欧阳测试甲乙丙丁戊己",
        "工作单位": "华东地区跨省综合技术服务与争议解决研究中心有限责任公司",
        "职务": "高级项目协调与合规管理负责人",
        "住所地": "北京市海淀区中关村科技园某大道一百二十八号创新中心A座二十八层东南侧",
        "经常居住地": "上海市浦东新区世纪大道某号国际商务中心三期十五层长地址压力测试单元",
        "证件号码": "TEST-ID-110105-19880215-002X",
    })
    people["被告"].update({
        "姓名": "司马测试庚辛壬癸子丑",
        "工作单位": "粤港澳大湾区数字内容运营与知识产权综合服务股份有限公司",
        "职务": "业务运营、风险控制及争议处理联合负责人",
        "住所地": "广东省深圳市南山区科技创新园某路九十九号联合办公区B栋三十六层",
        "经常居住地": "浙江省杭州市余杭区未来科技城某街道某社区长地址压力测试房屋",
        "证件号码": "TEST-ID-440305-19900428-0037",
    })
    people["委托诉讼代理人"][0].update({
        "姓名": "诸葛长姓名测试律师",
        "单位": "某某律师事务所跨区域争议解决与数字经济法律服务中心",
        "职务": "高级合伙人兼复杂诉讼项目负责人",
        "特别授权": True,
    })
    for index in (1, 2):
        people[f"法人{index}"].update({
            "名称": f"第{index}号跨区域综合产业投资运营与技术服务有限责任公司",
            "住所地": "江苏省南京市建邺区国际金融城某大道八十八号超长企业地址压力测试单元",
            "注册地": "江苏省南京市市场监督管理局登记辖区长注册地址测试区域",
            "法定代表人": "上官企业代表长姓名",
            "职务": "执行董事、总经理兼风险控制负责人",
        })

    # 通用规则根据模板结构动态产生填空/唯一标签路径。先探测规则名，再按
    # _get_path 的真实点分语义构造输入，避免把模板差异硬编码成 68 套 fixture。
    candidates: list[str] = []
    builder = rules_builder
    if builder is None:
        number = tree_dir.name[:2]
        resolved_tree, builder = resolve_case(
            _production_case_type(number), SKILL_DIR / "templates"
        )
        if resolved_tree.resolve() != tree_dir.resolve():
            raise RuntimeError(
                f"生产路由树不一致: {resolved_tree.name} != {tree_dir.name}"
            )
    for rule in builder(elements):
        match = RULE_PATH.match(getattr(rule, "__name__", ""))
        if not match:
            continue
        path = match.group(1)
        # 标题后空白区通常就是模板预留的大段填写区，全部施压；唯一标签
        # 只选择与请求、事实、依据和证据有关的业务字段，避免把姓名、日期、
        # 信用代码等元数据再次塞入超长正文，制造无业务意义的 20+ 页文档。
        if not path.startswith("填空.") and not any(
            word in path for word in REQUEST_WORDS + FACT_WORDS
        ):
            continue
        # 带复选框的路径代表枚举选项而非自由文本输入；把几百字写进该类
        # 占位会测试一个不存在的用户场景，并掩盖真正的长请求/事实字段。
        if any(mark in path for mark in ("□", "☑")):
            continue
        if path in candidates:
            continue
        candidates.append(path)

    def path_is_active(path: str) -> bool:
        """只保留能在原始模板上真实命中的生产规则路径。

        精调 builder 会同时携带若干跨模板兼容规则；规则名存在不代表当前
        树一定有对应锚点。逐路径用新解析树探测，避免选择注定 skipped 的
        兼容路径后把矩阵误判为生成器失败。
        """
        probe_elements = copy.deepcopy(elements)
        _set_path(probe_elements, path, _value_for_path(path, seed))
        probe_doc = DocParts(load_text_parts(tree_dir))
        for probe_rule in builder(probe_elements):
            match = RULE_PATH.match(getattr(probe_rule, "__name__", ""))
            if match is None or match.group(1) != path:
                continue
            try:
                if probe_rule(probe_doc, probe_elements):
                    return True
            except Exception:
                return False
        return False

    candidates = [path for path in candidates if path_is_active(path)]

    def priority(path: str, kind: str) -> tuple[int, str]:
        if kind == "request":
            if path.startswith("诉讼请求."):
                return (0, path)
            if "判项主文" in path or "具体请求" in path:
                return (1, path)
        else:
            if path.startswith("事实与理由."):
                return (0, path)
            if "事实理由" in path or "被诉决定" in path:
                return (1, path)
        if path.startswith("填空."):
            return (2, path)
        if path.startswith("标签."):
            return (3, path)
        return (2, path)

    selected: list[str] = []
    request_candidates = [
        path for path in candidates if any(word in path for word in REQUEST_WORDS)
    ]
    fact_candidates = [
        path for path in candidates if any(word in path for word in FACT_WORDS)
    ]
    if request_candidates:
        selected.append(min(request_candidates, key=lambda path: priority(path, "request")))
    remaining_facts = [path for path in fact_candidates if path not in selected]
    if remaining_facts:
        selected.append(min(remaining_facts, key=lambda path: priority(path, "fact")))
    if not selected and candidates:
        selected.append(sorted(candidates)[0])

    for path in selected:
        _set_path(elements, path, _value_for_path(path, seed))

    return elements, sorted(selected)


def primary_targets(templates_dir: Path) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for number in generic_case_numbers(templates_dir):
        tree = primary_tree_for(number, templates_dir)
        if tree is None:
            continue
        targets.append((number, tree))
    return targets


def stability_signature(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """提取可审阅的稳定性结构签名，排除亚像素抖动。

    门禁已独立验证居中/边界是否在容差内；稳定性指纹只比较会改变文书
    结构或阅读结果的页数、页码、空白状态、表格外边界/居中和字形存活。
    """
    normalized_reports: list[dict[str, Any]] = []
    for report in reports:
        measurements = report.get("measurements", {})
        if "page_summaries" in measurements:
            stable_measurements: dict[str, Any] = {
                "pages": measurements.get("pages"),
                "page_summaries": [
                    {
                        "page": summary.get("page"),
                        "width_points": round(float(summary.get("width_points", 0)), 1),
                        "height_points": round(float(summary.get("height_points", 0)), 1),
                        "table_center_offset_points": (
                            round(float(summary["table_center_offset_points"]) * 2) / 2
                            if summary.get("table_center_offset_points") is not None else None
                        ),
                        "table_outer_boundaries": sorted({
                            (
                                round(float(band["column_x_positions"][0]) * 2) / 2,
                                round(float(band["column_x_positions"][-1]) * 2) / 2,
                            )
                            for band in summary.get("table_bands", [])
                            if len(band.get("column_x_positions", [])) >= 2
                        }),
                        "footer_numbers": summary.get("footer_numbers", []),
                        "blank": summary.get("blank"),
                    }
                    for summary in measurements.get("page_summaries", [])
                ],
            }
        else:
            stable_measurements = measurements
        normalized_reports.append({
            "stage": report.get("stage"),
            "ok": report.get("ok"),
            "issues": [
                {
                    "code": issue.get("code"),
                    "page": issue.get("page"),
                    "anchor": issue.get("anchor"),
                }
                for issue in report.get("issues", [])
            ],
            "measurements": stable_measurements,
        })
    return {"reports": normalized_reports}


def stability_fingerprint(reports: list[dict[str, Any]]) -> str:
    """哈希可观察版式签名，排除临时路径和 PDF 元数据。"""
    return hashlib.sha256(_json_bytes(stability_signature(reports))).hexdigest()


def _selected_screenshot_pages(pdf_report: dict[str, Any]) -> list[int]:
    summaries = pdf_report.get("measurements", {}).get("page_summaries", [])
    if not summaries:
        return []
    pages = {1, len(summaries)}
    for issue in pdf_report.get("issues", []):
        if isinstance(issue.get("page"), int):
            pages.add(issue["page"])
    for index, summary in enumerate(summaries[:-1], 1):
        if any(band.get("reaches_page_bottom") for band in summary.get("table_bands", [])):
            pages.update((index, index + 1))
    return sorted(page for page in pages if 1 <= page <= len(summaries))


def _save_screenshots(pdf: Path, destination: Path, pages: list[int]) -> list[str]:
    import fitz

    destination.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf)
    saved: list[str] = []
    try:
        for page_number in pages:
            output = destination / f"page-{page_number:03d}.png"
            page = document[page_number - 1]
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(output)
            saved.append(str(output))
    finally:
        document.close()
    return saved


def render_one(
    number: str,
    tree_name: str,
    round_index: int,
    root: Path,
    evidence_dir: Path | None,
    renderer: Path,
    preserve_all_rounds: bool = False,
) -> dict[str, Any]:
    source = SKILL_DIR / "templates" / tree_name
    work = root / f"round-{round_index:02d}-{number}" / "tree"
    candidate = root / f"round-{round_index:02d}-{number}" / "candidate.docx"
    render_work: Path | None = None
    reports: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}
    elements: dict[str, Any] | None = None
    stress_paths: list[str] = []
    content_warnings: list[str] = []
    input_sha256: str | None = None
    try:
        case_type = _production_case_type(number)
        resolved_source, rules_builder = resolve_case(
            case_type, SKILL_DIR / "templates"
        )
        if resolved_source.resolve() != source.resolve():
            raise RuntimeError(
                f"生产路由树不一致: {resolved_source.name} != {source.name}"
            )
        elements, stress_paths = build_stress_elements(source, rules_builder)
        if not stress_paths:
            raise RuntimeError("未推导出请求/事实类长文本字段，拒绝空覆盖通过")
        input_sha256 = hashlib.sha256(_json_bytes(elements)).hexdigest()
        shutil.copytree(source, work)
        parts = load_text_parts(work)
        rules_result = apply_rules(
            DocParts(parts), rules_builder(elements), elements
        )
        errors = [name for status, name in rules_result["details"] if status == "error"]
        unresolved_stress = sorted(
            set(rules_result["unresolved_inputs"]).intersection(stress_paths)
        )
        content_warnings = sorted(
            set(rules_result["unresolved_inputs"]) - set(stress_paths)
        )
        if errors or unresolved_stress:
            raise RuntimeError(
                f"规则失败={errors[:3]} 压力字段未消费={unresolved_stress[:3]}"
            )
        policy = load_policy(SKILL_DIR / "config/layout-policy.json", tree_name)
        layout_stats = merge_sections_and_normalize(parts, policy)
        save_text_parts(work, parts)
        font_stats = apply_font_compatibility(work, policy)
        if not font_stats["ok"]:
            raise RuntimeError(f"字体兼容候选不可用: {font_stats['unresolved']}")
        cleanup_stats = apply_publication_mark_cleanup(work, policy)
        header_stats = apply_semantic_table_headers(work, policy)
        if header_stats["errors"]:
            raise RuntimeError(f"语义表头合同失败: {header_stats['errors'][:3]}")
        footers_fixed = fix_footers_and_pagination(
            work, page_mode=policy.get("page_numbers", "required")
        )
        pack_tree(work, candidate)

        static = audit_docx(candidate, policy)
        reports.append(static)
        pdf_path: Path | None = None
        if static["ok"]:
            pdf_path, render_work = render_docx(candidate, soffice=renderer)
            pdf_report = audit_pdf(pdf_path, policy)
            glyph_report = audit_text_survival(candidate, pdf_path, policy)
            reports.extend((pdf_report, glyph_report))

        issues = [issue for report in reports for issue in report.get("issues", [])]
        ok = len(reports) == 3 and all(
            report.get("ok") is True for report in reports
        ) and not issues
        if evidence_dir is not None and (preserve_all_rounds or round_index == 1 or not ok):
            case_dir = evidence_dir / f"round-{round_index:02d}" / f"{number}-{tree_name}"
            case_dir.mkdir(parents=True, exist_ok=True)
            input_path = case_dir / "stress-input.json"
            input_path.write_text(
                json.dumps(elements, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            docx_path = case_dir / "candidate.docx"
            shutil.copy2(candidate, docx_path)
            evidence.update({"input": str(input_path), "docx": str(docx_path)})
            if pdf_path is not None:
                saved_pdf = case_dir / "candidate.pdf"
                shutil.copy2(pdf_path, saved_pdf)
                evidence["pdf"] = str(saved_pdf)
                evidence["screenshots"] = _save_screenshots(
                    saved_pdf,
                    case_dir / "screenshots",
                    _selected_screenshot_pages(reports[1]),
                )

        page_count = 0
        glyph_measurements: dict[str, Any] = {}
        if len(reports) >= 2:
            page_count = reports[1].get("measurements", {}).get("pages", 0)
        if len(reports) >= 3:
            glyph_measurements = reports[2].get("measurements", {})
        signature = stability_signature(reports)
        return {
            "number": number,
            "tree": tree_name,
            "round": round_index,
            "ok": ok,
            "status": "PASS" if ok else "FAIL",
            "input_sha256": input_sha256,
            "docx_sha256": _sha256_file(candidate),
            "docx_content_sha256": _docx_content_sha256(candidate),
            "stress_path_count": len(stress_paths),
            "stress_paths": stress_paths,
            "content_warnings": content_warnings,
            "pages": page_count,
            "glyphs": glyph_measurements,
            "layout_stats": layout_stats,
            "font_stats": font_stats,
            "publication_cleanup": cleanup_stats,
            "semantic_headers": header_stats,
            "footers_fixed": footers_fixed,
            "issues": issues,
            "stability_signature": signature,
            "fingerprint": hashlib.sha256(_json_bytes(signature)).hexdigest(),
            "evidence": evidence,
        }
    except Exception as exc:
        # 渲染器崩溃、门禁异常等失败同样必须保留输入和候选件；否则矩阵
        # 只能报告“失败”，却无法复现或区分文档缺陷与运行环境问题。
        if evidence_dir is not None:
            case_dir = evidence_dir / f"round-{round_index:02d}" / f"{number}-{tree_name}"
            case_dir.mkdir(parents=True, exist_ok=True)
            if elements is not None:
                input_path = case_dir / "stress-input.json"
                input_path.write_text(
                    json.dumps(elements, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                evidence["input"] = str(input_path)
            if candidate.exists():
                docx_path = case_dir / "candidate.docx"
                shutil.copy2(candidate, docx_path)
                evidence["docx"] = str(docx_path)
        return {
            "number": number,
            "tree": tree_name,
            "round": round_index,
            "ok": False,
            "status": "FAIL",
            "input_sha256": input_sha256,
            "docx_sha256": _sha256_file(candidate) if candidate.exists() else None,
            "docx_content_sha256": (
                _docx_content_sha256(candidate) if candidate.exists() else None
            ),
            "stress_path_count": len(stress_paths),
            "stress_paths": stress_paths,
            "content_warnings": content_warnings,
            "pages": 0,
            "glyphs": {},
            "layout_stats": {},
            "issues": [{
                "code": "ECG-LONGTEXT-EXCEPTION",
                "stage": "matrix",
                "message": f"{type(exc).__name__}: {exc}",
            }],
            "stability_signature": None,
            "fingerprint": None,
            "evidence": evidence,
        }
    finally:
        if render_work is not None:
            shutil.rmtree(render_work, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--case", action="append", dest="cases", help="只跑指定两位编号，可重复")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument(
        "--evidence-all-rounds", action="store_true",
        help="保留每一轮证据（用于定位不稳定模板；全量运行会占用较多磁盘）",
    )
    parser.add_argument("--require-full", action="store_true", help="要求 68 树×3 轮完整通过")
    parser.add_argument("--soffice", type=Path)
    args = parser.parse_args()

    # 任何前置失败都不得留下上一轮成功报告。显式输出路径属于本次运行
    # 的目标文件，先移除旧文件，再在完整结束时写入新证据。
    if args.json_output is not None and args.json_output.exists():
        if not args.json_output.is_file():
            print(f"[longtext] JSON 输出路径不是文件: {args.json_output}", file=sys.stderr)
            return 2
        args.json_output.unlink()

    if args.evidence_dir is not None:
        if args.evidence_dir.exists() and not args.evidence_dir.is_dir():
            print(
                f"[longtext] 证据路径不是目录: {args.evidence_dir}",
                file=sys.stderr,
            )
            return 2
        if args.evidence_dir.exists() and any(args.evidence_dir.iterdir()):
            print(
                f"[longtext] 证据目录非空，拒绝复用旧证据: {args.evidence_dir}",
                file=sys.stderr,
            )
            return 2
        args.evidence_dir.mkdir(parents=True, exist_ok=True)

    renderer_path = _find_soffice(args.soffice)
    if not renderer_path:
        print("[longtext] 缺少 LibreOffice/soffice", file=sys.stderr)
        return 2
    renderer_version = _soffice_version(renderer_path)
    if _renderer_kind(renderer_version) != "official":
        print(f"[longtext] 非正式版渲染器，拒绝运行: {renderer_version}", file=sys.stderr)
        return 2
    renderer = Path(renderer_path)

    targets = primary_targets(SKILL_DIR / "templates")
    if args.cases:
        requested = set(args.cases)
        known = {number for number, _ in targets}
        unknown = sorted(requested - known)
        if unknown:
            print(f"[longtext] 未知编号: {', '.join(unknown)}", file=sys.stderr)
            return 2
        targets = [item for item in targets if item[0] in requested]

    root = Path(tempfile.mkdtemp(prefix="ecg-longtext-matrix-"))
    results: list[dict[str, Any]] = []
    warmup_failures: list[dict[str, Any]] = []
    try:
        # 同一模板连续跑完全部轮次，隔离“模板自身是否可重复”这一变量；
        # round-major 会让两次同模板渲染之间夹入 67 个无关模板，把长批次
        # 字体缓存/进程状态漂移误归因到模板稳定性。
        for position, (number, tree_name) in enumerate(targets, 1):
            if args.rounds > 1:
                warmup = render_one(
                    number, tree_name, 0, root, args.evidence_dir, renderer
                )
                if not warmup["ok"]:
                    warmup_failures.append(warmup)
                    print(
                        f"[longtext] {position:02d}/{len(targets):02d} WARMUP ✗ {number}",
                        flush=True,
                    )
            for round_index in range(1, args.rounds + 1):
                item = render_one(
                    number, tree_name, round_index, root, args.evidence_dir, renderer,
                    preserve_all_rounds=args.evidence_all_rounds,
                )
                results.append(item)
                marker = "✓" if item["ok"] else "✗"
                print(
                    f"[longtext] {position:02d}/{len(targets):02d} R{round_index} "
                    f"{marker} {number} pages={item['pages']} paths={item['stress_path_count']}",
                    flush=True,
                )

        fingerprints: dict[str, list[str | None]] = {}
        input_hashes: dict[str, list[str | None]] = {}
        content_hashes: dict[str, list[str | None]] = {}
        for item in results:
            fingerprints.setdefault(item["number"], []).append(item["fingerprint"])
            input_hashes.setdefault(item["number"], []).append(item["input_sha256"])
            content_hashes.setdefault(item["number"], []).append(item["docx_content_sha256"])
        stability = {
            number: (
                bool(values)
                and None not in values
                and len(set(values)) == 1
                and None not in input_hashes[number]
                and len(set(input_hashes[number])) == 1
                and None not in content_hashes[number]
                and len(set(content_hashes[number])) == 1
            )
            for number, values in fingerprints.items()
        }
        unstable_reasons = {
            number: [
                label for label, values in (
                    ("render_fingerprint", fingerprints[number]),
                    ("input_sha256", input_hashes[number]),
                    ("docx_content_sha256", content_hashes[number]),
                )
                if None in values or len(set(values)) != 1
            ]
            for number, stable in stability.items() if not stable
        }
        failed = [item for item in results if not item["ok"]]
        failed_cases = {item["number"] for item in failed}
        unstable = sorted(
            number for number, stable in stability.items()
            if number not in failed_cases and not stable
        )
        full_scope = len(targets) == 68 and args.rounds == 3
        status = (
            "FAIL" if failed or unstable or warmup_failures
            else ("DOMAIN_VERIFIED" if full_scope else "PARTIAL_VERIFIED")
        )
        payload = {
            "schema_version": 1,
            "status": status,
            "scope": "68 primary trees × deterministic long-party/request/fact rendered stress",
            "full_scope": full_scope,
            "rounds": args.rounds,
            "target_count": len(targets),
            "render_count": len(results),
            "warmup_count": len(targets) if args.rounds > 1 else 0,
            "warmup_failed": len(warmup_failures),
            "warmup_failures": warmup_failures,
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "unstable_cases": unstable,
            "unstable_reasons": unstable_reasons,
            "renderer": {"path": str(renderer), "version": renderer_version},
            "results": results,
        }
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(
            f"[longtext] {status}: 通过 {payload['passed']}/{payload['render_count']}，"
            f"失败 {payload['failed']}，预热失败 {payload['warmup_failed']}，"
            f"不稳定 {len(unstable)}"
        )
        if args.require_full and not full_scope:
            print("[longtext] --require-full 要求 68 树且 --rounds 3", file=sys.stderr)
            return 2
        return 0 if status != "FAIL" else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
