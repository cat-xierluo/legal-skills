#!/usr/bin/env python3
"""Git bundle 完整交接回归 —— "PM 实际收件"消费者测试。

场景：远端 GUI 任务无法 push，交付方用 zcode-gui-artifacts 真实 CLI
（pack / emit-chunk / unpack）把三件套 delivery.bundle（Git bundle）、
delivery.json、pr-body.md 打包传输；PM 作为消费者只凭 emit-chunk 的
有界 chunk 行重建文件，验证 raw offset/length/chunkSHA/fullSHA 合同，
然后 git bundle verify 并从 bundle 导入全新仓库，断言 immutable head
与文件内容等于源提交。

本测试不实现打包器，只消费其公开合同（references/zcode-gui-artifacts.md）：
- chunk 载荷 1000 字节；index 从 0 连续；offset == index * chunk_size；
  非末尾 chunk 长度恒为 1000；emit-chunk 输出固定键
  {schema, bundle_sha256, file, index, offset, length, base64}；
- unpack 全部验证通过才写盘，任一步失败零落盘，目标已存在从不覆盖；
- 退出码：0 成功；1 拒绝/校验失败；2 用法错误。

覆盖（含负控）：
  T01 完整交接正路（pack -> emit-chunk 逐条 -> 消费侧明示按 offset 重排
      重建 -> fullSHA 校验 -> git bundle verify -> clone 导入 -> head/
      内容等于源提交 -> unpack 三件套落盘与源字节一致）
  T02 bundle 文件截断 -> unpack 拒绝且零落盘
  T03 改一字节（base64 合法、解码长度不变、仅 SHA 失配）-> 拒绝零落盘
  T04 bundle 内 chunk 数组乱序 -> 拒绝（index 必须与数组位置一致）
  T05 bundle 内重复 chunk -> 拒绝
  T06 传输丢尾行 -> 消费侧重装层拒绝，不误报完整
  T07 目标已存在 -> 拒绝且哨兵文件不被覆盖
  T08 坏包（manifest sha256 被篡改）-> 拒绝且不留半交付

依赖（环境变量接入，不 mock）：
  ZCODE_GUI_ARTIFACTS           必填，指向真实 zcode-gui-artifacts.py。
                                未设置 -> 清晰 SKIP，exit 77。
                                设置但路径无效 -> 硬失败非零，不降级为 SKIP。
  ZCODE_GUI_ARTIFACTS_EXPECT_SHA256
                                可选，设置时校验 CLI 文件 SHA256 指纹，
                                不匹配 -> 硬失败非零。
  git                           必须在 PATH；缺失 -> 清晰 SKIP，exit 77。

用法：
  ZCODE_GUI_ARTIFACTS=/path/to/zcode-gui-artifacts.py \
    python3 skills/multi-agent-orchestration/scripts/test-zcode-gui-artifacts-consumer.py

仅用标准库；所有临时目录自建并在 finally 中清理；输出为有界单行日志，
末尾打印一行 JSON 摘要。任何用例失败 -> exit 1。
"""

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

CHUNK_SIZE = 1000
EMIT_KEYS = {"schema", "bundle_sha256", "file", "index", "offset",
             "length", "base64"}
SKIP_EXIT = 77
CLI_TIMEOUT = 120
GIT_TIMEOUT = 120

# 交付物三件套的固定相对路径（与真实交接合同一致）。
ARTIFACT_PATHS = ["delivery.bundle", "delivery.json", "pr-body.md"]

# 合成身份：仅通过单次环境变量传入子进程，绝不写入 git config。
COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "ZGUI Handoff Smoke",
    "GIT_AUTHOR_EMAIL": "zgui-handoff-smoke@example.invalid",
    "GIT_COMMITTER_NAME": "ZGUI Handoff Smoke",
    "GIT_COMMITTER_EMAIL": "zgui-handoff-smoke@example.invalid",
}

_results = []


