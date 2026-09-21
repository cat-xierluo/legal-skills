#!/usr/bin/env bash
# Task-ECG-003 回归：run_e2e.sh 失败传播与证据隔离
#
# 覆盖三个回归点：
#   R1 前段命令失败不被 tee/grep/tail 掩盖（set -o pipefail 生效）
#   R2 每次运行使用全新隔离证据目录，旧运行产物不会被复用
#   R3 成功路径真实生成当次证据（docx + 阶段日志落盘）
#
# R2/R3 用真实 harness 端到端验证；其中"真实 PDF 渲染"阶段依赖 LibreOffice，
# 未安装 soffice 的机器允许该阶段失败，但渲染阶段之前的所有阶段必须真实通过。
# T5 会在旧布局固定路径植入伪产物：restore_planted 统一兜底，任何退出路径
# （含中断/失败，经 EXIT trap）都恢复原文件或删除本次新建伪文件，并可重复调用。
# 运行：bash skills/elements-complaint-generator/tests/test_run_e2e_harness.sh
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HARNESS="$HERE/run_e2e.sh"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
OUTROOT="$SKILL_DIR/tests/output"

pass=0
fail=0
tmp="$(mktemp -d "${TMPDIR:-/tmp}/ecg-harness-test-XXXXXXXX")"
t5_backup="$tmp/backup"
mkdir -p "$t5_backup"
t5_planted=()

# 恢复所有已植入伪文件：有备份（原本存在）则还原，否则删除本次新建。
# 幂等：恢复后清空 t5_planted，可安全重复调用（trap 与流程内各调一次）。
restore_planted() {
  [ "${#t5_planted[@]}" -gt 0 ] || return 0
  for p in "${t5_planted[@]}"; do
    if [ -f "$t5_backup/$(basename "$p")" ]; then
      mv "$t5_backup/$(basename "$p")" "$p"
    else
      rm -f "$p"
    fi
  done
  t5_planted=()
}

# 在旧布局固定路径植入伪产物：若 harness 复用旧路径，断言阶段会因非法 zip 崩溃
plant_stale() {
  for f in 09-e2e.docx 05-e2e.docx; do
    p="$OUTROOT/$f"
    if [ -f "$p" ]; then mv "$p" "$t5_backup/$f"; fi
    printf 'STALE-GARBAGE-NOT-A-ZIP-ECG003' > "$p"
    t5_planted+=("$p")
  done
}

trap 'restore_planted; rm -rf "$tmp"' EXIT
trap 'exit 1' INT TERM
ok() { pass=$((pass + 1)); echo "✅ $1"; }
ng() { fail=$((fail + 1)); echo "❌ $1"; }

ok() { pass=$((pass + 1)); echo "✅ $1"; }
ng() { fail=$((fail + 1)); echo "❌ $1"; }

# 在已加载 run_e2e.sh 函数（不执行回归）的子 shell 里执行一段代码
in_harness_env() {
  EVIDENCE_DIR="$1" bash -c '
    source "'"$HARNESS"'"
    '"$2"'
  '
}

echo "==== T0 脚本自检 ===="
if [ -f "$HARNESS" ]; then ok "run_e2e.sh 存在"; else ng "run_e2e.sh 缺失"; fi
if bash -n "$HARNESS" 2>"$tmp/t0err"; then ok "run_e2e.sh 语法通过"; else ng "run_e2e.sh 语法错误：$(cat "$tmp/t0err")"; fi

echo "==== R1/T1 tee 不掩盖前段命令失败（run_stage）===="
t1_ev="$(mktemp -d)"
in_harness_env "$t1_ev" 'failer() { echo "marker-t1"; return 7; }; run_stage t1.log failer' >"$tmp/t1.out" 2>&1
t1_rc=$?
if [ "$t1_rc" -eq 7 ]; then ok "失败命令经 tee 后退出码 7 原样传播（exit=${t1_rc}）"; else ng "tee 掩盖或改写了失败码：期望 7，实际 $t1_rc"; fi
if grep -q "marker-t1" "$t1_ev/t1.log" 2>/dev/null; then ok "失败命令的输出已落盘证据日志"; else ng "证据日志未捕获失败命令输出"; fi
rm -rf "$t1_ev"

