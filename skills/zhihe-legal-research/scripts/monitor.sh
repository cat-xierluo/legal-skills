#!/bin/bash
# 智合法律研究 - 后台监控脚本
# 用法:
#   ./monitor.sh start <task_id> [timeout] [interval]  - 启动后台监控
#   ./monitor.sh status                                - 查看监控状态
#   ./monitor.sh results                               - 获取已完成但未读的结果
#   ./monitor.sh clear <task_id>                       - 清除已读结果
#   ./monitor.sh archive <task_id>                     - 归档研究结果
#
# 配置文件（自包含在 skill 内部）:
#   assets/pending.json    - 待处理任务
#   assets/completed.json  - 已完成结果（待通知）
#   assets/notified.json   - 已通知结果

set -e

# 获取 skill 根目录（使用相对路径，支持任意安装位置）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONFIG_DIR="${SKILL_ROOT}/assets"
PENDING_FILE="${CONFIG_DIR}/pending.json"
COMPLETED_FILE="${CONFIG_DIR}/completed.json"
NOTIFIED_FILE="${CONFIG_DIR}/notified.json"
ENV_FILE="${CONFIG_DIR}/.env"
ARCHIVE_DIR="${SKILL_ROOT}/archive"

BASE_URL="https://fc-openresearch-qzquocekez.cn-shanghai.fcapp.run"
DEFAULT_TIMEOUT=600
DEFAULT_INTERVAL=15

# 确保目录和文件存在
ensure_files() {
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"

    for f in "$PENDING_FILE" "$COMPLETED_FILE" "$NOTIFIED_FILE"; do
        if [[ ! -f "$f" ]]; then
            echo '[]' > "$f"
        fi
    done
}

# 加载 Token
load_token() {
    if [[ -f "$ENV_FILE" ]]; then
        source "$ENV_FILE" 2>/dev/null || true
    fi
    export LEGAL_RESEARCH_TOKEN
}

# 添加到待处理列表
add_pending() {
    local task_id="$1"
    local query="$2"

    ensure_files

    local pending
    pending=$(cat "$PENDING_FILE")

    # 检查是否已存在
    if echo "$pending" | grep -q "\"task_id\":\"${task_id}\""; then
        return 0
    fi

    # 添加新任务
    local new_entry="{\"task_id\":\"${task_id}\",\"query\":\"${query}\",\"submitted_at\":\"$(date -Iseconds)\",\"status\":\"pending\"}"
    echo "$pending" | jq --argjson new "$new_entry" '. + [$new]' > "$PENDING_FILE"
}

# 移动到已完成列表
move_to_completed() {
    local task_id="$1"
    local result="$2"

    ensure_files

    # 从 pending 移除
    local pending
    pending=$(cat "$PENDING_FILE")
    local task_info
    task_info=$(echo "$pending" | jq -r --arg tid "$task_id" '.[] | select(.task_id == $tid)')
    echo "$pending" | jq --arg tid "$task_id" 'del(.[] | select(.task_id == $tid))' > "$PENDING_FILE"

    # 添加到 completed
    local completed
    completed=$(cat "$COMPLETED_FILE")
    local query=$(echo "$task_info" | jq -r '.query // "未知问题"')
    local new_entry="{\"task_id\":\"${task_id}\",\"query\":\"${query}\",\"completed_at\":\"$(date -Iseconds)\",\"status\":\"completed\",\"result\":${result}}"
    echo "$completed" | jq --argjson new "$new_entry" '. + [$new]' > "$COMPLETED_FILE"
}

# 标记为已通知
mark_notified() {
    local task_id="$1"

    ensure_files

    local completed
    completed=$(cat "$COMPLETED_FILE")
    local task_info
    task_info=$(echo "$completed" | jq -r --arg tid "$task_id" '.[] | select(.task_id == $tid)')

    if [[ -n "$task_info" ]]; then
        # 从 completed 移除
        echo "$completed" | jq --arg tid "$task_id" 'del(.[] | select(.task_id == $tid))' > "$COMPLETED_FILE"

        # 添加到 notified
        local notified
        notified=$(cat "$NOTIFIED_FILE")
        local new_entry=$(echo "$task_info" | jq '. + {"notified_at":"'$(date -Iseconds)'"}')
        echo "$notified" | jq --argjson new "$new_entry" '. + [$new]' > "$NOTIFIED_FILE"
    fi
}

