#!/usr/bin/env bash
# agent-email 操作函数库 — 多 provider 邮箱封装
#
# 支持的后端（由 MAIL_PROVIDER 环境变量切换，默认 claw）：
#   claw     网易 ClawEmail（@clawemail/mail-cli，API Key 认证，零 token）
#   agently  腾讯 Agent Mail / QQ 邮箱（@tencent-qqmail/agently-cli，OAuth 认证）
#
# 三层 API：
#   1. mail_*               统一入口（推荐，与 provider 无关）
#   2. _claw_* / _agently_* 各 provider 实现（内部，一般不直接调）
#   3. claw_*               向后兼容别名（等价 MAIL_PROVIDER=claw 的 mail_*）
#
# 用法：
#   source skills/agent-email/scripts/mail-ops.sh
#   mail_send --to "a@b.com" --subject "主题" --body "正文"
#   MAIL_PROVIDER=agently mail_list --limit 10
#   export MAIL_PROVIDER=agently   # 切到腾讯，后续 mail_* 都走 agently
#
# 腾讯 Agent Mail 的写操作（send/reply/forward/trash）走两步确认（ctk_xxx）：
#   第一次调用返回 confirmation_token + summary → 停下问用户 →
#   用户确认后带 --confirmation-token <token> 重跑完成。详见 SKILL.md。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 加载 .env 配置
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.env"
  set +a
fi

# 默认值（.env 之后再设默认，保证 .env 的 MAIL_PROVIDER 优先）
MAIL_PROVIDER="${MAIL_PROVIDER:-claw}"
AGENT_EMAIL="${AGENT_EMAIL:-}"
AGENTLY_EMAIL="${AGENTLY_EMAIL:-}"
DISPLAY_NAME="${DISPLAY_NAME:-}"
INBOX_FID="${INBOX_FID:-1}"
SENT_FID="${SENT_FID:-3}"

# ════════════════════════════════════════════════════════════════
# provider CLI 路由（内部）
# ════════════════════════════════════════════════════════════════
_claw_cli() {
  npx --yes "@clawemail/mail-cli@latest" "$@"
}
_agently_cli() {
  if command -v agently-cli >/dev/null 2>&1; then
    agently-cli "$@"
  else
    # fallback：agently-cli 全局装在 npm prefix 下（可能是 hermes/nvm 等 node），
    # 不一定在当前 shell 的 PATH。自动找 npm 全局 bin。
    local npm_bin
    npm_bin="$(npm prefix -g 2>/dev/null)/bin"
    if [[ -x "${npm_bin}/agently-cli" ]]; then
      "${npm_bin}/agently-cli" "$@"
    else
      echo "错误: 未找到 agently-cli。请先安装：npm install -g @tencent-qqmail/agently-cli" >&2
      return 1
    fi
  fi
}

# ════════════════════════════════════════════════════════════════
# 网易 ClawEmail 实现（_claw_*）
# ════════════════════════════════════════════════════════════════

# 认证：委托给 claw_init（API Key 模式，见文件末尾）
_claw_login() { claw_init "$@"; }

# 当前账号：mail-cli 无原生 me 命令，读 .env 的 AGENT_EMAIL
_claw_me() {
  if [[ -n "$AGENT_EMAIL" ]]; then
    echo "$AGENT_EMAIL"
  else
    echo "（未配置 AGENT_EMAIL，请先运行 claw_init 完成网易 ClawEmail 配置）" >&2
    return 1
  fi
}

_claw_folders() { _claw_cli folder list "$@"; }

