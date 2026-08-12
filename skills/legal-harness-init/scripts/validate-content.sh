#!/usr/bin/env bash
# 校验待写入 AGENTS.md / CLAUDE.md 的候选内容，避免把凭证或可识别案件信息直接写进配置。

set -u

die() {
    printf 'validate-content.sh: 错误：%s\n' "$*" >&2
    exit 1
}

FILE=""
PRIVACY_MODE="strict"
while [ $# -gt 0 ]; do
    case "$1" in
        --file) [ $# -ge 2 ] || die "--file 需要参数"; FILE="$2"; shift 2 ;;
        --privacy-mode) [ $# -ge 2 ] || die "--privacy-mode 需要参数"; PRIVACY_MODE="$2"; shift 2 ;;
        -h|--help) sed -n '1,22p' "$0"; exit 0 ;;
        *) die "未知参数：$1" ;;
    esac
done

[ -n "$FILE" ] || die "缺 --file"
[ -f "$FILE" ] || die "文件不存在：$FILE"
[ -s "$FILE" ] || die "文件为空：$FILE"
case "$PRIVACY_MODE" in strict|local|team) ;; *) die "privacy-mode 必须是 strict / local / team" ;; esac

byte_count=$(wc -c < "$FILE" | tr -d ' ')
[ "$byte_count" -le 262144 ] || die "候选内容超过 256 KiB，请拆分或引用受控事实文件"

failed=false
reject() {
    printf 'validate-content.sh: 拒绝：%s\n' "$1" >&2
    failed=true
}

# 所有模式都禁止高敏个人身份号与疑似明文凭证；只报告类别，不回显敏感值。
if grep -Eiq '(^|[^0-9])[1-9][0-9]{5}(18|19|20)[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])[0-9]{3}[0-9Xx]([^0-9Xx]|$)' "$FILE"; then
    reject "发现疑似身份证号码"
fi
if awk '
    BEGIN { IGNORECASE=1; bad=0 }
    /^[[:space:]]*(禁止|不得|不要|严禁)/ { next }
    /(^|[^[:alnum:]_])(api[_-]?key|access[_-]?token|secret|password|密码|口令)[[:space:]]*[:=][[:space:]]*[^<{[([:space:]]/ { bad=1 }
    END { exit bad ? 0 : 1 }
' "$FILE"; then
    reject "发现疑似明文凭证赋值"
fi

# 三种模式的 AGENTS.md 都只能保存最小上下文；local/team 的差别在真实事实的受控载体，而不是放宽指令文件。
if grep -Eq '[(（]20[0-9]{2}[)）][^[:space:]]{0,40}号' "$FILE"; then
    reject "发现疑似真实案号；请改用项目代号或受控事实入口"
fi
if grep -Eq '(^|[^0-9])1[3-9][0-9]{9}([^0-9]|$)' "$FILE"; then
    reject "发现疑似手机号码"
fi
if grep -Eiq '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}' "$FILE"; then
    reject "发现疑似电子邮箱"
fi
if grep -Eq '(统一社会信用代码|信用代码)[[:space:]]*[:：][[:space:]]*[0-9A-HJ-NPQRTUWXY]{18}' "$FILE"; then
    reject "发现统一社会信用代码"
fi
if awk '
    /^[[:space:]]*[-*]?[[:space:]]*(委托人|客户|对方当事人|申请人|被申请人|原告|被告|案号|申请号|统一社会信用代码|项目金额|案件标的)[[:space:]]*[:：]/ {
        value=$0
        sub(/^[^:：]*[:：][[:space:]]*/, "", value)
        if (value !~ /^(项目代号|见|未写入|不写入|待补充|\.\.\.|\{|<|\[)/) bad=1
    }
    END { exit bad ? 0 : 1 }
' "$FILE"; then
    reject "发现直接写入的当事人、案号或金额字段"
fi

if [ "$failed" = true ]; then
    exit 1
fi

cat <<EOF
{"schema_version":"1","status":"valid","privacy_mode":"$PRIVACY_MODE","bytes":$byte_count}
EOF
