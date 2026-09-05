#!/usr/bin/env bash
# spawn-worker-deps.sh — worktree 依赖补偿 + 默认 verify 命令注入（Task-045/046，G31）
#
# 被 spawn-worker.sh source；依赖其全局变量：PROJECT_DIR / WORKTREE / VERIFY_COMMANDS、
# DEPS_MODE / AUTHORIZED_INSTALL_COMMANDS（--deps-mode 解析见 resolve_deps_mode）。
# 不自己 set -e（继承 spawn-worker.sh 的错误处理）。
#
# 背景（G31）：Orca worktree 落在 ~/orca/workspaces/<project>/<name>（独立路径树），
# 不在主仓父链上 → npm/vitest/tsc 向上解析找不到主仓 node_modules → worker 无法自验。
# tmux worktree 本在主仓子树（.claude/worktrees/）靠向上解析白嫖（G28），Orca 路径
# 打破后失效。本文件在 worktree 创建后软链主仓 node_modules（Node 项目）、并按
# package.json scripts 注入默认 verify 命令到白名单，让 worker 不靠路径巧合也能自验。
#
# 详见 references/10-parallel-lessons.md G28/G31、TASKS.md Task-045/046。

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

# --deps-mode auto|symlink|local 解析（FaroPDF 2026-08-30 连环坑：Orca worktree 软链
# 主仓 node_modules 导致 pnpm add 拒写软链、vite dev server server.fs.allow 拒软链路径
# → vitest 全挂，PM 被迫每次 spawn 后手工 rm 软链 + pnpm install 重建本地）。
#   - auto（默认）：本次 spawn 显式传了 --allow-install-command（PM 授权安装 = 任务会改
#     依赖）时自动选 local 并打印推断理由；否则保持 symlink，既有软链行为完全不变。
#   - symlink：强制软链（legacy 行为）。
#   - local：不建软链，worker 在 worktree 内本地安装（授权走既有 --allow-install-command
#     + --install-authorization-source 通道）。
# 非法值 fail-closed（spawn-worker-flags.sh 解析层已挡一次，此处兜底直接 source 本模块
# 的调用方）。向后兼容：DEPS_MODE 未设按 auto；AUTHORIZED_INSTALL_COMMANDS 未设按空。
resolve_deps_mode() {
  case "${DEPS_MODE:-auto}" in
    symlink|local)
      echo "SPAWN_WORKER_DEPS_MODE: $DEPS_MODE (explicit)"
      ;;
    auto)
      if [ -n "${AUTHORIZED_INSTALL_COMMANDS[*]-}" ]; then
        DEPS_MODE=local
        echo "SPAWN_WORKER_DEPS_MODE_AUTO_LOCAL: 检测到 --allow-install-command（任务会改依赖），auto 自动选 local：不建 node_modules 软链，worker 在 worktree 内本地安装"
      else
        DEPS_MODE=symlink
      fi
      ;;
    *)
      echo "ERROR: SPAWN_WORKER_DEPS_MODE_INVALID: $DEPS_MODE（只接受 auto|symlink|local）" >&2
      return 1
      ;;
  esac
}

# Node 项目 symlink 补偿（G31 原逻辑原样提取，行为零变化）。
ensure_node_deps_symlink() {
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
}

# Node 项目 local 模式（--deps-mode local，显式或 auto+--allow-install-command 推断）：
# 不建软链，worker 在 worktree 内本地安装；断链 fail-closed 语义保留——断软链会让
# install 写穿主仓依赖或让验证静默失败，local 模式同样拒绝启动这种"看似可用"的 worker。
ensure_node_deps_local() {
  if [ -L "$WORKTREE/node_modules" ] && [ ! -e "$WORKTREE/node_modules" ]; then
    echo "ERROR: SPAWN_WORKER_DEPS_BROKEN_LINK: worktree node_modules is a broken symlink; refusing to start an unverifiable worker" >&2
    return 1
  elif [ -e "$WORKTREE/node_modules" ]; then
    echo "SPAWN_WORKER_DEPS_EXISTS: worktree 已有 node_modules，跳过"
  else
    echo "SPAWN_WORKER_DEPS_LOCAL: 未建 node_modules 软链（deps-mode=local）；worker 首次验证前需在 worktree 内本地 install（如 pnpm install），安装授权走既有 --allow-install-command + --install-authorization-source 通道"
  fi
}

