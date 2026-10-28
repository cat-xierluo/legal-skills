#!/usr/bin/env python3
"""入卷前机械预检：私有材料泄露、非公开引用与未核验法条编号。

只做可重复的字符串与集合比对，不判断证明力、不评价观点强弱、
不判断法条是否真的适用。实体与法源语义由原法官会话审查并记录，
庭后独立复核复查；主控只转交机械信号和执行落盘。

预检报告只给出私有材料的序号与命中长度，不回显私有编号、标题或原文；
主控不得把报告粘贴到 cancel --reason、角色上下文或公开笔录。
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PRIVATE_ID = "MC-PRIVATE-ID"
PRIVATE_TEXT = "MC-PRIVATE-TEXT"
PRIVATE_TERM = "MC-PRIVATE-TERM"
PRIVATE_CITATION = "MC-PRIVATE-CITATION"
LAW_UNCITED = "MC-LAW-UNCITED"

# 只认「第X条」与「第X条第Y款」。「第X项」在正文里常指列表、问题或段落编号，
# 误报远多于收益，故不纳入。
LAW_ARTICLE = re.compile(
    r"第[零一二三四五六七八九十百千0-9]{1,6}条(?:第[零一二三四五六七八九十百千0-9]{1,6}款)?")
CONTRACT_CONTEXT = ("合同", "协议", "约定", "条款", "本约", "合约", "契约")
SHINGLE = 10
MAX_FINDINGS_PER_RULE = 5


def fail(message):
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(2)


def read_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"{label}无法读取完整 JSON：{path}（{type(exc).__name__}）")


def validate_documents(documents, label):
    if not isinstance(documents, list):
        fail(f"{label}.documents 必须是数组")
    ids = set()
    for index, doc in enumerate(documents, start=1):
        if not isinstance(doc, dict):
            fail(f"{label} 第 {index} 项不是对象")
        for key in ("id", "title", "text"):
            if key not in doc:
                fail(f"{label} 第 {index} 项缺少 {key}")
            if not isinstance(doc[key], str) or not doc[key].strip():
                fail(f"{label} 第 {index} 项 {key} 必须为非空文本")
        if doc["id"] in ids:
            fail(f"{label} 材料编号重复")
        ids.add(doc["id"])
        audience = doc.get("visible_to")
        if (not isinstance(audience, list) or not audience or
                not all(isinstance(role, str) and role for role in audience)):
            fail(f"{label} 第 {index} 项 visible_to 必须是非空文本数组")
        if len(set(audience)) != len(audience) or ("all" in audience and audience != ["all"]):
            fail(f"{label} 第 {index} 项 visible_to 公开标记或重复角色不合法")


def validate_packet(packet):
    if not isinstance(packet, dict):
        fail("packet 顶层必须是 JSON 对象")
    validate_documents(packet.get("documents"), "packet")
    assignment = packet.get("assignment")
    if assignment is not None and not isinstance(assignment, dict):
        fail("packet.assignment 必须是对象")


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        fail("manifest 顶层必须是 JSON 对象")
    validate_documents(manifest.get("documents"), "manifest")


def validate_submission(submission):
    if not isinstance(submission, dict):
        fail("submission 顶层必须是 JSON 对象")
    body = submission.get("body")
    if not isinstance(body, str) or not body.strip():
        fail("submission.body 必须是非空文本")
    citations = submission.get("citations", [])
    if not isinstance(citations, list) or not all(isinstance(c, str) for c in citations):
        fail("submission.citations 必须是文本数组")


def bind_packet_and_submission(packet, submission):
    """packet 与提交稿必须属于同一回合；避免用陈旧 packet 得到无意义结果。"""
    assignment = packet.get("assignment")
    if not isinstance(assignment, dict):
        fail("packet 缺少 assignment")
    for key in ("schema_version", "run_id", "turn_id", "role", "material_version",
                "read_through", "responds_to"):
        if key not in assignment or key not in submission:
            fail(f"packet 或 submission 缺少派发字段：{key}")
        if type(submission[key]) is not type(assignment[key]) or submission[key] != assignment[key]:
            fail(f"packet 与 submission 的 {key} 不一致；请使用同一回合的原样 packet")


def bind_manifest(packet, manifest):
    role = packet["assignment"]["role"]
    expected = [doc for doc in manifest["documents"]
                if doc["visible_to"] == ["all"] or role in doc["visible_to"]]
    expected_by_id = {doc["id"]: doc for doc in expected}
    actual_by_id = {doc["id"]: doc for doc in packet["documents"]}
    if actual_by_id != expected_by_id:
        fail("manifest 与本轮 packet 材料不一致；请使用派发时的完整材料快照")


def load_run_state(run):
    """复用书记员的只读事件校验与回放，避免在预检里另造一套协议解析。"""
    # 该脚本可能由用户直接运行而不带 -B；禁止 import 在 Skill 源码树生成 pyc。
    sys.dont_write_bytecode = True
    try:
        import clerk
    except ImportError as exc:
        fail(f"无法加载书记员模块：{type(exc).__name__}")
    try:
        events = clerk.load_events(run)
        state = clerk.replay(events)
        clerk.manifest_check(state["manifest"], state["roles"])
    except clerk.ClerkError as exc:
        fail(f"run 事件链校验失败：{exc}")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        fail(f"run 事件或材料结构损坏：{type(exc).__name__}")
    return clerk, state, events[-1]


def bind_run(packet, manifest, run):
    """绑定当前事件前缀、材料版本与当前派发；仅使用书记员的只读函数。"""
    clerk, state, last_event = load_run_state(run)
    if state.get("closed") is not None:
        fail("run 已关闭；不能再进行入卷前预检")
    if state.get("active") is None:
        fail("run 当前没有待处理派发；packet 可能已取消、已入卷或已过期")
    if clerk.canonical(manifest) != clerk.canonical(state["manifest"]):
        fail("--manifest 与 run 事件链当前材料不一致；请使用派发时的完整快照")
    if clerk.canonical(packet["assignment"]) != clerk.canonical(state["active"]):
        fail("packet 与 run 当前派发不一致；请使用本 run 当前回合的原样 packet")
    return {
        "status": "RUN_BOUND_PREFIX_ONLY",
        "run_id": state["run_id"],
        "material_version": state["material_version"],
        "manifest_sha256": clerk.digest(state["manifest"]),
        "observed_event_seq": last_event["seq"],
        "observed_event_sha256": last_event["hash"],
        "event_chain_scope": "VALIDATED_PREFIX",
        "tail_anchor": "NOT_AVAILABLE",
    }


def split_visibility(documents):
    """公开稿只以 visible_to == ["all"] 为可引用范围。

    多方可见不等于 ["all"]；公开稿会经 history 传播到全体角色。
    要披露这类材料，先更新完整清单为 ["all"] 并重派，沿用书记员的引用规则。
    """
    public, private = [], []
    for doc in documents:
        (public if doc.get("visible_to") == ["all"] else private).append(doc)
    return public, private


def compact(text):
    return re.sub(r"\s+", "", text)


def load_private_terms(path, manifest, private_docs):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        raw = Path(path).read_bytes()
        policy = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, ValueError, RecursionError):
        fail("私有词项策略无法读取或 JSON 不合法")
    if not isinstance(policy, dict) or set(policy) != {"schema", "manifest_sha256", "rules"}:
        fail("私有词项策略顶层结构不合法")
    if policy["schema"] != "moot-court-private-terms-v1":
        fail("私有词项策略 schema 不合法")
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")).encode("utf-8")
    if policy["manifest_sha256"] != hashlib.sha256(manifest_bytes).hexdigest():
        fail("私有词项策略清单摘要不匹配")
    if not isinstance(policy["rules"], list):
        fail("私有词项策略 rules 必须是数组")
    private_index = {doc["id"]: index for index, doc in enumerate(private_docs, 1)}
    seen_ids = set()
    prepared = []
    for rule in policy["rules"]:
        if not isinstance(rule, dict) or set(rule) != {"material_id", "terms"}:
            fail("私有词项策略规则结构不合法")
        material_id, terms = rule["material_id"], rule["terms"]
        if not isinstance(material_id, str) or material_id not in private_index:
            fail("私有词项策略材料未知或非私有")
        if material_id in seen_ids:
            fail("私有词项策略材料重复")
        seen_ids.add(material_id)
        if not isinstance(terms, list) or not terms:
            fail("私有词项策略 terms 必须是非空数组")
        normalized = set()
        for term in terms:
            if not isinstance(term, str):
                fail("私有词项策略词项类型不合法")
            term = compact(term)
            if not 4 <= len(term) <= 256 or term in normalized:
                fail("私有词项策略词项长度或重复不合法")
            normalized.add(term)
        prepared.append((private_index[material_id], normalized))
    return prepared, {"status": "MANIFEST_BOUND",
                      "policy_sha256": hashlib.sha256(raw).hexdigest(),
                      "rule_count": len(prepared)}


def find_private_terms(body, rules, public_docs):
    body = compact(body)
    public_texts = [compact(doc["text"]) for doc in public_docs]
    hits = []
    for index, terms in rules:
        rule_hits = []
        for term in sorted(terms):
            if term in body and not any(term in text for text in public_texts):
                rule_hits.append({"doc_ref": f"private_doc_{index}", "matched_chars": len(term)})
        hits.extend(rule_hits[:MAX_FINDINGS_PER_RULE])
    return hits


def shingles(text, size=SHINGLE):
    return {text[i:i + size] for i in range(max(0, len(text) - size + 1))}


def find_private_ids(body, private_docs):
    hits = []
    for index, doc in enumerate(private_docs, start=1):
        doc_id = doc["id"]
        # 编号按完整 token 比对，P-001 不误伤公开编号 P-0010。标题常是通用词，
        # 不再作为机械硬阻断条件。
        pattern = r"(?<![A-Za-z0-9_-])" + re.escape(doc_id) + r"(?![A-Za-z0-9_-])"
        if re.search(pattern, body):
            hits.append({"doc_ref": f"private_doc_{index}", "matched_chars": len(doc_id)})
    return hits[:MAX_FINDINGS_PER_RULE]


def find_private_text(body, private_docs, public_shingles):
    body_compact = compact(body)
    body_shingles = shingles(body_compact)
    hits = []
    for index, doc in enumerate(private_docs, start=1):
        # 仅比较私有材料独有的 10 字窗口，避免备忘引用公开原文时被误报。
        # 集合比对随文本长度增长，不截断长材料以换取速度。
        private_windows = shingles(compact(doc["text"])) - public_shingles
        if private_windows & body_shingles:
            hits.append({"doc_ref": f"private_doc_{index}", "matched_chars": SHINGLE})
    return hits[:MAX_FINDINGS_PER_RULE]


def find_private_citations(citations, public_ids):
    hits = []
    for index, citation in enumerate(citations, start=1):
        if citation not in public_ids:
            hits.append({"citation_ref": f"citation_{index}"})
    return hits[:MAX_FINDINGS_PER_RULE]


def find_unverified_law(body, public_compact):
    body_compact = compact(body)
    hits = set()
    for match in LAW_ARTICLE.finditer(body_compact):
        token = match.group(0)
        sentence_start = max(body_compact.rfind(mark, 0, match.start())
                             for mark in "。；!?") + 1
        prefix = body_compact[max(sentence_start, match.start() - 20):match.start()]
        if any(word in prefix for word in CONTRACT_CONTEXT) and not re.search(
                r"《[^》]+》|(?:法|条例|规定|解释)(?:第[零一二三四五六七八九十百千0-9]+条)?[^。；!?]*$",
                prefix):
            continue
        if token not in public_compact:
            hits.add(token)
    return sorted(hits)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="入卷前机械预检：私有材料泄露、非公开引用与未核验法条编号"
                    "（不判断法律语义；报告不回显私有内容）")
    parser.add_argument("--packet", required=True, help="dispatch 返回的原样 packet JSON")
    parser.add_argument("--manifest", required=True,
                        help="本次运行当前完整材料清单；仅凭角色 packet 无法发现他方私有材料")
    parser.add_argument("--run", default=None,
                        help="可选：只读校验书记员现存事件前缀，将完整清单与该前缀中的派发核对；"
                             "无独立尾部锚点，不能检测尾部删除或目录回滚")
    parser.add_argument("--submission", required=True, help="角色提交稿 JSON")
    parser.add_argument("--private-terms", default=None, help="可选：主控私有词项策略 JSON")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    args = parser.parse_args(argv)

    try:
        packet = read_json(args.packet, "packet")
        manifest = read_json(args.manifest, "manifest")
        submission = read_json(args.submission, "submission")
        validate_packet(packet)
        validate_manifest(manifest)
        validate_submission(submission)
        bind_packet_and_submission(packet, submission)
        manifest_binding = {"status": "SNAPSHOT_ONLY"}
        if args.run:
            run_dir = Path(args.run).expanduser()
            if not run_dir.is_dir():
                fail(f"run 目录不存在：{run_dir}")
            manifest_binding = bind_run(packet, manifest, run_dir)
        bind_manifest(packet, manifest)

        public_docs, private_docs = split_visibility(manifest["documents"])
        private_terms = []
        private_terms_binding = {"status": "NOT_PROVIDED"}
        if args.private_terms is not None:
            private_terms, private_terms_binding = load_private_terms(
                args.private_terms, manifest, private_docs)
        public_corpus = "\n".join(
            "\n".join((doc["text"], doc["title"], doc["locator"]))
            for doc in public_docs
        )
        public_compact = compact(public_corpus)
        public_shingles = set()
        for doc in public_docs:
            public_shingles.update(shingles(compact(doc["text"])))
        public_ids = {doc["id"] for doc in public_docs}
        body = submission["body"]

        findings = []
        for hit in find_private_ids(body, private_docs):
            findings.append({
                "rule": PRIVATE_ID,
                "severity": "block",
                "detail": f"公开稿出现 {hit['doc_ref']} 的标识形态"
                          f"（{hit['matched_chars']} 字）；具体编号不回显",
            })
        for hit in find_private_text(body, private_docs, public_shingles):
            findings.append({
                "rule": PRIVATE_TEXT,
                "severity": "block",
                "detail": f"公开稿命中 {hit['doc_ref']} 的私有原文"
                          f"（至少 {hit['matched_chars']} 字）；原文不回显",
            })
        for hit in find_private_terms(body, private_terms, public_docs):
            findings.append({
                "rule": PRIVATE_TERM,
                "severity": "block",
                "detail": f"公开稿命中 {hit['doc_ref']} 的登记词项"
                          f"（{hit['matched_chars']} 字）；词项不回显",
            })
        for hit in find_private_citations(submission.get("citations", []), public_ids):
            findings.append({
                "rule": PRIVATE_CITATION,
                "severity": "block",
                "detail": f"citations 的 {hit['citation_ref']} 指向非公开或未知材料编号；编号不回显",
            })
        for token in find_unverified_law(body, public_compact):
            findings.append({
                "rule": LAW_UNCITED,
                "severity": "warn",
                "detail": (f"法条编号「{token}」未见于任何公开材料，案卷内没有可核验的法源原文"
                           if args.private_terms is None else
                           "法条编号未见于任何公开材料，案卷内没有可核验的法源原文"),
            })

        blocked = [finding for finding in findings if finding["severity"] == "block"]
        result = {
            "ok": not blocked,
            "blocked": len(blocked),
            "warnings": len(findings) - len(blocked),
            "public_docs_considered": len(public_docs),
            "private_docs_considered": len(private_docs),
            "findings": findings,
            "manifest_binding": manifest_binding,
            "private_terms_binding": private_terms_binding,
            "note": "仅机械比对；不判断证明力、法条适用或观点强弱。"
                    "登记词项仅逐字匹配，不代表全面语义检测；"
                    "每组私有材料的词项命中最多列示5条，blocked按列示项计数；"
                    "未提供 --run 时清单仅为调用方快照，不能证明与书记员当前版本绑定；"
                    "提供 --run 时也只证明当前可见事件前缀，协议没有独立尾部锚点，"
                    "不能发现尾部事件整段删除或目录回滚；"
                    "报告已隐去私有编号与原文，不得粘贴进公开笔录、cancel 原因或角色上下文。",
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for finding in findings:
                mark = "阻断" if finding["severity"] == "block" else "提示"
                print(f"[{mark}] {finding['rule']}：{finding['detail']}")
            binding = manifest_binding["status"]
            if manifest_binding.get("event_chain_scope"):
                binding += f"（{manifest_binding['event_chain_scope']}）"
            print(f"清单绑定：{binding}")
            print(f"私有词项策略：{private_terms_binding['status']}")
            if args.private_terms is not None:
                print(f"策略文件 SHA-256：{private_terms_binding['policy_sha256']}；"
                      f"规则数量：{private_terms_binding['rule_count']}")
            if args.run:
                print("绑定范围：仅本次读取到的事件前缀；无独立尾部锚点，不能检测尾部删除或目录回滚。")
            else:
                print("绑定范围：仅调用方快照；未与书记员运行核对。")
            print("通过：未发现阻断项" if not blocked else f"未通过：{len(blocked)} 项阻断")
        return 1 if blocked else 0
    except SystemExit:
        raise
    except (TypeError, AttributeError, KeyError, ValueError, OSError) as exc:
        fail(f"输入结构损坏或无法处理：{type(exc).__name__}")


if __name__ == "__main__":
    sys.exit(main())
