#!/usr/bin/env python3
"""盲评探针准备器：把当前派发转成只含该角色可见内容的冷启动输入。

只调用既有 clerk.py packet，不再次 dispatch、不 commit、不修改 run。
本工具不加载、不拷贝、不引用复核答案资产；正文只含该角色可读内容。
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

CLERK = Path(__file__).resolve().parent / "clerk.py"
PROBE_SCHEMA_VERSION = 1
PROBE_KIND = "moot-court.blind-probe.packet.v1"

# 严格白名单：只透传 clerk packet 的这些键，其余字段一律丢弃。
PACKET_KEYS = ("instruction", "assignment", "documents", "history", "submission_template")
SUBMISSION_KEYS = {"schema_version", "run_id", "turn_id", "role", "material_version",
                   "read_through", "responds_to", "body", "citations"}

# fail-closed 自检：上游若把复核答案或运行内部路径混进角色输入，宁可报错也不产出。
# 刻意不含任何具体材料编号：编号随案件变化，硬编码会把某个案件的答案写死进通用工具。
FORBIDDEN_MARKERS = ("manifest.json", "semantic-probe-reviewer", "reviewer.json",
                     "expected_answer", "参考答案", "评分步骤",
                     "/events", "\\events")


class ProbeError(Exception):
    pass


def fail(message):
    print(f"prepare_probe: {message}", file=sys.stderr)
    raise SystemExit(2)


def read_packet(run):
    """实际调用书记员 CLI 取得当前派发，而不是复制它的内部实现。"""
    if not CLERK.is_file():
        raise ProbeError("未找到 clerk.py；请在技能 scripts 目录内运行本工具")
    if not run.exists() or not run.is_dir():
        raise ProbeError("庭审目录不存在；请确认 --run 指向已 init 的运行目录")
    try:
        finished = subprocess.run(
            [sys.executable, "-B", str(CLERK), "--run", str(run), "packet"],
            capture_output=True, text=True, timeout=60, check=False)
    except subprocess.TimeoutExpired as exc:
        # 60 秒到点属于运行故障，不是角色或材料问题；转成可读中文，不让 Traceback 泄漏到宿主。
        raise ProbeError(
            "书记员 CLI 超过 60 秒未返回，已中止；请确认运行目录可读、无并发占用后重试") from exc
    except OSError as exc:
        raise ProbeError(f"无法执行书记员 CLI：{type(exc).__name__}") from exc
    if finished.returncode != 0:
        detail = (finished.stderr or finished.stdout or "").strip().splitlines()
        raise ProbeError("书记员未返回可用 packet：" +
                         (detail[-1] if detail else f"exit {finished.returncode}"))
    try:
        packet = json.loads(finished.stdout)
    except ValueError as exc:
        raise ProbeError("书记员输出不是完整 JSON") from exc
    if not isinstance(packet, dict) or not all(key in packet for key in PACKET_KEYS):
        raise ProbeError("书记员 packet 缺少必要字段；请检查 clerk.py 协议")
    return {key: packet[key] for key in PACKET_KEYS}


def validate(packet):
    assignment = packet["assignment"]
    if not isinstance(assignment, dict):
        raise ProbeError("packet.assignment 结构异常")
    for key in ("run_id", "turn_id", "role", "material_version", "read_through"):
        if key not in assignment:
            raise ProbeError(f"派发缺少字段：{key}")
    template = packet["submission_template"]
    if not isinstance(template, dict) or set(template) != SUBMISSION_KEYS:
        raise ProbeError("提交模板字段不完整；不能凭猜测生成提交结构")
    if template["role"] != assignment["role"] or template["turn_id"] != assignment["turn_id"]:
        raise ProbeError("提交模板与当前派发不匹配；请重新取 packet")
    for key in ("documents", "history"):
        if not isinstance(packet[key], list):
            raise ProbeError(f"packet.{key} 结构异常")
    private = [doc for doc in packet["documents"] if doc.get("visible_to") != ["all"]]
    if not all(doc.get("visible_to") == [assignment["role"]] for doc in private):
        raise ProbeError("packet 含非本角色的私有材料；拒绝产出")
    blob = json.dumps(packet, ensure_ascii=False)
    for marker in FORBIDDEN_MARKERS:
        if marker in blob:
            raise ProbeError(f"packet 命中禁止内容标记（{marker}）；拒绝产出，请人工复核材料与派发文本")


def role_task(assignment):
    """通用角色任务文本：不针对任何案件，不含结论、标靶或评分信息。"""
    return [
        "通用角色任务（不含任何标准答案或评分信息）：",
        f"1. 你本轮只担任 assignment.role，任务范围以 assignment.issue、assignment.stage、"
        "assignment.prompt 为准。",
        "2. 可读材料仅限本文件 documents 已列条目；其中包含只对你可见的本方私有材料，"
        "可正常阅读和用于本方论证；不臆造未提供的材料或对方主张。",
        "3. 只依据 documents 与 history 推理；history 是已入卷的公开发言，不是本轮答案。",
        "4. 分开陈述已提供的事实、你的主张与假设；证据不足时直接说明不足。",
        "5. 正文可以引用你本轮可见的任何材料编号（含本方私有材料），但须标明其为本方私有准备；"
        "提交字段 citations 由书记员机械校验，只接受 documents 中 visible_to 为 [all] 的编号，"
        "填入本方私有编号会被拒绝入卷。",
        "5b. 他方私有材料未出现在本文件，不得引用、复述或推测其内容。",
        "6. 严格按 submission_template 的字段提交；除 body 外不要新增或删除字段，"
        "schema_version、run_id、turn_id、role、material_version、read_through、responds_to 原样保留。",
        "7. 本文件已含你本轮全部输入；不要去寻找本运行的清单、事件流或其他角色文件。",
    ]


def build(packet):
    assignment = packet["assignment"]
    return {
        "schema_version": PROBE_SCHEMA_VERSION,
        "probe_kind": PROBE_KIND,
        "role": assignment["role"],
        "turn_id": assignment["turn_id"],
        "record_through": assignment["read_through"],
        "input_policy": "本文件是本轮角色的唯一输入；不提供预期结论、评分标准或他方私有材料。",
        "instruction": packet["instruction"],
        "assignment": assignment,
        "role_task": role_task(assignment),
        "documents": packet["documents"],
        "history": packet["history"],
        "submission_template": packet["submission_template"],
    }


def write_once(path, payload):
    """以 O_EXCL 独占创建：目标已存在则拒绝，绝不覆盖、绝不删除原有文件。

    清理只针对本次调用自己创建的文件（os.open 成功即证明此前不存在）。
    写入或 fsync 失败时删除该半成品，避免留下被误当成完整输入的残缺文件；
    但不承诺"要么完整发布、要么目录完全不变"：创建与写入之间存在窗口，
    崩溃仍可能留下已清理前的残留，需人工确认。
    """
    if path.exists() or path.is_symlink():
        raise ProbeError("输出文件已存在；拒绝覆盖，请换一个 --output 路径")
    if not path.parent.is_dir():
        raise ProbeError("输出目录不存在；请先创建目录或改用已存在的路径")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    handle = None
    created = False
    completed = False
    try:
        handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        created = True
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            handle = None
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        completed = True
    except FileExistsError as exc:
        raise ProbeError("输出文件已存在；拒绝覆盖，请换一个 --output 路径") from exc
    except OSError as exc:
        raise ProbeError(f"无法写入输出：{type(exc).__name__}") from exc
    finally:
        if handle is not None:
            os.close(handle)
        # created 为真只可能是本次 os.open 独占成功，故删除不会碰到调用方原有文件；
        # 只在未写完时清理半成品，成功写完则保留。
        if created and not completed:
            try:
                path.unlink()
            except OSError:
                pass
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True,
                        help="已 init 且当前有待交稿派发的庭审目录；接受绝对路径或相对路径")
    parser.add_argument("--output", required=True,
                        help="本轮角色冷启动输入的写出路径（绝对或相对皆可）；已存在则拒绝")
    args = parser.parse_args(argv)
    try:
        # 不强制绝对路径：.expanduser() 相对路径按调用方 cwd 解析，与 clerk.py 行为一致。
        run = Path(args.run).expanduser()
        output = Path(args.output).expanduser()
        packet = read_packet(run)
        validate(packet)
        write_once(output, build(packet))
    except ProbeError as exc:
        fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