# worktree 创建后调用：按项目类型补偿依赖。
# 全局读：PROJECT_DIR、WORKTREE、DEPS_MODE、AUTHORIZED_INSTALL_COMMANDS。
# Node：先 resolve_deps_mode 解析模式，再按模式软链（symlink）或不补偿只打提示（local）。
# Rust：~/.cargo registry 共享、worktree target 独立，不补偿（仅打印 info）。
# Python：venv 含绝对路径、软链会挂，不自动补偿（打印 blocked，PM 决定是否手动建 venv）。
ensure_worktree_deps() {
  resolve_deps_mode || return 1
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
      if [ "$DEPS_MODE" = "local" ]; then
        ensure_node_deps_local || return 1
      else
        ensure_node_deps_symlink || return 1
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
      # venv 含绝对路径 shebang/激活脚本，自动软链有风险（venv 内绝对路径在多数
      # 布局下仍可用，但路径敏感场景会坏）。默认不补偿；PM 显式传
      # --python-runtime-symlink <主仓 .runtime 路径> 时按 opt-in 补偿（Task-061，
      # badminton-lab Wave 1/2 两轮验证的符号链接模式），且 fail-closed：
      #   - worktree 已有 .runtime（真实目录或有效软链）→ 保留不动
      #   - 源解释器 $src/venv/bin/python 不存在或为 0 字节占位（Wave 1 实际出现）
      #     → 拒绝启动，宁可报错也不留一个看似启动实际无法验证的 worker
      local rt_src="${PYTHON_RUNTIME_SYMLINK:-}"
      if [ -z "$rt_src" ]; then
        echo "SPAWN_WORKER_DEPS_PYTHON_BLOCKED: venv 路径敏感不自动补偿；PM 可传 --python-runtime-symlink <主仓 .runtime> 显式补偿，或 --allow-install-command 授权安装"
      elif [ -e "$WORKTREE/.runtime" ] || [ -L "$WORKTREE/.runtime" ]; then
        echo "SPAWN_WORKER_DEPS_PYTHON_RT_EXISTS: worktree .runtime 已存在，保留不动"
      elif [ ! -d "$rt_src" ]; then
        echo "ERROR: SPAWN_WORKER_DEPS_PYTHON_RT_INVALID: --python-runtime-symlink 源不是目录: $rt_src" >&2
        return 1
      elif [ ! -s "$rt_src/venv/bin/python" ]; then
        echo "ERROR: SPAWN_WORKER_DEPS_PYTHON_RT_INVALID: 源解释器缺失或为 0 字节占位: $rt_src/venv/bin/python" >&2
        return 1
      elif ln -s "$rt_src" "$WORKTREE/.runtime" 2>/dev/null; then
        echo "SPAWN_WORKER_DEPS_PYTHON_RT_LINKED: .runtime -> ${rt_src}（PM 显式授权的运行时共享）"
      else
        echo "ERROR: SPAWN_WORKER_DEPS_PYTHON_RT_LINK_FAILED: cannot link .runtime; refusing to start an unverifiable worker" >&2
        return 1
      fi
      ;;
  esac
}