# 列邮件。统一参数：--dir 映射到 claw 的 --fid（inbox→INBOX_FID, sent→SENT_FID）。
# 未指定文件夹时默认 INBOX_FID。其余参数（--limit/--unread/--json）透传。
_claw_list() {
  local had_fid=0
  local args=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --fid)
        had_fid=1; args+=(--fid "$2"); shift 2 ;;
      --dir)
        had_fid=1
        case "$2" in
          inbox|INBOX) args+=(--fid "$INBOX_FID") ;;
          sent|SENT)   args+=(--fid "$SENT_FID") ;;
          *)           args+=(--fid "$2") ;;
        esac
        shift 2 ;;
      *)
        args+=("$1"); shift ;;
    esac
  done
  [[ $had_fid -eq 0 ]] && args=(--fid "$INBOX_FID" "${args[@]}")
  _claw_cli mail list "${args[@]}"
}

# 读正文：mail_id 作为位置参数（兼容旧 claw_body <mid>）
_claw_read() {
  local id="$1"; shift
  _claw_cli read body --id "$id" "$@"
}

# 读结构（含附件列表与 part-id）
_claw_structure() {
  local id="$1"; shift
  _claw_cli read structure --id "$id" "$@"
}

# 搜索：透传（支持 --fid/--keyword/--since/--from/--json 等）
_claw_search() { _claw_cli mail search "$@"; }

# 发送邮件
# 用法: _claw_send --to <addr> --subject <subj> --body <text> | --body-file <path> [--html]
# 注：--cc/--bcc/--attachment/--confirmation-token 会被解析但忽略（mail-cli 不一定支持，
#     且无两步确认）；如需这些能力请用 agently 后端。
_claw_send() {
  local to="" subject="" body="" body_file="" html=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --to)               to="$2"; shift 2 ;;
      --cc|--bcc|--attachment) shift 2 ;;      # 解析但忽略
      --confirmation-token) shift 2 ;;         # claw 无两步确认
      --subject)          subject="$2"; shift 2 ;;
      --body)             body="$2"; shift 2 ;;
      --body-file)        body_file="$2"; shift 2 ;;
      --html)             html="--html"; shift ;;
      *)                  shift ;;
    esac
  done

  if [[ -z "$to" || -z "$subject" ]]; then
    echo "错误: 需要指定 --to 和 --subject" >&2
    return 1
  fi

  local args=(compose send)
  if [[ -n "$AGENT_EMAIL" && -n "$DISPLAY_NAME" ]]; then
    args+=(--from "\"${DISPLAY_NAME}\" <${AGENT_EMAIL}>")
  fi
  args+=(--to "$to" --subject "$subject")
  if [[ -n "$body" ]]; then args+=(--body "$body"); fi
  if [[ -n "$body_file" ]]; then args+=(--body-file "$body_file"); fi
  if [[ -n "$html" ]]; then args+=(--html); fi

  _claw_cli "${args[@]}"
}

# ClawEmail mail-cli 无原生 reply/forward；提示用 mail_send 手动构造
_claw_reply_unsupported() {
  echo "提示: 网易 mail-cli 无原生 reply/forward 命令。" >&2
  echo "      请先用 mail_read/mail_structure <id> 取原主题与发件人，" >&2
  echo "      再 mail_send --to <原发件人> --subject \"Re: <原主题>\" --body \"...\"。" >&2
  echo "      （原生 reply/forward 由腾讯 agently 后端支持）" >&2
  return 1
}

_claw_trash_unsupported() {
  echo "提示: 网易 mail-cli 暂无删除/移到回收站命令。" >&2
  echo "      （message +trash 由腾讯 agently 后端支持）" >&2
  return 1
}

_claw_watch_unsupported() {
  echo "提示: 网易 mail-cli 无长连接监听。可用 cron 定时 mail_list --unread 实现轮询。" >&2
  echo "      （message +watch 由腾讯 agently 后端支持）" >&2
  return 1
}

