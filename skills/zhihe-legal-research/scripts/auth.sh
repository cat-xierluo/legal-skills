#!/bin/bash
# 智合法律研究 - 认证脚本
# 用法:
#   ./auth.sh check              - 检查登录状态
#   ./auth.sh send-code <phone>  - 发送验证码
#   ./auth.sh verify <phone> <code> - 验证登录
#   ./auth.sh logout             - 清除登录凭证
#
# 配置文件:
#   assets/.env - 存储 Token 和手机号（自包含在 skill 内部）
#
# 环境变量:
#   LEGAL_RESEARCH_TOKEN - JWT Token (自动加载)

set -e

# 获取 skill 根目录（脚本所在目录的上级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 基础配置
BASE_URL="https://fc-openresearch-qzquocekez.cn-shanghai.fcapp.run"
CONFIG_DIR="${SKILL_ROOT}/assets"
ENV_FILE="${CONFIG_DIR}/.env"

# 确保配置目录存在
ensure_config_dir() {
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"
}

# 加载环境变量
load_token() {
    if [[ -f "$ENV_FILE" ]]; then
        source "$ENV_FILE" 2>/dev/null || true
    fi
    export LEGAL_RESEARCH_TOKEN
    export LEGAL_RESEARCH_PHONE
}

# 检查登录状态
check_auth() {
    load_token

    if [[ -z "$LEGAL_RESEARCH_TOKEN" ]]; then
        echo '{"code": 401, "message": "未登录，请先执行登录流程", "is_vip": false}'
        return 1
    fi

    local response
    response=$(curl -s -X GET "${BASE_URL}/api/user/profile" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}" \
        -H "Content-Type: application/json")

    # 响应不是有效 JSON（如服务端 500 HTML 错误页），视为 token 失效
    if [[ ! "$response" =~ ^\{ ]]; then
        echo '{"code": 401, "message": "登录状态已失效，请重新登录", "is_vip": false}'
        return 1
    fi

    echo "$response"
}

# 发送验证码
send_code() {
    local phone="$1"

    # 如果未提供手机号，尝试使用保存的手机号
    if [[ -z "$phone" ]]; then
        load_token
        phone="$LEGAL_RESEARCH_PHONE"
    fi

    if [[ -z "$phone" ]]; then
        echo '{"code": 400, "message": "请提供手机号（未找到已保存的手机号）"}'
        return 1
    fi

    # 验证手机号格式
    if [[ ! "$phone" =~ ^1[0-9]{10}$ ]]; then
        echo '{"code": 400, "message": "手机号格式错误，需要11位中国手机号（1开头）"}'
        return 1
    fi

    local payload
    payload=$(jq -n --arg p "$phone" '{"phone": $p}')

    curl -s -X POST "${BASE_URL}/api/auth/send-code" \
        -H "Content-Type: application/json" \
        -d "$payload"
}

# 验证登录
verify_code() {
    local phone="$1"
    local code="$2"

    if [[ -z "$phone" || -z "$code" ]]; then
        echo '{"code": 400, "message": "请提供手机号和验证码"}'
        return 1
    fi

    # 验证码格式
    if [[ ! "$code" =~ ^[0-9]{6}$ ]]; then
        echo '{"code": 400, "message": "验证码格式错误，需要6位数字"}'
        return 1
    fi

    local payload
    payload=$(jq -n --arg p "$phone" --arg c "$code" '{"phone": $p, "code": $c}')

    local response
    response=$(curl -s -X POST "${BASE_URL}/api/auth/verify-code" \
        -H "Content-Type: application/json" \
        -d "$payload")

    # 提取 token 并保存
    local token
    token=$(echo "$response" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

    if [[ -n "$token" ]]; then
        ensure_config_dir

        # 更新或添加 TOKEN
        if [[ -f "$ENV_FILE" ]] && grep -q "^LEGAL_RESEARCH_TOKEN=" "$ENV_FILE" 2>/dev/null; then
            if [[ "$(uname)" == "Darwin" ]]; then
                sed -i '' "s|^LEGAL_RESEARCH_TOKEN=.*|LEGAL_RESEARCH_TOKEN=${token}|" "$ENV_FILE"
            else
                sed -i "s|^LEGAL_RESEARCH_TOKEN=.*|LEGAL_RESEARCH_TOKEN=${token}|" "$ENV_FILE"
            fi
        else
            echo "LEGAL_RESEARCH_TOKEN=${token}" >> "$ENV_FILE"
        fi

        # 更新或添加 PHONE
        if [[ -f "$ENV_FILE" ]] && grep -q "^LEGAL_RESEARCH_PHONE=" "$ENV_FILE" 2>/dev/null; then
            if [[ "$(uname)" == "Darwin" ]]; then
                sed -i '' "s|^LEGAL_RESEARCH_PHONE=.*|LEGAL_RESEARCH_PHONE=${phone}|" "$ENV_FILE"
            else
                sed -i "s|^LEGAL_RESEARCH_PHONE=.*|LEGAL_RESEARCH_PHONE=${phone}|" "$ENV_FILE"
            fi
        else
            echo "LEGAL_RESEARCH_PHONE=${phone}" >> "$ENV_FILE"
        fi

        # 设置文件权限
        chmod 600 "$ENV_FILE"

        export LEGAL_RESEARCH_TOKEN="$token"
        echo "$response"
    else
        echo "$response"
        return 1
    fi
}

# 登出（清除凭证）
logout() {
    if [[ -f "$ENV_FILE" ]]; then
        rm -f "$ENV_FILE"
        echo '{"code": 200, "message": "已清除登录凭证"}'
    else
        echo '{"code": 200, "message": "无存储的凭证"}'
    fi
    unset LEGAL_RESEARCH_TOKEN
}

# 显示配置信息
show_config() {
    echo "配置目录: ${CONFIG_DIR}"
    echo "配置文件: ${ENV_FILE}"
    if [[ -f "$ENV_FILE" ]]; then
        echo "文件状态: 存在"
        if [[ -n "$LEGAL_RESEARCH_TOKEN" ]]; then
            echo "Token: 已设置 (${LEGAL_RESEARCH_TOKEN:0:20}...)"
        else
            echo "Token: 未设置"
        fi
    else
        echo "文件状态: 不存在"
    fi
}

# 主入口
case "${1:-}" in
    check)
        check_auth
        ;;
    send-code)
        send_code "$2"
        ;;
    verify)
        verify_code "$2" "$3"
        ;;
    logout)
        logout
        ;;
    config)
        load_token
        show_config
        ;;
    *)
        echo "用法: $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  check                  检查登录状态"
        echo "  send-code <phone>      发送验证码到指定手机"
        echo "  verify <phone> <code>  验证登录并保存 Token"
        echo "  logout                 清除登录凭证"
        echo "  config                 显示配置信息"
        echo ""
        echo "配置存储位置: assets/.env（skill 内部）"
        exit 1
        ;;
esac