# 派发副作用前调用：按 package.json scripts、Makefile 目标或有界 Python 标记
# 注入默认 verify 命令到全局 VERIFY_COMMANDS。
# 全局读写：VERIFY_COMMANDS、PROJECT_DIR。
# PM 已显式传 --verify-cmd（VERIFY_COMMANDS 非空）则不覆盖——PM 显式优先。
# package.json 路径：把 scripts 里存在的 typecheck/lint/test/test:e2e/build 注入
# "npm run <s>"。test:e2e 在 verification-gate 语义里是功能完成线（编译过 ≠
# 功能可用，FaroPDF 2026-08-05 QA-02 教训），所以只要项目有该 script 就默认
# 注入；无该 script 的项目自动跳过（grep -qx 守卫）。
# Makefile 路径（npm 未注入任何命令时兜底，Python/Cargo 等 Make 驱动项目）：
# 解析 "^target:" 形式的目标名，只注入白名单动词 test / test-* / check / ci / lint
# 为 "make <target>"；.PHONY、变量赋值、带路径的文件目标不匹配（字符类排除 / 与空白）。
# 只注入白名单动词是 fail-closed：PM 需要其他门禁目标（如 security-scan）时显式传
# --verify-cmd。
# install-guard 的 install 正则只匹配 npm install/ci/add，不匹配 npm run / make，故
# verify 命令走 allowed_shell 白名单（本函数注入后由 spawn-worker.sh 的 VERIFY_COMMANDS
# 进白名单）。
# Task-057。根因：badminton-lab 2026-08-25 Wave 2，Make 驱动的 Python 项目零注入，worker 的
# 全部 make 门禁被 SHELL_COMMAND_NOT_ALLOWLISTED 拦截，TDD 卡死在 RED 阶段。
inject_default_verify_commands() {
  if [ -z "$PROJECT_DIR" ]; then
    return 0
  fi

  # PM 已显式传 verify 命令 → 不覆盖。
  if [ "${#VERIFY_COMMANDS[@]}" -gt 0 ]; then
    return 0
  fi

  local npm_added=""
  local pkg="$PROJECT_DIR/package.json"
  if [ -f "$pkg" ]; then
    local scripts
    scripts=$(jq -r '.scripts // {} | keys[]' "$pkg" 2>/dev/null) || scripts=""
    if [ -n "$scripts" ]; then
      local s
      for s in typecheck lint test test:e2e build; do
        if printf '%s\n' "$scripts" | grep -qx "$s"; then
          VERIFY_COMMANDS+=("npm run $s")
          npm_added="$npm_added $s"
        fi
      done
    fi
  fi
  if [ -n "$npm_added" ]; then
    echo "SPAWN_WORKER_VERIFY_INJECTED: 默认 verify 命令已注入白名单 -$npm_added"
    # npm 是主项目类型，已注入即不再扫 Makefile，避免混合项目双份注入。
    return 0
  fi

  local mk="$PROJECT_DIR/Makefile"
  local make_added=""
  if [ -f "$mk" ]; then
    local targets
    targets=$(grep -E '^[a-zA-Z0-9_.-]+:' "$mk" 2>/dev/null | sed 's/:.*$//' | sort -u) || targets=""
    local t
    for t in $targets; do
      case "$t" in
        test|test-*|check|ci|lint)
          VERIFY_COMMANDS+=("make $t")
          make_added="$make_added $t"
          ;;
      esac
    done
  fi
  if [ -n "$make_added" ]; then
    echo "SPAWN_WORKER_VERIFY_INJECTED_MAKEFILE: 默认 verify 命令已注入白名单 (make) -$make_added"
    return 0
  fi

  # Python 仅识别项目根的显式 manifest + 根 tests/ 目录，不递归搜索、不执行配置，
  # 也不猜 pytest/tox/nox 等可能依赖额外环境的命令。嵌套项目必须走项目配置或
  # dispatch contract，以完整 `cd <dir> && ...` 字符串精确授权。
  if { [ -f "$PROJECT_DIR/pyproject.toml" ] || [ -f "$PROJECT_DIR/requirements.txt" ] || [ -f "$PROJECT_DIR/setup.py" ]; } \
    && [ -d "$PROJECT_DIR/tests" ]; then
    VERIFY_COMMANDS+=("python3 -m unittest discover -s tests -v")
    echo "SPAWN_WORKER_VERIFY_INJECTED_PYTHON: 默认 unittest discover 命令已注入白名单（仅项目根 tests/）"
  fi
}

