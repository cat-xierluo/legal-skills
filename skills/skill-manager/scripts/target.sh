#!/bin/bash

# Shared target resolution for Skill Manager scripts.
# Returns the agent config directory that owns skills/ and commands/.

is_agent_config_dir_name() {
    case "$1" in
        .codex|.claude|.openclaw|.agents|.agent)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

canonical_dir() {
    local dir="$1"
    if [ -d "$dir" ]; then
        (cd "$dir" 2>/dev/null && pwd) || printf '%s\n' "$dir"
    else
        printf '%s\n' "$dir"
    fi
}

find_agent_config_dir() {
    local start_dir="${1:-$PWD}"
    local fallback_dir="${2:-$PWD/.claude}"
    local current
    local home_dir="${HOME:-/Users/${USER}}"
    local max_iterations=20
    local iteration=0

    if [ -n "${SKILL_MANAGER_TARGET_DIR:-}" ]; then
        printf '%s\n' "$SKILL_MANAGER_TARGET_DIR"
        return 0
    fi

    current="$(canonical_dir "$start_dir")"

    # Global config roots: support calls from ~/.codex, ~/.claude and ~/.openclaw.
    for config_name in .codex .claude .openclaw .agents .agent; do
        case "$current" in
            "$home_dir/$config_name"|"$home_dir/$config_name"/*)
                printf '%s\n' "$home_dir/$config_name"
                return 0
                ;;
        esac
    done

    while [ "$iteration" -lt "$max_iterations" ]; do
        local current_name
        current_name="$(basename "$current")"

        if is_agent_config_dir_name "$current_name"; then
            printf '%s\n' "$current"
            return 0
        fi

        # Project-local config directories. Prefer Codex when multiple configs coexist.
        for config_name in .codex .claude .openclaw .agents .agent; do
            if [ -d "$current/$config_name" ]; then
                printf '%s\n' "$current/$config_name"
                return 0
            fi
        done

        local parent
        parent="$(dirname "$current")"

        if [ "$parent" = "$current" ]; then
            break
        fi

        local parent_name
        parent_name="$(basename "$parent")"

        if [ "$parent_name" = "skills" ] || [ "$parent_name" = "commands" ]; then
            local grandparent
            grandparent="$(dirname "$parent")"
            local grandparent_name
            grandparent_name="$(basename "$grandparent")"
            if is_agent_config_dir_name "$grandparent_name"; then
                printf '%s\n' "$grandparent"
                return 0
            fi
        fi

        current="$parent"
        iteration=$((iteration + 1))
    done

    printf '%s\n' "$fallback_dir"
}

# Find ALL agent config directories in the project.
# Returns newline-separated paths (one per line).
# - SKILL_MANAGER_TARGET_DIR set → returns that single dir
# - Called from global config root (~/codex etc.) → returns that single dir
# - Project directory → walks up to project root, returns all .codex/.claude/.openclaw found
# - Not found → returns fallback_dir
find_all_agent_config_dirs() {
    local start_dir="${1:-$PWD}"
    local fallback_dir="${2:-$PWD/.claude}"
    local current
    local home_dir="${HOME:-/Users/${USER}}"
    local max_iterations=20
    local iteration=0

    # Explicit override → single target
    if [ -n "${SKILL_MANAGER_TARGET_DIR:-}" ]; then
        printf '%s\n' "$SKILL_MANAGER_TARGET_DIR"
        return 0
    fi

    current="$(canonical_dir "$start_dir")"

    # Global config roots → single target (no multi-dir in global scope)
    for config_name in .codex .claude .openclaw .agents .agent; do
        case "$current" in
            "$home_dir/$config_name"|"$home_dir/$config_name"/*)
                printf '%s\n' "$home_dir/$config_name"
                return 0
                ;;
        esac
    done

    # Walk up to find project root
    while [ "$iteration" -lt "$max_iterations" ]; do
        local current_name
        current_name="$(basename "$current")"

        # If inside an agent config dir, step out to project root
        if is_agent_config_dir_name "$current_name"; then
            current="$(dirname "$current")"
        elif [ "$current_name" = "skills" ] || [ "$current_name" = "commands" ]; then
            local parent
            parent="$(dirname "$current")"
            local parent_name
            parent_name="$(basename "$parent")"
            if is_agent_config_dir_name "$parent_name"; then
                current="$(dirname "$parent")"
            fi
        fi

        # Check for agent config dirs at this level
        local found=0
        for config_name in .codex .claude .openclaw .agents .agent; do
            if [ -d "$current/$config_name" ]; then
                printf '%s\n' "$current/$config_name"
                found=1
            fi
        done

        if [ "$found" -eq 1 ]; then
            return 0
        fi

        local parent
        parent="$(dirname "$current")"

        if [ "$parent" = "$current" ]; then
            break
        fi

        current="$parent"
        iteration=$((iteration + 1))
    done

    printf '%s\n' "$fallback_dir"
}
