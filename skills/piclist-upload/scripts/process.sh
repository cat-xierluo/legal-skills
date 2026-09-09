#!/usr/bin/env bash
# PicList Markdown image processor
# Usage: ./process.sh [--dry-run] [--keep-local] [--in-place] <file.md|directory...>

set -o pipefail

PICLIST_SERVER="${PICLIST_SERVER:-http://127.0.0.1:36677}"
DRY_RUN=false
IN_PLACE=false
KEEP_LOCAL=false

# Throttling parameters
UPLOAD_INTERVAL="${UPLOAD_INTERVAL:-0.5}"
BATCH_SIZE="${BATCH_SIZE:-20}"
BATCH_REST="${BATCH_REST:-3}"

# Retry parameters
MAX_RETRIES="${MAX_RETRIES:-1}"
RETRY_DELAY="${RETRY_DELAY:-2}"
PICLIST_START_WAIT="${PICLIST_START_WAIT:-15}"

# Global counters
TOTAL_UPLOADED=0
TOTAL_SKIPPED=0
TOTAL_FAILED=0
TOTAL_DIRS_REMOVED=0
TOTAL_SESSION_UPLOADED=0

# Track directories where files were deleted
declare -A deleted_dirs

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --keep-local)
            KEEP_LOCAL=true
            shift
            ;;
        --in-place)
            IN_PLACE=true
            shift
            ;;
        -*)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

