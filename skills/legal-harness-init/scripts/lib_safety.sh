#!/usr/bin/env bash
# Shared file metadata and managed-block validation for all write/verify paths.
sha256_file() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        return 1
    fi
}

file_mode() {
    case "$(uname -s)" in
        Darwin|*BSD) stat -f '%Lp' "$1" ;;
        *) stat -c '%a' "$1" ;;
    esac
}

configuration_sha256() {
    local content digest
    content=$(mktemp "${TMPDIR:-/tmp}/legal-harness-body.XXXXXX") || return 1
    awk '
        $0 == "<!-- legal-harness-init:init-environment:start -->" { meta=1; next }
        $0 == "<!-- legal-harness-init:init-environment:end -->" { meta=0; next }
        !meta { lines[++n]=$0; if ($0 ~ /[^[:space:]]/) last=n }
        END { for (i=1; i<=last; i++) print lines[i] }
    ' "$1" > "$content"
    digest=$(sha256_file "$content") || { rm -f "$content"; return 1; }
    rm -f "$content"
    printf '%s' "$digest"
}

current_environment_recorded() {
    local digest row
    digest=$(configuration_sha256 "$1") || return 1
    row=$(awk '
        $0 == "<!-- legal-harness-init:init-environment:start -->" { meta=1; next }
        $0 == "<!-- legal-harness-init:init-environment:end -->" { meta=0; next }
        meta && /^\| [0-9]/ { row=$0 }
        END { print row }
    ' "$1")
    case "$row" in
        *"config-sha256=$digest"*) return 0 ;;
        *) return 1 ;;
    esac
}

validate_managed_markers() {
    # 所有 legal-harness-init 区块必须顺序成对、同 id 闭合且每个 id 唯一；不允许交叉或嵌套。
    awk '
        /<!--[[:space:]]*legal-harness-init:/ && $0 !~ /^<!--[[:space:]]legal-harness-init:[a-z0-9-]+:(start|end)[[:space:]]-->$/ { bad=1 }
        /^<!--[[:space:]]legal-harness-init:[a-z0-9-]+:(start|end)[[:space:]]-->$/ {
            marker=$0
            id=marker
            sub(/^<!--[[:space:]]legal-harness-init:/, "", id)
            sub(/:(start|end)[[:space:]]-->$/, "", id)
            kind=marker
            sub(/^.*:/, "", kind)
            sub(/[[:space:]]-->$/, "", kind)
            if (kind == "start") {
                if (open != "" || ++starts[id] > 1) bad=1
                open=id
            } else {
                if (open != id || ++ends[id] > 1) bad=1
                open=""
            }
        }
        END {
            if (open != "") bad=1
            for (id in starts) if (starts[id] != ends[id]) bad=1
            exit bad ? 1 : 0
        }
    ' "$1"
}
