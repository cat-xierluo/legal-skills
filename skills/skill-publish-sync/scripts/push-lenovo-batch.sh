#!/bin/bash
# push-lenovo-batch.sh — 批量把 SkillHub 已 synced 的 skill 上传到联想开放平台
#
# 用法:
#   bash skills/clawhub-sync/scripts/push-lenovo-batch.sh
#
# 设计:
#   - 从 config/allowlist-lenovo.yaml 读 skill 列表(每个 skill 至少有 display_name)
#   - 对每个 skill 跑 5 步:prepare / 写 .skill-config.json / package / push(expect 自动 y)/ 收 appId
#   - 输出:临时文件 /tmp/lenovo-batch-results.txt 含每条 skill 的 appId/version/status
#   - 异常:任何 skill 失败不阻塞后续 skill,记录到 results 文件
#
# 前提:
#   - lenovoskill login 已完成(否则 push 会 401)
#   - allowlist-lenovo.yaml 已配置完整
#   - 当前 skill 在仓库 skills/<name>/ 存在

set -e

SKILLS_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PREPARE_SCRIPT="$SCRIPT_DIR/prepare-publish.sh"
RESULTS_FILE="/tmp/lenovo-batch-results.txt"
TMP_ROOT="/tmp/lenovo-publish"
NPM_CMD="npx -y @lenovo-open/skill-cli"

# 清空旧结果(只在没已成功条目时才清空,支持断点续跑)
if [ ! -f "$RESULTS_FILE" ] || [ ! -s "$RESULTS_FILE" ]; then
  > "$RESULTS_FILE"
fi

# 解析 allowlist-lenovo.yaml 拿 skill 列表（按文件顺序）
mapfile -t SKILLS < <(awk '/^[a-z][a-z0-9_-]*:$/{gsub(":$",""); print}' "$SKILLS_ROOT/skills/clawhub-sync/config/allowlist-lenovo.yaml" | grep -v "^allowlist\|^sync")