if [ $# -eq 0 ]; then
    echo "Usage: $0 [--dry-run] [--keep-local] [--in-place] <file.md|directory...>" >&2
    exit 1
fi

# Function to upload a single image (with retries)
upload_image() {
    local image_path="$1"

    if [ ! -f "$image_path" ]; then
        echo "⚠️  File not found: $image_path" >&2
        return 1
    fi

    local attempt=0
    while [ "$attempt" -le "$MAX_RETRIES" ]; do
        # Bypass system proxy for localhost: PICLIST is local; system proxies
        # (e.g. http://127.0.0.1:1082) often return 503 for unknown ports,
        # which fools naive connectivity checks.
        local response
        response=$(curl -s --noproxy '*' -w "\n%{http_code}" -X POST "$PICLIST_SERVER/upload" -F "file=@$image_path" 2>/dev/null)

        # Split response body and HTTP status code
        local http_code
        http_code=$(echo "$response" | tail -1)
        local body
        body=$(echo "$response" | sed '$d')

        # Check for success
        if echo "$body" | jq -e '.success == true' >/dev/null 2>&1; then
            local url
            url=$(echo "$body" | jq -r '.result[0]')
            echo "$url"
            return 0
        fi

        attempt=$((attempt + 1))
        if [ "$attempt" -le "$MAX_RETRIES" ]; then
            echo "  ⚠️  Upload attempt $attempt failed (HTTP ${http_code:-???}), retrying in ${RETRY_DELAY}s..." >&2
            sleep "$RETRY_DELAY"
        fi
    done

    echo "❌ Upload failed after $((MAX_RETRIES + 1)) attempt(s): $image_path (last HTTP ${http_code:-???})" >&2
    return 1
}

# Function to delete local image file
delete_local_image() {
    local image_path="$1"
    if [ "$KEEP_LOCAL" = true ]; then
        return 0
    fi

    if [ -f "$image_path" ]; then
        local dir_path
        dir_path="$(dirname "$image_path")"
        rm -f "$image_path"
        echo "  🗑️  Deleted: $image_path"
        deleted_dirs["$dir_path"]=1
    fi
}

# Function to process a single markdown file
process_markdown_file() {
    local md_file="$1"
    local temp_file="${md_file}.tmp"
    local upload_count=0
    local skip_count=0
    local fail_count=0
    declare -A uploaded_files  # Track uploaded files to delete later

    echo "Processing: $md_file"

    # Read entire file content
    local content
    content=$(cat "$md_file")

    # Process all image references using grep
    local md_dir
    md_dir="$(dirname "$md_file")"

    # Extract all image references using grep
    local images
    images=$(grep -o '!\[[^]]*\]([^)]*)' "$md_file" 2>/dev/null || true)

    # Process each unique image
    local processed_paths=""
    while IFS= read -r match; do
        [ -z "$match" ] && continue

        # Extract alt text and path
        local alt_text="${match#*\[}"
        alt_text="${alt_text%\]*}"
        local image_path="${match#*\]}"
        image_path="${image_path#[\(]}"
        image_path="${image_path%\)}"

        # Skip if already processed this path
        if [[ "$processed_paths" =~ "|$image_path|" ]]; then
            : $((skip_count++))
            continue
        fi
        processed_paths="$processed_paths|$image_path|"

        # Skip if already a URL
        if [[ "$image_path" =~ ^https?:// ]]; then
            : $((skip_count++))
            continue
        fi

        # Resolve relative path
        local full_path="$md_dir/$image_path"

        # Normalize path
        full_path=$(cd "$(dirname "$full_path")" 2>/dev/null && pwd)/$(basename "$full_path") 2>/dev/null || true

        # Check if file exists
        if [ ! -f "$full_path" ]; then
            echo "  ⚠️  File not found: $image_path" >&2
            : $((fail_count++))
            continue
        fi

        if [ "$DRY_RUN" = true ]; then
            echo "  🔍 Would upload: $image_path"
            : $((upload_count++))
            continue
        fi

        # Upload image
        echo "  Uploading: $image_path..."
        local new_url
        new_url=$(upload_image "$full_path")

        if [ -n "$new_url" ]; then
            # Replace all occurrences in content
            content="${content//"$match"/![${alt_text}](${new_url})}"
            : $((upload_count++))

            # Track for deletion (use full_path as key)
            uploaded_files["$full_path"]=1

            # Delete local file immediately after successful upload
            delete_local_image "$full_path"

            # Throttle: basic interval after each upload
            TOTAL_SESSION_UPLOADED=$((TOTAL_SESSION_UPLOADED + 1))
            if [ "$(echo "$UPLOAD_INTERVAL > 0" | bc 2>/dev/null || echo 0)" = "1" ]; then
                sleep "$UPLOAD_INTERVAL"
            fi

            # Throttle: batch rest after every BATCH_SIZE uploads
            if [ $((TOTAL_SESSION_UPLOADED % BATCH_SIZE)) -eq 0 ]; then
                echo "  ⏸️  Batch rest ($BATCH_SIZE uploaded, pausing ${BATCH_REST}s)..."
                sleep "$BATCH_REST"
            fi
        else
            : $((fail_count++))
        fi
    done <<< "$images"

    # Report results
    if [ "$DRY_RUN" = true ]; then
        echo "  🔍 Preview candidates: $upload_count, ⏭️  Skipped: $skip_count, ❌ Failed: $fail_count"
    else
        echo "  ✅ Uploaded: $upload_count, ⏭️  Skipped: $skip_count, ❌ Failed: $fail_count"
    fi

    # Update global counters (use let to avoid set -e issues)
    let "TOTAL_UPLOADED += upload_count" || true
    let "TOTAL_SKIPPED += skip_count" || true
    let "TOTAL_FAILED += fail_count" || true

    # Write output
    if [ "$DRY_RUN" = true ]; then
        echo "  👀 Dry run complete: $md_file (未上传、未修改)"
    elif [ "$IN_PLACE" = true ]; then
        echo "$content" > "$temp_file"
        mv "$temp_file" "$md_file"
        echo "  ✏️  File updated: $md_file"
    else
        echo "$content"
    fi
}

# Extract host:port from PICLIST_SERVER URL (http://host:port/...)
extract_port() {
    echo "$PICLIST_SERVER" | sed -E 's|^https?://||; s|/.*$||; s|.*:||'
}

# Check if anything listens on the PicList port (local).
port_listening() {
    local port="$1"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN
}

# Wait up to N seconds for PicList port to start listening.
wait_for_port() {
    local port="$1"
    local max="${2:-$PICLIST_START_WAIT}"
    local i=0
    while [ "$i" -lt "$max" ]; do
        if port_listening "$port"; then
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done
    return 1
}

# Try to launch PicList app (macOS only; ignored elsewhere).
launch_piclist_app() {
    if [ "$(uname -s)" != "Darwin" ]; then
        return 1
    fi
    if [ ! -d "/Applications/PicList.app" ]; then
        return 1
    fi
    echo "🚀 尝试启动 PicList 应用..." >&2
    open -a PicList >/dev/null 2>&1
    return $?
}

# Function to check PicList Server availability
check_piclist_server() {
    local port
    port=$(extract_port)
    echo "🔍 检查 PicList HTTP Server (port $port)..."

    # Step 1: confirm something is actually listening on the port (bypass proxy).
    if ! port_listening "$port"; then
        echo "⚠️  PicList 端口 $port 未监听"
        if launch_piclist_app; then
            echo "⏳ 等待 PicList 启动（最多 ${PICLIST_START_WAIT}s）..."
            if wait_for_port "$port"; then
                echo "✅ PicList 已就绪"
            else
                echo "❌ PicList 启动超时"
                echo
                echo "请确保："
                echo "  1. PicList 应用正在运行"
                echo "  2. HTTP Server 已启用（默认端口 36677）"
                echo
                echo "配置指南: references/setup.md"
                echo "下载地址: https://github.com/Kuingsmile/PicList/releases"
                echo
                exit 1
            fi
        else
            echo "❌ 无法自动启动 PicList"
            echo
            echo "请确保："
            echo "  1. PicList 应用正在运行"
            echo "  2. HTTP Server 已启用（默认端口 36677）"
            echo
            echo "配置指南: references/setup.md"
            echo "下载地址: https://github.com/Kuingsmile/PicList/releases"
            echo
            exit 1
        fi
    fi

    # Step 2: probe business endpoint directly (bypass proxy). A system proxy
    # (e.g. 127.0.0.1:1082) returns 503 for unknown ports, so a bare `curl`
    # would falsely report "connection successful".
    local code
    code=$(curl -s --noproxy '*' -o /dev/null -w "%{http_code}" -m 5 "$PICLIST_SERVER/upload" 2>/dev/null || echo "000")
    if [ "$code" = "000" ] || [ "$code" = "503" ]; then
        echo "❌ PicList 业务端点不可达 (HTTP $code)"
        echo "   端口在监听，但上传端点无响应 — 通常是 PicList 应用卡死或图床后端未配置。"
        echo "   建议：在 PicList 应用里确认默认图床已选中且 token 未失效，必要时重启 PicList。"
        echo
        exit 1
    fi

    echo "✅ PicList Server 连接成功 ($PICLIST_SERVER, HTTP $code)"
    echo
}

# Function to collect markdown files from directories
collect_markdown_files() {
    for target in "$@"; do
        if [ -f "$target" ]; then
            # Single file
            if [[ "$target" =~ \.md$ ]]; then
                echo "$target"
            fi
        elif [ -d "$target" ]; then
            # Directory - find all .md files
            find "$target" -type f -name "*.md" -print
        fi
    done
}

# Main execution
check_piclist_server
echo "🔍 Scanning for Markdown files..."

md_files=()
while IFS= read -r file; do
    md_files+=("$file")
done < <(collect_markdown_files "$@")

if [ ${#md_files[@]} -eq 0 ]; then
    echo "❌ No Markdown files found" >&2
    exit 1
fi

echo "📝 Found ${#md_files[@]} Markdown file(s)"
echo

for md_file in "${md_files[@]}"; do
    echo
    process_markdown_file "$md_file"
done

# Clean up empty directories left after deleting images
if [ "$KEEP_LOCAL" = false ] && [ ${#deleted_dirs[@]} -gt 0 ]; then
    for dir in "${!deleted_dirs[@]}"; do
        if [ -d "$dir" ] && [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
            rmdir "$dir"
            echo "  🗑️  Removed empty dir: $dir"
            : $((TOTAL_DIRS_REMOVED++))
        fi
    done
fi

echo
echo "📊 Summary:"
if [ "$DRY_RUN" = true ]; then
    echo "  Total preview candidates: $TOTAL_UPLOADED"
else
    echo "  Total uploaded: $TOTAL_UPLOADED"
fi
echo "  Total skipped: $TOTAL_SKIPPED"
echo "  Total failed: $TOTAL_FAILED"
if [ "$KEEP_LOCAL" = false ]; then
    echo "  Empty dirs removed: $TOTAL_DIRS_REMOVED"
fi
