#!/bin/bash
# 智合法律研究 - 研究操作脚本
# 用法:
#   ./research.sh submit "<query>"           - 提交法律研究问题
#   ./research.sh status <task_id>           - 查询任务状态
#   ./research.sh result <task_id>           - 获取文字分析结果
#   ./research.sh report <task_id>           - 获取报告下载链接
#   ./research.sh history [page] [size]      - 查看历史任务
#   ./research.sh wait <task_id> [timeout]   - 轮询等待任务完成（阻塞式）
#   ./research.sh archive <task_id>          - 归档研究结果到 archive/
#
# 环境变量:
#   LEGAL_RESEARCH_TOKEN - JWT Token

set -e
export LC_ALL=UTF-8

# 获取 skill 根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 基础配置
BASE_URL="https://fc-openresearch-qzquocekez.cn-shanghai.fcapp.run"
CONFIG_DIR="${SKILL_ROOT}/assets"
ENV_FILE="${CONFIG_DIR}/.env"
ARCHIVE_DIR="${SKILL_ROOT}/archive"

# 默认轮询配置
DEFAULT_POLL_INTERVAL=15    # 轮询间隔（秒）
DEFAULT_TIMEOUT=600         # 默认超时（10分钟）

# 加载环境变量
load_token() {
    # 优先从 skill 专属配置加载
    if [[ -f "$ENV_FILE" ]]; then
        source "$ENV_FILE" 2>/dev/null || true
    fi
    # 兼容旧位置
    if [[ -z "$LEGAL_RESEARCH_TOKEN" && -f "${HOME}/.openclaw/.env" ]]; then
        source "${HOME}/.openclaw/.env" 2>/dev/null || true
    fi
    export LEGAL_RESEARCH_TOKEN
}

# 检查 Token
check_token() {
    if [[ -z "$LEGAL_RESEARCH_TOKEN" ]]; then
        echo '{"code": 401, "message": "未登录，请先执行 ./auth.sh 登录"}'
        return 1
    fi
}

# 提交研究问题
submit_query() {
    local query="$1"

    if [[ -z "$query" ]]; then
        echo '{"code": 400, "message": "请提供法律问题"}'
        return 1
    fi

    load_token
    check_token

    local payload
    payload=$(jq -n --arg q "$query" '{"query": $q}')

    curl -s -X POST "${BASE_URL}/api/research/query" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$payload"
}

# 查询任务状态
get_status() {
    local task_id="$1"

    if [[ -z "$task_id" ]]; then
        echo '{"code": 400, "message": "请提供 task_id"}'
        return 1
    fi

    load_token
    check_token

    curl -s -X GET "${BASE_URL}/api/research/status/${task_id}" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}"
}

# 获取研究结果
get_result() {
    local task_id="$1"

    if [[ -z "$task_id" ]]; then
        echo '{"code": 400, "message": "请提供 task_id"}'
        return 1
    fi

    load_token
    check_token

    curl -s -X GET "${BASE_URL}/api/research/result/${task_id}" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}"
}

# 获取报告下载链接
get_report() {
    local task_id="$1"

    if [[ -z "$task_id" ]]; then
        echo '{"code": 400, "message": "请提供 task_id"}'
        return 1
    fi

    load_token
    check_token

    curl -s -X GET "${BASE_URL}/api/research/report/${task_id}" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}"
}

# 查看历史任务
get_history() {
    local page="${1:-1}"
    local size="${2:-10}"

    load_token
    check_token

    curl -s -X GET "${BASE_URL}/api/research/history?page=${page}&size=${size}" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}"
}

# 轮询等待任务完成
wait_for_completion() {
    local task_id="$1"
    local timeout="${2:-$DEFAULT_TIMEOUT}"
    local interval="${3:-$DEFAULT_POLL_INTERVAL}"

    if [[ -z "$task_id" ]]; then
        echo '{"code": 400, "message": "请提供 task_id"}'
        return 1
    fi

    load_token
    check_token

    local elapsed=0
    local status=""

    echo "开始轮询任务状态 (task_id: ${task_id})"
    echo "超时: ${timeout}秒, 轮询间隔: ${interval}秒"
    echo "---"

    while [[ $elapsed -lt $timeout ]]; do
        status=$(get_status "$task_id")
        local state
        state=$(echo "$status" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

        echo "[$(date '+%H:%M:%S')] 状态: ${state:-unknown}"

        case "$state" in
            completed)
                echo "---"
                echo "任务完成！"
                echo "$status"
                return 0
                ;;
            failed)
                echo "---"
                echo "任务失败！"
                echo "$status"
                return 1
                ;;
            timeout)
                echo "---"
                echo "任务超时！"
                echo "$status"
                return 1
                ;;
            running|pending)
                sleep "$interval"
                elapsed=$((elapsed + interval))
                ;;
            *)
                echo "未知状态: $state"
                echo "$status"
                return 1
                ;;
        esac
    done

    echo "---"
    echo "轮询超时（${timeout}秒）"
    return 1
}

