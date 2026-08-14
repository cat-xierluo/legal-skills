#!/usr/bin/env bash
# spawn-worker-deps.sh — worktree 依赖补偿 + 默认 verify 命令注入（Task-045/046，G31）
#
# 被 spawn-worker.sh source；依赖其全局变量：PROJECT_DIR / WORKTREE / VERIFY_COMMANDS。
# 不自己 set -e（继承 spawn-worker.sh 的错误处理）。
#
# 背景（G31）：Orca worktree 落在 ~/orca/workspaces/<project>/<name>（独立路径树），
# 不在主仓父链上 → npm/vitest/tsc 向上解析找不到主仓 node_modules → worker 无法自验。
# tmux worktree 本在主仓子树（.claude/worktrees/）靠向上解析白嫖（G28），Orca 路径
# 打破后失效。本文件在 worktree 创建后软链主仓 node_modules（Node 项目）、并按
# package.json scripts 注入默认 verify 命令到白名单，让 worker 不靠路径巧合也能自验。
#
# 详见 references/09-parallel-lessons.md G28/G31、TASKS.md Task-045/046。

# 检测目录的项目类型。输出空格分隔的 kind（node rust python），可能多个（mixed）。
# 用文件存在性，简单可靠；不解析文件内容（避免误判）。
detect_project_type() {
  local dir="$1" kinds=""
  [ -f "$dir/package.json" ] && kinds="$kinds node"
  [ -f "$dir/Cargo.toml" ] && kinds="$kinds rust"
  if [ -f "$dir/pyproject.toml" ] || [ -f "$dir/requirements.txt" ] || [ -f "$dir/setup.py" ]; then
    kinds="$kinds python"
  fi
  printf '%s' "$kinds"
}

# worktree 创建后调用：按项目类型补偿依赖。
# 全局读：PROJECT_DIR、WORKTREE。
# Node：worktree 不在主仓父链 + 主仓有 node_modules + worktree 无 node_modules → 软链。
# Rust：~/.cargo registry 共享、worktree target 独立，不补偿（仅打印 info）。
# Python：venv 含绝对路径、软链会挂，不自动补偿（打印 blocked，PM 决定是否手动建 venv）。
ensure_worktree_deps() {
  if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "SPAWN_WORKER_DEPS_DRYRUN: dry-run 不软链"
    return 0
  fi
  if [ -z "$PROJECT_DIR" ] || [ -z "$WORKTREE" ] || [ ! -d "$WORKTREE" ]; then
    return 0
  fi

  local kinds
  kinds=$(detect_project_type "$PROJECT_DIR")

  case "$kinds" in
    *node*)
      local proj_nm="$PROJECT_DIR/node_modules"
      if [ ! -d "$proj_nm" ]; then
        echo "SPAWN_WORKER_DEPS_SKIP: 主仓无 node_modules，跳过软链（worker 需自行 npm install，受 install-guard 约束）"
      elif [ -L "$WORKTREE/node_modules" ] && [ ! -e "$WORKTREE/node_modules" ]; then
        echo "ERROR: SPAWN_WORKER_DEPS_BROKEN_LINK: worktree node_modules is a broken symlink; refusing to start an unverifiable worker" >&2
        return 1
      elif [ -e "$WORKTREE/node_modules" ]; then
        # worktree 已有 node_modules（真实目录或软链）—— 不覆盖，避免破坏既有状态。
        echo "SPAWN_WORKER_DEPS_EXISTS: worktree 已有 node_modules，跳过"
      else
        # 父链判断：worktree 物理路径是否以主仓物理路径为前缀。
        # tmux worktree 默认在 .claude/worktrees/（主仓子树）→ 在父链 → 向上解析够，不软链。
        # Orca worktree 在 ~/orca/workspaces/（独立路径树）→ 不在父链 → 软链补偿。
        local proj_real wt_real
        proj_real=$(cd "$PROJECT_DIR" && pwd -P)
        wt_real=$(cd "$WORKTREE" && pwd -P)
        if [ "$wt_real" != "${wt_real#"$proj_real"/}" ]; then
          echo "SPAWN_WORKER_DEPS_IN_TREE: worktree 在主仓父链，npm 向上解析即可，不软链（G28）"
        else
          if ln -s "$proj_real/node_modules" "$wt_real/node_modules" 2>/dev/null; then
            echo "SPAWN_WORKER_DEPS_LINKED: node_modules -> $proj_real/node_modules（worktree 不在主仓父链，G31 补偿）"
          else
            echo "ERROR: SPAWN_WORKER_DEPS_LINK_FAILED: cannot link node_modules; refusing to start an unverifiable worker" >&2
            return 1
          fi
        fi
      fi
      ;;
  esac

  case "$kinds" in
    *rust*)
      # ~/.cargo registry cache 全局共享；worktree 的 target/ 独立首次编译（首次慢、能跑）。
      echo "SPAWN_WORKER_DEPS_RUST_SHARED: cargo registry 共享，worktree target 独立，无需补偿"
      ;;
  esac

  case "$kinds" in
    *python*)
      # venv 含绝对路径 shebang/激活脚本，软链到 worktree 会破坏；不自动补偿。
      # PM 需手动在 worktree 建 venv 或传 --allow-install-command 授权 pip install。
      echo "SPAWN_WORKER_DEPS_PYTHON_BLOCKED: venv 路径敏感不自动补偿，PM 决定是否手动建 venv"
      ;;
  esac
}

# write_install_authorization 前（spawn-worker.sh 内）调用：按 package.json scripts
# 注入默认 verify 命令到全局 VERIFY_COMMANDS。
# 全局读写：VERIFY_COMMANDS、PROJECT_DIR。
# PM 已显式传 --verify-cmd（VERIFY_COMMANDS 非空）则不覆盖——PM 显式优先。
# 否则把 package.json scripts 里存在的 typecheck/lint/test/test:e2e/build 注入
# "npm run <s>"。test:e2e 在 verification-gate 语义里是功能完成线（编译过 ≠
# 功能可用，FaroPDF 2026-08-05 QA-02 教训），所以只要项目有该 script 就默认
# 注入；无该 script 的项目自动跳过（grep -qx 守卫）。
# install-guard 的 install 正则只匹配 npm install/ci/add，不匹配 npm run，故 verify 命令
# 走 allowed_shell 白名单（本函数注入后由 spawn-worker.sh 的 VERIFY_COMMANDS 进白名单）。
inject_default_verify_commands() {
  if [ -z "$PROJECT_DIR" ]; then
    return 0
  fi
  local pkg="$PROJECT_DIR/package.json"
  [ -f "$pkg" ] || return 0

  # PM 已显式传 verify 命令 → 不覆盖。
  if [ "${#VERIFY_COMMANDS[@]}" -gt 0 ]; then
    return 0
  fi

  local scripts
  scripts=$(jq -r '.scripts // {} | keys[]' "$pkg" 2>/dev/null) || return 0
  [ -z "$scripts" ] && return 0

  local added=""
  local s
  for s in typecheck lint test test:e2e build; do
    if printf '%s\n' "$scripts" | grep -qx "$s"; then
      VERIFY_COMMANDS+=("npm run $s")
      added="$added $s"
    fi
  done
  if [ -n "$added" ]; then
    echo "SPAWN_WORKER_VERIFY_INJECTED: 默认 verify 命令已注入白名单 -$added"
  fi
}