# 查询任务状态（带 Token）
query_status() {
    local task_id="$1"
    load_token

    if [[ -z "$LEGAL_RESEARCH_TOKEN" ]]; then
        echo '{"code": 401, "message": "未登录"}'
        return 1
    fi

    curl -s -X GET "${BASE_URL}/api/research/status/${task_id}" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}"
}

# 获取结果
get_result() {
    local task_id="$1"
    load_token

    curl -s -X GET "${BASE_URL}/api/research/result/${task_id}" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}"
}

# 获取报告链接
get_report() {
    local task_id="$1"
    load_token

    curl -s -X GET "${BASE_URL}/api/research/report/${task_id}" \
        -H "Authorization: Bearer ${LEGAL_RESEARCH_TOKEN}" 2>/dev/null || echo '{"code":404}'
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
        # 使用 gfm (GitHub Flavored Markdown) 格式，保留层级结构
        pandoc -f docx -t gfm --wrap=none --extract-media="${docx_file%/*}/media" "$docx_file" -o "$md_file" 2>/dev/null
        return $?
    else
        return 1
    fi
}

# 自动归档研究结果
auto_archive_result() {
    local task_id="$1"
    local query="$2"
    local result_json="$3"
    local report_json="$4"

    mkdir -p "$ARCHIVE_DIR"

    # 生成归档目录名
    local archive_name
    archive_name=$(generate_archive_name "${query:-法律研究}")
    local task_archive_dir="${ARCHIVE_DIR}/${archive_name}"
    mkdir -p "$task_archive_dir"

    # 提取结果文本
    local text_result
    text_result=$(echo "$result_json" | jq -r '.data.text_result // .text_result // ""' 2>/dev/null || echo "")

    # text_result 可能是 Python dict 格式，如 {'node_status': {}, 'Output': {'output': '...'}}
    # 尝试提取 Output.output 中的实际内容
    if echo "$text_result" | grep -q "'Output'" 2>/dev/null; then
        # 将 Python dict 的单引号转为双引号以便 jq 解析
        local extracted
        extracted=$(echo "$text_result" | sed "s/'/\"/g" | jq -r '.Output.output // empty' 2>/dev/null || echo "")
        if [[ -n "$extracted" ]]; then
            text_result="$extracted"
        fi
    fi

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

    echo "📁 归档目录: ${archive_name}"
    echo "   - ${result_filename} (研究结果)"

    # 下载报告（报告 API 返回 code 200 表示有报告，404 表示无）
    local report_code
    report_code=$(echo "$report_json" | jq -r '.code // 404' 2>/dev/null)

    if [[ "$report_code" == "200" ]]; then
        local report_url
        report_url=$(echo "$report_json" | jq -r '.data.report_url // empty' 2>/dev/null)

        # 生成统一的报告文件名（与 Markdown 保持一致）
        local report_filename
        report_filename=$(generate_report_filename "${query:-法律研究}")
        local docx_file="${task_archive_dir}/${report_filename%.md}.docx"

        if [[ -n "$report_url" && "$report_url" != "null" ]]; then
            echo "📥 正在下载报告: ${report_filename%.md}.docx"
            if curl -sL "$report_url" -o "$docx_file" 2>/dev/null && [[ -s "$docx_file" ]]; then
                echo "   - ${report_filename%.md}.docx (详细报告)"

                # 尝试转换为 Markdown（使用 _报告 后缀避免覆盖文字结果）
                local report_md_name="${report_filename%.md}_报告.md"
                local report_md="${task_archive_dir}/${report_md_name}"
                if convert_docx_to_md "$docx_file" "$report_md"; then
                    echo "   - ${report_md_name} (Markdown版本)"
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

    # 返回归档路径
    echo "ARCHIVE_PATH:${task_archive_dir}"
}

