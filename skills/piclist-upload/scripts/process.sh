#!/usr/bin/env bash
# PicList Markdown image processor
# Usage: ./process.sh [--dry-run] [--keep-local] [--in-place] <file.md|directory...>

set -o pipefail

PICLIST_SERVER="${PICLIST_SERVER:-http://127.0.0.1:36677}"
DRY_RUN=false
IN_PLACE=false
KEEP_LOCAL=false

# Global counters
TOTAL_UPLOADED=0
TOTAL_SKIPPED=0
TOTAL_FAILED=0

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

# Function to upload a single image
upload_image() {
    local image_path="$1"

    if [ ! -f "$image_path" ]; then
        echo "⚠️  File not found: $image_path" >&2
        return 1
    fi

    local response
    response=$(curl -s -X POST "$PICLIST_SERVER/upload" -F "file=@$image_path" 2>/dev/null)

    if echo "$response" | jq -e '.success == true' >/dev/null 2>&1; then
        local url
        url=$(echo "$response" | jq -r '.result[0]')
        echo "$url"
        return 0
    else
        echo "❌ Upload failed: $image_path" >&2
        return 1
    fi
}

# Function to delete local image file
delete_local_image() {
    local image_path="$1"
    if [ "$KEEP_LOCAL" = true ]; then
        return 0
    fi

    if [ -f "$image_path" ]; then
        rm -f "$image_path"
        echo "  🗑️  Deleted: $image_path"
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
        else
            : $((fail_count++))
        fi
    done <<< "$images"

    # Report results
    echo "  ✅ Uploaded: $upload_count, ⏭️  Skipped: $skip_count, ❌ Failed: $fail_count"

    # Update global counters (use let to avoid set -e issues)
    let "TOTAL_UPLOADED += upload_count" || true
    let "TOTAL_SKIPPED += skip_count" || true
    let "TOTAL_FAILED += fail_count" || true

    # Write output
    if [ "$IN_PLACE" = true ]; then
        echo "$content" > "$temp_file"
        mv "$temp_file" "$md_file"
        echo "  ✏️  File updated: $md_file"
    else
        echo "$content"
    fi
}

# Function to check PicList Server availability
check_piclist_server() {
    echo "🔍 检查 PicList HTTP Server..."

    # Test if server is accessible
    if ! curl -s --connect-timeout 3 "$PICLIST_SERVER/upload" >/dev/null 2>&1; then
        echo "❌ 无法连接到 PicList HTTP Server"
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

    echo "✅ PicList Server 连接成功 ($PICLIST_SERVER)"
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

echo
echo "📊 Summary:"
echo "  Total uploaded: $TOTAL_UPLOADED"
echo "  Total skipped: $TOTAL_SKIPPED"
echo "  Total failed: $TOTAL_FAILED"
