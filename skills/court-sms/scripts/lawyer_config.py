#!/usr/bin/env python3
"""Manage private lawyer profiles. Secrets are read from stdin or a hidden prompt."""
import argparse
import getpass
import json
import os
import re
import sys
import tempfile
from pathlib import Path


DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "lawyers.json"


class ProfileError(ValueError):
    pass


def load_profiles(path=DEFAULT_PATH):
    path = Path(path)
    if not path.exists():
        return {"schema_version": 1, "lawyers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        raise ProfileError("invalid_private_config") from error
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("lawyers"), dict):
        raise ProfileError("invalid_private_config")
    for key, profile in data["lawyers"].items():
        if not isinstance(key, str) or not isinstance(profile, dict) or not isinstance(profile.get("name"), str):
            raise ProfileError("invalid_private_config")
    return data


def normalize_mobile(value):
    if not isinstance(value, str):
        raise ProfileError("invalid_mobile")
    value = re.sub(r"[\s()-]", "", value)
    if value.startswith("+86"):
        value = value[3:]
    if not re.fullmatch(r"1[0-9]{10}", value):
        raise ProfileError("invalid_mobile")
    return value


def normalize_mobile_last4(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}", value):
        raise ProfileError("invalid_mobile_last4")
    return value


def validate_mobile_fields(profile):
    mobile = profile.get("mobile")
    tail = profile.get("mobile_last4")
    if mobile is not None:
        mobile = normalize_mobile(mobile)
    if tail is not None:
        tail = normalize_mobile_last4(tail)
    if mobile and tail and mobile[-4:] != tail:
        raise ProfileError("mobile_tail_conflict")
    return mobile, tail


def select_identity(path=DEFAULT_PATH, lawyer_id=None, method="sjhm"):
    profiles = load_profiles(path)["lawyers"]
    if lawyer_id is None:
        if not profiles:
            raise ProfileError("missing_lawyer_profile")
        raise ProfileError("lawyer_selection_required")
    if lawyer_id not in profiles:
        raise ProfileError("unknown_lawyer_id")
    profile = profiles[lawyer_id]
    if method == "sjhm":
        mobile, mobile_tail = validate_mobile_fields(profile)
        if mobile:
            tail = mobile[-4:]
        elif mobile_tail:
            tail = mobile_tail
        else:
            raise ProfileError("missing_mobile")
    elif method == "zjhm":
        tail = profile.get("id_last4")
        if not isinstance(tail, str) or not re.fullmatch(r"[0-9a-zA-Z]{4}", tail):
            raise ProfileError("missing_or_invalid_id_last4")
    else:
        raise ProfileError("unsupported_identity_method")
    return lawyer_id, tail