# 监控任务（阻塞式）
monitor_task() {
    local task_id="$1"
    local timeout="${2:-$DEFAULT_TIMEOUT}"
    local interval="${3:-$DEFAULT_INTERVAL}"

    ensure_files
    load_token

    local elapsed=0
    local query=""

    # 先从 pending 中获取 query
    if [[ -f "$PENDING_FILE" ]]; then
        query=$(cat "$PENDING_FILE" | jq -r --arg tid "$task_id" '.[] | select(.task_id == $tid) | .query' 2>/dev/null || echo "")
    fi

    while [[ $elapsed -lt $timeout ]]; do
        local status_response
        status_response=$(query_status "$task_id")
        local state
        state=$(echo "$status_response" | jq -r '.data.status // "unknown"')

        case "$state" in
            completed)
                # 获取完整结果
                local result
                result=$(get_result "$task_id")
                local report
                report=$(get_report "$task_id")

                # 从 status 响应中提取 query（如果之前没有）
                if [[ -z "$query" ]]; then
                    query=$(echo "$status_response" | jq -r '.data.query // "法律研究"' 2>/dev/null || echo "法律研究")
                fi

                # 合并结果
                local full_result
                full_result=$(echo "$result" | jq --argjson report "$report" '. + {report: $report}')

                # 保存到已完成列表
                move_to_completed "$task_id" "$full_result"

                # 自动归档
                echo "---"
                echo "📋 任务完成，正在自动归档..."
                auto_archive_result "$task_id" "$query" "$result" "$report"

                echo ""
                echo "COMPLETED:${task_id}"
                return 0
                ;;
            failed|timeout)
                # 保存失败状态
                move_to_completed "$task_id" "{\"status\":\"${state}\",\"error\":\"任务${state}\"}"
                echo "${state^^}:${task_id}"
                return 1
                ;;
            pending|running)
                sleep "$interval"
                elapsed=$((elapsed + interval))
                ;;
            *)
                echo "ERROR:${task_id}:未知状态 ${state}"
                return 1
                ;;
        esac
    done

    echo "TIMEOUT:${task_id}"
    return 1
}

# 查看监控状态
show_status() {
    ensure_files

    echo "=== 待处理任务 ==="
    cat "$PENDING_FILE" | jq -r '.[] | "[\(.task_id[0:8])] \(.query[0:50])... (\(.status))"' 2>/dev/null || echo "无"

    echo ""
    echo "=== 已完成待通知 ==="
    local completed_count
    completed_count=$(cat "$COMPLETED_FILE" | jq 'length')
    if [[ "$completed_count" -gt 0 ]]; then
        echo "🔔 有 ${completed_count} 个任务已完成，等待通知用户"
        cat "$COMPLETED_FILE" | jq -r '.[] | "[\(.task_id[0:8])] \(.query[0:30])... 完成于 \(.completed_at)"'
    else
        echo "无"
    fi

    echo ""
    echo "=== 已通知（今日） ==="
    cat "$NOTIFIED_FILE" | jq -r '.[] | "[\(.task_id[0:8])] \(.query[0:30])..."' 2>/dev/null || echo "无"
}

# 获取已完成但未通知的结果
get_pending_results() {
    ensure_files

    local completed
    completed=$(cat "$COMPLETED_FILE")
    local count
    count=$(echo "$completed" | jq 'length')

    if [[ "$count" -gt 0 ]]; then
        echo "$completed"
    else
        echo '[]'
    fi
}

# 清除已读结果
clear_result() {
    local task_id="$1"
    mark_notified "$task_id"
    echo "已清除任务 ${task_id} 的通知"
}

# 主入口
case "${1:-}" in
    add)
        add_pending "$2" "$3"
        ;;
    monitor)
        monitor_task "$2" "$3" "$4"
        ;;
    status)
        show_status
        ;;
    results)
        get_pending_results
        ;;
    clear)
        clear_result "$2"
        ;;
    *)
        echo "用法: $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  add <task_id> <query>         添加待监控任务"
        echo "  monitor <task_id> [timeout] [interval]  阻塞监控任务"
        echo "  status                        查看监控状态"
        echo "  results                       获取已完成但未通知的结果"
        echo "  clear <task_id>               标记结果为已读"
        echo ""
        echo "文件位置:"
        echo "  ${CONFIG_DIR}/"
        exit 1
        ;;
esac