# 一键获取完整结果（状态+结果+报告）
get_full_result() {
    local task_id="$1"

    if [[ -z "$task_id" ]]; then
        echo '{"code": 400, "message": "请提供 task_id"}'
        return 1
    fi

    load_token
    check_token

    # 先检查状态
    local status_response
    status_response=$(get_status "$task_id")
    local state
    state=$(echo "$status_response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

    if [[ "$state" != "completed" ]]; then
        echo "$status_response"
        return 1
    fi

    # 获取结果
    local result_response
    result_response=$(get_result "$task_id")

    # 获取报告（如果有）
    local report_response
    report_response=$(get_report "$task_id" 2>/dev/null || echo '{"code":404}')

    # 组合输出
    echo "{"
    echo "\"status\": \"completed\","
    echo "\"task_id\": \"${task_id}\","
    echo "\"result\": ${result_response},"
    echo "\"report\": ${report_response}"
    echo "}"
}

# 生成归档目录名（格式：YYMMDD 主题_法律研究报告）
generate_archive_name() {
    local query="$1"
    local date_prefix
    date_prefix=$(date '+%y%m%d')

    # 提取研究主题：尝试从问题中提取关键词
    local topic
    # 移除特殊字符，提取前50个字符作为主题
    topic=$(python3 -c "
import re, sys
q = sys.argv[1]
q = re.sub(r'[/\\\\:*?\"<>|？]', ' ', q)
q = q.lstrip('：:')
q = q[:50].rstrip()
print(q)
" "$query")

    # 组合命名：YYMMDD 主题_法律研究报告
    echo "${date_prefix} ${topic}_法律研究报告"
}

# 生成报告文件名（格式：YYMMDD 主题_法律研究报告.md）
generate_report_filename() {
    local query="$1"
    local date_prefix
    date_prefix=$(date '+%y%m%d')

    # 提取主题关键词（与文件夹名保持一致）
    local topic
    topic=$(python3 -c "
import re, sys
q = sys.argv[1]
q = re.sub(r'[/\\\\:*?\"<>|？]', ' ', q)
q = q.lstrip('：:')
q = q[:50].rstrip()
print(q)
" "$query")

    echo "${date_prefix} ${topic}_法律研究报告.md"
}

# 将 docx 转换为 Markdown（需要 pandoc）
convert_docx_to_md() {
    local docx_file="$1"
    local md_file="$2"

    if command -v pandoc &>/dev/null; then
        # 使用 gfm (GitHub Flavored Markdown) 格式，保留层级结构，提取图片
        pandoc -f docx -t gfm --wrap=none --extract-media="${docx_file%/*}/media" "$docx_file" -o "$md_file" 2>/dev/null
        return $?
    else
        return 1
    fi
}

# 归档研究结果
archive_result() {
    local task_id="$1"

    if [[ -z "$task_id" ]]; then
        echo '{"code": 400, "message": "请提供 task_id"}'
        return 1
    fi

    load_token
    check_token

    # 获取任务状态和查询内容
    local status_response
    status_response=$(get_status "$task_id")
    local state
    state=$(echo "$status_response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

    if [[ "$state" != "completed" ]]; then
        echo "{\"code\": 400, \"message\": \"任务未完成，当前状态: ${state}\"}"
        return 1
    fi

    # 获取结果
    local result_response
    result_response=$(get_result "$task_id")

    # 从 status 获取 query（result API 不含 query 字段）
    local query
    query=$(echo "$status_response" | jq -r '.data.query // ""' 2>/dev/null || echo "")
    local text_result
    text_result=$(echo "$result_response" | jq -r '.data.text_result // .text_result // ""' 2>/dev/null || echo "")

    # text_result 可能是 Python dict 格式，如 {'node_status': {}, 'Output': {'output': '...'}}
    # 尝试提取 Output.output 中的实际内容
    if echo "$text_result" | grep -q "'Output'" 2>/dev/null; then
        local extracted
        extracted=$(echo "$text_result" | sed "s/'/\"/g" | jq -r '.Output.output // empty' 2>/dev/null || echo "")
        if [[ -n "$extracted" ]]; then
            text_result="$extracted"
        fi
    fi

    # 生成归档目录名
    local archive_name
    archive_name=$(generate_archive_name "${query:-法律研究}")
    local task_archive_dir="${ARCHIVE_DIR}/${archive_name}"
    mkdir -p "$task_archive_dir"

    # 保存结果为 Markdown（使用主题命名）
    local result_filename="${archive_name}.md"
    local result_file="${task_archive_dir}/${result_filename}"
    {
        echo "# 法律研究报告"
        echo ""
        echo "**任务ID**: ${task_id}"
        echo "**归档时间**: $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""
        echo "## 研究问题"
        echo ""
        echo "${query:-未知问题}"
        echo ""
        echo "---"
        echo ""
        echo "## 研究结果"
        echo ""
        echo "${text_result}"
    } > "$result_file"

    local files=("${result_filename}")

    # 尝试下载报告（报告 API 返回 code 200 表示有报告，404 表示无）
    local report_response
    report_response=$(get_report "$task_id" 2>/dev/null || echo '{"code":404}')
    local report_code
    report_code=$(echo "$report_response" | jq -r '.code // 404' 2>/dev/null)

    if [[ "$report_code" == "200" ]]; then
        local report_url
        report_url=$(echo "$report_response" | jq -r '.data.report_url // empty' 2>/dev/null)

        # 生成统一的报告文件名（与 Markdown 保持一致）
        local report_filename
        report_filename=$(generate_report_filename "${query:-法律研究}")
        local docx_file="${task_archive_dir}/${report_filename%.md}.docx"

        if [[ -n "$report_url" ]]; then
            echo "📥 正在下载报告: ${report_filename%.md}.docx"
            if curl -sL "$report_url" -o "$docx_file" 2>/dev/null && [[ -s "$docx_file" ]]; then
                echo "   - ${report_filename%.md}.docx (详细报告)"
                files+=("${report_filename%.md}.docx")

                # 尝试转换为 Markdown（使用 _报告 后缀避免覆盖文字结果）
                local report_md_name="${report_filename%.md}_报告.md"
                local report_md="${task_archive_dir}/${report_md_name}"
                if convert_docx_to_md "$docx_file" "$report_md"; then
                    echo "   - ${report_md_name} (Markdown版本)"
                    files+=("${report_md_name}")
                fi
            else
                echo "⚠️ 报告下载失败，链接已保存到归档文件"
                echo "" >> "$result_file"
                echo "## 报告下载链接" >> "$result_file"
                echo "" >> "$result_file"
                echo "[报告](${report_url})" >> "$result_file"
            fi
        fi
    else
        echo "ℹ️ 该任务无 Word 报告（仅文字结果）"
    fi

    echo ""
    echo "✅ 归档完成: ${task_archive_dir}/"
    for f in "${files[@]}"; do
        echo "   - ${f}"
    done

    # 返回 JSON 结果
    local files_json
    files_json=$(printf '%s\n' "${files[@]}" | jq -R . | jq -s .)
    echo ""
    echo "{\"code\": 200, \"archive_path\": \"${task_archive_dir}\", \"archive_name\": \"${archive_name}\", \"files\": ${files_json}}"
}

# 列出归档
list_archive() {
    if [[ ! -d "$ARCHIVE_DIR" ]]; then
        echo "[]"
        return 0
    fi

    local result="["
    local first=true

    for dir in "$ARCHIVE_DIR"/*/; do
        if [[ -d "$dir" ]]; then
            local task_id
            task_id=$(basename "$dir")

            if [[ "$first" == "true" ]]; then
                first=false
            else
                result+=","
            fi

            result+="{\"task_id\":\"${task_id}\",\"path\":\"${dir}\"}"
        fi
    done

    result+="]"
    echo "$result"
}

# 主入口
case "${1:-}" in
    submit)
        submit_query "$2"
        ;;
    status)
        get_status "$2"
        ;;
    result)
        get_result "$2"
        ;;
    report)
        get_report "$2"
        ;;
    history)
        get_history "$2" "$3"
        ;;
    wait)
        wait_for_completion "$2" "$3" "$4"
        ;;
    full)
        get_full_result "$2"
        ;;
    archive)
        archive_result "$2"
        ;;
    list-archive)
        list_archive
        ;;
    *)
        echo "用法: $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  submit \"<query>\"        提交法律研究问题"
        echo "  status <task_id>        查询任务状态"
        echo "  result <task_id>        获取文字分析结果"
        echo "  report <task_id>        获取报告下载链接"
        echo "  history [page] [size]   查看历史任务"
        echo "  wait <task_id> [timeout] [interval]  轮询等待完成"
        echo "  full <task_id>          一键获取完整结果（需任务已完成）"
        echo "  archive <task_id>       归档研究结果到 archive/"
        echo "  list-archive            列出所有归档"
        echo ""
        echo "归档目录结构:"
        echo "  archive/YYMMDD 主题_法律研究报告/"
        echo "    ├── ...研究报告.md         - 研究结果摘要"
        echo "    ├── ...研究报告.docx       - Word 报告（如有）"
        echo "    ├── ...研究报告_报告.md    - Word 转 Markdown（如有）"
        echo "    └── media/                  - 报告图片（如有）"
        echo ""
        echo "示例:"
        echo "  $0 submit \"劳动合同到期不续签需要赔偿吗？\""
        echo "  $0 archive abc123"
        exit 1
        ;;
esac