# 兜底:allowlist-lenovo.yaml 没有 skill 时从 SkillHub records 取
if [ ${#SKILLS[@]} -eq 0 ]; then
  echo "⚠️  allowlist-lenovo.yaml 未配置,自动从 sync-records.yaml 抽取 SkillHub 已 synced 的 skill"
  mapfile -t SKILLS < <(python3 -c "
import yaml, sys
d = yaml.safe_load(open('$SKILLS_ROOT/skills/clawhub-sync/config/sync-records.yaml'))
for name, rec in d['records'].items():
    p = rec.get('platforms', {})
    if 'skillhub' in p and p['skillhub'].get('status') == 'synced':
        print(name)
")
fi

echo "=== 批量上传 ${#SKILLS[@]} 个 skill 到联想开放平台 ==="
echo ""

TOTAL=${#SKILLS[@]}
SUCCESS=0
FAILED=0

for i in "${!SKILLS[@]}"; do
  SKILL="${SKILLS[$i]}"
  IDX=$((i+1))
  TMPDIR="$TMP_ROOT-$SKILL"
  ZIP_PATH="$TMPDIR/dist/${SKILL}-*.zip"

  # 断点续跑:跳过已成功的 skill
  if [ -f "$RESULTS_FILE" ] && grep -q "^${SKILL}[[:space:]]" "$RESULTS_FILE" 2>/dev/null; then
    PREV=$(grep "^${SKILL}[[:space:]]" "$RESULTS_FILE" | head -1)
    case "$PREV" in
      *PUSH_FAILED*|*PREPARE_FAILED*|*PACKAGE_FAILED*|*NO_ZIP*)
        echo "─── [$IDX/$TOTAL] $SKILL (重试) ───" ;;
      *)
        echo "─── [$IDX/$TOTAL] $SKILL (跳过,已成功) ───"
        SUCCESS=$((SUCCESS+1))
        continue ;;
    esac
  else
    echo "─── [$IDX/$TOTAL] $SKILL ───"
  fi

  # 1) prepare-publish
  if ! bash "$PREPARE_SCRIPT" --platform lenovo "$SKILLS_ROOT/skills/$SKILL" > /dev/null 2>&1; then
    echo "  ❌ prepare-publish 失败"
    echo "$SKILL\tPREPARE_FAILED\t$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$RESULTS_FILE"
    FAILED=$((FAILED+1))
    continue
  fi

  # 2) 写 .skill-config.json
  # 从 SKILL.md 读 description + version
  DESC=$(awk '/^---$/{c++; next} c==2{exit} c==1 && /^description:/{sub(/^description: */,""); print; exit}' "$SKILLS_ROOT/skills/$SKILL/SKILL.md" | head -1)
  VER=$(awk '/^---$/{c++; next} c==2{exit} c==1 && /^version:/{sub(/^version: */,""); gsub(/"/,""); print; exit}' "$SKILLS_ROOT/skills/$SKILL/SKILL.md" | head -1)
  DN=$(awk '/^[a-z]/ && /display_name:/{found=1; sub(/.*display_name: */,""); gsub(/["\\]/,""); print; exit}' "$SKILLS_ROOT/skills/clawhub-sync/config/allowlist-lenovo.yaml")
  # ↑ 这段 awk 不准,改成 python 读 yaml
  DN=$(python3 -c "
import yaml
d = yaml.safe_load(open('$SKILLS_ROOT/skills/clawhub-sync/config/allowlist-lenovo.yaml'))
print(d.get('$SKILL', {}).get('display_name', '$SKILL'))
")

  cat > "$TMPDIR/.skill-config.json" <<EOF
{
  "name": "$SKILL",
  "displayName": "$DN",
  "description": "$DESC",
  "version": "$VER",
  "slug": "$SKILL",
  "ignore": ["archive/**", "*.log", ".DS_Store"]
}
EOF

  # 3) package
  cd "$TMPDIR"
  if ! $NPM_CMD package > /dev/null 2>&1; then
    echo "  ❌ package 失败"
    echo "$SKILL\tPACKAGE_FAILED\t$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$RESULTS_FILE"
    FAILED=$((FAILED+1))
    cd "$SKILLS_ROOT"
    continue
  fi

  ZIP_FILE=$(ls "$TMPDIR/dist/"${SKILL}"-"*.zip 2>/dev/null | head -1)
  if [ -z "$ZIP_FILE" ]; then
    echo "  ❌ zip 未生成"
    echo "$SKILL\tNO_ZIP\t$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$RESULTS_FILE"
    FAILED=$((FAILED+1))
    cd "$SKILLS_ROOT"
    continue
  fi

  # 4) push with expect
  PUSH_OUTPUT=$(expect <<EOF
set timeout 120
spawn $NPM_CMD push --zipAbsPath $ZIP_FILE
expect {
  -re "Update Notes.*›" { send "v$VER: 批量同步到联想开放平台\r" }
  timeout { puts "TIMEOUT_NOTES"; exit 1 }
}
expect {
  -re "continue.*\\?" { send "y\r" }
  timeout { puts "TIMEOUT_CONFIRM"; exit 1 }
}
sleep 2
expect eof
EOF
)
  cd "$SKILLS_ROOT"

  # 从 expect 输出里用正则抓 appId(混合了 spinner/控制字符)
  APP_ID=$(echo "$PUSH_OUTPUT" | grep -oE "appId: [0-9]+" | head -1 | awk '{print $2}')
  if [ -n "$APP_ID" ]; then
    echo "  ✅ appId=$APP_ID v$VER"
    echo -e "$SKILL\t$APP_ID\t$VER\t$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$RESULTS_FILE"
    SUCCESS=$((SUCCESS+1))
  else
    # 调试:保留完整输出供事后分析
    ERR_OUT=$(echo "$PUSH_OUTPUT" | grep -oE "(FAIL|Error|error|Failed)[^[:cntrl:]]*" | head -1)
    if [ -z "$ERR_OUT" ]; then
      ERR_OUT=$(echo "$PUSH_OUTPUT" | tr -d '[:cntrl:]' | tail -1 | head -c 150)
    fi
    echo "  ❌ push 失败: $ERR_OUT"
    echo -e "$SKILL\tPUSH_FAILED\t$ERR_OUT" >> "$RESULTS_FILE"
    FAILED=$((FAILED+1))
  fi
done

echo ""
echo "=== 批量上传完成 ==="
echo "成功: $SUCCESS / $TOTAL"
echo "失败: $FAILED / $TOTAL"
echo "详细结果: $RESULTS_FILE"
echo ""
echo "=== 结果文件预览 ==="
cat "$RESULTS_FILE"