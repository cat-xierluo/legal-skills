#!/usr/bin/env bash
# env-hygiene · 运行时环境审计与账本
# 用法:
#   env-audit.sh                  审计：垫片归属 / PATH 解析 / 缓存 / LaunchAgents / 账本
#   env-audit.sh record "说明"     向账本追加一条记录（自动加时间戳）
# 退出码: 0=正常  2=检测到运行时垫片漂移（node/npm/npx 非 nvm 默认或死链）
set -uo pipefail

LEDGER="${ENV_LEDGER:-$HOME/.config/env-ledger.md}"
NVM_HOME="${NVM_DIR:-$HOME/.nvm}"
LOCAL_BIN="$HOME/.local/bin"

say() { printf '   %s\n' "$*"; }
sec() { printf '\n== %s ==\n' "$*"; }

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

audit() {
  local drift=0

  # 注：bash 3.2 下变量名后紧跟全角字符会被吃进名字，此处及下方一律用 ${} 包裹
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
            *) mark="🚨 非 nvm 默认"; drift=1 ;;
          esac
        else
          mark="⚠️ 无法比对"
        fi
      else
        mark="🚨 死链"; drift=1
      fi
      say "$t → $tgt   [$mark]"
    elif [ -e "$p" ]; then
      say "$t 存在但非符号链接（异常形态）"
    else
      say "$t 不存在，PATH 将落到其他 node"
    fi
  done

  sec "2. PATH 上的实际解析"
  if command -v node >/dev/null 2>&1; then
    say "node: $(command -v node)  ($(node -v 2>/dev/null || echo '?'))"
  else
    say "node: PATH 上不可用"
  fi
  if command -v npm >/dev/null 2>&1; then
    say "npm -g prefix: $(npm prefix -g 2>/dev/null || echo '?')"
  fi
  if command -v python3 >/dev/null 2>&1; then
    say "python3: $(command -v python3)  ($(python3 -V 2>&1))"
  fi
  which -a node 2>/dev/null | awk '!seen[$0]++' | while IFS= read -r p; do
    if [ -x "$p" ]; then
      say "  $p  ($("$p" -v 2>/dev/null || echo '版本获取失败'))"
    else
      say "  ${p}（不可执行）"
    fi
  done

  sec "3. node 版本与缓存体积"
  if [ -d "$NVM_HOME/versions/node" ]; then
    ls "$NVM_HOME/versions/node" 2>/dev/null | sed 's/^/   nvm: /'
  else
    say "（nvm 未安装任何版本）"
  fi
  du -sh "$HOME/.npm" "$HOME/.bun/install/cache" 2>/dev/null | sed 's/^/   /'
  local brew_cache
  brew_cache=$(brew --cache 2>/dev/null || true)
  [ -n "$brew_cache" ] && du -sh "$brew_cache" 2>/dev/null | sed 's/^/   /'
  return 0
}

audit_rest() {
  sec "4. $LOCAL_BIN 符号链接清单（死链标 ⚠️）"
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

  sec "5. LaunchAgents"
  local n
  n=$(ls "$HOME/Library/LaunchAgents/"*.plist 2>/dev/null | wc -l | tr -d ' ')
  say "共 ${n} 个:"
  ls "$HOME/Library/LaunchAgents/" 2>/dev/null | sed 's/^/   /'

  sec "6. 账本（${LEDGER}）"
  if [ -f "$LEDGER" ]; then
    tail -n 8 "$LEDGER" | sed 's/^/   /'
  else
    say "（账本尚未创建，用 record 子命令初始化）"
  fi
}

run_audit() {
  local drift=0 unverifiable=0
  # 垫片比对结果决定退出码，单独跑一遍轻量判定
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
  audit
  audit_rest
  echo
  if [ "$unverifiable" -eq 1 ]; then
    echo "结论: ⚠️ 无法解析 nvm 默认版本，本次未验证垫片漂移"
    exit 3
  elif [ "$drift" -eq 0 ]; then
    echo "结论: ✅ node 垫片与 nvm 默认一致，未见漂移"
    exit 0
  else
    echo "结论: 🚨 检测到运行时垫片漂移——见上方 [🚨] 标记。多为厂商应用更新劫持了 ~/.local/bin；先报告用户，勿擅自改回。"
    exit 2
  fi
}

record() {
  local msg="${1:-}"
  if [ -z "$msg" ]; then
    echo "用法: env-audit.sh record \"说明（谁/做了什么/如何回滚）\"" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$LEDGER")"
  if [ ! -f "$LEDGER" ]; then
    printf '# 环境变更账本（env-hygiene）\n\n格式：- 日期 时间 — 说明（操作者 / 回滚方式）\n\n' > "$LEDGER"
  fi
  printf -- '- %s — %s\n' "$(date '+%Y-%m-%d %H:%M')" "$msg" >> "$LEDGER"
  echo "已记账 → $LEDGER"
}

case "${1:-audit}" in
  audit)  run_audit ;;
  record) record "${2:-}" ;;
  *) echo "用法: env-audit.sh [audit | record \"说明\"]" >&2; exit 1 ;;
esac