echo "==== R1/T2 grep 不掩盖前段命令失败（run_stage_filtered）===="
t2_ev="$(mktemp -d)"
in_harness_env "$t2_ev" 'failer() { echo "版式门禁 fake-pass"; return 3; }; run_stage_filtered t2.log "rules|版式门禁" failer' >"$tmp/t2.out" 2>&1
t2_rc=$?
if [ "$t2_rc" -eq 3 ]; then ok "命令打印可匹配行后失败，退出码 3 不被 grep 吞掉（exit=${t2_rc}）"; else ng "grep+tee 掩盖失败：期望 3，实际 ${t2_rc}（旧版此场景假绿）"; fi
if grep -q "版式门禁 fake-pass" "$t2_ev/t2.log" 2>/dev/null; then ok "完整输出（含失败前输出）已落盘证据日志"; else ng "证据日志未捕获完整输出"; fi
in_harness_env "$t2_ev" 'runner() { echo "nothing relevant"; return 0; }; run_stage_filtered t2b.log "rules|版式门禁" runner' >"$tmp/t2b.out" 2>&1
t2b_rc=$?
if [ "$t2b_rc" -ne 0 ]; then ok "grep 无匹配按失败处理（fail-closed，exit=${t2b_rc}）"; else ng "grep 无匹配被当成成功"; fi
rm -rf "$t2_ev"

echo "==== R1/T3 tail 不掩盖前段命令失败（run_stage_tail）===="
t3_ev="$(mktemp -d)"
in_harness_env "$t3_ev" 'failer() { echo "line-a"; echo "line-b"; return 5; }; run_stage_tail t3.log 1 failer' >"$tmp/t3.out" 2>&1
t3_rc=$?
if [ "$t3_rc" -eq 5 ]; then ok "失败命令经 tail 后退出码 5 原样传播（exit=${t3_rc}）"; else ng "tail 掩盖失败：期望 5，实际 $t3_rc"; fi
if grep -q "line-b" "$t3_ev/t3.log" 2>/dev/null; then ok "完整输出已落盘证据日志"; else ng "证据日志未捕获完整输出"; fi
rm -rf "$t3_ev"

echo "==== R2/T4 证据目录每次全新隔离（resolve_evidence_dir）===="
d1="$(in_harness_env "" 'resolve_evidence_dir')"
d2="$(in_harness_env "" 'resolve_evidence_dir')"
if [ -n "$d1" ] && [ -n "$d2" ] && [ "$d1" != "$d2" ]; then
  ok "两次解析得到不同目录：$(basename "$d1") / $(basename "$d2")"
else
  ng "证据目录未隔离：d1=$d1 d2=$d2"
fi
case "$d1" in "$OUTROOT"/e2e-*) ok "默认证据目录位于 tests/output/e2e-* 下"; ;; *) ng "默认证据目录位置异常：$d1"; ;; esac
[ -d "$d1" ] && [ -d "$d2" ] && ok "证据目录已真实创建" || ng "证据目录未创建"
rm -rf "$d1" "$d2"
# 结构护栏：产物不允许再写固定 tests/output/ 路径；断言必须经证据目录解析
if grep -q -- "--output tests/output/" "$HARNESS"; then
  ng "仍存在固定输出路径 tests/output/（旧产物复用隐患）"
else
  ok "无固定输出路径，产物全部写入当次证据目录"
fi
if grep -q "os.path.basename(path)" "$HARNESS" && grep -q 'set -euo pipefail' "$HARNESS"; then
  ok "断言按证据目录解析 + pipefail 已开启"
else
  ng "缺少证据目录解析或 pipefail"
fi

