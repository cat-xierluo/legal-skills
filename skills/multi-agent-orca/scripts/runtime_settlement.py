"""只读推导 Orca runtime/resource 结算；不调用 RPC 或生命周期 mutation。

原始响应保留于受信调用者管理的证据根；输出仅携带最小字段。文件哈希
证明本地证据一致性，不认证采集者、provider 或任意 OS 资源。
Delivery/ack 字段来源：Orca 1.4.197 的 out/main/index.js（a60fbf4d…），
及 out/cli/handlers/orchestration/message-check-handler.js。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

PREFIX = "multi-agent-orchestration."
BINDING = PREFIX + "runtime-binding.v1"
REQUEST = PREFIX + "runtime-observe-request.v1"
COMMAND = PREFIX + "command-observation.v1"
SNAPSHOT = PREFIX + "runtime-observation.v1"
RECEIPT = PREFIX + "runtime-settlement-receipt.v1"
LEASE = PREFIX + "provider-lease.v2"
LEASE_RELEASE = PREFIX + "provider-lease-release.v1"
MAX_BYTES = 16 * 1024 * 1024
SHA = re.compile(r"^[a-f0-9]{64}$")


class SettlementError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def fail(code, message):
    raise SettlementError(code, message)


def guarded(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SettlementError:
            raise
        except (ValueError, OSError, TypeError, KeyError, IndexError, AttributeError, RecursionError, OverflowError) as exc:
            raise SettlementError("INVALID_EVIDENCE", type(exc).__name__ + ": 证据不可读取或无法验证") from exc
    return call


def obj(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        fail("INVALID_SCHEMA", "对象字段缺失、未知或类型错误")
    return value


def text(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        fail("INVALID_SCHEMA", "需要无控制字符的非空字符串")
    return value


def number(value, minimum=0):
    if type(value) is not int or value < minimum:
        fail("INVALID_SCHEMA", "需要指定范围内的整数")
    return value


def sha_value(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        fail("INVALID_SCHEMA", "需要小写 SHA-256")
    return value


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def same(a, b):
    return canonical(a) == canonical(b)


def raw_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                fail("INVALID_SCHEMA", "JSON 不得含重复 key")
            out[key] = value
        return out
    def constant(value):
        fail("INVALID_SCHEMA", "JSON 不得含非有限数值")
    def floating(value):
        result = float(value)
        if not math.isfinite(result):
            constant(value)
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise SettlementError("INVALID_JSON", "JSON 证据无法严格解析") from exc
    if not isinstance(value, dict):
        fail("INVALID_SCHEMA", "JSON 顶层必须为对象")
    return value


def checked(path, *, directory=False, missing=False):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        fail("UNSAFE_PATH", "需要无 .. 的规范绝对路径")
    for node in reversed((path, *path.parents)):
        try:
            mode = node.lstat().st_mode
        except FileNotFoundError:
            if missing:
                continue
            fail("MISSING_FILE", "引用的证据路径不存在")
        if stat.S_ISLNK(mode):
            fail("UNSAFE_PATH", "证据路径及父节点不得含符号链接")
        if node != path or directory:
            if not stat.S_ISDIR(mode):
                fail("UNSAFE_PATH", "父节点必须为真实目录")
        elif not stat.S_ISREG(mode):
            fail("UNSAFE_PATH", "证据必须为普通文件")
    return path


def relative(value):
    text(value)
    if Path(value).is_absolute() or "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
        fail("UNSAFE_PATH", "证据引用需要受限相对路径")
    return value


def read(path):
    path = checked(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            fail("INVALID_EVIDENCE", "证据不是受限大小的普通文件")
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    checked(path)
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if len(raw) > MAX_BYTES or identity(before) != identity(after) or identity(after) != identity(path.stat()):
        fail("INPUT_CHANGED", "读取期间证据变化或超出大小限制")
    return raw


def timestamp(value):
    text(value)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc).isoformat()
    except ValueError as exc:
        raise SettlementError("INVALID_TIME", "命令观察时间必须为带时区 ISO 时间") from exc


def envelope(schema, payload):
    return {"schema_version": schema, "payload": payload, "sha256": digest(payload)}


def unwrap(value, schema):
    obj(value, {"schema_version", "payload", "sha256"})
    if value["schema_version"] != schema or not isinstance(value["payload"], dict) or sha_value(value["sha256"]) != digest(value["payload"]):
        fail("RECEIPT_DRIFT", "收据类型或 payload 摘要不一致")
    return value["payload"]


def publish(path, value):
    path = checked(Path(path).absolute(), missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    checked(path.parent, directory=True)
    raw = canonical(value) + b"\n"
    if path.exists():
        if read(path) != raw:
            fail("OUTPUT_CONFLICT", "不得覆盖不同的既有观察/收据")
        return "UNCHANGED"
    fd, name = tempfile.mkstemp(prefix=".runtime-settlement-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if read(path) != raw:
                fail("OUTPUT_CONFLICT", "并发输出与现有收据冲突")
            return "UNCHANGED"
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return "CREATED"


def validate_binding(value):
    obj(value, {"schema_version", "binding_id", "cli_argv0", "runtime", "run", "task_id", "dispatch_id", "worktree_id",
                "terminal_handle", "session_id", "lease", "delivery", "correlation"})
    if value["schema_version"] != BINDING:
        fail("INVALID_SCHEMA", "不支持的 runtime binding")
    for key in ("binding_id", "cli_argv0", "task_id", "dispatch_id", "worktree_id", "terminal_handle", "session_id"):
        text(value[key])
    obj(value["runtime"], {"observer_runtime_id", "worker_runtime_epoch", "process_incarnation"})
    for item in value["runtime"].values():
        text(item)
    obj(value["run"], {"run_id", "consumer_generation"})
    text(value["run"]["run_id"]); number(value["run"]["consumer_generation"])
    lease = obj(value["lease"], {"requirement", "allocation_id", "provider", "reason", "path"})
    if lease["requirement"] == "REQUIRED":
        for key in ("allocation_id", "provider", "path"):
            text(lease[key])
        if lease["reason"] != "DECLARED_ALLOCATION" or not Path(lease["path"]).is_absolute() or ".." in Path(lease["path"]).parts:
            fail("INVALID_SCHEMA", "lease 必须绑定精确分配路径")
    elif lease["requirement"] == "NONE_REQUIRED":
        if any(lease[key] is not None for key in ("allocation_id", "provider", "path")) or lease["reason"] != "UNCONFIGURED_PROVIDER_LIMIT":
            fail("INVALID_SCHEMA", "NONE_REQUIRED 必须为显式未配置 lease 策略")
    else:
        fail("INVALID_SCHEMA", "不支持的 lease requirement")
    delivery = obj(value["delivery"], {"requirement", "reason", "delivery_id", "message_ids"})
    if not isinstance(delivery["message_ids"], list) or len(set(map(str, delivery["message_ids"]))) != len(delivery["message_ids"]):
        fail("INVALID_SCHEMA", "message_ids 必须是唯一 ID 数组")
    for item in delivery["message_ids"]:
        text(item)
    if delivery["delivery_id"] is not None:
        text(delivery["delivery_id"])
    if delivery["requirement"] == "REQUIRED":
        if delivery["reason"] != "WORKER_DONE":
            fail("INVALID_SCHEMA", "REQUIRED Delivery 必须明确 worker_done 义务")
    elif delivery["requirement"] == "NONE_REQUIRED":
        if delivery["reason"] != "TERMINAL_LOSS_RECOVERY" or delivery["delivery_id"] is not None or delivery["message_ids"]:
            fail("INVALID_SCHEMA", "NONE_REQUIRED 仅用于明确 terminal-loss 恢复")
    else:
        fail("INVALID_SCHEMA", "不支持的 delivery requirement")
    if value["correlation"] is not None:
        correlation = obj(value["correlation"], {"attempt_id", "worker_id", "worker_contract_sha256", "authorization_receipt_sha256"})
        text(correlation["attempt_id"]); text(correlation["worker_id"])
        sha_value(correlation["worker_contract_sha256"]); sha_value(correlation["authorization_receipt_sha256"])
    return value


class Reader:
    def __init__(self, root):
        self.root = checked(root, directory=True)
        self.dependencies = {}

    def file(self, path):
        path = checked(path)
        raw = read(path)
        ref = {"path": str(path), "sha256": raw_sha(raw)}
        old = self.dependencies.get(str(path))
        if old is not None and old != ref:
            fail("INPUT_CHANGED", "重复读取同一依赖得到不同内容")
        self.dependencies[str(path)] = ref
        return raw

    def bound(self, ref):
        obj(ref, {"path", "sha256"})
        path = self.root / relative(ref["path"])
        if raw_sha(raw := self.file(path)) != sha_value(ref["sha256"]):
            fail("HASH_MISMATCH", "绑定证据文件摘要不匹配")
        return raw

    def recheck(self):
        for ref in self.dependencies.values():
            if raw_sha(read(Path(ref["path"]))) != ref["sha256"]:
                fail("INPUT_CHANGED", "事务结束前证据发生变化")

    def refs(self):
        return [self.dependencies[key] for key in sorted(self.dependencies)]


def expected_argv(role, binding, actual):
    base = [binding["cli_argv0"], "orchestration"]
    run_id, dispatch = binding["run"]["run_id"], binding["dispatch_id"]
    known = {
        "run": [base + ["run-show", "--id", run_id, "--json"]],
        "tasks": [base + ["task-list", "--run", run_id, "--json"], base + ["task-list", "--run", run_id, "--brief", "--json"]],
        "worker": [base + ["worker-show", "--dispatch", dispatch, "--json"]],
        "release": [base + ["worker-release", "--dispatch", dispatch, "--json"]],
        "authority": [base + ["run-use", "--id", run_id, "--json"]],
    }
    if role in known:
        if actual not in known[role]:
            fail("ARGV_MISMATCH", "命令 argv 未绑定要求的精确 Run/Dispatch")
        return
    if role in {"delivery", "ack"}:
        if actual[:3] != base + ["check"]:
            fail("ARGV_MISMATCH", "Delivery 必须来自当前 check 命令")
        options = actual[3:]
        parsed = {}
        i = 0
        while i < len(options):
            key = options[i]
            if key in parsed or key not in {"--json", "--run", "--ack", "--wait", "--timeout-ms"}:
                fail("ARGV_MISMATCH", "check 参数重复、未知或为非完整批次历史视图")
            if key in {"--json", "--wait"}:
                parsed[key] = True; i += 1
            else:
                if i + 1 >= len(options):
                    fail("ARGV_MISMATCH", "check 参数缺值")
                parsed[key] = options[i + 1]; i += 2
        if "--json" not in parsed or parsed.get("--run", run_id) != run_id:
            fail("ARGV_MISMATCH", "check 必须绑定当前 Run 并返回 JSON")
        if (role == "ack") != ("--ack" in parsed):
            fail("ARGV_MISMATCH", "Delivery 与 ack 命令角色不匹配")
        return
    if role == "lease_release":
        # 只读取既有 provider-lease release 命令结果；从不执行它。
        if len(actual) < 4 or Path(actual[1]).name != "provider-lease.py" or actual[2] != "release":
            fail("ARGV_MISMATCH", "lease 释放必须为明确 provider-lease.py release")
        flags = actual[3:]
        values = {}
        i = 0
        while i < len(flags):
            key = flags[i]
            if key in values or key not in {"--root", "--lease-file", "--session", "--resource-settled", "--orca-cli", "--runtime-binding", "--release-receipt"}:
                fail("ARGV_MISMATCH", "lease release 参数不支持")
            if key == "--resource-settled":
                values[key] = True; i += 1
            else:
                if i + 1 >= len(flags):
                    fail("ARGV_MISMATCH", "lease release 参数缺值")
                values[key] = flags[i + 1]; i += 2
        if (values.get("--lease-file") != binding["lease"]["path"] or values.get("--session") != binding["session_id"]
                or values.get("--resource-settled") is not True or values.get("--orca-cli") != binding["cli_argv0"]
                or values.get("--root") != str(Path(binding["lease"]["path"]).parent.parent)):
            fail("ARGV_MISMATCH", "lease release 未精确绑定 Session/path/root/CLI")
        if "--runtime-binding" in values or "--release-receipt" in values:
            expected_receipt = str(Path(binding["lease"]["path"]).parent.parent / ".runtime-release-receipts" / (digest(binding) + ".json"))
            if not Path(values.get("--runtime-binding", "")).is_absolute() or values.get("--release-receipt") != expected_receipt:
                fail("ARGV_MISMATCH", "bound lease release 缺少固定 binding/receipt 路径")
        return
    fail("INVALID_SCHEMA", "未知命令角色")


def command(reader, ref, role, binding, runtime_id):
    data = parse(reader.bound(ref))
    obj(data, {"schema_version", "argv", "exit_code", "observed_at", "stdout", "stderr"})
    if data["schema_version"] != COMMAND or not isinstance(data["argv"], list) or not data["argv"]:
        fail("INVALID_SCHEMA", "命令观察缺少版本化 argv")
    for arg in data["argv"]:
        text(arg)
    if type(data["exit_code"]) is not int:
        fail("INVALID_SCHEMA", "退出码必须是整数")
    expected_argv(role, binding, data["argv"])
    observed_at = timestamp(data["observed_at"])
    raw = reader.bound(data["stdout"])
    reader.bound(data["stderr"])
    summary = {"observed_at": observed_at, "exit_code": data["exit_code"], "accepted": False,
               "error_code": None, "stdout_sha256": data["stdout"]["sha256"]}
    try:
        response = parse(raw)
    except SettlementError as exc:
        if exc.code != "INVALID_JSON":
            raise
        summary["error_code"] = "NON_JSON_COMMAND_OUTPUT"
        return data, None, summary
    if role != "lease_release":
        if type(response.get("ok")) is not bool:
            fail("INVALID_SCHEMA", "RPC 外包装缺少 boolean ok")
        meta = response.get("_meta")
        if isinstance(meta, dict) and meta.get("runtimeId") is not None:
            if text(meta["runtimeId"]) != runtime_id:
                fail("MIXED_RUNTIME", "同一观察中的命令来自不同 runtime")
        elif response["ok"]:
            fail("INVALID_SCHEMA", "成功 RPC 缺少 _meta.runtimeId")
        if response["ok"] and data["exit_code"] == 0:
            if not isinstance(response.get("result"), dict):
                fail("INVALID_SCHEMA", "RPC result 必须为对象")
            summary["accepted"] = True
        else:
            error = response.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            summary["error_code"] = text(code) if isinstance(code, str) and code else "RPC_FAILED"
    else:
        summary["accepted"] = data["exit_code"] == 0 and response.get("released") is True
        if not summary["accepted"]:
            summary["error_code"] = "LEASE_RELEASE_NOT_CONFIRMED"
    return data, response, summary


def equal_identity(actual, expected, field):
    if not same(actual, expected):
        fail("IDENTITY_MISMATCH", "身份字段不一致: " + field)


def native_worker(response, binding):
    value = response["result"]
    for field in ("dispatch", "worker", "observation"):
        if not isinstance(value.get(field), dict):
            fail("INVALID_SCHEMA", "worker-show 缺少完整结构: " + field)
    dispatch, worker, observation = value["dispatch"], value["worker"], value["observation"]
    expected = {"id": binding["dispatch_id"], "task_id": binding["task_id"], "run_id": binding["run"]["run_id"],
                "assignee_handle": binding["terminal_handle"], "process_incarnation": binding["runtime"]["process_incarnation"]}
    for key, item in expected.items():
        equal_identity(dispatch.get(key), item, "dispatch." + key)
    for key, item in {"dispatch_id": binding["dispatch_id"], "runtime_epoch": binding["runtime"]["worker_runtime_epoch"],
                      "worktree_id": binding["worktree_id"], "agent_terminal_handle": binding["terminal_handle"]}.items():
        equal_identity(worker.get(key), item, "worker." + key)
    for mapping, keys in ((dispatch, ("status",)), (worker, ("state", "stage")), (observation, ("status",))):
        for key in keys:
            text(mapping.get(key))
    if type(observation.get("exactWorker")) is not bool:
        fail("INVALID_SCHEMA", "observation.exactWorker 必须为 boolean")
    resource = value.get("terminalResource")
    normalized_resource = None
    if resource is not None:
        if not isinstance(resource, dict):
            fail("INVALID_SCHEMA", "terminalResource 类型错误")
        for key, item in {"terminalHandle": binding["terminal_handle"], "worktreeId": binding["worktree_id"],
                          "originDispatchId": binding["dispatch_id"], "ownerDispatchId": binding["dispatch_id"]}.items():
            equal_identity(resource.get(key), item, "terminalResource." + key)
        for key in ("id", "ownershipState", "releaseState"):
            text(resource.get(key))
        normalized_resource = {key: resource.get(key) for key in ("id", "ownershipState", "releaseState", "retainedReason",
                                                               "releaseCompletedAt", "releaseError")}
        for key in ("retainedReason", "releaseCompletedAt", "releaseError"):
            if normalized_resource[key] is not None:
                text(normalized_resource[key])
        if normalized_resource["releaseCompletedAt"] is not None:
            normalized_resource["releaseCompletedAt"] = timestamp(normalized_resource["releaseCompletedAt"])
    residuals = worker.get("residualResources")
    if not isinstance(residuals, list):
        fail("INVALID_SCHEMA", "worker.residualResources 必须为数组")
    if "residual_resources" in worker:
        # upstream 同时提供 JSON string 与解析数组；必须同值，不择一吞掉冲突。
        raw = worker["residual_resources"]
        if not isinstance(raw, str):
            fail("INVALID_SCHEMA", "residual_resources 必须是 JSON 字符串")
        parsed = parse('{"items":' + raw + '}')["items"]
        equal_identity(parsed, residuals, "worker.residualResources")
    return {"dispatch_status": dispatch["status"], "worker_state": worker["state"], "worker_stage": worker["stage"],
            "terminal_observation": {"status": observation["status"], "exact_worker": observation["exactWorker"]},
            "terminal_resource": normalized_resource, "residual_resource_count": len(residuals)}


def terminal_is_released(worker):
    resource = worker["terminal_resource"]
    return bool(resource and resource["ownershipState"] == "released" and resource["releaseState"] == "released"
                and resource["releaseCompletedAt"] and resource["releaseError"] is None and worker["residual_resource_count"] == 0
                and worker["terminal_observation"]["status"] in {"missing", "exited"}
                and worker["worker_state"] in {"succeeded", "failed", "stopped", "abandoned"})


@guarded
def validate_lease_release(receipt, binding, *, record_sha256=None, runtime_id=None):
    release = unwrap(receipt, LEASE_RELEASE)
    obj(release, {"expected_binding", "binding_sha256", "lease_path", "lease_record_sha256", "released", "released_at", "resource_observation"})
    for key, expected in {"expected_binding": binding, "binding_sha256": digest(binding), "lease_path": binding["lease"]["path"],
                          "released": True}.items():
        equal_identity(release[key], expected, "lease_release." + key)
    resource_proof = obj(release["resource_observation"], {"argv", "exit_code", "stdout", "stdout_sha256", "stderr", "stderr_sha256", "observer_runtime_id", "worker"})
    expected_argv("worker", binding, resource_proof["argv"])
    if not isinstance(resource_proof["stdout"], str) or not isinstance(resource_proof["stderr"], str):
        fail("INVALID_SCHEMA", "嵌套资源观察必须保留原始 stdout 字符串")
    nested_raw = resource_proof["stdout"].encode('utf-8')
    if raw_sha(nested_raw) != sha_value(resource_proof["stdout_sha256"]):
        fail("HASH_MISMATCH", "嵌套资源观察 stdout hash 不一致")
    if raw_sha(resource_proof["stderr"].encode('utf-8')) != sha_value(resource_proof["stderr_sha256"]):
        fail("HASH_MISMATCH", "嵌套资源观察 stderr hash 不一致")
    nested_response = parse(nested_raw)
    if nested_response.get("ok") is not True:
        fail("INVALID_EVIDENCE", "嵌套资源观察不是成功 RPC")
    equal_identity(nested_response.get("_meta", {}).get("runtimeId"), resource_proof["observer_runtime_id"], "lease_release.runtimeId")
    nested_worker = native_worker(nested_response, binding)
    equal_identity(nested_worker, resource_proof["worker"], "lease_release.worker")
    if type(resource_proof["exit_code"]) is not int or resource_proof["exit_code"] != 0 or not terminal_is_released(nested_worker):
        fail("INVALID_EVIDENCE", "lease release 缺少 exact resource 后态")
    if nested_worker["terminal_resource"]["releaseCompletedAt"] > timestamp(release["released_at"]):
        fail("INVALID_ORDER", "lease release 不能先于 terminal resource 后态")
    text(resource_proof["observer_runtime_id"])
    if runtime_id is not None and resource_proof["observer_runtime_id"] != runtime_id:
        fail("MIXED_RUNTIME", "lease release 的实际 resource 观察来自不同 runtime")
    sha_value(release["lease_record_sha256"])
    if record_sha256 is not None:
        equal_identity(release["lease_record_sha256"], record_sha256, "lease_release.lease_record_sha256")
    return release


def delivery_facts(response, binding):
    value = response["result"]
    equal_identity(value.get("runId"), binding["run"]["run_id"], "delivery.runId")
    delivery_id = text(value.get("deliveryId"))
    if binding["delivery"]["delivery_id"] is not None:
        equal_identity(delivery_id, binding["delivery"]["delivery_id"], "delivery.deliveryId")
    messages = value.get("messages")
    if not isinstance(messages, list) or number(value.get("count")) != len(messages) or not messages:
        fail("INVALID_SCHEMA", "Delivery 必须保存完整非空 batch 及精确 count")
    result, ids = [], set()
    for message in messages:
        if not isinstance(message, dict):
            fail("INVALID_SCHEMA", "Delivery message 必须为对象")
        ident = text(message.get("id"))
        if ident in ids:
            fail("INVALID_SCHEMA", "Delivery 消息 ID 重复")
        ids.add(ident)
        equal_identity(message.get("run_id"), binding["run"]["run_id"], "message.run_id")
        equal_identity(message.get("to_handle"), "run:" + binding["run"]["run_id"], "message.to_handle")
        kind = text(message.get("type"))
        contract = text(message.get("delivery_contract"))
        payload = message.get("payload")
        parsed = parse(payload) if isinstance(payload, str) and payload.strip() else {}
        target = (kind == "worker_done" and contract == "current_delivery"
                  and parsed.get("taskId") == binding["task_id"] and parsed.get("dispatchId") == binding["dispatch_id"]
                  and parsed.get("outcome") in {"succeeded", "failed"})
        result.append({"message_id": ident, "message_sha256": digest(message), "type": kind, "delivery_contract": contract,
                       "target_worker_done": target, "outcome": parsed.get("outcome") if target else None})
    if binding["delivery"]["message_ids"]:
        equal_identity(sorted(ids), sorted(binding["delivery"]["message_ids"]), "delivery.message_ids")
    return {"delivery_id": delivery_id, "messages": result, "count": len(result), "messages_sha256": digest(messages)}


def build_snapshot(request_path):
    request_path = checked(Path(request_path).absolute())
    reader = Reader(request_path.parent)
    request_raw = reader.file(request_path)
    request = parse(request_raw)
    obj(request, {"schema_version", "observer_runtime_id", "binding", "commands", "lease_record", "lease_release"})
    if request["schema_version"] != REQUEST:
        fail("INVALID_SCHEMA", "不支持的 observation request")
    runtime_id = text(request["observer_runtime_id"])
    binding = validate_binding(parse(reader.bound(request["binding"])))
    commands = obj(request["commands"], set(), {"run", "tasks", "worker", "release", "delivery", "ack", "authority"})
    calls, summaries = {}, {}
    for role, ref in sorted(commands.items()):
        calls[role] = command(reader, ref, role, binding, runtime_id)
        summaries[role] = calls[role][2]
    observed = {"observer_runtime_id": runtime_id, "original_observer_runtime_id": binding["runtime"]["observer_runtime_id"],
                "runtime_changed": runtime_id != binding["runtime"]["observer_runtime_id"],
                "run": None, "task": None, "worker": None, "lease": None, "delivery": None, "acknowledged_delivery_id": None,
                "commands": summaries}
    accepted = lambda role: role in calls and calls[role][2]["accepted"]
    if accepted("run"):
        run = calls["run"][1]["result"].get("run")
        if not isinstance(run, dict):
            fail("INVALID_SCHEMA", "run-show 缺少 run 对象")
        equal_identity(run.get("id"), binding["run"]["run_id"], "run.id")
        number(run.get("consumer_generation"))
        equal_identity(run["consumer_generation"], binding["run"]["consumer_generation"], "run.consumer_generation")
        observed["run"] = {"run_id": run["id"], "consumer_generation": run["consumer_generation"]}
    if accepted("tasks"):
        value = calls["tasks"][1]["result"]
        equal_identity(value.get("runId"), binding["run"]["run_id"], "tasks.runId")
        tasks = value.get("tasks")
        if not isinstance(tasks, list) or number(value.get("count")) != len(tasks):
            fail("INVALID_SCHEMA", "task-list count 与完整数组不一致")
        ids = set(); selected = []
        for task in tasks:
            if not isinstance(task, dict):
                fail("INVALID_SCHEMA", "Task 必须为对象")
            task_id = text(task.get("id"))
            if task_id in ids:
                fail("INVALID_SCHEMA", "重复 Task id")
            ids.add(task_id)
            equal_identity(task.get("run_id"), binding["run"]["run_id"], "task.run_id")
            if task_id == binding["task_id"]:
                selected.append({"task_id": task_id, "status": text(task.get("status"))})
        if len(selected) != 1:
            fail("IDENTITY_MISMATCH", "task-list 没有唯一匹配目标 Task")
        observed["task"] = selected[0]
    if accepted("worker"):
        observed["worker"] = native_worker(calls["worker"][1], binding)
        released_at = (observed["worker"]["terminal_resource"] or {}).get("releaseCompletedAt")
        if released_at and released_at > summaries["worker"]["observed_at"]:
            fail("INVALID_ORDER", "资源释放时间不能晚于 worker 后态观察")
    if request["lease_record"] is not None:
        lease = parse(reader.bound(request["lease_record"]))
        observed["lease"] = {"schema": lease.get("schema"), "binding_verified": False, "release_verified": False,
                             "record_sha256": request["lease_record"]["sha256"]}
        if lease.get("schema") == LEASE:
            obj(lease, {"schema", "state", "allocation_id", "provider", "session", "transport", "resource_handle",
                        "runtime_binding_sha256", "lease_path"}, {"created_at", "updated_at"})
            for key, expected in {"allocation_id": binding["lease"]["allocation_id"], "provider": binding["lease"]["provider"],
                                  "session": binding["session_id"], "resource_handle": binding["terminal_handle"],
                                  "runtime_binding_sha256": digest(binding), "lease_path": binding["lease"]["path"]}.items():
                equal_identity(lease[key], expected, "lease." + key)
            if lease["transport"] != "orca_terminal" or lease["state"] not in {"active", "released"}:
                fail("INVALID_SCHEMA", "v2 lease transport/state 不支持")
            observed["lease"].update(binding_verified=True, state=lease["state"])
        elif lease.get("schema") == PREFIX + "provider-lease.v1":
            observed["lease"]["state"] = text(lease.get("state"))
            if "runtime_binding_sha256" in lease:
                for key, expected in {"allocation_id": binding["lease"]["allocation_id"], "provider": binding["lease"]["provider"],
                                      "session": binding["session_id"], "resource_handle": binding["terminal_handle"],
                                      "runtime_binding_sha256": digest(binding), "lease_path": binding["lease"]["path"],
                                      "state": "active", "transport": "orca_terminal"}.items():
                    equal_identity(lease.get(key), expected, "lease." + key)
                observed["lease"]["binding_verified"] = True
        else:
            fail("INVALID_SCHEMA", "未知 lease schema")
    if request["lease_release"] is not None:
        call = command(reader, request["lease_release"], "lease_release", binding, runtime_id)
        summaries["lease_release"] = call[2]
        if call[2]["accepted"]:
            equal_identity(call[1].get("lease_file"), binding["lease"]["path"], "lease_release.lease_file")
            if observed["lease"] and observed["lease"]["binding_verified"]:
                release = unwrap(call[1].get("runtime_release"), LEASE_RELEASE)
                validate_lease_release(call[1]["runtime_release"], binding,
                                       record_sha256=observed["lease"]["record_sha256"], runtime_id=runtime_id)
                if timestamp(release["released_at"]) > call[2]["observed_at"]:
                    fail("INVALID_ORDER", "lease 释放时间不能晚于命令观察")
                argv = call[0]["argv"]
                if "--runtime-binding" not in argv or "--release-receipt" not in argv:
                    fail("ARGV_MISMATCH", "绑定的 release 必须来自明确 bound release 入口")
                observed["lease"]["release_verified"] = True
                observed["lease"]["released_at"] = timestamp(release["released_at"])
    if accepted("delivery"):
        observed["delivery"] = delivery_facts(calls["delivery"][1], binding)
    if accepted("ack"):
        call, response, _ = calls["ack"]
        equal_identity(response["result"].get("runId"), binding["run"]["run_id"], "ack.runId")
        ack_id = call["argv"][call["argv"].index("--ack") + 1]
        equal_identity(response["result"].get("acknowledged"), ack_id, "ack.acknowledged")
        observed["acknowledged_delivery_id"] = ack_id
        if observed["delivery"]:
            equal_identity(ack_id, observed["delivery"]["delivery_id"], "ack.delivery_id")
            if summaries["ack"]["observed_at"] < summaries["delivery"]["observed_at"]:
                fail("INVALID_ORDER", "ack 观察不能早于原 Delivery")
    dates = [item["observed_at"] for item in summaries.values()]
    interval = {"earliest": min(dates) if dates else None, "latest": max(dates) if dates else None}
    payload = {"source": {"evidence_root": str(reader.root), "request": {"path": request_path.name, "sha256": raw_sha(request_raw)}},
               "expected_binding": binding, "binding_sha256": digest(binding), "observed": observed, "observed_interval": interval}
    reader.recheck()
    return envelope(SNAPSHOT, payload), reader


def derive(snapshot):
    payload = unwrap(snapshot, SNAPSHOT)
    binding, observed = payload["expected_binding"], payload["observed"]
    missing, actions = [], []
    target = {"run_id": binding["run"]["run_id"], "task_id": binding["task_id"], "dispatch_id": binding["dispatch_id"],
              "terminal_handle": binding["terminal_handle"], "session_id": binding["session_id"]}
    def need(code, subject, role, action="OBTAIN_FRESH_OBSERVATION", kind="READ_ONLY"):
        item = {"code": code, "subject": subject, "evidence_role": role}
        if item not in missing:
            missing.append(item)
        act = {"kind": kind, "action": action, "target": target, "reason_codes": [code], "argv": []}
        act["action_id"] = digest(act)
        if act not in actions:
            actions.append(act)
    for role in ("run", "tasks", "worker"):
        summary = observed["commands"].get(role)
        if summary is None:
            need("MISSING_COMMAND", role, role)
        elif not summary["accepted"]:
            need(summary["error_code"] or "COMMAND_FAILED", role, role, "RESTORE_EXACT_OWNER_AUTHORITY", "MANUAL")
    if "authority" in observed["commands"] and not observed["commands"]["authority"]["accepted"]:
        need(observed["commands"]["authority"]["error_code"] or "AUTHORITY_UNAVAILABLE", "authority", "authority", "RESTORE_EXACT_OWNER_AUTHORITY", "MANUAL")
    task, worker = observed["task"], observed["worker"]
    logical = False
    outcome = "UNKNOWN"
    terminal_loss = False
    terminal_released = False
    if task and worker and observed["run"]:
        ts, ds, ws = task["status"], worker["dispatch_status"], worker["worker_state"]
        terminal_loss = worker["worker_stage"] == "terminal_missing" and worker["terminal_observation"]["status"] == "missing"
        if ts == "completed" and ds == "completed" and ws == "succeeded":
            logical, outcome = True, "SUCCEEDED"
        elif ts == "failed" and ds == "failed" and ws in {"failed", "stopped", "abandoned"}:
            logical = True
            outcome = "INVALID_RUNTIME" if terminal_loss or ws == "abandoned" else "FAILED"
        elif ds == "failed" or ws in {"failed", "stopped", "abandoned"}:
            outcome = "INVALID_RUNTIME" if terminal_loss or ws == "abandoned" else "FAILED"
            need("TASK_DISPATCH_UNSETTLED", "logical_state", "tasks+worker", "RECONCILE_TASK_WITH_EXACT_OWNER", "MANUAL")
        elif ds in {"pending", "dispatched"} and ts in {"pending", "ready", "dispatched"} and ws in {"ready", "active"}:
            outcome = "RUNNING"
        else:
            need("LOGICAL_STATE_UNPROVEN", "logical_state", "tasks+worker", "INSPECT_EXACT_DISPATCH", "READ_ONLY")
        if not logical and outcome == "RUNNING":
            need("WORKER_STILL_ACTIVE", "logical_state", "worker", "WAIT_FOR_EXACT_WORKER", "READ_ONLY")
        resource = worker["terminal_resource"]
        terminal_released = terminal_is_released(worker)
        if not terminal_released:
            need("TERMINAL_RELEASE_UNPROVEN", "terminal", "worker.terminalResource", "ACCOUNT_EXACT_TERMINAL_WITH_OWNER", "MANUAL")
    else:
        need("LOGICAL_STATE_UNPROVEN", "logical_state", "run+tasks+worker")
        need("TERMINAL_RELEASE_UNPROVEN", "terminal", "worker.terminalResource")
    lease_info = observed["lease"]
    if binding["lease"]["requirement"] == "NONE_REQUIRED":
        lease_settled = lease_info is None
        if lease_info is not None:
            need("UNEXPECTED_LEASE", "lease", "lease_record", "INSPECT_EXACT_ALLOCATION", "MANUAL")
    else:
        lease_settled = bool(lease_info and lease_info["binding_verified"] and lease_info["release_verified"])
        if not lease_settled:
            code = "LEGACY_LEASE_UNBOUND" if lease_info and not lease_info["binding_verified"] else "LEASE_RELEASE_UNPROVEN"
            need(code, "lease", "lease_record+lease_release", "OBTAIN_EXACT_ALLOCATION_RELEASE_PROOF", "MANUAL")
    resources = terminal_released and lease_settled
    delivery = observed["delivery"]
    if binding["delivery"]["requirement"] == "NONE_REQUIRED":
        delivery_settled = terminal_loss and outcome == "INVALID_RUNTIME" and delivery is None and observed["acknowledged_delivery_id"] is None
        if not delivery_settled:
            need("DELIVERY_NONE_REQUIREMENT_UNPROVEN", "delivery", "worker", "INSPECT_DELIVERY_OBLIGATION", "MANUAL")
    else:
        delivery_settled = bool(delivery and observed["acknowledged_delivery_id"] == delivery["delivery_id"])
        if observed["acknowledged_delivery_id"]:
            resource_time = (worker or {}).get("terminal_resource") or {}
            required_times = [resource_time.get("releaseCompletedAt"), (lease_info or {}).get("released_at")]
            if any(value and value > observed["commands"]["ack"]["observed_at"] for value in required_times):
                delivery_settled = False
                need("ACK_PRECEDES_RESOURCE_SETTLEMENT", "delivery", "ack+worker+lease", "ACK_EXACT_HANDLED_DELIVERY_WITH_OWNER", "MANUAL")
        if not delivery:
            need("MISSING_COMPLETE_DELIVERY", "delivery", "delivery")
        else:
            expected_outcome = "succeeded" if outcome == "SUCCEEDED" else "failed" if outcome in {"FAILED", "INVALID_RUNTIME"} else None
            for message in delivery["messages"]:
                if not message["target_worker_done"]:
                    delivery_settled = False
                    need("UNHANDLED_BATCH_MESSAGE", message["message_id"], "delivery", "PROCESS_EVERY_BATCH_MESSAGE_WITH_ITS_OWNER", "MANUAL")
                elif expected_outcome is None or message["outcome"] != expected_outcome or not logical or not resources:
                    delivery_settled = False
                    need("WORKER_DONE_NOT_ACCOUNTED", message["message_id"], "delivery+worker", "ACCOUNT_EXACT_WORKER_BEFORE_ACK", "MANUAL")
        if not observed["acknowledged_delivery_id"]:
            need("ACK_NOT_CONFIRMED", "delivery", "ack", "ACK_EXACT_HANDLED_DELIVERY_WITH_OWNER", "MANUAL")
    complete = logical and resources and delivery_settled and not missing
    return {"expected_binding": binding, "binding_sha256": payload["binding_sha256"], "observed": observed,
            "observed_interval": payload["observed_interval"], "effective_outcome": outcome,
            "logical_settled": logical, "resources_settled": resources, "delivery_settled": delivery_settled,
            "complete": complete, "settlement_state": "SETTLED" if complete else "UNSETTLED",
            "missing_evidence": sorted(missing, key=lambda v: (v["code"], v["subject"], v["evidence_role"])),
            "next_actions": sorted(actions, key=lambda v: v["action_id"]), "enforcement_boundary": "captured_local_evidence_only"}


def verify_snapshot(path):
    path = checked(Path(path).absolute())
    raw = read(path); saved = parse(raw); payload = unwrap(saved, SNAPSHOT)
    source = obj(payload.get("source"), {"evidence_root", "request"})
    root = checked(Path(text(source["evidence_root"])), directory=True)
    request = obj(source["request"], {"path", "sha256"})
    request_path = root / relative(request["path"])
    if raw_sha(read(request_path)) != sha_value(request["sha256"]):
        fail("HASH_MISMATCH", "snapshot 的原 request 已漂移")
    expected, reader = build_snapshot(request_path)
    reader.file(path)
    if not same(saved, expected):
        fail("SNAPSHOT_DRIFT", "snapshot 未由当前原始证据推导")
    return saved, raw, reader


@guarded
def observe(request_path, output_path):
    snapshot, reader = build_snapshot(request_path)
    action = publish(output_path, snapshot)
    return {"ok": True, "action": action, "snapshot_path": str(Path(output_path).absolute()),
            "observation_sha256": snapshot["sha256"], "expected_binding": snapshot["payload"]["expected_binding"],
            "binding_sha256": snapshot["payload"]["binding_sha256"], "observed_interval": snapshot["payload"]["observed_interval"],
            "lifecycle_mutations": False, "dependencies": reader.refs()}


@guarded
def reconcile(snapshot_path, output_path):
    snapshot, raw, reader = verify_snapshot(snapshot_path)
    payload = derive(snapshot)
    payload["snapshot"] = {"path": str(Path(snapshot_path).absolute()), "sha256": raw_sha(raw)}
    receipt = envelope(RECEIPT, payload)
    reader.recheck()
    action = publish(output_path, receipt)
    return {"ok": True, "action": action, "receipt_path": str(Path(output_path).absolute()),
            "receipt_sha256": raw_sha(canonical(receipt) + b"\n"), "observation_sha256": snapshot["sha256"],
            **payload, "lifecycle_mutations": False, "dependencies": reader.refs()}


@guarded
def verify(receipt_path):
    receipt_path = checked(Path(receipt_path).absolute())
    raw = read(receipt_path); value = parse(raw); payload = unwrap(value, RECEIPT)
    ref = obj(payload.get("snapshot"), {"path", "sha256"})
    snapshot, snapshot_raw, reader = verify_snapshot(Path(text(ref["path"])))
    if raw_sha(snapshot_raw) != sha_value(ref["sha256"]):
        fail("HASH_MISMATCH", "receipt snapshot 字节已漂移")
    expected = {**derive(snapshot), "snapshot": ref}
    if not same(expected, payload):
        fail("RECEIPT_DRIFT", "receipt 决策不能由原始证据重新推导")
    reader.file(receipt_path)
    reader.recheck()
    return {"ok": True, "verified": True, "receipt_sha256": raw_sha(raw), "observation_sha256": snapshot["sha256"],
            **expected, "lifecycle_mutations": False, "dependencies": reader.refs()}
