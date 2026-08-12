#!/usr/bin/env bash
# 从 write.sh 保存的首次原始备份恢复文件，并恢复首次写入前的权限与内容哈希。

set -u

die() {
    printf 'restore.sh: 错误：%s\n' "$*" >&2
    exit 1
}

json_escape() {
    local s="${1-}"
    s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/\\n}; s=${s//$'\r'/\\r}; s=${s//$'\t'/\\t}
    printf '%s' "$s"
}

sha256_file() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        printf ''
    fi
}

TARGET=""
DRY_RUN=false
while [ $# -gt 0 ]; do
    case "$1" in
        --target) [ $# -ge 2 ] || die "--target 需要参数"; TARGET="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done

[ -n "$TARGET" ] || die "缺 --target"
BACKUP="${TARGET}.bak.legal-harness-init"
META="${BACKUP}.meta"
[ ! -L "$TARGET" ] || die "目标是符号链接；请改用真实文件路径"
[ ! -L "$BACKUP" ] || die "原始备份是符号链接，拒绝恢复"
[ ! -L "$META" ] || die "备份元数据是符号链接，拒绝恢复"
[ -f "$BACKUP" ] || die "原始备份不存在：$BACKUP"
[ -f "$META" ] || die "备份元数据不存在：$META"

expected_mode=$(sed -n 's/.*"mode":"\([0-9][0-9]*\)".*/\1/p' "$META" | head -1)
expected_sha=$(sed -n 's/.*"sha256":"\([0-9a-fA-F]*\)".*/\1/p' "$META" | head -1)
[ -n "$expected_mode" ] || die "备份元数据缺 mode"
[ -n "$expected_sha" ] || die "备份元数据缺 sha256"
actual_backup_sha=$(sha256_file "$BACKUP")
if [ "$actual_backup_sha" != "$expected_sha" ]; then
    die "原始备份哈希与元数据不一致，拒绝恢复"
fi

if [ "$DRY_RUN" = true ]; then
    cat <<EOF
{"schema_version":"1","status":"dry_run","target":"$(json_escape "$TARGET")","backup":"$(json_escape "$BACKUP")","mode":"$(json_escape "$expected_mode")","sha256":"$(json_escape "$actual_backup_sha")"}
EOF
    exit 0
fi

parent=$(dirname "$TARGET")
[ -d "$parent" ] || die "目标父目录不存在：$parent"
candidate=$(mktemp "${parent}/.legal-harness-restore.XXXXXX") || die "无法创建恢复候选文件"
if ! cp -p "$BACKUP" "$candidate"; then
    rm -f "$candidate"
    die "无法复制原始备份"
fi
chmod "$expected_mode" "$candidate" 2>/dev/null || { rm -f "$candidate"; die "无法恢复原始权限"; }
mv "$candidate" "$TARGET" || { rm -f "$candidate"; die "原子恢复失败"; }

restored_sha=$(sha256_file "$TARGET")
[ "$restored_sha" = "$expected_sha" ] || die "恢复后哈希校验失败"
cat <<EOF
{"schema_version":"1","status":"restored","target":"$(json_escape "$TARGET")","mode":"$(json_escape "$expected_mode")","sha256":"$(json_escape "$restored_sha")"}
EOF