echo "==== R2/T4b 显式 E2E_EVIDENCE_DIR 视为父目录，非空旧证据被隔离 ===="
with_root() {
  E2E_EVIDENCE_DIR="$1" bash -c '
    source "'"$HARNESS"'"
    '"$2"'
  '
}
t4_root="$(mktemp -d)"
printf 'OLD-EVIDENCE-ECG003' > "$t4_root/09-e2e.docx"
d3="$(with_root "$t4_root" 'resolve_evidence_dir')"
d4="$(with_root "$t4_root" 'resolve_evidence_dir')"
if [ -n "$d3" ] && [ -n "$d4" ] && [ "$d3" != "$d4" ]; then
  ok "显式根下两次解析得到不同子目录：$(basename "$d3") / $(basename "$d4")"
else
  ng "显式根未按运行隔离：d3=$d3 d4=$d4"
fi
case "$d3" in "$t4_root"/e2e-*) ok "运行目录是显式根下的唯一新建子目录"; ;; *) ng "运行目录不在显式根下：$d3"; ;; esac
if [ "$(cat "$t4_root/09-e2e.docx" 2>/dev/null)" = "OLD-EVIDENCE-ECG003" ]; then
  ok "显式根内已存在的旧证据原样保留、未被读取或改动"
else
  ng "旧证据被移动/删除/改动（隔离失败）"
fi
if [ -d "$d3" ] && [ -z "$(ls -A "$d3" 2>/dev/null)" ]; then
  ok "运行目录由本次运行全新创建（空目录起步）"
else
  ng "运行目录非全新：$d3"
fi
rm -rf "$t4_root"

echo "==== R2+R3/T5 真实 harness：旧产物不复用 + 当次证据生成 ===="
mkdir -p "$OUTROOT"
plant_stale
find "$OUTROOT" -maxdepth 1 -type d -name 'e2e-*' | sort >"$tmp/t5before.txt"
bash "$HARNESS" >"$tmp/t5run.log" 2>&1
t5_rc=$?
restore_planted
find "$OUTROOT" -maxdepth 1 -type d -name 'e2e-*' | sort >"$tmp/t5after.txt"
t5_new="$(comm -13 "$tmp/t5before.txt" "$tmp/t5after.txt")"
t5_count="$(printf '%s' "$t5_new" | grep -c .)"
if [ "$t5_count" -eq 1 ]; then
  t5_dir="$t5_new"
  ok "本次运行产生唯一全新证据目录：$(basename "$t5_dir")"
else
  t5_dir=""
  ng "期望恰好 1 个新证据目录，实际 ${t5_count}：$t5_new"
fi
if [ -n "$t5_dir" ] && grep -q "全部案由回归通过" "$t5_dir/assertions.log" 2>/dev/null; then
  ok "断言阶段全部通过（植入的旧路径伪产物未被读取，旧证据未复用）"
else
  ng "断言未通过或读取了旧证据：assertions.log=$(ls "$t5_dir" 2>/dev/null | tr '\n' ' ')，运行日志尾部：$(tail -3 "$tmp/t5run.log")"
fi
if [ -n "$t5_dir" ] && [ -f "$t5_dir/09-e2e.docx" ] && [ -f "$t5_dir/05-e2e.docx" ] && [ -f "$t5_dir/60-enforcement.docx" ]; then
  ok "成功路径当次 docx 证据已落盘（09/05/60）"
else
  ng "当次 docx 证据缺失"
fi
if [ -n "$t5_dir" ] && [ -f "$t5_dir/render-09-sample.log" ]; then
  ok "已推进到渲染阶段（渲染前所有阶段真实通过）"
  # 与 layout_gate 渲染器选址同口径，且必须为正式版（official）才把完整
  # harness 成功作为硬断言：dev/unknown 渲染器不暴露系统中文字体，不能作为
  # 中文视觉验收，输出 NOT_VERIFIED（环境性不可验），绝不表述为可用渲染器。
  renderer_kind="$(python3 -c "
