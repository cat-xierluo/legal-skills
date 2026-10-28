#!/usr/bin/env python3
"""Runtime 候选包准备器：从生产 Skill 显式抽出全新候选目录与任务输入。

只做文件级准备：复制显式允许集、原样带入合成案卷、展开统一任务占位符，
并记录可复算摘要。不启动宿主、不联网、不安装依赖、不代写角色发言，
不签 G5 或 DOMAIN_VERIFIED。目录筛选只界定可见内容，不构成工具权限隔离；
宿主侧仍须按书记员协议控制 packet 与可见范围。

占位符契约：task-file 必须至少各含一个 {skill_dir}、{manifest}、{run_dir}，可重复；
只对这三个做全量定点字符串替换（不 eval、不 format）。出现其他 {token} 默认按
fail-closed 拒绝；确属任务文本的加 --allow-unknown-placeholders 原样保留并记录。
{run_dir} 默认展开为 <bundle>/hearing（不创建；书记员 init 接受不存在或完全为空的
目录，混入其他材料即拒）。--run-dir 只接受源 Skill 与 bundle/skill 之外的全新绝对
路径，同样不创建。
链接核验：候选 markdown 的相对 inline 链接与相对图片逐条解析；外部 URL、mailto 与
锚点跳过（不联网）；绝对路径目标拒绝；引用式链接、快捷链接、链接定义、脚注、自动
链接与转义方括号等形态不在核验能力内，出现即 fail-closed 拒绝——不宣称覆盖任意
Markdown。
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

SCHEMA_VERSION = 1
BUNDLE_KIND = "moot-court.runtime-candidate.v1"
PROJECTION_KIND = "moot-court.skill.dev-commands-paragraph.v1"
DEV_MARKER = "开发验证命令："
DEFAULT_RUN_DIR_NAME = "hearing"
PLACEHOLDERS = ("skill_dir", "manifest", "run_dir")
ALLOWED_REF_NAMES = (
    "checklist.md",
    "civil-hearing.md",
    "clerk-protocol.md",
    "criminal-hearing.md",
    "drill.md",
    "fixed-role-hearing-audit.md",
    "information-model.md",
    "intake.md",
    "procedure-profiles.md",
    "research-methods.md",
    "review-rubric.md",
    "role-profiles.md",
    "runtime-adapters.md",
    "runtime-validation.md",
    "templates.md",
)

# 显式允许集：不递归全拷。源中其余文件一律不带入并如实记入 excluded_paths。
ALLOWED_PATHS = (
    "SKILL.md",
    "LICENSE.txt",
    *(f"references/{name}" for name in ALLOWED_REF_NAMES),
    "scripts/audit_fixed_role_hearing.py",
    "scripts/audit_workbuddy_trace.py",
    "scripts/clerk.py",
    "scripts/presubmit_check.py",
    "assets/civil-case.example.json",
    "assets/criminal-case.example.json",
)
assert len(ALLOWED_PATHS) == len(set(ALLOWED_PATHS)), "内部不变量：允许集不得重复"

# 投影后 SKILL.md 不得再出现的排除内容引用（链接或裸文件名均视为断链/引向评测侧）。
SKILL_FORBIDDEN_TOKENS = (
    "evaluation.md", "blind-probe.md", "semantic-probe-reviewer",
    "claude-stream", "index_claude_trace", "prepare_probe",
    "test_clerk", "test_presubmit_check", "test_index_claude_trace",
    "test_prepare_probe", "TASKS.md", "CHANGELOG.md", "DECISIONS.md",
)

MARKDOWN_TOKEN = re.compile(
    r"!?\[(?P<text>[^\]\n]*)\]\(\s*<?(?P<target>[^<>\n)]*?)>?"
    r"(?:\s+[\"'][^\"']*[\"'])?\s*\)")
ESCAPED_BRACKET = re.compile(r"\\[\[\]]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE_LINE = re.compile(r"^(?: {0,3})(?:```|~~~)")
CODE_SPAN = re.compile(r"`+[^`\n]*`+")
REFERENCE_USE = re.compile(r"\[[^\]\n]+\]\[[^\]\n]*\]")
SHORTCUT_USE = re.compile(r"\[[^\]\n]+\](?!\()")
LINK_DEFINITION = re.compile(r"^[ ]{0,3}\[[^\]\n]+\]:", re.MULTILINE)
FOOTNOTE_USE = re.compile(r"\[\^[^\]\n]+\]")
FOOTNOTE_DEF = re.compile(r"^[ ]{0,3}\[\^[^\]\n]+\]:", re.MULTILINE)
AUTOLINK = re.compile(r"<[A-Za-z][A-Za-z0-9+.\-]*:[^<>\n]*>")
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


class PrepareError(Exception):
    """可预期的拒绝原因：统一 exit 2 并输出中文说明，不让 Traceback 泄漏到宿主。"""


def require(condition, message):
    if not condition:
        raise PrepareError(message)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path, label):
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PrepareError(f"{label}无法读取：{type(exc).__name__}") from exc


def decode_utf8(data, label):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PrepareError(f"{label}不是 UTF-8 文本，拒绝带入候选") from exc


def list_source_files(skill_dir):
    """不跟随 symlink 地列出源目录全部文件；symlink 单列，允许集命中即拒绝。"""
    files, symlinks = [], []
    for current, dirs, names in os.walk(str(skill_dir), followlinks=False):
        dirs[:] = sorted(dirs)
        base = Path(current)
        for name in sorted(names):
            path = base / name
            rel = path.relative_to(skill_dir).as_posix()
            if path.is_symlink():
                symlinks.append(rel)
            elif path.is_file():
                files.append(rel)
    return sorted(files), sorted(symlinks)


def check_allowed_sources(skill_dir, present, symlinks):
    """允许集逐项：存在、常规、自身非 symlink。

    源树内部 symlink 目录不会被 walk 跟随，其下允许文件因此缺席 present，
    由缺文件分支拒绝；不为此发明额外的目录级豁免逻辑。
    """
    bad_links = [rel for rel in ALLOWED_PATHS if rel in symlinks]
    require(not bad_links, "允许源文件是 symlink，拒绝：" + ", ".join(bad_links))
    missing = [rel for rel in ALLOWED_PATHS if rel not in present]
    require(not missing, "允许集缺文件，拒绝准备（不盲删引用依赖）：" + ", ".join(missing))
    for rel in ALLOWED_PATHS:
        require(".." not in Path(rel).parts, f"允许路径含异常组件：{rel}")


def project_skill(text):
    """唯一、有限、fail-closed：只剔除以“开发验证命令：”开头的整段。"""
    positions = [m.start() for m in re.finditer(re.escape(DEV_MARKER), text)]
    require(len(positions) == 1,
            f"SKILL.md 中“{DEV_MARKER}”出现 {len(positions)} 次，无法唯一定位，交回 PM 处理")
    start = positions[0]
    require(start == 0 or text[start - 1] == "\n",
            f"“{DEV_MARKER}”不在行首，剔除将伤及正文，交回 PM 处理")
    require(start == 0 or text[max(0, start - 2):start] == "\n\n",
            f"“{DEV_MARKER}”不是独立段落起始，交回 PM 处理")
    ends = [i for i in (text.find("\n\n", start), text.find("\n# ", start)) if i != -1]
    end = min(ends) if ends else len(text)
    paragraph = text[start:end]
    require(bool(paragraph.strip()) and "\n\n" not in paragraph,
            "开发验证段落边界异常，交回 PM 处理")
    head = text[:start]
    collapsed = False
    if end == len(text):
        removal_end = len(text)
        if head.endswith("\n\n"):
            head = head[:-1]
            collapsed = True
    else:
        removal_end = end + 2
    projected = head + text[removal_end:]
    hits = [token for token in SKILL_FORBIDDEN_TOKENS if token in projected]
    require(not hits, "投影后 SKILL.md 仍引用排除内容，拒绝：" + ", ".join(hits))
    projection = {
        "kind": PROJECTION_KIND,
        "marker": DEV_MARKER,
        "operation": "remove-single-paragraph",
        "paragraph_chars": len(paragraph),
        "trailing_blank_line_collapsed": collapsed,
        "before_sha256": sha256_hex(text.encode("utf-8")),
        "after_sha256": sha256_hex(projected.encode("utf-8")),
        "note": "候选 SKILL.md 仅剔除该段；其余字节与源一致。",
    }
    return projected, projection


def validate_task_text(text):
    counts = {}
    for match in PLACEHOLDER.finditer(text):
        counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    unknown = sorted(set(counts) - set(PLACEHOLDERS))
    for name in PLACEHOLDERS:
        require(counts.get(name, 0) >= 1,
                "task-file 必须至少各含一个 {skill_dir}、{manifest}、{run_dir}；"
                f"实际 {{{name}}} 出现 {counts.get(name, 0)} 次")
    return counts, unknown


def expand_task(text, values):
    expanded = text
    for name in PLACEHOLDERS:
        expanded = expanded.replace("{" + name + "}", values[name])
    leftover = sorted({m.group(1) for m in PLACEHOLDER.finditer(expanded)} & set(PLACEHOLDERS))
    require(not leftover, "展开后仍残留已定义占位符：" + ", ".join(leftover))
    return expanded


def strip_non_prose(text):
    """去掉围栏代码块、HTML 注释与行内代码：其中的方括号/尖括号不是链接语法。"""
    lines = text.split("\n")
    out = []
    fence = None
    for line in lines:
        if fence is not None:
            if line.strip().startswith(fence) and line.strip().lstrip(fence[0]).strip() == "":
                fence = None
            continue
        match = FENCE_LINE.match(line)
        if match:
            fence = match.group(0).strip()[0] * 3
            continue
        out.append(line)
    prose = "\n".join(out)
    prose = HTML_COMMENT.sub(" ", prose)
    return CODE_SPAN.sub(" ", prose)


def unsupported_markdown_forms(text):
    """核验器不支持、且可能藏匿未核验链接的形态；出现即拒绝（fail-closed）。"""
    scan = ESCAPED_BRACKET.sub("", strip_non_prose(text))
    forms = []
    if ESCAPED_BRACKET.search(strip_non_prose(text)):
        forms.append("转义方括号")
    if LINK_DEFINITION.search(scan):
        forms.append("链接定义")
    if FOOTNOTE_DEF.search(scan) or FOOTNOTE_USE.search(scan):
        forms.append("脚注")
    if REFERENCE_USE.search(scan):
        forms.append("引用式链接")
    elif SHORTCUT_USE.search(scan):
        forms.append("快捷链接")
    for match in MARKDOWN_TOKEN.finditer(scan):
        if scan[match.end():match.end() + 1] == "[":
            forms.append("引用式链接")
    scan = MARKDOWN_TOKEN.sub(" ", scan)
    scan = AUTOLINK.sub(" ", scan)
    if "[" in scan or "]" in scan:
        forms.append("无法归类的方括号语法")
    return sorted(set(forms))


def inline_targets(text):
    """返回 (kind, raw_target, absolute)：kind ∈ {link, image}；图片与链接同等核验。"""
    targets = []
    for match in MARKDOWN_TOKEN.finditer(text):
        image = match.group(0).startswith("!")
        kind = "image" if image else "link"
        target = match.group("target").strip()
        if not target or target.startswith("#"):
            continue
        if target.startswith("/"):
            targets.append((kind, target, True))
            continue
        if SCHEME.match(target):
            continue
        target = target.split("#", 1)[0].strip()
        if target:
            targets.append((kind, target, False))
    return targets


def check_links(candidate_texts):
    """投影后候选 markdown 的相对链接与相对图片必须解析到在包文件上；不支持的
    Markdown 形态与绝对路径目标一律拒绝；外部 URL、mailto 与锚点跳过，不联网。"""
    names = set(candidate_texts)
    checked = []
    for source, text in sorted(candidate_texts.items()):
        if not source.endswith(".md"):
            continue
        forms = unsupported_markdown_forms(text)
        require(not forms,
                f"候选 markdown 含链接核验器不支持的形态（{', '.join(forms)}），"
                f"无法证明不含未核验链接，拒绝：{source}")
        base_dir = str(Path(source).parent)
        # 目标在剥离围栏/注释/行内代码后的正文上抽取：其中的方括号不是链接语法。
        for kind, raw, absolute in inline_targets(strip_non_prose(text)):
            label = "图片" if kind == "image" else "链接"
            require(not absolute,
                    f"候选{label}核验拒绝绝对路径目标：{source} → {raw}")
            joined = os.path.normpath(os.path.join(base_dir, raw)).replace(os.sep, "/")
            require(not joined.startswith("../") and joined != "..",
                    f"候选{label}逃出 skill 目录：{source} → {raw}")
            require(joined in names,
                    f"候选{label}指向未带入内容（断链）：{source} → {raw}（解析为 {joined}）")
            checked.append({"source": source, "kind": kind, "target": joined})
    return checked


class Tracker:
    """仅清理本次创建且身份未改变的文件、空目录；不爬升到未登记的祖先。"""

    def __init__(self):
        self.files = []
        self.dirs = []

    def cleanup(self):
        for path, identity in reversed(self.files):
            try:
                stat = path.lstat()
                if (stat.st_dev, stat.st_ino) == identity:
                    path.unlink()
            except OSError:
                pass
        for path, identity in reversed(self.dirs):
            try:
                stat = path.lstat()
                if (stat.st_dev, stat.st_ino) == identity:
                    path.rmdir()
            except OSError:
                pass

    def directory(self, path):
        stat = path.lstat()
        self.dirs.append((path, (stat.st_dev, stat.st_ino)))


def ensure_dir(path, bundle_root, tracker):
    """只创建 bundle 根之下的目录；创建前逐级拒绝 symlink 组件。"""
    require(path == bundle_root or bundle_root in path.parents,
            f"内部不变量：越出 bundle 的目录不予创建：{path}")
    parents = []
    current = path
    while not current.exists():
        require(not current.is_symlink(), f"输出目录组件是 symlink，拒绝：{current.name}")
        parents.append(current)
        current = current.parent
    for directory in reversed(parents):
        directory.mkdir(exist_ok=False, mode=0o700)
        tracker.directory(directory)


def write_new(path, data, tracker):
    handle = None
    try:
        handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PrepareError(f"输出文件已存在，拒绝覆盖：{path.name}") from exc
    except OSError as exc:
        raise PrepareError(f"无法创建 {path.name}：{type(exc).__name__}") from exc
    stat = os.fstat(handle)
    tracker.files.append((path, (stat.st_dev, stat.st_ino)))
    try:
        with os.fdopen(handle, "wb") as stream:
            handle = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise PrepareError(f"写入 {path.name} 失败：{type(exc).__name__}") from exc
    finally:
        if handle is not None:
            os.close(handle)


def canonical_core(core):
    return json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def reject_symlink_ancestors(probe, label):
    """显式路径（输入与输出）的既有祖先组件不允许 symlink；macOS 系统级软链
    （/var、/tmp → /private/*）豁免——其真实落点仍由 realpath 包含判定兜底。"""
    for ancestor in probe.parents:
        if not ancestor.is_symlink():
            continue
        name = ancestor.name
        real = os.path.realpath(str(ancestor))
        if name in ("var", "tmp") and real.endswith(os.sep + "private" + os.sep + name):
            continue
        raise PrepareError(f"{label} 的祖先组件是 symlink，拒绝：{ancestor}")


def resolve_inputs(args):
    def abs_path(raw, label):
        require(str(raw).strip(), f"--{label} 不能为空")
        return Path(raw).expanduser().absolute()

    skill_dir = abs_path(args.skill_dir, "skill-dir")
    manifest = abs_path(args.manifest, "manifest")
    task_file = abs_path(args.task_file, "task-file")
    require(str(args.output).strip(), "--output 不能为空")
    output = Path(args.output).expanduser().absolute()
    return skill_dir, manifest, task_file, output


def check_locations(skill_dir, manifest, task_file, output):
    require(not skill_dir.is_symlink(), f"--skill-dir 本身是 symlink，拒绝：{skill_dir}")
    reject_symlink_ancestors(skill_dir, "--skill-dir")
    require(skill_dir.is_dir(), f"--skill-dir 不是目录：{skill_dir}")
    require(manifest.is_file() and not manifest.is_symlink(),
            f"--manifest 不存在或不是常规文件：{manifest}")
    reject_symlink_ancestors(manifest, "--manifest")
    require(task_file.is_file() and not task_file.is_symlink(),
            f"--task-file 不存在或不是常规文件：{task_file}")
    reject_symlink_ancestors(task_file, "--task-file")
    reject_symlink_ancestors(output, "--output")
    require(not output.is_symlink(), f"--output 路径是 symlink，拒绝：{output}")
    require(not output.exists(), f"输出目录已存在，拒绝覆盖：{output}")
    # 嵌套判定走 realpath 对账：祖先链允许系统级软链（如 macOS /var 临时目录），
    # 但解析后的实际落点不得位于（或等于）源 Skill 之内。输出必须不存在，
    # 因而不可能反过来成为源 Skill 的祖先，无需额外反向判定。
    real_skill = os.path.realpath(str(skill_dir))
    real_parent = os.path.realpath(str(output.parent))
    require(real_parent != real_skill and not real_parent.startswith(real_skill + os.sep),
            f"输出不得嵌在源 Skill 目录内：{output}")
    require(output.parent.is_dir(), f"输出父目录不存在或不是目录：{output.parent}")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skill-dir", required=True,
                        help="生产 moot-court 技能目录（只读，绝不修改）")
    parser.add_argument("--manifest", required=True,
                        help="合成案卷 materials.json（只读，字节原样带入）")
    parser.add_argument("--task-file", required=True,
                        help="原始统一任务文本，须含 {skill_dir}、{manifest}、{run_dir} 各至少一次")
    parser.add_argument("--output", required=True,
                        help="全新的候选 bundle 目录；已存在、嵌套或 symlink 均拒绝")
    parser.add_argument("--run-dir", default=None,
                        help="可选：{run_dir} 展开用的绝对路径（源 Skill 与 bundle/skill 之外，不创建）；"
                             f"缺省为 <bundle>/{DEFAULT_RUN_DIR_NAME}（同样不创建）")
    parser.add_argument("--allow-unknown-placeholders", action="store_true",
                        help="允许任务文本中的其他 {token} 原样保留并记录；默认拒绝")
    args = parser.parse_args(argv)

    tracker = Tracker()
    try:
        skill_dir, manifest, task_file, output_raw = resolve_inputs(args)
        output = check_locations(skill_dir, manifest, task_file, output_raw)
        output_real_parent = os.path.realpath(str(output.parent))

        present, symlinks = list_source_files(skill_dir)
        check_allowed_sources(skill_dir, present, symlinks)

        payload = {}
        original_sha = {}
        for rel in ALLOWED_PATHS:
            data = read_bytes(skill_dir / rel, f"源文件 {rel}")
            text = decode_utf8(data, f"源文件 {rel}")
            payload[rel] = (data, text)
            original_sha[rel] = sha256_hex(data)

        manifest_data = read_bytes(manifest, "案卷")
        decode_utf8(manifest_data, "案卷")
        task_data = read_bytes(task_file, "任务文件")
        task_text = decode_utf8(task_data, "任务文件")

        counts, unknown = validate_task_text(task_text)
        require(not unknown or args.allow_unknown_placeholders,
                "task-file 含未定义占位符：" + ", ".join("{" + n + "}" for n in unknown) +
                "。默认 fail-closed 拒绝；确属任务文本请加 --allow-unknown-placeholders 原样保留")

        projected_skill, projection = project_skill(payload["SKILL.md"][1])

        if args.run_dir is None:
            run_dir_value = str(output / DEFAULT_RUN_DIR_NAME)
            run_dir_policy = {"mode": "default-bundle-child",
                              "note": f"<bundle>/{DEFAULT_RUN_DIR_NAME}，不创建；"
                                      "书记员 init 接受不存在或完全为空的目录"}
        else:
            run_dir = Path(args.run_dir).expanduser()
            require(run_dir.is_absolute(), "--run-dir 必须是绝对路径")
            require(not run_dir.exists(),
                    f"--run-dir 已存在，拒绝复用既有演练目录：{run_dir}")
            require(not run_dir.is_symlink(), f"--run-dir 是 symlink，拒绝：{run_dir}")
            reject_symlink_ancestors(run_dir, "--run-dir")
            # 角色冷启动只能读候选 skill 与 bundle 顶层输入；演练目录落进源 Skill、
            # bundle 或 skill/ 之内都会把产物混入可见内容清单，一律拒绝。
            # macOS 临时目录自带 /var→/private/var 软链，词法与 realpath 两种形态都要对账。
            containers = {
                "源 Skill": [str(skill_dir), os.path.realpath(str(skill_dir))],
                "候选 skill": [str(output / "skill"),
                              os.path.realpath(str(output / "skill"))],
                "bundle": [str(output), os.path.realpath(str(output))],
            }

            def inside_any(candidate, parents):
                return any(candidate == parent or candidate.startswith(parent + os.sep)
                           for parent in parents)

            def inside_any_form(candidates, parents):
                return any(inside_any(form, parents) for form in candidates)

            # 对完整目标检查，包含目标恰等于 bundle 的情形；只检查父目录会漏过它。
            run_forms = (str(run_dir), os.path.realpath(str(run_dir)))
            require(not inside_any_form(run_forms, containers["源 Skill"]),
                    f"--run-dir 不得位于源 Skill 内：{run_dir}")
            require(not inside_any_form(run_forms, containers["候选 skill"]),
                    f"--run-dir 不得位于候选 skill 内：{run_dir}")
            require(not inside_any_form(run_forms, containers["bundle"]),
                    f"--run-dir 不得位于 bundle 内：{run_dir}")
            # 演练目录及其父级允许尚不存在：书记员 init 自行创建；本工具绝不创建。
            run_dir_value = str(run_dir)
            run_dir_policy = {"mode": "caller-specified",
                              "note": "源 Skill 与 bundle 之外的绝对路径，未创建"}
        # 任务必须指向 bundle 内的候选副本，而不是源 Skill/源案卷；否则宿主仍能读到
        # 被排除的评测答案与开发资产，候选包就失去隔离意义。
        values = {"skill_dir": str(output / "skill"),
                  "manifest": str(output / "materials.json"),
                  "run_dir": run_dir_value}
        expanded = expand_task(task_text, values)

        candidate_texts = {}
        candidate_data = {}
        for rel in ALLOWED_PATHS:
            if rel == "SKILL.md":
                data = projected_skill.encode("utf-8")
                candidate_texts[rel] = projected_skill
            else:
                data = payload[rel][0]
                candidate_texts[rel] = payload[rel][1]
            candidate_data[rel] = data
        links = check_links(candidate_texts)

        # 链接与占位符全部核验通过后，才开始触碰文件系统。
        output.mkdir(parents=False, exist_ok=False, mode=0o700)
        tracker.directory(output)
        require(os.path.realpath(str(output)).startswith(output_real_parent + os.sep),
                "输出目录创建后解析位置异常，疑似 symlink 逃逸")

        for rel in sorted(ALLOWED_PATHS, key=lambda p: (str(Path(p).parent), p)):
            target = output / "skill" / rel
            ensure_dir(target.parent, output, tracker)
            write_new(target, candidate_data[rel], tracker)
        write_new(output / "materials.json", manifest_data, tracker)
        write_new(output / "task-source.txt", task_data, tracker)
        write_new(output / "task.md", expanded.encode("utf-8"), tracker)

        candidate_sha = {rel: sha256_hex(candidate_data[rel]) for rel in ALLOWED_PATHS}
        bundle_files = {}
        for written, rel in [(output / "materials.json", "materials.json"),
                             (output / "task-source.txt", "task-source.txt"),
                             (output / "task.md", "task.md")]:
            bundle_files[rel] = sha256_hex(read_bytes(written, "bundle 文件"))

        core = {
            "schema_version": SCHEMA_VERSION,
            "kind": BUNDLE_KIND,
            "skill": "moot-court",
            "prepared_by": Path(__file__).name,
            "boundary": "只做文件级准备：不启动宿主、不联网、不安装、不修改任何已有文件；"
                        "目录筛选不构成工具权限隔离；不签 G5 或 DOMAIN_VERIFIED；"
                        "本包不是盲测沙箱，只是可见内容清单",
            "path_policy": "摘要条目只记文件名与相对路径；绝对路径仅出现在 "
                           "placeholder_expansion（task.md 复算所必需）",
            "allowed_original_paths": sorted(ALLOWED_PATHS),
            "excluded_paths": sorted(set(present) - set(ALLOWED_PATHS)),
            "bundle_top_level": ["manifest.json", "materials.json", "skill",
                                 "task-source.txt", "task.md"],
            "inputs": {
                "manifest": {"original_filename": manifest.name,
                             "bundle_name": "materials.json",
                             "sha256": sha256_hex(manifest_data)},
                "task_source": {"original_filename": task_file.name,
                                "bundle_name": "task-source.txt",
                                "sha256": sha256_hex(task_data)},
                "task_expanded": {"bundle_name": "task.md",
                                  "sha256": sha256_hex(expanded.encode("utf-8"))},
                "placeholder_expansion": [
                    {"name": name, "source_occurrences": counts.get(name, 0),
                     "expanded_to": values[name]} for name in PLACEHOLDERS],
                "unknown_placeholders_kept": unknown if args.allow_unknown_placeholders else [],
                "run_dir_policy": run_dir_policy,
            },
            # 合同允许的唯一点：SKILL.md 末尾“开发验证命令：”段；其余文件逐字节同源。
            "projections": [projection],
            "link_check": {
                "policy": "投影后候选 markdown 相对链接逐条解析（去锚点，外部 URL 与 mailto 跳过，不联网）；"
                          "必须命中候选目录内实际在包的文件，否则拒绝",
                "checked": links,
            },
            "source_readonly": {
                "policy": "源 Skill 一律只读；original_files_sha256 为读取时逐文件 SHA，"
                          "验收方可对源目录复算比对",
                "files": original_sha,
            },
            "candidate_files_sha256": candidate_sha,
            "bundle_other_files_sha256": bundle_files,
        }
        core["bundle_manifest_sha256"] = sha256_hex(canonical_core(core).encode("utf-8"))
        bundle_manifest_data = (json.dumps(core, ensure_ascii=False, sort_keys=True,
                                           indent=2) + "\n").encode("utf-8")
        write_new(output / "manifest.json", bundle_manifest_data, tracker)
    except PrepareError as exc:
        tracker.cleanup()
        print(f"prepare_runtime_candidate: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        tracker.cleanup()
        print(f"prepare_runtime_candidate: 准备过程失败：{type(exc).__name__}", file=sys.stderr)
        return 2

    print(json.dumps({
        "ok": True,
        "bundle": str(output),
        "skill_version_note": "候选摘要见 manifest.json，不在 stdout 重复",
        "allowed_count": len(core["allowed_original_paths"]),
        "excluded_count": len(core["excluded_paths"]),
        "links_checked": len(core["link_check"]["checked"]),
        "bundle_manifest_sha256": core["bundle_manifest_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