# 下载附件
# 新签名（推荐）: _claw_download --id <mid> --part <pid> --out-file <dir>
# 旧签名（兼容）: _claw_download <mid>  → 自动转 --id <mid>，但不带 --part（按需补）
_claw_download() {
  if [[ "${1:-}" != "--id" && "${1:-}" != -* && -n "${1:-}" ]]; then
    # 旧式位置参数 <mid>
    local mid="$1"; shift
    echo "提示: 建议先 mail_structure $mid 拿附件 part-id，再用 --id --part --out-file 精确下载" >&2
    _claw_cli read attachment --id "$mid" "$@"
  else
    _claw_cli read attachment "$@"
  fi
}

_claw_mailboxes() { _claw_cli clawemail list "$@"; }
_claw_create()    { _claw_cli clawemail create "$@"; }

# ════════════════════════════════════════════════════════════════
# 腾讯 Agent Mail 实现（_agently_*）
# ════════════════════════════════════════════════════════════════

# 自动完成腾讯的两步确认（ctk）：第一次拿 token，立即带 token 重跑真发。
# 对调用方透明——一次调用即可，不会因 ctk 5 分钟过期失败（两次调用无间隔）。
# 若调用方已传 --confirmation-token（手动第二步），直接透传。
# 取舍见 DEC-006：把"用户确认"放在对话层（Agent 拟稿 → 用户说"发" → 一次发出），
# 而非 agently-cli 的 ctk 层——对自动化（cron）友好，也避开过期坑。
_agently_auto_two_step() {
  local resp ctk rc
  if [[ " $* " == *" --confirmation-token "* ]]; then
    _agently_cli "$@"           # 手动两步第二步，透传
    return $?
  fi
  resp=$(_agently_cli "$@" 2>&1)
  rc=$?
  # agently-cli 输出含 JSON + tip 提示行，用 grep 提取（不依赖 jq 解析整段，不怕尾部 tip）
  if printf '%s' "$resp" | grep -q '"confirmation_required"'; then
    ctk=$(printf '%s' "$resp" | grep -oE 'ctk_[A-Za-z0-9_-]+' | head -1)
    if [[ -n "$ctk" ]]; then
      _agently_cli "$@" --confirmation-token "$ctk"
      return $?
    fi
  fi
  printf '%s\n' "$resp"
  return $rc
}

# OAuth 授权：后台 pty 跑 auth login，抓 stdout 的授权 URL 给用户
# 腾讯官方把 pty+URL 抓取甩给宿主 Agent，这里做工程化封装。
_agently_login() {
  echo "→ 启动 OAuth 授权（agently-cli auth login）..." >&2
  if ! command -v agently-cli >/dev/null 2>&1; then
    echo "错误: 未找到 agently-cli，请先安装：npm install -g @tencent-qqmail/agently-cli" >&2
    return 1
  fi

  local log
  log="$(mktemp -t agently-auth)"
  # macOS 原生 pty（script）后台跑 auth login，输出落日志
  script -qfc "agently-cli auth login" /dev/null > "$log" 2>&1 &
  local pid=$!

  # 轮询日志直到抓到授权 URL 或命令退出
  local url=""
  for _ in $(seq 1 30); do
    url="$(grep -oE 'https?://[^ ]+' "$log" 2>/dev/null | head -1)"
    [[ -n "$url" ]] && break
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1
  done

  if [[ -z "$url" ]]; then
    echo "错误: 未能从 agently-cli 输出抓取授权 URL。" >&2
    echo "------ agently-cli 输出 ------" >&2
    cat "$log" >&2
    rm -f "$log"
    return 1
  fi

  # URL 视为 opaque string 原样展示（不编码、不拼接、不加标点）
  echo "请点击或复制以下链接在浏览器中完成授权："
  printf '%s\n' "$url"
  echo "（在浏览器中完成授权后，命令会自动退出）" >&2
  wait "$pid"
  rm -f "$log"

  echo "→ 验证身份..." >&2
  _agently_cli +me
}

_agently_me()     { _agently_cli +me "$@"; }

_agently_folders() {
  echo "腾讯 Agent Mail 用 --dir inbox|sent|trash|spam 枚举，无独立 folder list。" >&2
  echo "示例: mail_list --dir sent --limit 10" >&2
  return 0
}

