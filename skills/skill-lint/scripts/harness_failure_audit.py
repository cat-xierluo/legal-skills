#!/usr/bin/env python3
"""对 Skill 中可静态确认的 Harness 失效模式做确定性审查。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "archive",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "vendor",
}
TEXT_SUFFIXES = {
    ".bash",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
}
CONFIG_DRIVEN_WORDS = re.compile(
    r"(全部由\s*(?:config|配置)|(?:config|配置)\s*驱动|config-driven)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relative: str
    text: str
    lines: tuple[str, ...]
    is_test: bool


def _is_skipped(relative: Path) -> bool:
    return any(part in SKIP_DIRS or part.startswith(".worktree") for part in relative.parts)


def _is_test_path(relative: Path) -> bool:
    lowered_parts = {part.lower() for part in relative.parts}
    name = relative.name.lower()
    return bool(
        lowered_parts & {"test", "tests", "eval", "evals", "fixtures"}
        or name.startswith("test_")
        or name.startswith("test-")
        or name.endswith("_test.py")
        or name.startswith("run-evals")
        or name.startswith("smoke-")
        or "regression" in name
    )


def _read_sources(candidate_root: Path) -> list[SourceFile]:
    sources: list[SourceFile] = []
    for path in sorted(candidate_root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(candidate_root)
        if _is_skipped(relative) or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        sources.append(
            SourceFile(
                path=path,
                relative=relative.as_posix(),
                text=text,
                lines=tuple(text.splitlines()),
                is_test=_is_test_path(relative),
            )
        )
    return sources


def _evidence(lines: tuple[str, ...], line_numbers: Iterable[int]) -> str:
    selected: list[str] = []
    for number in sorted(set(line_numbers))[:4]:
        if 1 <= number <= len(lines):
            value = lines[number - 1].strip()
            if len(value) > 180:
                value = value[:177] + "..."
            selected.append(f"L{number}: {value}")
    return " | ".join(selected)


def _finding(
    *,
    finding_id: str,
    severity: str,
    confidence: str,
    category: str,
    source: SourceFile,
    line: int,
    evidence_lines: Iterable[int],
    message: str,
    impact: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "confidence": confidence,
        "category": category,
        "file": source.relative,
        "line": line,
        "evidence": _evidence(source.lines, evidence_lines),
        "message": message,
        "impact": impact,
        "recommendation": recommendation,
        "detection_level": "static-deterministic",
    }


def _first_matching_line(source: SourceFile, pattern: re.Pattern[str]) -> int | None:
    for number, line in enumerate(source.lines, 1):
        if pattern.search(line):
            return number
    return None


def _production_scripts(sources: list[SourceFile]) -> list[SourceFile]:
    return [
        source
        for source in sources
        if not source.is_test
        and source.path.suffix.lower() in {".py", ".sh", ".bash"}
        and "scripts" in Path(source.relative).parts
    ]


def _spec_sources(sources: list[SourceFile]) -> list[SourceFile]:
    return [
        source
        for source in sources
        if source.relative == "SKILL.md"
        or (
            source.relative.startswith("references/")
            and source.path.suffix.lower() == ".md"
        )
    ]


def _scan_failure_swallowing(
    production: list[SourceFile], tests: list[SourceFile]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    executable = re.compile(
        r"(?:run_check|checker|scan(?:\.sh)?|"
        r"(?:check|verify|validate)[-_][A-Za-z0-9_-]+|"
        r"(?:bash|sh|python3?|node)\b[^\n]*(?:check|scan|verify|validate)"
        r"[A-Za-z0-9_.-]*\.(?:sh|py|js))",
        re.IGNORECASE,
    )
    for source in production:
        if source.path.suffix.lower() not in {".sh", ".bash"}:
            continue
        hits: list[int] = []
        for number, line in enumerate(source.lines, 1):
            if line.lstrip().startswith("#"):
                continue
            if "|| true" not in line:
                continue
            context = "\n".join(source.lines[max(0, number - 10) : number])
            if executable.search(line) or (
                re.search(r"}\s*>.*\|\|\s*true", line) and executable.search(context)
            ):
                hits.append(number)
        if hits:
            findings.append(
                _finding(
                    finding_id="HFA-001",
                    severity="hard",
                    confidence="high",
                    category="failure-propagation",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="生产入口吞掉 checker/scan 的真实失败状态。",
                    impact="子检查器崩溃、空输出或非零退出后，汇总层仍可能继续并给出假通过。",
                    recommendation=(
                        "逐个捕获 checker 退出码；要求合法结构化结果和预期 checker 集齐全，"
                        "任何异常、空输出或缺项都转为 hard finding。"
                    ),
                )
            )

    for source in tests:
        if source.path.suffix.lower() not in {".sh", ".bash"}:
            continue
        hits: list[int] = []
        for number, line in enumerate(source.lines, 1):
            if line.lstrip().startswith("#"):
                continue
            if "|| true" not in line:
                continue
            if re.search(
                r"^\s*(?:cat\b|rm\b|kill\b|pkill\b|cleanup\b)|"
                r"\btmux\s+kill-session\b|\bgit\b[^\n]*\bworktree\s+remove\b",
                line,
                re.I,
            ):
                continue
            nearby = "\n".join(source.lines[number : min(len(source.lines), number + 8)])
            if not re.search(r"(?:PIPESTATUS|\$\?|returncode|exit[_ -]?code)", nearby):
                hits.append(number)
        if hits:
            findings.append(
                _finding(
                    finding_id="HRA-001",
                    severity="hard",
                    confidence="high",
                    category="eval-integrity",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="测试/eval 丢弃被测命令退出码且未作等价断言。",
                    impact="用例只证明某段文字出现，错误退出语义或 checker 崩溃仍可被记为 PASS。",
                    recommendation=(
                        "显式保存并断言退出码，同时解析结构化输出、核对完整 checker 集，"
                        "并断言不存在互相矛盾的结果。"
                    ),
                )
            )
    return findings


def _scan_process_substitution(production: list[SourceFile]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    checker_command = re.compile(
        r"^\s*(?:run_)?(?:check(?:er)?|scan|verify|validate)"
        r"(?:[-_][A-Za-z0-9_]+)?(?=\s|[;|)]|$)|"
        r"^\s*(?:bash|python3?|node)\s+[^|;]*(?:/|^)"
        r"(?:check|scan|verify|validate)[A-Za-z0-9_.-]*\.(?:sh|py|js)\b",
        re.I,
    )
    for source in production:
        hits: list[int] = []
        for number, line in enumerate(source.lines, 1):
            if line.lstrip().startswith("#"):
                continue
            window = "\n".join(
                source.lines[max(0, number - 3) : min(len(source.lines), number + 5)]
            )
            if re.search(r"(?:PIPESTATUS|wait\s+['\"]?\$|coproc|status=)", window):
                continue
            substitution = re.search(r"<\s*<\(([^)]*)\)", line)
            if substitution and checker_command.search(substitution.group(1)):
                hits.append(number)
                continue
            pipe = re.search(r"(?<!\|)\|(?!\|)", line)
            if pipe:
                producer = line[: pipe.start()]
                if checker_command.search(producer):
                    hits.append(number)
        if hits:
            findings.append(
                _finding(
                    finding_id="HFA-002",
                    severity="hard",
                    confidence="medium",
                    category="failure-propagation",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="checker 位于 process substitution/管道子进程，父流程未核验其退出状态。",
                    impact="生产者失败可能只表现为空输入，父进程随后按零条结果或成功路径继续。",
                    recommendation=(
                        "先把 checker 输出写入临时文件并单独保存退出码，验证成功后再消费；"
                        "或使用能显式 wait 并检查状态的进程模型。"
                    ),
                )
            )
    return findings


def _scan_success_claims(production: list[SourceFile]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    failure_fallback = re.compile(
        r"\|\|\s*(?:print_warn|warn|echo|printf|true|:)", re.IGNORECASE
    )
    success_call = re.compile(
        r"(?:print_pass|success|echo|printf).*"
        r"(?:成功|已创建|已完成|已推送|\bPASS(?:ED)?\b|\bVERIFIED\b)",
        re.IGNORECASE,
    )
    for source in production:
        pairs: list[tuple[int, int]] = []
        for number, line in enumerate(source.lines, 1):
            if not failure_fallback.search(line):
                continue
            for later in range(number + 1, min(len(source.lines), number + 4) + 1):
                intervening = "\n".join(source.lines[number : later - 1])
                if any(not value.strip() for value in source.lines[number : later - 1]):
                    break
                if re.search(
                    r"^\s*(?:exit\b|return\b|raise\b)", intervening, re.M
                ):
                    break
                if success_call.search(source.lines[later - 1]):
                    pairs.append((number, later))
                    break
        if pairs:
            evidence_lines = [value for pair in pairs for value in pair]
            findings.append(
                _finding(
                    finding_id="HFA-003",
                    severity="hard",
                    confidence="high",
                    category="completion-claim",
                    source=source,
                    line=pairs[0][1],
                    evidence_lines=evidence_lines,
                    message="失败 fallback 后仍无条件输出成功/完成声明。",
                    impact="外部动作失败时，用户和上游编排仍会收到虚假的完成信号。",
                    recommendation=(
                        "只在命令退出码为 0 且真实回执可解析时输出成功；失败分支必须非零退出。"
                        "PR 操作还应捕获并验证返回 URL。"
                    ),
                )
            )
    return findings


def _scan_grep_double_zero(production: list[SourceFile]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    pattern = re.compile(r"grep\s+[^\n]*-c[^\n]*\|\|\s*(?:echo|printf)\s+['\"]?0", re.I)
    for source in production:
        if source.path.suffix.lower() not in {".sh", ".bash"}:
            continue
        hits = [
            number
            for number, line in enumerate(source.lines, 1)
            if pattern.search(line)
        ]
        if hits:
            findings.append(
                _finding(
                    finding_id="HFA-004",
                    severity="hard",
                    confidence="high",
                    category="shell-counting",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="`grep -c ... || echo 0` 会在零匹配时产生两个零。",
                    impact="命令替换得到 `0\\n0`，后续整数比较可能报错或进入错误分支。",
                    recommendation=(
                        "使用 `count=$(grep -c ... || true); count=${count:-0}`，"
                        "并另行区分 grep 的无匹配(1)与执行错误(>1)。"
                    ),
                )
            )
    return findings


def _scan_state_contract(
    sources: list[SourceFile], production: list[SourceFile], specs: list[SourceFile]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    shared_state = re.compile(
        r"(?:STATE_(?:FILE|DIR)|state_(?:file|dir))\s*=.*"
        r"(?:SKILL_ROOT|SCRIPT_DIR|Path\(__file__\)|candidate_root).*(?:state|history)",
        re.IGNORECASE,
    )
    project_signal = any(
        re.search(r"(?:REPO_ROOT|PROJECT_ROOT|项目维度|跨项目|per-project)", source.text, re.I)
        for source in sources
    )
    if project_signal:
        for source in production:
            line = _first_matching_line(source, shared_state)
            if line:
                findings.append(
                    _finding(
                        finding_id="HFA-005",
                        severity="hard",
                        confidence="high",
                        category="state-scope",
                        source=source,
                        line=line,
                        evidence_lines=[line],
                        message="项目级状态固定存放在 Skill 安装根目录。",
                        impact="同一 Skill 审查多个项目时会覆盖或继承彼此 baseline/history，产生跨项目误报与漏报。",
                        recommendation=(
                            "把状态放入被审项目的显式本地目录，或按 canonical project path 哈希隔离；"
                            "状态记录必须绑定项目标识和 schema version。"
                        ),
                    )
                )
                break

    claim_source: SourceFile | None = None
    claim_line: int | None = None
    for source in specs:
        for number, line in enumerate(source.lines, 1):
            if re.search(r"(?:更新|写入|update).*(?:last_scan_at|history)", line, re.I):
                claim_source, claim_line = source, number
                break
        if claim_source:
            break
    if claim_source and claim_line:
        entrypoints = [
            source
            for source in production
            if Path(source.relative).name.lower()
            in {"scan.sh", "scan.py", "run.sh", "run.py", "main.sh", "main.py"}
        ]
        entry_text = "\n".join(source.text for source in entrypoints)
        writes_last_scan = bool(
            re.search(
                r"(?:write|dump|jq|printf|update|set).{0,120}last_scan_at|"
                r"last_scan_at.{0,120}(?:write|dump|jq|printf|update|set)",
                entry_text,
                re.I | re.S,
            )
        )
        writes_history = bool(
            re.search(
                r"(?:write|dump|jq|printf|append|update).{0,120}history|"
                r"history.{0,120}(?:write|dump|jq|printf|append|update)",
                entry_text,
                re.I | re.S,
            )
        )
        if entrypoints and not (writes_last_scan and writes_history):
            findings.append(
                _finding(
                    finding_id="HFA-006",
                    severity="hard",
                    confidence="high",
                    category="declared-side-effect",
                    source=claim_source,
                    line=claim_line,
                    evidence_lines=[claim_line],
                    message="规范声明主扫描会更新 state 时间/历史，但入口没有对应持久化路径。",
                    impact="状态长期陈旧，后续流程可能把旧证据当作当前执行记录。",
                    recommendation=(
                        "在成功扫描的原子提交阶段写入 last_scan_at/history，并添加运行前后状态断言；"
                        "若不再承诺该副作用，应删除规范声明。"
                    ),
                )
            )
    return findings


def _scan_baseline_usage(
    sources: list[SourceFile], production: list[SourceFile], specs: list[SourceFile]
) -> list[dict[str, Any]]:
    normative: tuple[SourceFile, int] | None = None
    for source in specs:
        for number, line in enumerate(source.lines, 1):
            if re.search(r"(?:基线|baseline).*(?:×|乘|multiplier)", line, re.I):
                normative = (source, number)
                break
        if normative:
            break
    if not normative:
        return []

    consumers = [
        source
        for source in production
        if "baseline" not in Path(source.relative).name.lower()
    ]
    code = "\n".join(
        line
        for source in consumers
        for line in source.lines
        if not line.lstrip().startswith("#")
    )
    reads_multiplier = bool(
        re.search(
            r"(?:cfg_|get|jq|grep|json|yaml).{0,100}(?:multiplier|baselines)|"
            r"(?:multiplier|baselines).{0,100}(?:cfg_|get|jq|grep|json|yaml)",
            code,
            re.I | re.S,
        )
    )
    compares_threshold = bool(
        re.search(r"(?:multiplier|baseline)[^\n]{0,100}(?:\*|-gt|>|>=)", code, re.I)
    )
    if reads_multiplier and compares_threshold:
        return []
    source, line = normative
    return [
        _finding(
            finding_id="HFA-007",
            severity="hard",
            confidence="high",
            category="unused-policy",
            source=source,
            line=line,
            evidence_lines=[line],
            message="规范声明 baseline × multiplier 阈值，但执行路径没有读取并比较该策略。",
            impact="配置看似可调，实际结果仍是固定提示或无条件告警，导致配置与行为漂移。",
            recommendation=(
                "在实际 checker 中解析 baseline 和 multiplier、计算阈值并分支；"
                "用极端 seed/multiplier 的回归用例证明配置确实改变结果。"
            ),
        )
    ]


def _scan_cli_and_config(production: list[SourceFile]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    unknown_arg = re.compile(r"^\s*\*\)\s*(?:shift|:|continue)\s*;;")
    for source in production:
        hits: list[int] = []
        for number, line in enumerate(source.lines, 1):
            if not unknown_arg.search(line):
                continue
            before = "\n".join(source.lines[max(0, number - 14) : number])
            if re.search(r"(?:while|until)\s+.*\$\#", before) and re.search(
                r"case\s+['\"]?\$1", before
            ):
                hits.append(number)
        if hits:
            findings.append(
                _finding(
                    finding_id="HFA-008",
                    severity="hard",
                    confidence="high",
                    category="cli-contract",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="未知 CLI 参数被静默忽略。",
                    impact="参数拼写错误会让程序在默认范围运行，并可能对错误对象给出通过结论。",
                    recommendation="未知参数和缺失参数值必须输出明确错误并非零退出；为 typo 添加负向测试。",
                )
            )

    for source in production:
        hits: list[int] = []
        for number, line in enumerate(source.lines, 1):
            if re.search(
                r"(?:awk[^\n]*(?:yaml|yml)|(?:yaml|yml)[^\n]*awk|"
                r"json\.loads|jq\b)[^\n]*\|\|\s*true",
                line,
                re.I,
            ):
                hits.append(number)
            elif re.search(
                r"grep\s+-[A-Za-z]*E\s+['\"]?\$[A-Za-z_]*(?:PATTERN|REGEX)"
                r"[^\n]*\|\|\s*true",
                line,
                re.I,
            ):
                hits.append(number)
        if hits:
            findings.append(
                _finding(
                    finding_id="HFA-009",
                    severity="hard",
                    confidence="high",
                    category="config-fail-closed",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="配置/YAML/动态正则解析错误被折叠成空值或零匹配。",
                    impact="非法配置会退化为默认或无检查状态，最终可能显示通过而不是配置错误。",
                    recommendation=(
                        "分别处理“无匹配”和“解析/正则错误”；解析错误必须产生 config-error hard finding，"
                        "并加入非法 YAML、非法 regex、缺字段故障用例。"
                    ),
                )
            )
    return findings


def _scan_json_emission(production: list[SourceFile]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    raw_json = re.compile(r"printf\s+['\"].*\{.*%s", re.I)
    for source in production:
        if source.path.suffix.lower() not in {".sh", ".bash"}:
            continue
        hits = [
            number
            for number, line in enumerate(source.lines, 1)
            if raw_json.search(line)
        ]
        if hits and not re.search(r"(?:jq\s+-n|json\.dumps|JSON\.stringify)", source.text):
            findings.append(
                _finding(
                    finding_id="HFA-010",
                    severity="hard",
                    confidence="high",
                    category="structured-output",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="用 raw printf 插值拼接 JSON，未做字符串转义或解析复验。",
                    impact="路径/消息中的引号、反斜杠或换行会生成非法 JSON；grep 汇总仍可能把它计为结果。",
                    recommendation=(
                        "使用 jq -n、Python json.dumps 或同等 JSON encoder；汇总入口必须逐行解析并按 schema 校验。"
                    ),
                )
            )
    return findings


def _scan_git_side_effects(production: list[SourceFile]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    side_effect = re.compile(
        r"^\s*\bgit\b(?:\s+-C\s+(?:\"[^\"]+\"|'[^']+'|\S+))?\s+"
        r"(?:checkout|switch|commit|push)\b|\bgh\s+pr\s+create\b",
        re.I,
    )
    for source in production:
        hits = [
            number
            for number, line in enumerate(source.lines, 1)
            if not line.lstrip().startswith("#")
            and (
                side_effect.search(line)
                and (
                    line.lstrip().startswith("git ")
                    or line.lstrip().startswith("gh ")
                )
            )
        ]
        if not hits:
            continue
        safety = source.text.lower()
        missing: list[str] = []
        mutates_worktree = bool(
            re.search(
                r"^\s*git\b[^\n]*\b(?:checkout|switch|commit)\b",
                source.text,
                re.I | re.M,
            )
        )
        isolated_temp_repo = bool(
            re.search(r"\bmktemp\b", source.text, re.I)
            and re.search(r"^\s*git\s+init\b", source.text, re.I | re.M)
        )
        if (
            mutates_worktree
            and not isolated_temp_repo
            and "git worktree" not in safety
            and "enterworktree" not in safety
        ):
            missing.append("worktree 隔离")
        is_safe_push_implementation = bool(
            Path(source.relative).name in {"safe-push.sh", "safe_push.sh"}
            and re.search(
                r"(?:check[-_]outgoing[-_]identit|expected[-_]email|"
                r"author.{0,40}committer)",
                source.text,
                re.I | re.S,
            )
        )
        if (
            "git push" in safety
            and "safe-push" not in safety
            and "safe_push" not in safety
            and not is_safe_push_implementation
        ):
            missing.append("safe-push/提交身份与 outgoing range 核验")
        if "gh pr create" in safety and not re.search(
            r"(?:pr_url|pull_request_url|https://github\.com/.*/pull/|--json\s+url)",
            source.text,
            re.I,
        ):
            missing.append("PR URL 回执")
        if missing:
            findings.append(
                _finding(
                    finding_id="HFA-011",
                    severity="hard",
                    confidence="high",
                    category="git-side-effect",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="Git/PR 副作用绕过可审计安全边界：" + "、".join(missing) + "。",
                    impact="可能污染用户当前分支、用错身份推送，或在 PR 未创建时仍声称完成。",
                    recommendation=(
                        "在独立 worktree 执行；push 前核验完整 outgoing range 的 author/committer；"
                        "仅在捕获并验证 PR URL 后声明创建成功。"
                    ),
                )
            )
    return findings


def _scan_destructive_transforms(
    production: list[SourceFile], tests: list[SourceFile]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    destructive_sources: list[tuple[SourceFile, list[int]]] = []
    bounded_retention = re.compile(
        r"(?:保留|只留|keep|retain|latest|last).{0,30}\d+|"
        r"(?:count|len|bc|entries|records|条目|记录).{0,30}(?:>|>=).{0,10}\d+",
        re.I,
    )
    structured_records = re.compile(
        r"(?:progress|history|tasks?|logs?|entries|records|"
        r"进度|历史|任务|日志|条目|记录)",
        re.I,
    )
    for source in production:
        hits: list[int] = []
        for number, line in enumerate(source.lines, 1):
            if not re.search(
                r"(?:mv\s+['\"]?\$[A-Za-z0-9_]+.*\$[A-Za-z0-9_]+|"
                r"write_text\(|replace\(|>\s*['\"]?\$[A-Za-z0-9_]+)",
                line,
                re.I,
            ):
                continue
            local_context = "\n".join(
                source.lines[max(0, number - 12) : min(len(source.lines), number + 12)]
            )
            if (
                re.search(r"(?:trim|prune|compact|裁剪|删减)", local_context, re.I)
                and bounded_retention.search(local_context)
                and structured_records.search(local_context)
            ):
                hits.append(number)
        if hits:
            destructive_sources.append((source, hits))
            findings.append(
                _finding(
                    finding_id="HFA-012",
                    severity="warning",
                    confidence="medium",
                    category="destructive-transform",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="trim/rewrite 路径会替换原文件，但代码内未见数据守恒证明。",
                    impact="边界条件可能删除全部记录、错误排序或丢失应迁移的数据。",
                    recommendation=(
                        "先构造新内容并验证保留数、迁移数、总数守恒，再原子替换；失败时保留原文件。"
                    ),
                )
            )
    if destructive_sources:
        test_text = "\n".join(source.text for source in tests)
        has_conservation = bool(
            re.search(
                r"(?:idempoten|幂等|conservation|守恒|data[_ -]?loss|"
                r"保留.{0,20}(?:5|five)|second[_ -]?run)",
                test_text,
                re.I | re.S,
            )
        )
        if not has_conservation:
            source, hits = destructive_sources[0]
            findings.append(
                _finding(
                    finding_id="HRA-002",
                    severity="hard",
                    confidence="high",
                    category="regression-coverage",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="破坏性 trim/rewrite 没有数据守恒和幂等回归。",
                    impact="普通字符串断言无法发现“应该保留 5 条却全部删除”等真实数据损坏。",
                    recommendation=(
                        "增加 before/after fixture：断言保留最近 N 条、旧数据按约定迁移、总量守恒，"
                        "并对同一输入连续运行两次验证幂等。"
                    ),
                )
            )
    return findings


def _scan_config_drift(
    production: list[SourceFile], specs: list[SourceFile]
) -> list[dict[str, Any]]:
    claim: tuple[SourceFile, int] | None = None
    for source in specs:
        for number, line in enumerate(source.lines, 1):
            if CONFIG_DRIVEN_WORDS.search(line):
                claim = (source, number)
                break
        if claim:
            break
    if not claim:
        return []

    hardcoded = re.compile(
        r"(?:declare\s+-A\s+files|\[\"(?:docs/|README\.md|AGENTS\.md)|"
        r"grep[^\n]*\^###\s+(?:ISS|Task)|multiplier[^\n]*1\.5)",
        re.I,
    )
    for source in production:
        hits = [
            number
            for number, line in enumerate(source.lines, 1)
            if hardcoded.search(line)
        ]
        if hits:
            return [
                _finding(
                    finding_id="HFA-013",
                    severity="warning",
                    confidence="medium",
                    category="config-implementation-drift",
                    source=source,
                    line=hits[0],
                    evidence_lines=hits,
                    message="规范声称配置驱动，但执行/基线入口仍含硬编码路径、编号模式或阈值。",
                    impact="某一入口修复后，其他入口仍按旧项目约定运行，形成部分落地和跨项目漂移。",
                    recommendation=(
                        "让生产、首次基线、维护与测试共用同一配置访问层；"
                        "为两组不同路径/编号配置建立参数化回归。"
                    ),
                )
            ]
    return []


def audit_candidate(candidate_root: Path) -> dict[str, Any]:
    candidate_root = candidate_root.expanduser().resolve()
    if not (candidate_root / "SKILL.md").is_file():
        raise ValueError(f"候选目录缺少 SKILL.md: {candidate_root}")
    sources = _read_sources(candidate_root)
    production = _production_scripts(sources)
    tests = [source for source in sources if source.is_test]
    specs = _spec_sources(sources)

    findings: list[dict[str, Any]] = []
    findings.extend(_scan_failure_swallowing(production, tests))
    findings.extend(_scan_process_substitution(production))
    findings.extend(_scan_success_claims(production))
    findings.extend(_scan_grep_double_zero(production))
    findings.extend(_scan_state_contract(sources, production, specs))
    findings.extend(_scan_baseline_usage(sources, production, specs))
    findings.extend(_scan_cli_and_config(production))
    findings.extend(_scan_json_emission(production))
    findings.extend(_scan_git_side_effects(production))
    findings.extend(_scan_destructive_transforms(production, tests))
    findings.extend(_scan_config_drift(production, specs))

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for finding in findings:
        unique.setdefault((finding["id"], finding["file"]), finding)
    ordered = sorted(
        unique.values(), key=lambda item: (item["file"], item["line"], item["id"])
    )
    summary = {
        "hard": sum(item["severity"] == "hard" for item in ordered),
        "warning": sum(item["severity"] == "warning" for item in ordered),
        "info": sum(item["severity"] == "info" for item in ordered),
        "total": len(ordered),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "single",
        "candidate_root": str(candidate_root),
        "skill": candidate_root.name,
        "status": (
            "FAIL"
            if summary["hard"]
            else ("WARN" if summary["warning"] else "PASS")
        ),
        "summary": summary,
        "findings": ordered,
    }


def discover_skill_roots(collection_root: Path) -> list[Path]:
    collection_root = collection_root.expanduser().resolve()
    roots: list[Path] = []
    for path in sorted(collection_root.rglob("SKILL.md")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(collection_root)
        if _is_skipped(relative):
            continue
        roots.append(path.parent)
    return roots


def audit_collection(collection_root: Path) -> dict[str, Any]:
    collection_root = collection_root.expanduser().resolve()
    roots = discover_skill_roots(collection_root)
    if not roots:
        raise ValueError(f"集合中未发现任何 SKILL.md: {collection_root}")
    reports = [audit_candidate(root) for root in roots]
    totals = {
        "skills": len(reports),
        "failed_skills": sum(report["status"] == "FAIL" for report in reports),
        "warning_skills": sum(report["status"] == "WARN" for report in reports),
        "hard": sum(report["summary"]["hard"] for report in reports),
        "warning": sum(report["summary"]["warning"] for report in reports),
        "info": sum(report["summary"]["info"] for report in reports),
        "findings": sum(report["summary"]["total"] for report in reports),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "batch",
        "collection_root": str(collection_root),
        "status": "FAIL" if totals["hard"] else ("WARN" if totals["warning"] else "PASS"),
        "summary": totals,
        "skills": reports,
    }


def _write_output(report: dict[str, Any], output: str | None) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="审查单个 Skill")
    audit_parser.add_argument("--candidate-root", required=True)
    audit_parser.add_argument("--output")

    batch_parser = subparsers.add_parser("batch", help="递归审查 Skill 集合")
    batch_parser.add_argument("--root", required=True)
    batch_parser.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "audit":
            report = audit_candidate(Path(args.candidate_root))
        else:
            report = audit_collection(Path(args.root))
    except (OSError, ValueError) as exc:
        print(f"HARNESS_FAILURE_AUDIT_BLOCKED: {exc}", file=sys.stderr)
        return 2
    _write_output(report, args.output)
    return 1 if report["summary"]["hard"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