def log(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def record(name, ok, detail=""):
    _results.append({"case": name, "ok": bool(ok), "detail": detail[:300]})
    log("[%s] %s%s" % ("ok" if ok else "FAIL", name,
                       (" :: " + detail[:300]) if detail else ""))
    return ok


class TestFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise TestFailure(message)


def bounded(text, limit=400):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def run_cli(cli_path, argv, timeout=CLI_TIMEOUT):
    """运行真实 artifacts CLI，返回 (returncode, stdout, stderr)。"""
    proc = subprocess.run(
        [sys.executable, cli_path] + argv,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def cli_stdout_json(name, cli_path, argv, expect_rc=0):
    """运行 CLI 并校验返回码与 stdout 单行 JSON；返回解析后的对象。"""
    rc, out, err = run_cli(cli_path, argv)
    require(rc == expect_rc,
            "%s: expected exit %d, got %d :: stderr=%s"
            % (name, expect_rc, rc, bounded(err)))
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    require(len(lines) == 1,
            "%s: expected exactly 1 stdout JSON line, got %d :: out=%s"
            % (name, len(lines), bounded(out)))
    try:
        return json.loads(lines[0])
    except ValueError as exc:
        raise TestFailure("%s: stdout is not valid JSON (%s) :: %s"
                          % (name, exc, bounded(lines[0])))


def expect_rejection(name, cli_path, argv, target_dir):
    """负控断言：CLI 以退出码 1 明示拒绝（非崩溃），且零落盘。

    区分预期拒绝（exit 1）与意外失败（其他退出码/信号 -> 测试失败）。
    """
    rc, out, err = run_cli(cli_path, argv)
    if rc == 0:
        raise TestFailure("%s: expected rejection but CLI reported success"
                          % name)
    require(rc == 1,
            "%s: expected clean rejection exit 1, got %d (crash/other) "
            ":: stderr=%s" % (name, rc, bounded(err)))
    require(not os.path.lexists(target_dir),
            "%s: half-delivery left on disk at %s" % (name, target_dir))
    return err


def write_file(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def load_manifest(bundle_path):
    """消费侧解析 manifest；用 object_pairs_hook 检测重复键（合同拒绝）。"""
    def no_dupes(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError("duplicate JSON key: %r" % key)
            seen[key] = value
        return seen
    raw = read_bytes(bundle_path)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=no_dupes), \
        sha256_hex(raw)


def collect_emit_chunks(cli_path, bundle_path, rel_path):
    """PM 收件侧：仅凭 emit-chunk 输出的有界行收集某文件的全部 chunk。

    模拟真实终端传输：行以乱序到达（故意 shuffle 收集顺序），
    重排是消费侧的明示合同（按 offset 排序 + index 连续性核验）。
    """
    manifest, bundle_sha = load_manifest(bundle_path)
    entry = next(f for f in manifest["files"] if f["path"] == rel_path)
    expected_count = len(entry["chunks"])
    received = []
    for index in range(expected_count):
        emit = cli_stdout_json(
            "emit-chunk/%s#%d" % (rel_path, index), cli_path,
            ["emit-chunk", "--bundle", bundle_path,
             "--file", rel_path, "--chunk", str(index)])
        require(set(emit.keys()) == EMIT_KEYS,
                "emit-chunk keys must be exactly %s, got %s"
                % (sorted(EMIT_KEYS), sorted(emit.keys())))
        require(emit["schema"] == manifest["schema"],
                "emit schema mismatch: %r" % emit["schema"])
        require(emit["bundle_sha256"] == bundle_sha,
                "emit bundle_sha256 mismatch for %s#%d (wrong-source "
                "chunk must be detectable)" % (rel_path, index))
        require(emit["file"] == rel_path and emit["index"] == index,
                "emit file/index mismatch: %r/%r"
                % (emit["file"], emit["index"]))
        received.append(emit)
    # 乱序到达 -> 消费侧明示重排：按 offset 排序后核验连续性。
    arrived = list(reversed(received))
    arrived.sort(key=lambda c: c["offset"])
    for position, chunk in enumerate(arrived):
        require(chunk["index"] == position,
                "reassembly contract: index must be contiguous from 0 "
                "after offset sort (position %d got index %r)"
                % (position, chunk["index"]))
        require(chunk["offset"] == position * CHUNK_SIZE,
                "reassembly contract: offset must be index*%d "
                "(got %r at position %d)" % (CHUNK_SIZE, chunk["offset"],
                                             position))
    return arrived, entry, bundle_sha


def reassemble(chunks, entry, rel_path):
    """从 emit 行重建字节并核对 raw 合同 + fullSHA；返回重建字节。

    仅信任 emit 行字段（模拟收件方看不到原始 manifest 的极端通道），
    size/sha256 期望值由调用方提供的 entry 承担。
    """
    size = entry["size"]
    expected_count = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
    require(len(chunks) == expected_count,
            "%s: reassembly got %d chunks, expected %d (missing/truncated "
            "transfer must be detected)" % (rel_path, len(chunks),
                                            expected_count))
    blob = bytearray()
    for position, chunk in enumerate(chunks):
        require(chunk["length"] == (CHUNK_SIZE if position < expected_count - 1
                                    else size - position * CHUNK_SIZE),
                "%s#%d: length %r violates boundary rule"
                % (rel_path, position, chunk["length"]))
        raw = base64.b64decode(chunk["base64"].encode("ascii"), validate=True)
        require(len(raw) == chunk["length"],
                "%s#%d: decoded %d bytes != declared length %d"
                % (rel_path, position, len(raw), chunk["length"]))
        blob += raw
    require(len(blob) == size,
            "%s: reassembled %d bytes != declared size %d"
            % (rel_path, len(blob), size))
    require(sha256_hex(bytes(blob)) == entry["sha256"],
            "%s: reassembled fullSHA mismatch" % rel_path)
    return bytes(blob)


def make_source_repo(repo_dir, text):
    """最小 Git 源仓库：合成文本 commit（身份走单次环境变量）。

    文本必须是高熵内容：极小 repo 的 git bundle 仅数百字节，
    无法跨越 chunk 边界，会让 chunking 合同测试失真。
    """
    def git(*argv, **kwargs):
        proc = subprocess.run(
            ["git"] + list(argv), cwd=repo_dir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=GIT_TIMEOUT, **kwargs)
        require(proc.returncode == 0,
                "git %s failed (%d) :: %s"
                % (" ".join(argv[:2]), proc.returncode,
                   bounded(proc.stderr.decode("utf-8", "replace"))))
        return proc.stdout.decode("utf-8", "replace")

    git("init", "--initial-branch=main", "-q", ".")
    write_file(os.path.join(repo_dir, "handoff-note.md"),
               text.encode("utf-8"))
    git("add", "handoff-note.md")
    env = dict(os.environ)
    env.update(COMMIT_ENV)
    proc = subprocess.run(
        ["git", "commit", "-q", "-m",
         "synthetic handoff commit for consumer smoke test"],
        cwd=repo_dir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=GIT_TIMEOUT)
    require(proc.returncode == 0,
            "git commit failed (%d) :: %s"
            % (proc.returncode,
               bounded(proc.stderr.decode("utf-8", "replace"))))
    head = git("rev-parse", "HEAD").strip()
    bundle_path = os.path.join(repo_dir, "handoff.bundle")
    git("bundle", "create", bundle_path, "--all")
    require(os.path.isfile(bundle_path) and os.path.getsize(bundle_path) > 0,
            "git bundle create produced no output")
    return head, read_bytes(bundle_path)


def flip_one_bit(data):
    """翻转中部一个 bit，构造 base64 合法、长度不变、内容损坏的字节。"""
    mutable = bytearray(data)
    position = len(mutable) // 2
    mutable[position] ^= 0x01
    return bytes(mutable)


def rebuild_manifest(manifest, mutate):
    """深拷贝 manifest，应用 mutate(manifest)，序列化为 bundle 字节。

    仅使用 reference 中公开的固定合同字段，不依赖实现内部。
    """
    import copy
    mutated = copy.deepcopy(manifest)
    mutate(mutated)
    raw = (json.dumps(mutated, ensure_ascii=True, sort_keys=True,
                      indent=2) + "\n").encode("utf-8")
    return raw


# ---------------------------------------------------------------- scenarios

def deterministic_entropy_text(total_chars):
    """固定 seed 的高熵 hex 文本：确保 git bundle 压缩后仍 > 1000 字节，
    真实跨越多个 chunk（压缩后不足 1000 字节会让 chunking 测试失真）。"""
    import random
    rng = random.Random(0x67684953)  # 'ghIS'
    pieces = []
    produced = 0
    while produced < total_chars:
        piece = "%032x" % rng.getrandbits(128)
        pieces.append(piece)
        produced += len(piece) + 1
    lines = []
    for start in range(0, len(pieces), 8):
        lines.append(" ".join(pieces[start:start + 8]))
    text = "handoff smoke entropy payload\n" + "\n".join(lines) + "\n"
    return text


def build_transfer_fixture(cli_path, work):
    """独立构建传输 fixture：合成 repo -> 真实 git bundle -> 三件套 ->
    真实 CLI pack。T01..T08 全部消费该 fixture。"""
    src_repo = os.path.join(work, "src-repo")
    os.makedirs(src_repo)
    text = deterministic_entropy_text(4096)
    head, git_bundle_bytes = make_source_repo(src_repo, text)
    require(len(git_bundle_bytes) > CHUNK_SIZE,
            "git bundle too small to exercise chunking (%d bytes); "
            "fixture entropy insufficient" % len(git_bundle_bytes))

    payload_root = os.path.join(work, "payload-root")
    os.makedirs(payload_root)
    write_file(os.path.join(payload_root, "delivery.bundle"),
               git_bundle_bytes)
    delivery_json = json.dumps({
        "task": "TASK-2026-10-03-ZGUI-HANDOFF-SMOKE",
        "head": head,
        "base": "0" * 40,
        "paths": ARTIFACT_PATHS,
        "note": "synthetic minimal delivery manifest fixture",
    }, indent=2).encode("utf-8") + b"\n"
    write_file(os.path.join(payload_root, "delivery.json"), delivery_json)
    pr_body = ("# handoff smoke PR body\n\nsynthetic content only.\n"
               "- immutable head: %s\n" % head).encode("utf-8")
    write_file(os.path.join(payload_root, "pr-body.md"), pr_body)

    transfer_dir = os.path.join(work, "transfer")
    os.makedirs(transfer_dir)
    artifacts_bundle = os.path.join(transfer_dir, "delivery.bundle")
    summary = cli_stdout_json(
        "fixture/pack", cli_path,
        ["pack", "--source", payload_root,
         "--task", "TASK-2026-10-03-ZGUI-HANDOFF-SMOKE",
         "--session", "smoke-session", "--branch",
         "test/zcode-gui-handoff-smoke",
         "--base", "0" * 40, "--head", head,
         "--output", artifacts_bundle] + ARTIFACT_PATHS)
    require(summary.get("files") == len(ARTIFACT_PATHS),
            "pack summary files=%r, expected %d"
            % (summary.get("files"), len(ARTIFACT_PATHS)))
    require(summary.get("bundle_sha256") == sha256_hex(
        read_bytes(artifacts_bundle)),
        "pack bundle_sha256 does not match on-disk bundle")
    return {
        "head": head,
        "text": text,
        "git_bundle_bytes": git_bundle_bytes,
        "payload_root": payload_root,
        "artifacts_bundle": artifacts_bundle,
        "pack_summary": summary,
    }


def scenario_full_handoff(cli_path, work, fixture):
    """T01 完整交接正路：emit-chunk 消费侧明示重排重建 -> fullSHA 校验
    -> git bundle verify -> clone 导入 -> unpack 落盘逐一比对。"""
    head = fixture["head"]
    git_bundle_bytes = fixture["git_bundle_bytes"]
    text = fixture["text"]
    artifacts_bundle = fixture["artifacts_bundle"]

    # PM 收件：仅凭 emit-chunk 行重建三件套（乱序到达 -> 明示重排）。
    reassembled = {}
    for rel in ARTIFACT_PATHS:
        chunks, entry, bundle_sha = collect_emit_chunks(
            cli_path, artifacts_bundle, rel)
        reassembled[rel] = reassemble(chunks, entry, rel)
        require(bundle_sha == fixture["pack_summary"]["bundle_sha256"],
                "%s: bundle_sha changed mid-transfer" % rel)

    require(reassembled["delivery.bundle"] == git_bundle_bytes,
            "T01: reassembled git bundle != source bytes")
    require(reassembled["delivery.json"] == read_bytes(
        os.path.join(fixture["payload_root"], "delivery.json")),
        "T01: reassembled delivery.json != source bytes")
    require(reassembled["pr-body.md"] == read_bytes(
        os.path.join(fixture["payload_root"], "pr-body.md")),
        "T01: reassembled pr-body.md != source bytes")

    # Git 真实消费 1：bundle verify（需在仓库上下文执行）。
    consumer_repo = os.path.join(work, "verify-repo")
    subprocess.run(["git", "init", "-q", consumer_repo],
                   check=True, timeout=GIT_TIMEOUT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    verify_src = os.path.join(work, "verify-src.bundle")
    write_file(verify_src, reassembled["delivery.bundle"])
    proc = subprocess.run(
        ["git", "-C", consumer_repo, "bundle", "verify", verify_src],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=GIT_TIMEOUT)
    require(proc.returncode == 0,
            "T01: git bundle verify rejected reassembled bundle (%d) :: %s"
            % (proc.returncode,
               bounded(proc.stderr.decode("utf-8", "replace"))))
    # 不同 git 版本把 ref 列表输出到 stdout 或 stderr，双流核查 head。
    verify_output = proc.stdout + proc.stderr
    require(head.encode("utf-8") in verify_output,
            "T01: git bundle verify output lacks head %s" % head)

    # Git 真实消费 2：从 bundle 导入全新仓库，head/内容等于源提交。
    cloned = os.path.join(work, "consumer-repo")
    proc = subprocess.run(
        ["git", "clone", "-q", verify_src, cloned],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=GIT_TIMEOUT)
    require(proc.returncode == 0,
            "T01: git clone from bundle failed (%d) :: %s"
            % (proc.returncode,
               bounded(proc.stderr.decode("utf-8", "replace"))))
    proc = subprocess.run(["git", "-C", cloned, "rev-parse", "HEAD"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=GIT_TIMEOUT)
    require(proc.returncode == 0 and
            proc.stdout.decode().strip() == head,
            "T01: cloned HEAD %r != source commit %s"
            % (proc.stdout.decode().strip(), head))
    with open(os.path.join(cloned, "handoff-note.md"), "rb") as fh:
        cloned_text = fh.read()
    require(cloned_text == text.encode("utf-8"),
            "T01: cloned file content differs from source commit")

    # Git 真实消费 3：unpack 三件套到新目录，与源字节一致。
    unpacked = os.path.join(work, "unpacked")
    cli_stdout_json("T01/unpack", cli_path,
                    ["unpack", "--bundle", artifacts_bundle,
                     "--target", unpacked])
    for rel in ARTIFACT_PATHS:
        require(read_bytes(os.path.join(unpacked, rel)) ==
                reassembled[rel],
                "T01: unpacked %s differs from reassembled bytes" % rel)
    return head, sha256_hex(git_bundle_bytes)


def scenario_truncated_bundle(cli_path, work, fixture):
    """T02 bundle 文件截断 -> 拒绝且零落盘。"""
    manifest_bytes = read_bytes(fixture["artifacts_bundle"])
    truncated = os.path.join(work, "truncated.bundle")
    write_file(truncated, manifest_bytes[:len(manifest_bytes) - 64])
    target = os.path.join(work, "target-t02")
    expect_rejection("T02", cli_path,
                     ["unpack", "--bundle", truncated, "--target", target],
                     target)


def scenario_flipped_byte(cli_path, work, fixture):
    """T03 改一字节：base64 合法、解码长度一致，仅 SHA 复核失败 ->
    拒绝且零落盘。"""
    bundle_path = fixture["artifacts_bundle"]
    manifest, _ = load_manifest(bundle_path)

    def flip(manifest_obj):
        chunks = manifest_obj["files"][0]["chunks"]
        raw = base64.b64decode(chunks[0]["base64"].encode("ascii"),
                               validate=True)
        chunks[0]["base64"] = base64.b64encode(
            flip_one_bit(raw)).decode("ascii")

    tampered = os.path.join(work, "flipped-byte.bundle")
    write_file(tampered, rebuild_manifest(manifest, flip))
    target = os.path.join(work, "target-t03")
    expect_rejection("T03", cli_path,
                     ["unpack", "--bundle", tampered, "--target", target],
                     target)


def scenario_out_of_order_chunks(cli_path, work, fixture):
    """T04 bundle 内 chunk 数组乱序 -> 拒绝（index 必须与数组位置一致）。

    消费侧重排合同只适用于"emit 行乱序到达"，manifest 内部结构
    乱序是坏包，必须 fail-closed。
    """
    bundle_path = fixture["artifacts_bundle"]
    manifest, _ = load_manifest(bundle_path)

    def swap(manifest_obj):
        chunks = manifest_obj["files"][0]["chunks"]
        require(len(chunks) >= 2, "fixture needs >=2 chunks")
        chunks[0], chunks[1] = chunks[1], chunks[0]

    swapped = os.path.join(work, "out-of-order.bundle")
    write_file(swapped, rebuild_manifest(manifest, swap))
    target = os.path.join(work, "target-t04")
    expect_rejection("T04", cli_path,
                     ["unpack", "--bundle", swapped, "--target", target],
                     target)


def scenario_duplicate_chunk(cli_path, work, fixture):
    """T05 bundle 内重复 chunk（复制首 chunk 顶替第二个，count 不变）->
    拒绝（index/offset 不连续即重复证据）。"""
    bundle_path = fixture["artifacts_bundle"]
    manifest, _ = load_manifest(bundle_path)

    def duplicate(manifest_obj):
        chunks = manifest_obj["files"][0]["chunks"]
        require(len(chunks) >= 2, "fixture needs >=2 chunks")
        chunks[1] = dict(chunks[0])

    duped = os.path.join(work, "duplicate-chunk.bundle")
    write_file(duped, rebuild_manifest(manifest, duplicate))
    target = os.path.join(work, "target-t05")
    expect_rejection("T05", cli_path,
                     ["unpack", "--bundle", duped, "--target", target],
                     target)


def scenario_missing_tail_chunk(cli_path, work, fixture):
    """T06 传输丢尾行：消费侧重装层必须拒绝，不得误报完整。

    收件侧合同（emit 行驱动）在此由本测试自身承担并验证：
    缺行时 chunk 计数/字节数/SHA 三处必须暴露不一致。
    """
    bundle_path = fixture["artifacts_bundle"]
    manifest, _ = load_manifest(bundle_path)
    entry = manifest["files"][0]
    require(len(entry["chunks"]) >= 2, "fixture needs >=2 chunks")
    # 模拟终端通道丢了最后一个 emit 行后按 offset 重排。
    short = sorted(entry["chunks"][:-1], key=lambda c: c["offset"])
    rejected = False
    try:
        reassemble(short, entry, entry["path"])
    except TestFailure:
        rejected = True
    require(rejected,
            "T06: consumer reassembly accepted a transfer missing the "
            "tail chunk (false-complete)")


def scenario_target_exists(cli_path, work, fixture):
    """T07 目标已存在 -> 拒绝且哨兵文件不被覆盖。"""
    bundle_path = fixture["artifacts_bundle"]
    target = os.path.join(work, "target-t07")
    os.makedirs(target)
    sentinel = os.path.join(target, "sentinel.txt")
    sentinel_bytes = b"do-not-overwrite\n"
    write_file(sentinel, sentinel_bytes)
    rc, out, err = run_cli(cli_path,
                           ["unpack", "--bundle", bundle_path,
                            "--target", target])
    require(rc != 0,
            "T07: unpack into existing target reported success")
    require(rc == 1,
            "T07: expected clean rejection exit 1, got %d :: %s"
            % (rc, bounded(err)))
    require(read_bytes(sentinel) == sentinel_bytes,
            "T07: sentinel file was modified")
    require(not os.path.lexists(os.path.join(target, "delivery.bundle")),
            "T07: unpack wrote into existing target")


def scenario_bad_manifest_sha(cli_path, work, fixture):
    """T08 坏包：manifest sha256 字段被篡改 -> 拒绝且不留半交付。"""
    bundle_path = fixture["artifacts_bundle"]
    manifest, _ = load_manifest(bundle_path)

    def bad_sha(manifest_obj):
        entry = manifest_obj["files"][1]
        entry["sha256"] = ("0" * 63 + "1")

    tampered = os.path.join(work, "bad-sha.bundle")
    write_file(tampered, rebuild_manifest(manifest, bad_sha))
    target = os.path.join(work, "target-t08")
    expect_rejection("T08", cli_path,
                     ["unpack", "--bundle", tampered, "--target", target],
                     target)


# ------------------------------------------------------------------- main

def resolve_cli():
    """依赖解析：缺依赖清晰 SKIP(77)；显式配置无效硬失败。"""
    value = os.environ.get("ZCODE_GUI_ARTIFACTS")
    if not value:
        log("SKIP: environment variable ZCODE_GUI_ARTIFACTS is not set; "
            "point it at the real zcode-gui-artifacts.py to run this "
            "consumer regression")
        sys.exit(SKIP_EXIT)
    value = os.path.abspath(value)
    if not os.path.exists(value):
        log("FAIL: ZCODE_GUI_ARTIFACTS is set but path does not exist: %s"
            % value)
        sys.exit(1)
    if os.path.islink(value) or not os.path.isfile(value):
        log("FAIL: ZCODE_GUI_ARTIFACTS must be a regular file, got: %s"
            % value)
        sys.exit(1)
    expected = os.environ.get("ZCODE_GUI_ARTIFACTS_EXPECT_SHA256")
    if expected:
        actual = sha256_hex(read_bytes(value))
        if actual != expected.lower():
            log("FAIL: ZCODE_GUI_ARTIFACTS sha256 fingerprint mismatch: "
                "expected %s, actual %s" % (expected, actual))
            sys.exit(1)
    git_path = shutil.which("git")
    if not git_path:
        log("SKIP: git not found on PATH; this regression synthesizes a "
            "real git repository and bundle, so git is required")
        sys.exit(SKIP_EXIT)
    return value, git_path


def main():
    cli_path, _ = resolve_cli()
    head = None
    work = tempfile.mkdtemp(prefix="zgui-handoff-smoke-")
    cases = [
        ("T01 full-handoff-roundtrip",
         lambda: scenario_full_handoff(cli_path, work, fixture)),
        ("T02 truncated-bundle-rejected",
         lambda: scenario_truncated_bundle(cli_path, work, fixture)),
        ("T03 flipped-byte-rejected",
         lambda: scenario_flipped_byte(cli_path, work, fixture)),
        ("T04 out-of-order-chunks-rejected",
         lambda: scenario_out_of_order_chunks(cli_path, work, fixture)),
        ("T05 duplicate-chunk-rejected",
         lambda: scenario_duplicate_chunk(cli_path, work, fixture)),
        ("T06 missing-tail-chunk-no-false-complete",
         lambda: scenario_missing_tail_chunk(cli_path, work, fixture)),
        ("T07 target-exists-never-overwrite",
         lambda: scenario_target_exists(cli_path, work, fixture)),
        ("T08 bad-manifest-sha-no-half-delivery",
         lambda: scenario_bad_manifest_sha(cli_path, work, fixture)),
    ]
    try:
        fixture = build_transfer_fixture(cli_path, work)
    except Exception as exc:  # fixture 失败则全体用例无意义，直陈并退出
        record("FIXTURE build-transfer", False,
               str(exc) if isinstance(exc, TestFailure)
               else "%s: %s" % (type(exc).__name__, exc))
        log(json.dumps({"test": "test-zcode-gui-artifacts-consumer",
                        "passed": 0, "total": 1,
                        "results": _results}, sort_keys=True))
        shutil.rmtree(work, ignore_errors=True)
        sys.exit(1)

    for name, case_fn in cases:
        try:
            outcome = case_fn()
            if isinstance(outcome, tuple):
                head = outcome[0]
            record(name, True)
        except TestFailure as exc:
            record(name, False, str(exc))
        except Exception as exc:  # 环境性崩溃也必须以非零退出并留有界证据
            record(name, False, "%s: %s" % (type(exc).__name__, exc))
    shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for r in _results if r["ok"])
    total = len(_results)
    summary = {
        "test": "test-zcode-gui-artifacts-consumer",
        "cli": os.path.basename(cli_path),
        # head 仅在全部通过时回填，避免半途失败时输出误导值。
        "head": head if (total and passed == total) else None,
        "passed": passed,
        "total": total,
        "results": _results,
    }
    log(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    if total == 0 or passed != total:
        sys.exit(1)
    log("PASS: %d/%d consumer cases (git bundle handoff round-trip ok)"
        % (passed, total))
    sys.exit(0)


if __name__ == "__main__":
    main()
