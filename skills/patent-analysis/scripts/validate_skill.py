#!/usr/bin/env python3
"""Validate patent-analysis public files without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


SKILL_DIR = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "2.1.1"

FORBIDDEN_PATTERNS = {
    "placeholder_case": re.compile(r"(?:案号\s*[:：]?|最高法知(?:民|行)[^\n]{0,12})(?:[^\n]{0,20})(?:XXX|若干)"),
    "four_month_reply": re.compile(
        r"(?:答复[^\n]{0,20}(?:4|四)\s*个?月|(?:4|四)\s*个?月[^\n]{0,20}答复)"
    ),
    "six_month_suit": re.compile(
        r"(?:无效[^\n]{0,30}(?:起诉|诉讼)[^\n]{0,20}(?:6|六)\s*个?月|"
        r"无效[^\n]{0,30}(?:6|六)\s*个?月[^\n]{0,20}(?:起诉|诉讼))"
    ),
    "six_month_appeal": re.compile(
        r"(?:上诉[^\n]{0,20}(?:6|六)\s*个?月|(?:6|六)\s*个?月[^\n]{0,20}上诉)"
    ),
    "unsupported_percentage": re.compile(r"(?:无效|侵权|胜诉|案件)[^\n]{0,30}(?:\d+\s*%|\d+\s*[-—至]\s*\d+\s*%)"),
    "missing_collaborator": re.compile(r"(?<!legal-)proposal-generator|case-analysis-summary|litigation-preparation"),
    "evidence_gate_override": re.compile(
        r"(?:即使|即便)[^\n]{0,40}(?:B/D|`?B`?|`?C`?|`?D`?)[^\n]{0,40}"
        r"(?:仍可|仍然可以|也可|也可以|可以)[^\n]{0,20}(?:全面覆盖|字面落入|侵权成立)"
    ),
    "preliminary_evidence_counted": re.compile(
        r"(?:B-初步支持|D-无法判断|B/D)[^\n]{0,40}(?:可以|可)(?:计入|视为)[^\n]{0,12}(?:覆盖|落入)"
    ),
    "missing_input_still_rated": re.compile(
        r"(?:缺少|未提供|未核验)[^\n]{0,80}(?:仍可|仍然可以|可以继续|可继续)"
        r"[^\n]{0,20}(?:风险评级|评级|确定性结论)"
    ),
}


def public_markdown_files() -> list[Path]:
    files = [SKILL_DIR / "SKILL.md", SKILL_DIR / "README.md"]
    files.extend(sorted((SKILL_DIR / "references").glob("*.md")))
    return files


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    try:
        block = text.split("---\n", 2)[1]
    except IndexError:
        return {}
    result: dict[str, str] = {}
    for line in block.splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
        if match:
            result[match.group(1)] = match.group(2).strip("\"'")
    return result


def check_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        raw_target = match.group(1).strip().split(maxsplit=1)[0].strip("<>\"")
        if not raw_target or raw_target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target_part = unquote(raw_target.split("#", 1)[0])
        target = (path.parent / target_part).resolve()
        if not target.exists():
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path.relative_to(SKILL_DIR)}:{line}: relative link not found: {raw_target}")
    return errors


def check_public_content(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        errors.extend(check_links(path, text))
        for code, pattern in FORBIDDEN_PATTERNS.items():
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{path.relative_to(SKILL_DIR)}:{line}: {code}: {match.group(0)!r}")
    return errors


def forbidden_codes(text: str) -> list[str]:
    return [code for code, pattern in FORBIDDEN_PATTERNS.items() if pattern.search(text)]


def check_required_rules(skill_text: str, fto_text: str) -> list[str]:
    errors: list[str] = []
    skill_requirements = [
        "A-已证实",
        "B-初步支持",
        "C-不相同/缺失",
        "D-无法判断",
        "证据不足，暂不能判断是否全面覆盖",
        "不默认只看权利要求 1",
        "无论是否同时存在 `B/D`",
        "仅在不存在 `C`",
    ]
    fto_requirements = [
        "目标法域",
        "产品版本",
        "实施行为",
        "检索截止日",
        "法律状态",
        "必须停止风险评级，只输出补充或核验清单",
    ]
    for phrase in skill_requirements:
        if phrase not in skill_text:
            errors.append(f"SKILL.md: missing required rule: {phrase}")
    for phrase in fto_requirements:
        if phrase not in fto_text:
            errors.append(f"references/05-fto-analysis.md: missing FTO gate: {phrase}")
    return errors


def second_level_section(text: str, heading: str) -> str:
    match = re.search(
        rf"^{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s|\Z)",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1) if match else ""


def check_legal_basis(
    legal_text: str | None = None,
    equivalence_text: str | None = None,
) -> list[str]:
    """Require a link-free, multi-provision legal basis for core doctrines."""
    if legal_text is None:
        legal_text = (SKILL_DIR / "references" / "00-legal-basis.md").read_text(encoding="utf-8")
    if equivalence_text is None:
        equivalence_text = (SKILL_DIR / "references" / "08-doctrine-of-equivalents.md").read_text(
            encoding="utf-8"
        )

    errors: list[str] = []
    for name, text in [
        ("references/00-legal-basis.md", legal_text),
        ("references/08-doctrine-of-equivalents.md", equivalence_text),
    ]:
        if re.search(r"https?://", text, flags=re.IGNORECASE):
            errors.append(f"{name}: public legal basis must not contain web URLs")

    sections = {
        "保护范围": second_level_section(legal_text, "## 二、保护范围与权利要求解释"),
        "全面覆盖": second_level_section(legal_text, "## 三、全面覆盖与字面落入"),
        "等同原则": second_level_section(legal_text, "## 四、等同原则及其限制"),
    }
    for doctrine, section_text in sections.items():
        if not section_text:
            errors.append(f"references/00-legal-basis.md: missing section: {doctrine}")

    required_groups = {
        "保护范围": [
            "《专利法》第六十四条",
            "《专利纠纷若干规定》第十三条",
            "《专利侵权司法解释（一）》第一条",
            "《专利侵权司法解释（一）》第二条",
            "《专利侵权司法解释（一）》第三条",
            "《专利侵权司法解释（一）》第四条",
            "《专利侵权司法解释（一）》第五条",
        ],
        "全面覆盖": [
            "《专利侵权司法解释（一）》第七条",
            "《专利侵权司法解释（二）》第五条",
            "《专利侵权司法解释（二）》第七条",
            "《专利侵权司法解释（二）》第八条",
            "《专利侵权司法解释（二）》第九条",
            "《专利侵权司法解释（二）》第十条",
            "《专利侵权司法解释（二）》第十一条",
            "《专利侵权司法解释（二）》第十二条",
        ],
        "等同原则": [
            "《专利纠纷若干规定》第十三条",
            "《专利侵权司法解释（一）》第五条",
            "《专利侵权司法解释（一）》第六条",
            "《专利侵权司法解释（二）》第八条",
            "《专利侵权司法解释（二）》第十二条",
            "《专利侵权司法解释（二）》第十三条",
        ],
    }
    for doctrine, phrases in required_groups.items():
        missing = [phrase for phrase in phrases if phrase not in sections[doctrine]]
        if missing:
            errors.append(f"references/00-legal-basis.md: {doctrine} missing provisions: {missing}")

    equivalence_requirements = [
        "《最高人民法院关于审理专利纠纷案件适用法律问题的若干规定》第十三条",
        "《专利侵权司法解释（一）》第七条",
        "《专利侵权司法解释（一）》第四条",
        "《专利侵权司法解释（一）》第五条",
        "《专利侵权司法解释（一）》第六条",
        "《专利侵权司法解释（二）》第八条",
        "《专利侵权司法解释（二）》第十二条",
        "《专利侵权司法解释（二）》第十三条",
    ]
    missing = [phrase for phrase in equivalence_requirements if phrase not in equivalence_text]
    if missing:
        errors.append(f"references/08-doctrine-of-equivalents.md: missing provisions: {missing}")
    return errors


def check_root_readme_release(readme_text: str) -> list[str]:
    errors: list[str] = []
    match = re.search(
        r'<tr>\s*<td><a href="skills/patent-analysis/"[^>]*>.*?</tr>',
        readme_text,
        flags=re.DOTALL,
    )
    if not match:
        return ["root README: patent-analysis release row not found"]
    block = match.group(0)
    expected_label = f"v{RELEASE_VERSION}"
    if expected_label not in block:
        errors.append(f"root README: patent-analysis release row does not show {expected_label}")
    linked_versions = re.findall(r"patent-analysis-(\d+\.\d+\.\d+)\.zip", block)
    if any(version != RELEASE_VERSION for version in linked_versions):
        errors.append(f"root README: download version mismatch: {linked_versions}")
    if not linked_versions and "待发布" not in block:
        errors.append(
            f"root README: {expected_label} has neither a matching download nor a pending-release label"
        )
    return errors


def check_local_release() -> list[str]:
    errors: list[str] = []
    changelog = (SKILL_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (SKILL_DIR / "README.md").read_text(encoding="utf-8")
    license_text = (SKILL_DIR / "LICENSE.txt").read_text(encoding="utf-8")
    version_heading = re.search(r"^## \[([^]]+)]", changelog, flags=re.MULTILINE)
    if not version_heading or version_heading.group(1).lstrip("v") != RELEASE_VERSION:
        errors.append(f"CHANGELOG.md: latest version is not {RELEASE_VERSION}")
    if f"v{RELEASE_VERSION}" not in readme:
        errors.append(f"README.md: missing v{RELEASE_VERSION}")
    if "CC BY-NC 4.0" not in readme:
        errors.append("README.md: missing CC BY-NC 4.0 license label")
    if not license_text.startswith("Creative Commons Attribution-NonCommercial 4.0 International\n"):
        errors.append("LICENSE.txt: not the expected CC BY-NC 4.0 text")
    if "ShareAlike" in license_text or "by-nc-sa" in license_text.lower():
        errors.append("LICENSE.txt: contains ShareAlike terms inconsistent with CC BY-NC")

    expected_references = {f"{index:02d}-{name}.md" for index, name in enumerate([
        "legal-basis",
        "single-patent-summary",
        "multi-patent-comparison",
        "infringement-comparison",
        "validity-analysis",
        "fto-analysis",
        "design-around",
        "patent-valuation",
        "doctrine-of-equivalents",
        "invalidation-defense",
        "visualization",
    ])}
    actual_references = {path.name for path in (SKILL_DIR / "references").glob("*.md")}
    if actual_references != expected_references:
        errors.append(
            "references: unexpected file set: "
            f"missing={sorted(expected_references - actual_references)}, "
            f"extra={sorted(actual_references - expected_references)}"
        )
    return errors


def check_repo_sync(repo_root: Path) -> list[str]:
    errors: list[str] = []
    marketplace = repo_root / ".claude-plugin" / "marketplace.json"
    root_readme = repo_root / "README.md"
    try:
        data = json.loads(marketplace.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"marketplace parse failed: {exc}"]

    entries = [item for item in data.get("plugins", []) if item.get("name") == "patent-analysis"]
    if len(entries) != 1:
        errors.append(f"marketplace: expected one patent-analysis entry, found {len(entries)}")
    elif str(entries[0].get("version")) != RELEASE_VERSION:
        errors.append(
            f"marketplace: patent-analysis version is {entries[0].get('version')!r}, "
            f"expected {RELEASE_VERSION!r}"
        )

    try:
        readme_text = root_readme.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"root README read failed: {exc}")
    else:
        errors.extend(check_root_readme_release(readme_text))
    for collaborator in [
        "patent-download",
        "legal-ocr",
        "mineru-ocr",
        "yuandian-law-search",
        "legal-proposal-generator",
        "legal-visualization",
        "md2word",
    ]:
        if not (repo_root / "skills" / collaborator / "SKILL.md").is_file():
            errors.append(f"collaborator not found: skills/{collaborator}/SKILL.md")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, help="Also validate repository publishing metadata")
    args = parser.parse_args()

    files = public_markdown_files()
    errors: list[str] = []
    missing = [str(path.relative_to(SKILL_DIR)) for path in files if not path.is_file()]
    errors.extend(f"missing file: {path}" for path in missing)
    existing = [path for path in files if path.is_file()]

    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    metadata = frontmatter(skill_text)
    expected = {"name": "patent-analysis", "version": RELEASE_VERSION, "license": "CC-BY-NC"}
    for key, value in expected.items():
        if metadata.get(key) != value:
            errors.append(f"SKILL.md frontmatter: {key}={metadata.get(key)!r}, expected {value!r}")

    errors.extend(check_public_content(existing))
    errors.extend(check_local_release())
    errors.extend(
        check_required_rules(
            skill_text,
            (SKILL_DIR / "references" / "05-fto-analysis.md").read_text(encoding="utf-8"),
        )
    )
    errors.extend(check_legal_basis())
    if args.repo_root:
        errors.extend(check_repo_sync(args.repo_root.resolve()))

    result = {"status": "PASS" if not errors else "FAIL", "checks": len(existing), "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
