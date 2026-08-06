# ============================================================
# WorkBuddy 每日积分签到（Windows PowerShell 版，兼容 PS 5.1）
#
# 流程：读取本地令牌 → 查询签到状态 → 未签到则领取 → 写日志
# 用法：
#   powershell -ExecutionPolicy Bypass -File checkin.ps1
# 或（显式指定运行时）：
#   $env:WB_CHECKIN_NODE="C:\path\to\node.exe"
#   $env:WB_CHECKIN_ELECTRON="C:\path\to\electron.exe"
#   powershell -ExecutionPolicy Bypass -File checkin.ps1
# 定时（示例，每天 09:00，管理员或普通用户均可）：
#   schtasks /Create /TN WorkBuddyDailyCheckin /TR "powershell -ExecutionPolicy Bypass -File C:\path\checkin.ps1" /SC DAILY /ST 09:00 /F
#
# 运行时策略：Node 优先（读取 v5.3.8+ 新版明文登录态），缺失时回退到 Electron + safeStorage。
#
# ⚠️ 凭据安全提示：
#   - 本地令牌（accessToken）等同 WorkBuddy 账号密码，仅在本脚本内存中使用，
#     通过管道立即消费，不写入日志、不落地、不回显。
#   - 日志（logs/checkin.log）只记录签到结果（积分/连续天数），不含令牌。
#   - 切勿将日志、脚本输出粘贴分享或提交到任何仓库。
# ============================================================
$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DecryptJs = Join-Path $ScriptDir "decrypt-token.js"
$SkillRoot = Split-Path -Parent $ScriptDir
$LogDir = Join-Path $SkillRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "checkin.log"

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# ---------- 可选：随机错峰（避免整点风暴） ----------
# 设置环境变量 WB_CHECKIN_JITTER=<秒> 时，开始前随机等待 0~N 秒
if ($env:WB_CHECKIN_JITTER) {
    try {
        $max = [int]$env:WB_CHECKIN_JITTER
        if ($max -gt 0) { Start-Sleep -Seconds (Get-Random -Maximum $max) }
    } catch {}
}

# ---------- 探测 Node 运行时（v5.3.8+ 新版明文登录态优先用 Node 直读） ----------
function Find-Node {
    if ($env:WB_CHECKIN_NODE -and (Test-Path $env:WB_CHECKIN_NODE)) { return $env:WB_CHECKIN_NODE }
    $cands = @(
        (Get-Command node -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        (Join-Path $env:ProgramFiles "nodejs\node.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs\node.exe")
    )
    foreach ($c in $cands) { if ($c -and (Test-Path $c)) { return $c } }
    return ""
}

# ---------- 探测 Electron 运行时（仅旧版 state.vscdb 回退分支需要） ----------
function Find-Electron {
    if ($env:WB_CHECKIN_ELECTRON -and (Test-Path $env:WB_CHECKIN_ELECTRON)) {
        return $env:WB_CHECKIN_ELECTRON
    }
    $cands = @(
        (Join-Path $HOME ".workbuddy\tools\electron\electron.exe"),
        (Join-Path $HOME ".workbuddy\skills\workbuddy-checkin\.runtime\electron\electron.exe"),
        (Join-Path $SkillRoot ".runtime\electron\electron.exe"),
        (Join-Path $ScriptDir "..\node_modules\electron\dist\electron.exe")
    )
    foreach ($c in $cands) { if ($c -and (Test-Path $c)) { return $c } }
    return ""
}

# ---------- 1. 读取令牌：Node 优先，Electron 回退 ----------
$Token = ""
# Node 优先
$NodeBin = Find-Node
if ($NodeBin) {
    try {
        $out = & $NodeBin $DecryptJs 2>$null | Select-String "^DECRYPT_RESULT:"
        if ($out) { $Token = (($out | Select-Object -First 1).Line -replace "^DECRYPT_RESULT:", "").Trim() }
    } catch {}
}
# Electron 回退（Node 未取到有效 token，或 Node 报 ERR —— 如旧版账户无明文文件、纯 Node 无法解密 state.vscdb）
if (-not $Token -or $Token.StartsWith("ERR")) {
    $Electron = Find-Electron
    if ($Electron) {
        # 关键：若环境存在 ELECTRON_RUN_AS_NODE，必须移除，否则 require('electron') 拿不到 safeStorage
        Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
        try {
            $out = & $Electron $DecryptJs 2>$null | Select-String "^DECRYPT_RESULT:"
            if ($out) { $Token = (($out | Select-Object -First 1).Line -replace "^DECRYPT_RESULT:", "").Trim() }
        } catch {
            Write-Log "❌ 调用 Electron 解密脚本出错：$($_.Exception.Message)"
        }
    }
}

if (-not $Token) {
    Write-Log "❌ 未找到 Node 或 Electron 运行时，或运行时未能产出令牌。请安装 Node.js，或设置 WB_CHECKIN_NODE / WB_CHECKIN_ELECTRON。"
    exit 1
}
if ($Token.StartsWith("ERR")) {
    Write-Log "❌ 获取令牌失败（$Token）。请确认已安装并登录 WorkBuddy 桌面端。"
    exit 1
}

$Api = "https://copilot.tencent.com"

# ---------- 2. 查询签到状态 ----------
$Status = ""
try {
    $Status = & curl.exe -s -m 15 -X POST "$Api/billing/meter/checkin-status" `
        -H "Content-Type: application/json" -H "Accept: application/json" `
        -H "Authorization: Bearer $Token" -d '{}' 2>$null
} catch { $Status = "" }
if (-not $Status) { Write-Log "❌ 查询签到状态失败（网络异常）"; exit 1 }
if ($Status -match "401|unauthorized") { Write-Log "❌ 令牌已过期（401），请打开 WorkBuddy 桌面端刷新登录态后重试"; exit 1 }

# 注意：today_checked_in 字段在 v5.3.8 实测不可靠（签到成功后仍可能为 false）。
# 此处仅用于快速短路与 401 探测；真正的幂等兜底在下方 daily-checkin 的 code=10001 处理。
$Checked = $false
try { $Checked = [bool]($Status | ConvertFrom-Json).data.today_checked_in } catch {}
if ($Checked) { Write-Log "✅ 今日已签到，无需重复领取"; exit 0 }

# ---------- 3. 执行签到 ----------
$Result = ""
try {
    $Result = & curl.exe -s -m 15 -X POST "$Api/billing/meter/daily-checkin" `
        -H "Content-Type: application/json" -H "Accept: application/json" `
        -H "Authorization: Bearer $Token" -d '{}' 2>$null
} catch { $Result = "" }
if (-not $Result) { Write-Log "❌ 签到请求失败（网络异常）"; exit 1 }

$Credit = ""
try {
    $d = $Result | ConvertFrom-Json
    if ($d.code -eq 0) { $Credit = "OK credit=$($d.data.credit) streak_days=$($d.data.streak_days)" }
    elseif ($d.code -eq 10001) { $Credit = "ALREADY today" }   # 当日已签到：接口幂等拒绝，视为成功
    else { $Credit = "FAIL code=$($d.code) msg=$($d.msg)" }
} catch { $Credit = "PARSE_ERR" }

if ($Credit -like "OK*") { Write-Log "🎉 签到成功！领取 $Credit" }
elseif ($Credit -like "ALREADY*") { Write-Log "✅ 今日已签到，无需重复领取（接口返回已签到）" }
else { Write-Log "⚠️ 签到未成功：$Credit" }
