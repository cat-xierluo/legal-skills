#!/bin/bash
# 智合法律研究 - Token 管理脚本
# 用法:
#   ./token-manager.sh show      - 显示当前 Token（脱敏）
#   ./token-manager.sh export    - 导出 Token 到 stdout
#   ./token-manager.sh set <token> - 手动设置 Token
#   ./token-manager.sh clear     - 清除 Token
#   ./token-manager.sh migrate   - 从旧位置迁移 Token

set -e

CONFIG_DIR="${HOME}/.zhihe-legal-research"
ENV_FILE="${CONFIG_DIR}/config"
OLD_ENV_FILE="${HOME}/.openclaw/.env"

# 显示 Token（脱敏）
show_token() {
    if [[ -f "$ENV_FILE" ]]; then
        source "$ENV_FILE" 2>/dev/null || true
        if [[ -n "$LEGAL_RESEARCH_TOKEN" ]]; then
            local masked="${LEGAL_RESEARCH_TOKEN:0:20}...${LEGAL_RESEARCH_TOKEN: -10}"
            echo "Token: ${masked}"
            echo "来源: ${ENV_FILE}"
        else
            echo "Token: 未设置"
        fi
    else
        echo "Token: 未设置（配置文件不存在）"
    fi
}

# 导出 Token
export_token() {
    if [[ -f "$ENV_FILE" ]]; then
        source "$ENV_FILE" 2>/dev/null || true
        if [[ -n "$LEGAL_RESEARCH_TOKEN" ]]; then
            echo "LEGAL_RESEARCH_TOKEN=${LEGAL_RESEARCH_TOKEN}"
        fi
    fi
}

# 手动设置 Token
set_token() {
    local token="$1"

    if [[ -z "$token" ]]; then
        echo "错误: 请提供 Token"
        return 1
    fi

    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"

    if [[ -f "$ENV_FILE" ]] && grep -q "^LEGAL_RESEARCH_TOKEN=" "$ENV_FILE" 2>/dev/null; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|^LEGAL_RESEARCH_TOKEN=.*|LEGAL_RESEARCH_TOKEN=${token}|" "$ENV_FILE"
        else
            sed -i "s|^LEGAL_RESEARCH_TOKEN=.*|LEGAL_RESEARCH_TOKEN=${token}|" "$ENV_FILE"
        fi
    else
        echo "LEGAL_RESEARCH_TOKEN=${token}" >> "$ENV_FILE"
    fi

    chmod 600 "$ENV_FILE"
    echo "Token 已保存到: ${ENV_FILE}"
}

# 清除 Token
clear_token() {
    if [[ -f "$ENV_FILE" ]]; then
        rm -f "$ENV_FILE"
        echo "Token 已清除"
    else
        echo "无存储的 Token"
    fi
}

# 从旧位置迁移
migrate_token() {
    if [[ -f "$OLD_ENV_FILE" ]]; then
        source "$OLD_ENV_FILE" 2>/dev/null || true
        if [[ -n "$LEGAL_RESEARCH_TOKEN" ]]; then
            mkdir -p "$CONFIG_DIR"
            chmod 700 "$CONFIG_DIR"
            echo "LEGAL_RESEARCH_TOKEN=${LEGAL_RESEARCH_TOKEN}" > "$ENV_FILE"
            chmod 600 "$ENV_FILE"
            echo "Token 已从 ${OLD_ENV_FILE} 迁移到 ${ENV_FILE}"
        else
            echo "旧配置文件中未找到 Token"
        fi
    else
        echo "旧配置文件不存在: ${OLD_ENV_FILE}"
    fi
}

# 主入口
case "${1:-}" in
    show)
        show_token
        ;;
    export)
        export_token
        ;;
    set)
        set_token "$2"
        ;;
    clear)
        clear_token
        ;;
    migrate)
        migrate_token
        ;;
    *)
        echo "用法: $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  show          显示当前 Token（脱敏）"
        echo "  export        导出 Token 到 stdout"
        echo "  set <token>   手动设置 Token"
        echo "  clear         清除 Token"
        echo "  migrate       从旧位置 (~/.openclaw/.env) 迁移 Token"
        exit 1
        ;;
esac
