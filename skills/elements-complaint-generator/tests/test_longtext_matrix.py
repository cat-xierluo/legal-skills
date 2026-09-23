#!/usr/bin/env python3
"""长文本矩阵的快速合同测试（不启动 LibreOffice）。"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "tests"))

from smoke_render_longtext import (  # noqa: E402
    _selected_screenshot_pages,
    build_stress_elements,
    primary_targets,
    stability_fingerprint,
)


def main() -> int:
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    templates = SKILL_DIR / "templates"
    targets = primary_targets(templates)
    require(len(targets) == 68, f"主文书目标应为 68，实际 {len(targets)}")
    require(len({number for number, _ in targets}) == 68, "编号必须唯一")
    require(
        [number for number, _ in targets] == [f"{i:02d}" for i in range(1, 69)],
        "编号必须连续覆盖 01—68",
    )

    coverage = {}
    for number, tree_name in targets:
        _, paths = build_stress_elements(templates / tree_name)
        coverage[number] = paths
    require(
        all(coverage.values()),
        "每棵主文书必须至少推导出一个请求/事实类长文本路径: "
        + ", ".join(number for number, paths in coverage.items() if not paths),
    )

    tree = templates / dict(targets)["09"]
    first, first_paths = build_stress_elements(tree)
    second, second_paths = build_stress_elements(tree)
    require(first == second and first_paths == second_paths, "压力输入必须确定性")
    require(len(first["当事人"]["原告"]["住所地"]) >= 30, "原告地址未施压")
    require(len(first["当事人"]["被告"]["工作单位"]) >= 20, "被告单位未施压")
    require(bool(first_paths), "必须从模板推导至少一个长文本填充路径")
    require(all(path.startswith("填空.") or any(
        word in path for word in ("请求", "金额", "费用", "损失", "赔偿", "本金", "利息", "主文", "事实", "理由", "经过", "内容", "依据", "情况", "说明", "证据")
    ) for path in first_paths), "唯一标签只能选择请求/事实相关业务字段")

    reports = [{
        "stage": "rendered",
        "ok": True,
        "issues": [],
        "measurements": {"pages": 2, "page_summaries": [{"page": 1}, {"page": 2}]},
        "ignored_runtime_path": "/tmp/one",
    }]
    same = [{**reports[0], "ignored_runtime_path": "/tmp/two"}]
    require(stability_fingerprint(reports) == stability_fingerprint(same), "临时路径不得影响指纹")
    jittered = [{
        **reports[0],
        "measurements": {
            "pages": 2,
            "page_summaries": [
                {
                    "page": 1,
                    "width_points": 595.281,
                    "height_points": 841.891,
                    "table_center_offset_points": 0.03,
                    "table_bands": [{
                        "column_x_positions": [64.08, 177.54, 531.27],
                        "y0": 101.17,
                        "y1": 799.92,
                        "reaches_page_bottom": True,
                    }],
                    "footer_numbers": ["1"],
                    "blank": False,
                },
                {"page": 2},
            ],
        },
    }]
    jittered_again = [{
        **jittered[0],
        "measurements": {
            "pages": 2,
            "page_summaries": [
                {
                    **jittered[0]["measurements"]["page_summaries"][0],
                    "table_center_offset_points": -0.04,
                    "table_bands": [{
                        **jittered[0]["measurements"]["page_summaries"][0]["table_bands"][0],
                        "y0": 101.23,
                        "y1": 799.87,
                    }],
                },
                {"page": 2},
            ],
        },
    }]
    require(
        stability_fingerprint(jittered) == stability_fingerprint(jittered_again),
        "亚像素抖动不得影响指纹",
    )
    changed_pagination = [{
        **jittered[0],
        "measurements": {
            **jittered[0]["measurements"],
            "page_summaries": [{
                **jittered[0]["measurements"]["page_summaries"][0],
                "footer_numbers": ["99"],
            }, {"page": 2}],
        },
    }]
    require(
        stability_fingerprint(jittered) != stability_fingerprint(changed_pagination),
        "页码变化必须影响指纹",
    )
    changed_geometry = [{
        **jittered[0],
        "measurements": {
            **jittered[0]["measurements"],
            "page_summaries": [{
                **jittered[0]["measurements"]["page_summaries"][0],
                "table_center_offset_points": 1.6,
                "table_bands": [{
                    **jittered[0]["measurements"]["page_summaries"][0]["table_bands"][0],
                    "column_x_positions": [66.0, 179.5, 533.3],
                }],
            }, {"page": 2}],
        },
    }]
    require(
        stability_fingerprint(jittered) != stability_fingerprint(changed_geometry),
        "表格居中或外边界变化必须影响指纹",
    )

    pdf_report = {
        "issues": [{"page": 3}],
        "measurements": {"page_summaries": [
            {"page": 1, "table_bands": []},
            {"page": 2, "table_bands": [{"reaches_page_bottom": True}]},
            {"page": 3, "table_bands": []},
            {"page": 4, "table_bands": []},
        ]},
    }
    require(_selected_screenshot_pages(pdf_report) == [1, 2, 3, 4], "截图页选择错误")
    print("[longtext-contract] 目标枚举、确定性输入、稳定指纹和截图选择通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