def save_profile(path, lawyer_id, name, updates):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", lawyer_id) or not name.strip():
        raise ProfileError("invalid_lawyer_id_or_name")
    if not isinstance(updates, dict) or set(updates) - {"mobile", "mobile_last4", "id_last4", "delivery_recipient", "note"}:
        raise ProfileError("invalid_profile_fields")
    # An explicit null clears nothing: keep the stored value.
    cleaned = {key: value for key, value in updates.items() if value is not None}
    if "mobile" in cleaned and cleaned["mobile"] is not None:
        cleaned["mobile"] = normalize_mobile(cleaned["mobile"])
    if "mobile_last4" in cleaned and cleaned["mobile_last4"] is not None:
        cleaned["mobile_last4"] = normalize_mobile_last4(cleaned["mobile_last4"])
    if "id_last4" in cleaned and cleaned["id_last4"] is not None:
        value = cleaned["id_last4"]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-zA-Z]{4}", value):
            raise ProfileError("invalid_id_last4")
    if "delivery_recipient" in cleaned and not isinstance(cleaned["delivery_recipient"], bool):
        raise ProfileError("invalid_delivery_recipient_flag")
    if "note" in cleaned and cleaned["note"] is not None and not isinstance(cleaned["note"], str):
        raise ProfileError("invalid_note")
    path = Path(path)
    if path.is_symlink():
        raise ProfileError("config_symlink_not_supported")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ProfileError("config_busy") from error
    os.close(descriptor)
    temporary = None
    try:
        data = load_profiles(path)
        profile = data["lawyers"].get(lawyer_id, {})
        profile.update({"name": name.strip(), **cleaned})
        validate_mobile_fields(profile)
        if not profile.get("mobile") and not profile.get("mobile_last4") and not profile.get("id_last4"):
            raise ProfileError("missing_identity_data")
        data["lawyers"][lawyer_id] = profile
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".lawyers-", suffix=".json", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
        return {"status": "saved", "lawyer_id": lawyer_id,
                "has_mobile": bool(profile.get("mobile")),
                "has_mobile_last4": bool(profile.get("mobile_last4")),
                "has_id_last4": bool(profile.get("id_last4"))}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_PATH)
    sub = parser.add_subparsers(dest="action", required=True)
    setter = sub.add_parser("set")
    setter.add_argument("--lawyer-id", required=True)
    setter.add_argument("--name", required=True)
    setter.add_argument("--stdin", action="store_true", help="read a JSON object with mobile/mobile_last4/id_last4 from stdin")
    tail_setter = sub.add_parser("set-tail")
    tail_setter.add_argument("--lawyer-id", required=True)
    tail_setter.add_argument("--name", required=True)
    tail_setter.add_argument("--stdin", action="store_true", help='read {"mobile_last4":"xxxx"} from stdin')
    getter = sub.add_parser("get")
    getter.add_argument("--lawyer-id")
    getter.add_argument("--method", choices=("sjhm", "zjhm"), default="sjhm")
    getter.add_argument("--reveal", action="store_true", help="print the last four digits; off by default")
    sub.add_parser("list")
    marker = sub.add_parser("mark")
    marker.add_argument("--lawyer-id", required=True)
    marker.add_argument("--delivery-recipient", choices=("true", "false"), required=True)
    args = parser.parse_args()
    try:
        if args.action == "set":
            updates = json.load(sys.stdin) if args.stdin else {"mobile": getpass.getpass("律师手机号（仅存本机）: ")}
            result = save_profile(args.config, args.lawyer_id, args.name, updates)
        elif args.action == "set-tail":
            updates = (json.load(sys.stdin) if args.stdin else
                       {"mobile_last4": getpass.getpass("受送达人手机号后四位（仅存本机）: ")})
            if not isinstance(updates, dict) or set(updates) != {"mobile_last4"}:
                raise ProfileError("expected_mobile_last4_only")
            normalize_mobile_last4(updates["mobile_last4"])
            result = save_profile(args.config, args.lawyer_id, args.name, updates)
        elif args.action == "get":
            lawyer_id, tail = select_identity(args.config, args.lawyer_id, args.method)
            result = {"lawyer_id": lawyer_id, "method": args.method}
            if args.reveal:
                result["last4"] = tail
            else:
                result["last4_available"] = True
        elif args.action == "mark":
            profiles = load_profiles(args.config)["lawyers"]
            if args.lawyer_id not in profiles:
                raise ProfileError("unknown_lawyer_id")
            result = save_profile(
                args.config, args.lawyer_id, profiles[args.lawyer_id]["name"],
                {"delivery_recipient": args.delivery_recipient == "true"},
            )
        else:
            result = {"lawyers": [
                {"lawyer_id": key, "name": value["name"],
                 "has_mobile": bool(value.get("mobile")),
                 "has_mobile_last4": bool(value.get("mobile_last4")),
                 "has_id_last4": bool(value.get("id_last4"))}
                for key, value in load_profiles(args.config)["lawyers"].items()
            ]}
    except (ProfileError, OSError, ValueError) as error:
        reason = str(error) if isinstance(error, ProfileError) else "profile_operation_failed"
        print(json.dumps({"status": "error", "reason": reason}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