import sys
sys.path.insert(0, '$SKILL_DIR/scripts')
from layout_gate import _find_soffice, _renderer_kind, _soffice_version
path = _find_soffice()
print('' if not path else _renderer_kind(_soffice_version(path)))
" 2>/dev/null | tail -1)"
  if [ "$renderer_kind" = "official" ]; then
    if [ "$t5_rc" -eq 0 ]; then ok "本机有正式版渲染器，完整 harness 退出码 0"; else ng "本机有正式版渲染器但 harness 失败（exit=${t5_rc}）：$(tail -3 "$tmp/t5run.log")"; fi
  elif [ -z "$renderer_kind" ]; then
    echo "ℹ️  NOT_VERIFIED：本机无 LibreOffice，渲染阶段环境性不可验（exit=${t5_rc}）"
  else
    echo "⚠️  NOT_VERIFIED：本机仅有 ${renderer_kind} 渲染器（headless 开发构建不暴露系统中文字体），rendered 验收环境性不可验（exit=${t5_rc}）"
  fi
else
  ng "未推进到渲染阶段，渲染前有阶段失败（exit=${t5_rc}）：$(tail -5 "$tmp/t5run.log")"
fi

echo "==== R1/T6 真实 harness：管道阶段失败整体非零（shim 注入）===="
t6_bin="$tmp/bin"; mkdir -p "$t6_bin"
REAL_PY="$(command -v python3)"
cat >"$t6_bin/python3" <<EOF
#!/bin/sh
case "\$*" in
  *scripts/fill_template.py*) echo "rules=1 完整性=1 版式门禁=1"; exit 3 ;;
esac
exec "$REAL_PY" "\$@"
EOF
chmod +x "$t6_bin/python3"
PATH="$t6_bin:$PATH" bash "$HARNESS" >"$tmp/t6run.log" 2>&1
t6_rc=$?
if [ "$t6_rc" -ne 0 ]; then
  ok "fill 阶段打印可匹配行后失败，harness 整体退出非零（exit=${t6_rc}，旧版此场景假绿）"
else
  ng "管道阶段失败被掩盖，harness 退出 0"
fi
if grep -q "证据已保留" "$tmp/t6run.log"; then ok "失败路径给出证据目录指引"; else ng "失败路径缺少证据目录指引"; fi

echo "==== R2/T7 植入伪文件恢复逻辑可重复调用 ===="
t7_probe="$OUTROOT/zz ecg003 restore probe.docx"
# 场景 A：位置原有文件 → 恢复应还原原内容
printf 'ORIGINAL-CONTENT-ECG003' > "$t7_probe"
mv "$t7_probe" "$t5_backup/$(basename "$t7_probe")"
printf 'PLANTED-FAKE' > "$t7_probe"
t5_planted=("$t7_probe")
restore_planted
if [ "$(cat "$t7_probe" 2>/dev/null)" = "ORIGINAL-CONTENT-ECG003" ]; then
  ok "原有文件被植入后恢复为原内容"
else
  ng "原有文件未正确恢复：$(cat "$t7_probe" 2>/dev/null)"
fi
restore_planted
if [ "$(cat "$t7_probe" 2>/dev/null)" = "ORIGINAL-CONTENT-ECG003" ]; then
  ok "重复调用恢复无副作用（幂等）"
else
  ng "重复调用破坏已恢复文件"
fi
# 场景 B：位置原本无文件 → 恢复应删除本次新建伪文件
printf 'PLANTED-FAKE-B' > "$t7_probe"
t5_planted=("$t7_probe")
restore_planted
restore_planted
if [ ! -f "$t7_probe" ]; then
  ok "新建伪文件恢复即删除，重复调用安全"
else
  ng "新建伪文件未被删除"
fi
rm -f "$t7_probe" "$t5_backup/$(basename "$t7_probe")"

echo "==== 汇总 ===="
echo "通过 $pass / $((pass + fail))"
if [ "$fail" -eq 0 ]; then
  echo "✅ Task-ECG-003 回归全部通过"
  exit 0
fi
echo "❌ Task-ECG-003 回归存在失败：$fail 项"
exit 1
