#!/usr/bin/env python3
"""审查运行时配置：审查人资料、审查上下文与时间线。"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = SKILL_ROOT / "config"
CONFIG_DIR = Path(
    os.environ.get("CONTRACT_COPILOT_CONFIG_DIR", str(DEFAULT_CONFIG_DIR))
).expanduser()
PROFILE_PATH = Path(
    os.environ.get(
        "CONTRACT_COPILOT_REVIEWER_PROFILE", str(CONFIG_DIR / "reviewer_profile.json")
    )
).expanduser()
PROFILE_TEMPLATE_PATH = Path(
    os.environ.get(
        "CONTRACT_COPILOT_REVIEWER_PROFILE_EXAMPLE",
        str(DEFAULT_CONFIG_DIR / "reviewer_profile.example.json"),
    )
).expanduser()
REVIEW_MEMORY_PATH = Path(
    os.environ.get(
        "CONTRACT_COPILOT_REVIEW_MEMORY",
        str(CONFIG_DIR / "review_memory.json"),
    )
).expanduser()
REVIEW_MEMORY_TEMPLATE_PATH = Path(
    os.environ.get(
        "CONTRACT_COPILOT_REVIEW_MEMORY_EXAMPLE",
        str(DEFAULT_CONFIG_DIR / "review_memory.example.json"),
    )
).expanduser()

DEFAULT_INITIALS = "CA"
DEFAULT_TIME_GAP_MINUTES = 5
DEFAULT_TIME_GAP_MAX_MINUTES = 10
DEFAULT_START_DELAY_MINUTES = 0
DEFAULT_START_DELAY_MAX_MINUTES = 2
DEFAULT_INTRA_ACTION_GAP_MINUTES = 1
DEFAULT_INTRA_ACTION_GAP_MAX_MINUTES = 2
DEFAULT_REVIEW_INTENSITY = "常规"
DEFAULT_NONINTERACTIVE_REVIEW_INTENSITY = "强势"
DEFAULT_EDIT_POLICY = "revise-first"

PARTY_ROLE_ALIASES = {
    "party_a": "甲方",
    "甲方": "甲方",
    "a": "甲方",
    "甲": "甲方",
    "party_b": "乙方",
    "乙方": "乙方",
    "b": "乙方",
    "乙": "乙方",
    "neutral": "中立",
    "中立": "中立",
    "other": "其他",
    "其他": "其他",
}

REVIEW_INTENSITY_ALIASES = {
    "克制": "克制",
    "保守": "克制",
    "谨慎": "克制",
    "light": "克制",
    "light-touch": "克制",
    "常规": "常规",
    "标准": "常规",
    "一般": "常规",
    "normal": "常规",
    "moderate": "常规",
    "强势": "强势",
    "严格": "强势",
    "assertive": "强势",
    "aggressive": "强势",
    "strict": "强势",
}


def get_local_timezone():
    return datetime.now().astimezone().tzinfo or timezone.utc


def get_local_now() -> datetime:
    return datetime.now().astimezone(get_local_timezone())


def format_word_local_timestamp(value: datetime) -> str:
    localized = value.astimezone(get_local_timezone())
    return localized.isoformat(timespec="seconds")


def derive_initials(author: str) -> str:
    text = re.sub(r"\s+", " ", author).strip()
    if not text:
        return DEFAULT_INITIALS

    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    if cjk_chars:
        return "".join(cjk_chars[:2]) or DEFAULT_INITIALS

    words = re.findall(r"[A-Za-z0-9]+", text)
    if len(words) >= 2:
        return (words[0][:1] + words[1][:1]).upper()
    if words:
        return words[0][:2].upper()
    return text[:2].upper() or DEFAULT_INITIALS


def default_profile() -> dict[str, Any]:
    return {
        "author": "",
        "initials": "",
        "organization": "",
        "department": "",
        "confirmed": False,
        "time_gap_min_minutes": DEFAULT_TIME_GAP_MINUTES,
        "time_gap_max_minutes": DEFAULT_TIME_GAP_MAX_MINUTES,
    }


def default_review_memory() -> dict[str, Any]:
    return {
        "contracts": {},
        "clients": {},
    }


def _load_profile_from(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_profile()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return default_profile()
    merged = default_profile()
    merged.update({key: value for key, value in payload.items() if value is not None})
    return merged


def _load_memory_from(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_review_memory()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return default_review_memory()
    merged = default_review_memory()
    for key in ("contracts", "clients"):
        current = payload.get(key)
        if isinstance(current, dict):
            merged[key] = current
    return merged


def load_profile() -> dict[str, Any]:
    return _load_profile_from(PROFILE_PATH)


def load_profile_template() -> dict[str, Any]:
    return _load_profile_from(PROFILE_TEMPLATE_PATH)


def load_review_memory() -> dict[str, Any]:
    return _load_memory_from(REVIEW_MEMORY_PATH)


def load_review_memory_template() -> dict[str, Any]:
    return _load_memory_from(REVIEW_MEMORY_TEMPLATE_PATH)


def save_profile(profile: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = default_profile()
    merged.update({key: value for key, value in profile.items() if value is not None})
    PROFILE_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_review_memory(memory: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = default_review_memory()
    for key in ("contracts", "clients"):
        current = memory.get(key)
        if isinstance(current, dict):
            merged[key] = current
    REVIEW_MEMORY_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _should_prompt_for_profile() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_required_field(prompt_text: str) -> str:
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        print("该字段不能为空，请重新输入。", file=sys.stderr)


def _prompt_optional_field(prompt_text: str) -> str:
    return input(prompt_text).strip()


def _prompt_required_field_with_default(prompt_text: str, current_value: str) -> str:
    if not str(current_value or "").strip():
        return _prompt_required_field(prompt_text)

    while True:
        value = input(
            f"{prompt_text}（当前值：{current_value}；直接回车确认）："
        ).strip()
        if value:
            return value
        if current_value:
            return current_value
        print("该字段不能为空，请重新输入。", file=sys.stderr)


def _prompt_optional_field_with_default(prompt_text: str, current_value: str) -> str:
    if not str(current_value or "").strip():
        return _prompt_optional_field(prompt_text)
    value = input(
        f"{prompt_text}（当前值：{current_value}；直接回车保留）："
    ).strip()
    return value or current_value


def _print_profile_notice() -> None:
    print(
        "首次使用需要记录审查人信息：姓名、律所/公司名称，部门可选。"
        "该配置只保存在当前本地 skill 的 config 目录中，不会自动上传；"
        "后续可随时通过自然语言让我帮你修改。",
        file=sys.stderr,
    )


def _print_profile_confirmation_notice() -> None:
    print(
        "检测到当前环境存在审查人配置，但尚未完成本环境确认。"
        "请确认审查人姓名、律所/公司名称和可选部门后，再继续执行审查。",
        file=sys.stderr,
    )


def _print_review_context_notice() -> None:
    print(
        "首次补齐审查上下文时，需要确认客户名称、审查立场和审查口径。"
        "这些信息只保存在当前本地 skill 的 config 目录中，后续命中同名合同时会默认带出；"
        "也可以随时通过自然语言让我帮你修改。",
        file=sys.stderr,
    )


def _normalize_lookup_key(value: str) -> str:
    text = re.sub(r"[\W_]+", "", str(value or ""), flags=re.UNICODE).strip()
    return text.lower()


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def normalize_party_role(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return PARTY_ROLE_ALIASES.get(raw.lower()) or PARTY_ROLE_ALIASES.get(raw) or ""


def normalize_review_intensity(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return (
        REVIEW_INTENSITY_ALIASES.get(raw.lower())
        or REVIEW_INTENSITY_ALIASES.get(raw)
        or ""
    )


def _resolve_parties(summary: dict[str, Any], meta: dict[str, Any]) -> tuple[str, str]:
    for container in (summary, meta):
        parties = container.get("parties")
        if isinstance(parties, dict):
            party_a = _first_text(
                parties.get("party_a"),
                parties.get("party_a_name"),
                parties.get("甲方"),
            )
            party_b = _first_text(
                parties.get("party_b"),
                parties.get("party_b_name"),
                parties.get("乙方"),
            )
            if party_a or party_b:
                return party_a, party_b

        party_a = _first_text(
            container.get("party_a"),
            container.get("party_a_name"),
            container.get("甲方"),
        )
        party_b = _first_text(
            container.get("party_b"),
            container.get("party_b_name"),
            container.get("乙方"),
        )
        if party_a or party_b:
            return party_a, party_b
    return "", ""


def infer_client_name(
    summary: dict[str, Any],
    meta: dict[str, Any],
    party_role: str,
) -> str:
    party_a, party_b = _resolve_parties(summary, meta)
    if party_role == "甲方":
        return party_a
    if party_role == "乙方":
        return party_b
    return _first_text(meta.get("client_name"), summary.get("client_name"))


def _prompt_choice(
    prompt_text: str,
    *,
    normalizer,
    default: str = "",
) -> str:
    while True:
        raw = input(prompt_text).strip()
        if not raw and default:
            return default
        normalized = normalizer(raw)
        if normalized:
            return normalized
        print("请输入有效选项。", file=sys.stderr)


def resolve_review_context(
    *,
    input_docx: str | Path | None,
    plan_meta: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    client_name: str | None = None,
    party_role: str | None = None,
    review_intensity: str | None = None,
    edit_policy: str | None = None,
) -> dict[str, Any]:
    meta = plan_meta if isinstance(plan_meta, dict) else {}
    contract_name = _first_text(
        meta.get("contract_name"),
        meta.get("title"),
        Path(input_docx).stem if input_docx else "",
    )
    contract_key = _normalize_lookup_key(contract_name)

    memory_exists = REVIEW_MEMORY_PATH.exists()
    memory = load_review_memory() if memory_exists else load_review_memory_template()
    contracts = memory.get("contracts")
    clients = memory.get("clients")
    if not isinstance(contracts, dict):
        contracts = {}
        memory["contracts"] = contracts
    if not isinstance(clients, dict):
        clients = {}
        memory["clients"] = clients

    contract_record = contracts.get(contract_key, {}) if contract_key else {}
    if not isinstance(contract_record, dict):
        contract_record = {}

    resolved_party_role = normalize_party_role(
        party_role or meta.get("party_role") or meta.get("role")
    )
    if not resolved_party_role:
        resolved_party_role = normalize_party_role(contract_record.get("party_role"))

    resolved_client_name = _first_text(
        client_name,
        meta.get("client_name"),
        contract_record.get("client_name"),
    )

    client_record: dict[str, Any] = {}
    if resolved_client_name:
        current = clients.get(_normalize_lookup_key(resolved_client_name), {})
        if isinstance(current, dict):
            client_record = current

    if not resolved_party_role:
        resolved_party_role = normalize_party_role(
            client_record.get("preferred_party_role")
        )

    if not resolved_client_name:
        inferred = infer_client_name(
            summary if isinstance(summary, dict) else {},
            meta,
            resolved_party_role,
        )
        resolved_client_name = inferred or ""
        if resolved_client_name:
            current = clients.get(_normalize_lookup_key(resolved_client_name), {})
            if isinstance(current, dict):
                client_record = current

    resolved_review_intensity = normalize_review_intensity(
        review_intensity
        or meta.get("review_intensity")
        or contract_record.get("review_intensity")
        or client_record.get("preferred_review_intensity")
    )

    if _should_prompt_for_profile():
        if not resolved_client_name or not resolved_party_role or not resolved_review_intensity:
            _print_review_context_notice()
        if not resolved_client_name:
            resolved_client_name = _prompt_required_field(
                "请输入客户名称（通常为我方主体名称）："
            )
        if not resolved_party_role:
            resolved_party_role = _prompt_choice(
                "请选择审查立场（甲方/乙方/中立/其他）：",
                normalizer=normalize_party_role,
            )
        if not resolved_review_intensity:
            resolved_review_intensity = _prompt_choice(
                "请选择审查口径（克制/常规/强势）：",
                normalizer=normalize_review_intensity,
                default=DEFAULT_REVIEW_INTENSITY,
            )
    else:
        if not resolved_client_name:
            resolved_client_name = (
                infer_client_name(
                    summary if isinstance(summary, dict) else {},
                    meta,
                    resolved_party_role,
                )
                or "未提及/待补充"
            )
        if not resolved_party_role:
            resolved_party_role = "其他"
        if not resolved_review_intensity:
            resolved_review_intensity = DEFAULT_NONINTERACTIVE_REVIEW_INTENSITY

    resolved_edit_policy = str(edit_policy or meta.get("edit_policy") or "").strip()
    if resolved_edit_policy:
        raw_edit_policy = resolved_edit_policy.lower()
        if raw_edit_policy not in {"revise-first", "balanced", "comment-first"}:
            raise ValueError(f"不支持的 edit_policy: {resolved_edit_policy}")
        resolved_edit_policy = raw_edit_policy
    else:
        resolved_edit_policy = DEFAULT_EDIT_POLICY

    now = format_word_local_timestamp(get_local_now())
    contract_key = contract_key or _normalize_lookup_key(contract_name or resolved_client_name)
    stored_client_name = (
        resolved_client_name if resolved_client_name != "未提及/待补充" else ""
    )
    client_key = _normalize_lookup_key(stored_client_name)
    if contract_key:
        contracts[contract_key] = {
            "contract_name": contract_name,
            "client_name": stored_client_name,
            "party_role": resolved_party_role,
            "review_intensity": resolved_review_intensity,
            "edit_policy": resolved_edit_policy,
            "source_filename": Path(input_docx).name if input_docx else "",
            "last_reviewed_at": now,
        }
    if client_key:
        clients[client_key] = {
            "client_name": stored_client_name,
            "preferred_party_role": resolved_party_role,
            "preferred_review_intensity": resolved_review_intensity,
            "last_contract_name": contract_name,
            "updated_at": now,
        }
    save_review_memory(memory)

    return {
        "contract_name": contract_name,
        "client_name": resolved_client_name,
        "party_role": resolved_party_role,
        "review_intensity": resolved_review_intensity,
        "edit_policy": resolved_edit_policy,
        "memory_contract_hit": bool(contract_record),
        "memory_client_hit": bool(client_record),
    }


def resolve_reviewer_profile(
    author: str | None,
    initials: str | None,
    organization: str | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    profile_exists = PROFILE_PATH.exists()
    profile = load_profile() if profile_exists else load_profile_template()
    profile_confirmed = bool(profile.get("confirmed"))
    resolved_author = str(author or profile.get("author") or "").strip()
    resolved_organization = str(organization or profile.get("organization") or "").strip()
    resolved_department = str(department or profile.get("department") or "").strip()
    explicit_identity_provided = author is not None or organization is not None
    prompted_for_profile = False

    if not resolved_author or not resolved_organization:
        if _should_prompt_for_profile():
            _print_profile_notice()
            if not resolved_author:
                resolved_author = _prompt_required_field("首次使用，请输入审查人姓名：")
            if not resolved_organization:
                resolved_organization = _prompt_required_field(
                    "请输入律所名称或公司名称："
                )
            if not resolved_department:
                resolved_department = _prompt_optional_field(
                    "请输入部门名称（可留空）："
                )
            prompted_for_profile = True
        else:
            raise ValueError(
                "未检测到完整的审查人配置。请先填写 "
                f"{PROFILE_PATH}，至少提供 author 和 organization，"
                "或在执行时显式传入 --author 与 --organization。"
            )
    elif _should_prompt_for_profile() and not profile_confirmed and not explicit_identity_provided:
        _print_profile_confirmation_notice()
        resolved_author = _prompt_required_field_with_default(
            "请确认审查人姓名", resolved_author
        )
        resolved_organization = _prompt_required_field_with_default(
            "请确认律所名称或公司名称", resolved_organization
        )
        if department is None:
            resolved_department = _prompt_optional_field_with_default(
                "请确认部门名称（可留空）", resolved_department
            )
        prompted_for_profile = True

    if initials is not None:
        resolved_initials = str(initials).strip()
    else:
        resolved_initials = str(profile.get("initials") or "").strip()

    profile["author"] = resolved_author
    profile["initials"] = resolved_initials
    profile["organization"] = resolved_organization
    profile["department"] = resolved_department
    profile["confirmed"] = bool(
        profile_confirmed or prompted_for_profile or explicit_identity_provided
    )
    save_profile(profile)
    if not profile_exists:
        print(f"已保存审查人配置：{PROFILE_PATH}", file=sys.stderr)
    return load_profile()


def build_comment_author_display(profile: dict[str, Any]) -> str:
    author = str(profile.get("author") or "").strip()
    organization = str(profile.get("organization") or "").strip()
    if author and organization:
        return f"{author}｜{organization}"
    return author or organization


class ReviewTimeline:
    def __init__(
        self,
        *,
        gap_min_minutes: int = DEFAULT_TIME_GAP_MINUTES,
        gap_max_minutes: int = DEFAULT_TIME_GAP_MAX_MINUTES,
        intra_action_gap_min_minutes: int = DEFAULT_INTRA_ACTION_GAP_MINUTES,
        intra_action_gap_max_minutes: int = DEFAULT_INTRA_ACTION_GAP_MAX_MINUTES,
        start_at: datetime | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.gap_min_minutes = max(1, int(gap_min_minutes))
        self.gap_max_minutes = max(self.gap_min_minutes, int(gap_max_minutes))
        self.intra_action_gap_min_minutes = max(1, int(intra_action_gap_min_minutes))
        self.intra_action_gap_max_minutes = max(
            self.intra_action_gap_min_minutes,
            int(intra_action_gap_max_minutes),
        )
        self.start_at = start_at
        self.random = rng or random.Random()
        self._next_finding_start: datetime | None = None
        self._active_finding_start: datetime | None = None
        self._active_last_emitted: datetime | None = None

    def _draw_intra_action_gap(self) -> int:
        return self.random.randint(
            self.intra_action_gap_min_minutes,
            self.intra_action_gap_max_minutes,
        )

    def _draw_finding_gap(self) -> int:
        return self.random.randint(self.gap_min_minutes, self.gap_max_minutes)

    def _resolve_start_time(self) -> datetime:
        if self.start_at is not None:
            if self.start_at.tzinfo is None:
                resolved = self.start_at.replace(tzinfo=get_local_timezone())
            else:
                resolved = self.start_at.astimezone(get_local_timezone())
            return self._normalize_timestamp_floor(resolved)

        resolved = get_local_now() + timedelta(
            minutes=self.random.randint(
                DEFAULT_START_DELAY_MINUTES,
                DEFAULT_START_DELAY_MAX_MINUTES,
            )
        )
        return self._normalize_timestamp_floor(resolved)

    @staticmethod
    def _normalize_timestamp_floor(value: datetime) -> datetime:
        if value.microsecond == 0:
            return value
        return (value + timedelta(seconds=1)).replace(microsecond=0)

    def start_finding(self):
        finding_start = self._next_finding_start or self._resolve_start_time()
        finding_start = self._normalize_timestamp_floor(finding_start)
        self._active_finding_start = finding_start
        self._active_last_emitted = None
        current = finding_start

        def provider():
            nonlocal current
            emitted = current
            self._active_last_emitted = emitted
            current = current + timedelta(minutes=self._draw_intra_action_gap())
            return emitted

        return provider

    def complete_finding(self) -> None:
        base = self._active_last_emitted or self._active_finding_start or self._resolve_start_time()
        self._next_finding_start = self._normalize_timestamp_floor(
            base + timedelta(minutes=self._draw_finding_gap())
        )
        self._active_finding_start = None
        self._active_last_emitted = None

    def build(self, count: int) -> list[str]:
        if count <= 0:
            return []
        timestamps = []
        for _ in range(count):
            provider = self.start_finding()
            timestamps.append(format_word_local_timestamp(provider()))
            self.complete_finding()
        return timestamps
