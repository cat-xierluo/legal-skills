#!/usr/bin/env bash
# env-doctor · 本机开发环境与全局包体检、账本
# 覆盖: node/npm/npx 垫片、nvm、python 解释器版图、pip/pipx、uv、brew、bun、
#       PATH、cron、brew services、LaunchAgents、shell rc 漂移对照
# 用法:
#   env-doctor.sh                 快速体检（本地信息，秒级）
#   env-doctor.sh full            深度体检（追加 brew outdated，需网络，较慢）
#   env-doctor.sh snapshot        重立漂移基线（确认 rc/LaunchAgents 变更合法后执行）
#   env-doctor.sh record "说明"    向账本追加一条记录（自动加时间戳）
# 退出码: 0=正常  2=检测到运行时垫片漂移  3=无法解析 nvm 默认、未验证
# 环境变量: ENV_LEDGER 账本路径；ENV_DOCTOR_STATE 漂移基线文件路径（默认 ~/.config/env-doctor/state）
set -uo pipefail

LEDGER="${ENV_LEDGER:-$HOME/.config/env-ledger.md}"
STATE_FILE="${ENV_DOCTOR_STATE:-$HOME/.config/env-doctor/state}"
NVM_HOME="${NVM_DIR:-$HOME/.nvm}"
LOCAL_BIN="$HOME/.local/bin"
RC_FILES="$HOME/.zshenv $HOME/.zprofile $HOME/.zshrc $HOME/.zlogin $HOME/.profile $HOME/.bashrc"

say() { printf '   %s\n' "$*"; }
sec() { printf '\n== %s ==\n' "$*"; }
# 注：bash 3.2 下变量名后紧跟全角字符会被吃进名字，变量一律 ${} 包裹