# 腾讯命令多为「名词 +动词」风格（message +list / attachment +download）
_agently_list()      { _agently_cli message +list "$@"; }
# agently 后端 message +read 需要 --id：兼容「位置参数 <id>」与「--id <id>」两种调用
_agently_read() {
  if [[ "${1:-}" != --* && -n "${1:-}" ]]; then
    _agently_cli message +read --id "$1" "${@:2}"
  else
    _agently_cli message +read "$@"
  fi
}
_agently_structure() { _agently_read "$@"; }  # 复用 read（已含 body+attachments），自动处理 --id
_agently_search()    { _agently_cli message +search "$@"; }
_agently_send()      { _agently_auto_two_step message +send "$@"; }
_agently_reply()     { _agently_auto_two_step message +reply "$@"; }
_agently_forward()   { _agently_auto_two_step message +forward "$@"; }
_agently_trash()     { _agently_auto_two_step message +trash "$@"; }
# 注意：agently-cli 的 attachment +download --output 须传【相对路径】（在目标目录内执行），
#       传绝对路径会静默不落地。调用前先 cd 到目标目录，再 --output .
_agently_download()  { _agently_cli attachment +download "$@"; }
_agently_watch()     { _agently_cli message +watch "$@"; }

# ════════════════════════════════════════════════════════════════
# 统一 API（mail_*）— 推荐入口，按 MAIL_PROVIDER 分派
# ════════════════════════════════════════════════════════════════
_dispatch() {
  local act="$1"; shift
  case "$MAIL_PROVIDER" in
    claw|clawemail)
      case "$act" in
        login)     _claw_login "$@" ;;
        me)        _claw_me "$@" ;;
        list)      _claw_list "$@" ;;
        read)      _claw_read "$@" ;;
        structure) _claw_structure "$@" ;;
        search)    _claw_search "$@" ;;
        send)      _claw_send "$@" ;;
        reply)     _claw_reply_unsupported "$@" ;;
        forward)   _claw_reply_unsupported "$@" ;;
        trash)     _claw_trash_unsupported "$@" ;;
        download)  _claw_download "$@" ;;
        folders)   _claw_folders "$@" ;;
        watch)     _claw_watch_unsupported "$@" ;;
        *) echo "未知动作: $act" >&2; return 1 ;;
      esac ;;
    agently|tencent|qq)
      case "$act" in
        login)     _agently_login "$@" ;;
        me)        _agently_me "$@" ;;
        list)      _agently_list "$@" ;;
        read)      _agently_read "$@" ;;
        structure) _agently_structure "$@" ;;
        search)    _agently_search "$@" ;;
        send)      _agently_send "$@" ;;
        reply)     _agently_reply "$@" ;;
        forward)   _agently_forward "$@" ;;
        trash)     _agently_trash "$@" ;;
        download)  _agently_download "$@" ;;
        folders)   _agently_folders "$@" ;;
        watch)     _agently_watch "$@" ;;
        *) echo "未知动作: $act" >&2; return 1 ;;
      esac ;;
    *)
      echo "错误: 未知 MAIL_PROVIDER='$MAIL_PROVIDER'（支持: claw | agently）" >&2
      return 1 ;;
  esac
}

mail_login()     { _dispatch login "$@"; }
mail_me()        { _dispatch me "$@"; }
mail_list()      { _dispatch list "$@"; }
mail_read()      { _dispatch read "$@"; }
mail_structure() { _dispatch structure "$@"; }
mail_search()    { _dispatch search "$@"; }
mail_send()      { _dispatch send "$@"; }
mail_reply()     { _dispatch reply "$@"; }
mail_forward()   { _dispatch forward "$@"; }
mail_trash()     { _dispatch trash "$@"; }
mail_download()  { _dispatch download "$@"; }
mail_folders()   { _dispatch folders "$@"; }
mail_watch()     { _dispatch watch "$@"; }