verification_fail() {
  echo "ERROR: SPAWN_WORKER_VERIFICATION_CONTRACT_INVALID: $*" >&2
  return 64
}

# 将 JSON 数组逐项原样读入 VERIFY_COMMANDS。jq 的 NUL 分隔避免空格、引号和中文
# 被 shell 分词；命令本身禁止换行/NUL，保证它仍是单条可审计 Shell 输入。
read_verification_json_array() {
  local json="$1" command
  VERIFY_COMMANDS=()
  while IFS= read -r -d '' command; do
    VERIFY_COMMANDS+=("$command")
  done < <(printf '%s' "$json" | jq -j '.[] | ., "\u0000"')
}

# 单一来源顺序：无合同时的显式 --verify-cmd；否则 dispatch 合同；再到项目
# 配置与有界默认发现。多个权威来源不静默合并：CLI 与合同并存会拒绝。
resolve_verification_commands() {
  local config_path config_json selected_json matches value_kind

  if [ -n "${VERIFICATION_CONTRACT:-}" ] || [ -n "${VERIFICATION_TASK_ID:-}" ]; then
    [ -n "${VERIFICATION_CONTRACT:-}" ] && [ -n "${VERIFICATION_TASK_ID:-}" ] \
      || verification_fail "--verification-contract and --verification-task-id must be provided together" || return $?
    [ "${#VERIFY_COMMANDS[@]}" -eq 0 ] \
      || verification_fail "do not combine --verify-cmd with --verification-contract; the task contract must remain the single authority" || return $?
    [ -f "$VERIFICATION_CONTRACT" ] \
      || verification_fail "verification contract is not a readable file: $VERIFICATION_CONTRACT" || return $?
    python3 "$SCRIPT_DIR/dispatch-value-gate.py" "$VERIFICATION_CONTRACT" >/dev/null 2>&1 \
      || verification_fail "verification contract did not pass dispatch-value-gate.v2 preflight" || return $?
    config_json=$(jq -c --arg id "$VERIFICATION_TASK_ID" '
      if .schema_version != "dispatch-value-gate.v2" then error("schema_version") else . end
      | [.tasks[]? | select(.task_id == $id)]' "$VERIFICATION_CONTRACT" 2>/dev/null) \
      || verification_fail "contract must be valid dispatch-value-gate.v2 JSON" || return $?
    matches=$(printf '%s' "$config_json" | jq 'length')
    [ "$matches" -eq 1 ] \
      || verification_fail "task_id '$VERIFICATION_TASK_ID' must match exactly one contract task (matched $matches)" || return $?
    value_kind=$(printf '%s' "$config_json" | jq -r '.[0].value_kind // ""')
    selected_json=$(printf '%s' "$config_json" | jq -c '.[0].verification_commands')
    printf '%s' "$selected_json" | jq -e 'type == "array" and all(.[]; type == "string")' >/dev/null \
      || verification_fail "selected task verification_commands must be an array of strings" || return $?
    read_verification_json_array "$selected_json"
    VERIFY_COMMAND_SOURCE="dispatch-contract:$VERIFICATION_TASK_ID"
    case "$value_kind" in
      implementation|reusable_verification) REQUIRE_VERIFICATION=1 ;;
      merge_gate) ;;
      *) verification_fail "selected task has unsupported value_kind '$value_kind'" || return $? ;;
    esac
  elif [ "${#VERIFY_COMMANDS[@]}" -gt 0 ]; then
    VERIFY_COMMAND_SOURCE="cli:--verify-cmd"
  else
    config_path="${PROJECT_CONFIG_FILE:-}"
    if [ -n "$config_path" ]; then
      case "$config_path" in
        /*) ;;
        *) config_path="$PROJECT_DIR/$config_path" ;;
      esac
    fi
    if [ -z "$config_path" ] && [ -f "$PROJECT_DIR/.claude/orchestration.config.json" ]; then
      config_path="$PROJECT_DIR/.claude/orchestration.config.json"
    fi
    if [ -n "$config_path" ]; then
      [ -f "$config_path" ] \
        || verification_fail "project config is not a readable file: $config_path" || return $?
      config_json=$(jq -c '
        if .schema != "multi-agent-orchestration.project-config.v1" then error("schema") else . end
        | if (.verification | type) != "object" then error("verification") else . end' "$config_path" 2>/dev/null) \
        || verification_fail "project config must be valid project-config.v1 JSON with a verification object" || return $?
      if [ -n "${WORKER_TYPE:-}" ]; then
        printf '%s' "$config_json" | jq -e --arg type "$WORKER_TYPE" '.verification.by_worker_type | type == "object" and has($type)' >/dev/null \
          || verification_fail "unknown worker type '$WORKER_TYPE' in verification.by_worker_type" || return $?
        selected_json=$(printf '%s' "$config_json" | jq -c --arg type "$WORKER_TYPE" '.verification.by_worker_type[$type]')
        VERIFY_COMMAND_SOURCE="project-config:by_worker_type:$WORKER_TYPE"
      else
        selected_json=$(printf '%s' "$config_json" | jq -c '.verification.default')
        VERIFY_COMMAND_SOURCE="project-config:default"
      fi
      printf '%s' "$selected_json" | jq -e 'type == "array" and all(.[]; type == "string")' >/dev/null \
        || verification_fail "selected project verification profile must be an array of strings" || return $?
      read_verification_json_array "$selected_json"
      if printf '%s' "$config_json" | jq -e '.verification.required == true' >/dev/null; then
        REQUIRE_VERIFICATION=1
      elif ! printf '%s' "$config_json" | jq -e '.verification.required == false or .verification.required == null' >/dev/null; then
        verification_fail "verification.required must be boolean when present" || return $?
      fi
      PROJECT_CONFIG_FILE="$config_path"
    else
      [ -z "${WORKER_TYPE:-}" ] \
        || verification_fail "--worker-type requires a project config" || return $?
      inject_default_verify_commands
      if [ "${#VERIFY_COMMANDS[@]}" -gt 0 ]; then
        VERIFY_COMMAND_SOURCE="bounded-project-discovery"
      else
        VERIFY_COMMAND_SOURCE="none"
      fi
    fi
  fi
  printf 'SPAWN_WORKER_VERIFY_PREFLIGHT: source=%s required=%s count=%s\n' \
    "$VERIFY_COMMAND_SOURCE" "$REQUIRE_VERIFICATION" "${#VERIFY_COMMANDS[@]}"
}

validate_verification_commands() {
  local command seen="" index=0
  for command in "${VERIFY_COMMANDS[@]}"; do
    [ -n "$command" ] \
      || verification_fail "verification command[$index] is empty" || return $?
    case "$command" in
      [[:space:]]*|*[[:space:]]) verification_fail "verification command[$index] has surrounding whitespace" || return $? ;;
    esac
    case "$command" in
      *$'\n'*|*$'\r'*) verification_fail "verification command[$index] must be one line" || return $? ;;
    esac
    if printf '%s\n' "$seen" | grep -Fqx -- "$command"; then
      verification_fail "duplicate verification command[$index]: $command" || return $?
    fi
    seen="${seen}${seen:+$'\n'}$command"
    if python3 "$SCRIPT_DIR/dependency-install-guard.py" --classify-install "$command"; then
      verification_fail "verification command may install or mutate dependencies: $command; authorize installation separately" || return $?
    fi
    index=$((index + 1))
  done
  if [ "${REQUIRE_VERIFICATION:-0}" -eq 1 ] && [ "${#VERIFY_COMMANDS[@]}" -eq 0 ]; then
    verification_fail "self-verification is required but no command resolved; use --verify-cmd, --verification-contract + --verification-task-id, or project verification config" || return $?
  fi
}