# 解析 nvm default alias（兼容 lts/* 间接指向），成功则输出版本 bin 目录
resolve_nvm_default_bin() {
  local alias_dir="$NVM_HOME/alias" v name
  [ -r "$alias_dir/default" ] || return 1
  v=$(<"$alias_dir/default")
  if [[ "$v" == lts/* ]]; then
    name="${v#lts/}"
    if [ "$name" = "*" ]; then
      # lts/* = 最新 LTS：取 alias/lts/ 下字典序最大的代号（LTS 代号按字母序发布）
      name=$(ls "$alias_dir/lts" 2>/dev/null | sort | tail -n 1)
      [ -n "$name" ] || return 1
    fi
    [ -r "$alias_dir/lts/$name" ] || return 1
    v=$(<"$alias_dir/lts/$name")
  fi
  [ -d "$NVM_HOME/versions/node/$v/bin" ] || return 1
  printf '%s\n' "$NVM_HOME/versions/node/$v/bin"
}

audit_shims() {
  sec "1. node/npm/npx 垫片归属（${LOCAL_BIN}）"
  local expected_bin=""
  expected_bin=$(resolve_nvm_default_bin || true)
  if [ -n "$expected_bin" ]; then
    say "nvm 默认 → $expected_bin"
  else
    say "⚠️ 无法解析 nvm 默认版本（~/.nvm/alias），只列不比对"
  fi
  local t p tgt mark
  for t in node npm npx; do
    p="$LOCAL_BIN/$t"
    if [ -L "$p" ]; then
      tgt=$(readlink "$p")
      mark=""
      if [ -e "$p" ]; then
        if [ -n "$expected_bin" ]; then
          case "$tgt" in
            "$expected_bin"*) mark="✅ nvm 默认" ;;
            *) mark="🚨 非 nvm 默认" ;;
          esac
        else
          mark="⚠️ 无法比对"
        fi
      else
        mark="🚨 死链"
      fi
      say "$t → $tgt   [$mark]"
    elif [ -e "$p" ]; then
      say "$t 存在但非符号链接（异常形态）"
    else
      say "$t 不存在，PATH 将落到其他 node"
    fi
  done
}

audit_path() {
  sec "2. PATH 实际解析与解释器版图"
  if command -v node >/dev/null 2>&1; then
    say "node: $(command -v node)  ($(node -v 2>/dev/null || echo '?'))"
  else
    say "node: PATH 上不可用"
  fi
  if command -v npm >/dev/null 2>&1; then
    say "npm -g prefix: $(npm prefix -g 2>/dev/null || echo '?')"
  fi
  if command -v python3 >/dev/null 2>&1; then
    say "python3（默认）: $(command -v python3)  ($(python3 -V 2>&1))"
    say "pip 落点: $(python3 -m pip -V 2>/dev/null || echo '?')"
  fi
  say "PATH 上全部 node:"
  which -a node 2>/dev/null | awk '!seen[$0]++' | while IFS= read -r p; do
    if [ -x "$p" ]; then
      say "  ${p}  ($("$p" -v 2>/dev/null || echo '版本获取失败'))"
    else
      say "  ${p}（不可执行）"
    fi
  done
  say "PATH 上全部 python3:"
  which -a python3 2>/dev/null | awk '!seen[$0]++' | while IFS= read -r p; do
    [ -x "$p" ] && say "  ${p}  ($("$p" -V 2>&1 || echo '版本获取失败'))"
  done
  if command -v uv >/dev/null 2>&1; then
    say "uv python（前 8 行）:"
    uv python list 2>/dev/null | head -n 8 | sed 's/^/     /'
  fi
}

audit_pkg_managers() {
  sec "3. 包管理器与全局落点"
  if command -v npm >/dev/null 2>&1; then
    say "npm 全局（当前 prefix: $(npm prefix -g 2>/dev/null || echo '?')）:"
    npm ls -g --depth=0 2>/dev/null | tail -n +2 | sed 's/^/     /'
  else
    say "npm: 不可用"
  fi
  if command -v uv >/dev/null 2>&1; then
    say "uv tools:"
    uv tool list 2>/dev/null | sed 's/^/     /'
  else
    say "uv: 未安装"
  fi
  if command -v pipx >/dev/null 2>&1; then
    say "pipx:"
    pipx list --short 2>/dev/null | sed 's/^/     /'
  else
    say "pipx: 未安装"
  fi
  if command -v python3 >/dev/null 2>&1; then
    local n
    n=$(python3 -m pip list --user 2>/dev/null | tail -n +3 | wc -l | tr -d ' ')
    say "pip --user 包数: ${n}（原则上不应手装 CLI，见纪律 1）"
  fi
  if [ -d "$HOME/.bun/bin" ]; then
    say "bun 全局命令: $(ls "$HOME/.bun/bin" 2>/dev/null | tr '\n' ' ')"
  fi
  if command -v brew >/dev/null 2>&1; then
    say "brew leaves: $(brew leaves 2>/dev/null | wc -l | tr -d ' ') 个主包（full 模式看过时清单）"
    say "brew services: $(brew services list 2>/dev/null | tail -n +2 | wc -l | tr -d ' ') 项，其中 started $(brew services list 2>/dev/null | grep -c started) 项"
  else
    say "brew: 未安装"
  fi
  local cron_n
  cron_n=$(crontab -l 2>/dev/null | grep -c . || true)
  say "cron 任务: ${cron_n} 行（明细见第 6 节）"
}

audit_full_extra() {
  sec "3b. brew 过时包（full 模式，需网络）"
  local out n
  out=$(HOMEBREW_NO_AUTO_UPDATE=1 brew outdated 2>/dev/null || true)
  if [ -z "$out" ]; then
    say "0 个过时"
  else
    n=$(printf '%s\n' "$out" | grep -c .)
    say "${n} 个过时:"
    printf '%s\n' "$out" | sed 's/^/     /'
  fi
}

audit_caches() {
  sec "4. 缓存体积（可安全清理：npm/bun/uv/pip 缓存与 brew cache）"
  du -sh "$HOME/.npm" "$HOME/.bun/install/cache" \
        "$HOME/Library/Caches/uv" "$HOME/Library/Caches/pip" 2>/dev/null | sed 's/^/   /'
  local brew_cache
  brew_cache=$(brew --cache 2>/dev/null || true)
  [ -n "$brew_cache" ] && du -sh "$brew_cache" 2>/dev/null | sed 's/^/   /'
}

audit_shim_list() {
  sec "5. ${LOCAL_BIN} 符号链接清单（死链标 ⚠️）"
  local p tgt found=0
  for p in "$LOCAL_BIN"/*; do
    [ -L "$p" ] || continue
    found=1
    tgt=$(readlink "$p")
    if [ -e "$p" ]; then
      printf '   %-24s → %s\n' "${p##*/}" "$tgt"
    else
      printf '   %-24s → %s  ⚠️死链\n' "${p##*/}" "$tgt"
    fi
  done
  [ "$found" -eq 0 ] && say "（无符号链接）"
}

audit_launchagents() {
  sec "6. LaunchAgents 与 cron"
  local n
  n=$(ls "$HOME/Library/LaunchAgents/"*.plist 2>/dev/null | wc -l | tr -d ' ')
  say "LaunchAgents 共 ${n} 个:"
  ls "$HOME/Library/LaunchAgents/" 2>/dev/null | sed 's/^/   /'
  say "cron:"
  crontab -l 2>/dev/null | sed 's/^/     /' || say "（无 crontab）"
}

audit_ledger() {
  sec "7. 账本（${LEDGER}）"
  if [ -f "$LEDGER" ]; then
    tail -n 8 "$LEDGER" | sed 's/^/   /'
  else
    say "（账本尚未创建，用 record 子命令初始化）"
  fi
}

hash_file() { shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'; }

current_la_names() { ls "$HOME/Library/LaunchAgents/" 2>/dev/null | sort; }
stored_la_names() { grep '^la:' "$STATE_FILE" 2>/dev/null | cut -d: -f2-; }

audit_drift() {
  sec "8. 环境漂移对照（rc 文件与 LaunchAgents，基线: ${STATE_FILE}）"
  if [ ! -f "$STATE_FILE" ]; then
    say "（尚无基线，跑一次 snapshot 立基线）"
    return 0
  fi
  local f stored cur diffs=0
  for f in $RC_FILES; do
    stored=$(grep -F "rc:$f=" "$STATE_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2)
    if [ -f "$f" ]; then
      cur=$(hash_file "$f")
      if [ -z "$stored" ]; then
        say "⚠️ ${f} 存在但未入基线（snapshot 未覆盖，重跑 snapshot）"
      elif [ "$stored" != "$cur" ]; then
        say "🚨 ${f} 自基线以来内容已变更（确认合法后重跑 snapshot 并记账）"
        diffs=1
      fi
    else
      if [ -n "$stored" ]; then
        say "ℹ️ ${f} 已删除（基线里有记录）"
        diffs=1
      fi
    fi
  done
  local added removed
  added=$(comm -13 <(stored_la_names) <(current_la_names))
  removed=$(comm -23 <(stored_la_names) <(current_la_names))
  if [ -n "$added" ]; then
    say "🚨 LaunchAgents 新增: $(echo "$added" | tr '\n' ' ')"
    diffs=1
  fi
  if [ -n "$removed" ]; then
    say "ℹ️ LaunchAgents 消失: $(echo "$removed" | tr '\n' ' ')"
    diffs=1
  fi
  [ "$diffs" -eq 0 ] && say "✅ rc 文件与 LaunchAgents 均与基线一致"
}

snapshot() {
  mkdir -p "$(dirname "$STATE_FILE")"
  {
    printf '# env-doctor 漂移基线（%s 由 snapshot 生成；确认变更合法后重跑以重立）\n' "$(date '+%Y-%m-%d %H:%M')"
    local f
    for f in $RC_FILES; do
      [ -f "$f" ] && printf 'rc:%s=%s\n' "$f" "$(hash_file "$f")"
    done
    current_la_names | sed 's/^/la:/'
  } > "$STATE_FILE"
  say "已立基线 → $STATE_FILE"
  say "rc 文件 $(grep -c '^rc:' "$STATE_FILE") 个、LaunchAgents $(grep -c '^la:' "$STATE_FILE") 个已入基线"
  echo "提示: 变更被确认合法后，用 snapshot 重立基线；重大变更建议同时 record 记账。"
}

run_audit() {
  local mode="${1:-fast}"
  local drift=0 unverifiable=0
  local expected_bin p t
  expected_bin=$(resolve_nvm_default_bin || true)
  if [ -n "$expected_bin" ]; then
    for t in node npm npx; do
      p="$LOCAL_BIN/$t"
      if [ -L "$p" ]; then
        case "$(readlink "$p")" in
          "$expected_bin"*) ;;
          *) drift=1 ;;
        esac
        [ -e "$p" ] || drift=1
      fi
    done
  else
    unverifiable=1
  fi
  audit_shims
  audit_path
  audit_pkg_managers
  [ "$mode" = "full" ] && audit_full_extra
  audit_caches
  audit_shim_list
  audit_launchagents
  audit_ledger
  audit_drift
  echo
  if [ "$unverifiable" -eq 1 ]; then
    echo "结论: ⚠️ 无法解析 nvm 默认版本，本次未验证垫片漂移（第 8 节漂移对照独立生效）"
    exit 3
  elif [ "$drift" -eq 0 ]; then
    echo "结论: ✅ node 垫片与 nvm 默认一致，未见漂移（第 8 节为环境面漂移，不计入退出码）"
    exit 0
  else
    echo "结论: 🚨 检测到运行时垫片漂移——见上方 [🚨] 标记。多为厂商应用更新劫持了 ~/.local/bin；先报告用户，勿擅自改回。"
    exit 2
  fi
}

record() {
  local msg="${1:-}"
  if [ -z "$msg" ]; then
    echo "用法: env-doctor.sh record \"说明（谁/做了什么/如何回滚）\"" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$LEDGER")"
  if [ ! -f "$LEDGER" ]; then
    printf '# 环境变更账本（env-doctor）\n\n格式：- 日期 时间 — 说明（操作者 / 回滚方式）\n\n' > "$LEDGER"
  fi
  printf -- '- %s — %s\n' "$(date '+%Y-%m-%d %H:%M')" "$msg" >> "$LEDGER"
  echo "已记账 → $LEDGER"
}

case "${1:-audit}" in
  audit|"") run_audit fast ;;
  full)     run_audit full ;;
  snapshot) snapshot ;;
  record)   record "${2:-}" ;;
  *) echo "用法: env-doctor.sh [audit | full | snapshot | record \"说明\"]" >&2; exit 1 ;;
esac