# ════════════════════════════════════════════════════════════════
# 向后兼容别名（claw_*）— 等价 MAIL_PROVIDER=claw 的 mail_*
# 保留是为了不破坏已有的 cron / 脚本调用。新代码请用 mail_*。
# ════════════════════════════════════════════════════════════════
claw_send()      { MAIL_PROVIDER=claw mail_send "$@"; }
claw_list()      { MAIL_PROVIDER=claw mail_list "$@"; }
claw_body()      { MAIL_PROVIDER=claw mail_read "$@"; }
claw_structure() { MAIL_PROVIDER=claw mail_structure "$@"; }
claw_search()    { MAIL_PROVIDER=claw mail_search "$@"; }
claw_download()  { MAIL_PROVIDER=claw mail_download "$@"; }
claw_folders()   { MAIL_PROVIDER=claw mail_folders "$@"; }
# 子邮箱管理为网易专属，保留直通
claw_mailboxes() { _claw_cli clawemail list "$@"; }
claw_create()    { _claw_cli clawemail create "$@"; }

# ════════════════════════════════════════════════════════════════
# 首次配置 — 网易 ClawEmail（API Key 模式）
# 用法: claw_init "t1/xxxxxxxxxx" ["显示名称"]
# ════════════════════════════════════════════════════════════════
claw_init() {
  local auth_url="$1"

  # 1. 解析认证 URL 获取凭证
  echo "→ 解析认证 URL..."
  local creds
  creds=$(curl -sL "https://u.163.com/${auth_url}")
  if [[ -z "$creds" ]]; then
    echo "错误: 认证 URL 无效或已过期（有效期 30 分钟）" >&2
    return 1
  fi

  # 解析：第一行 name:account-id:，第二行 __apikey__:workspace:ck_live_xxx
  local name apikey
  name=$(echo "$creds" | head -1 | cut -d: -f1)
  apikey=$(echo "$creds" | grep "__apikey__" | cut -d: -f3)

  if [[ -z "$apikey" ]]; then
    echo "错误: 未能从认证 URL 获取 API Key" >&2
    return 1
  fi

  echo "  邮箱: ${name}@claw.163.com"

  # 2. 存储 API Key
  echo "→ 存储 API Key..."
  _claw_cli auth apikey set "$apikey"

  # 3. 创建默认 Profile
  echo "→ 配置 Profile..."
  _claw_cli auth login --user "${name}@claw.163.com" --auth-method password --password "$apikey"

  # 4. 验证
  echo "→ 验证连通..."
  _claw_cli folder list

  echo ""
  echo "✅ 配置完成！邮箱: ${name}@claw.163.com"

  # 5. 写入 .env 备份配置（保留已有的 MAIL_PROVIDER 等字段）
  local display_name="${2:-${name}}"
  printf -v display_name_q '%q' "$display_name"
  cat > "${SCRIPT_DIR}/.env" <<EOF
# Agent Email 环境配置
# 默认后端（claw | agently）
MAIL_PROVIDER=claw

# ── 网易 ClawEmail ──
AGENT_EMAIL=${name}@claw.163.com
DISPLAY_NAME=${display_name_q}
CLAW_PREFIX=${name}
CLAW_PROFILE=default
INBOX_FID=1
SENT_FID=3

# ── 腾讯 Agent Mail（agently-cli，OAuth 凭据由 CLI 自管）──
# AGENTLY_EMAIL=

# ── 常用联系人（按需补充）──
EOF
  echo "  配置已写入 ${SCRIPT_DIR}/.env"
  echo "  发送邮件: mail_send --to 'xxx@example.com' --subject '主题' --body '内容'"
  echo "  查看收件箱: mail_list --fid 1   （或 MAIL_PROVIDER=agently mail_list --dir inbox）"
}
