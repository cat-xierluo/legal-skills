# ============================================================
# WorkBuddy 每日积分签到（Windows PowerShell 版，兼容 PS 5.1）
#
# 流程：读取本地令牌 -> 查询签到状态 -> 未签到则领取 -> 写日志
# 用法：
#   powershell -ExecutionPolicy Bypass -File checkin.ps1
# 或（显式指定运行时）：
#   $env:WB_CHECKIN_NODE="C:/path/to/node.exe"
#   $env:WB_CHECKIN_ELECTRON="C:/path/to/electron.exe"
#   powershell -ExecutionPolicy Bypass -File checkin.ps1
# 定时（示例，每天 09:00，管理员或普通用户均可）：
#   schtasks /Create /TN WorkBuddyDailyCheckin /TR "powershell -ExecutionPolicy Bypass -File C:/path/checkin.ps1" /SC DAILY /ST 09:00 /F
#
# 运行时策略：Node 优先（读取 v5.3.8+ 新版明文登录态），缺失时回退到 Electron + safeStorage。
#
# 凭据安全提示：
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

# 1. 读取令牌：Node 优先，Electron 回退
$Token = ""; $AccUid = ""; $AccDomain = ""; $EntId = ""
$NodeBin = Find-Node
if ($NodeBin) {
    try {
        $outLines = & $NodeBin $DecryptJs 2>$null
        foreach ($l in $outLines) {
            if ($l -match "^DECRYPT_RESULT:") { $Token = ($l -replace "^DECRYPT_RESULT:", "").Trim() }
            elseif ($l -match "^ACCOUNT_UID:") { $AccUid = ($l -replace "^ACCOUNT_UID:", "").Trim() }
            elseif ($l -match "^AUTH_DOMAIN:") { $AccDomain = ($l -replace "^AUTH_DOMAIN:", "").Trim() }
            elseif ($l -match "^ENTERPRISE_ID:") { $EntId = ($l -replace "^ENTERPRISE_ID:", "").Trim() }
        }
    } catch {}
}
# Electron 回退（Node 未取到有效 token，或 Node 报 ERR —— 如旧版账户无明文文件、纯 Node 无法解密 state.vscdb）
if (-not $Token -or $Token.StartsWith("ERR")) {
    $Electron = Find-Electron
    if ($Electron) {
        # 关键：若环境存在 ELECTRON_RUN_AS_NODE，必须移除，否则 require('electron') 拿不到 safeStorage
        Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
        try {
            $outLines = & $Electron $DecryptJs 2>$null
            foreach ($l in $outLines) {
                if ($l -match "^DECRYPT_RESULT:") { $Token = ($l -replace "^DECRYPT_RESULT:", "").Trim() }
                elseif ($l -match "^ACCOUNT_UID:") { $AccUid = ($l -replace "^ACCOUNT_UID:", "").Trim() }
                elseif ($l -match "^AUTH_DOMAIN:") { $AccDomain = ($l -replace "^AUTH_DOMAIN:", "").Trim() }
                elseif ($l -match "^ENTERPRISE_ID:") { $EntId = ($l -replace "^ENTERPRISE_ID:", "").Trim() }
            }
        } catch {
            Write-Log "调用 Electron 解密脚本出错：$($_.Exception.Message)"
        }
    }
}

if (-not $Token) {
    Write-Log "未找到 Node 或 Electron 运行时，或运行时未能产出令牌。请安装 Node.js，或设置 WB_CHECKIN_NODE / WB_CHECKIN_ELECTRON。"
    exit 1
}
if ($Token.StartsWith("ERR")) {
    Write-Log "获取令牌失败（$Token）。请确认已安装并登录 WorkBuddy 桌面端。"
    exit 1
}

$Api = "https://copilot.tencent.com"

# 复刻 WorkBuddy 桌面端真实签名（逆向自 app.asar 的 buildHeaders）：
# 官方接口路径需 /v2/ 前缀，且必须带 X-User-Id（企业账号另带 X-Enterprise-Id / X-Tenant-Id）。
# 缺任一项都会被 APISIX 网关判定为未授权（HTTP 401）。
function Invoke-CheckinApi([string]$Path) {
    $a = @(
        "-s", "-m", "15", "-w", "\n%{http_code}", "-X", "POST",
        "$Api$Path",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-H", "Authorization: Bearer $Token",
        "-H", "X-User-Id: $AccUid"
    )
    if ($AccDomain) { $a += "-H"; $a += "X-Domain: $AccDomain" }
    if ($EntId) { $a += "-H"; $a += "X-Enterprise-Id: $EntId"; $a += "-H"; $a += "X-Tenant-Id: $EntId" }
    $a += "-d"; $a += "{}"
    $raw = & curl.exe @a 2>$null
    # 末行是 HTTP 状态码，其余为响应体；返回 [状态码, 响应体]
    if (-not $raw) { return @("000", "") }
    $lines = @($raw)
    $code = [string]($lines | Select-Object -Last 1)
    $body = if ($lines.Count -gt 1) { ($lines | Select-Object -First ($lines.Count - 1)) -join "" } else { "" }
    return @($code, $body)
}

# 2. 查询签到状态
# 鉴权失败一律以真实 HTTP 状态码判定，不再匹配响应体子串。
# 旧实现用 `$Status -match "401|unauthorized"` 扫响应体，而响应体带随机 UUID 的 requestId，
# 约 0.57%/次 会因 UUID 里恰好出现 "401" 被误判为令牌过期 —— 脚本在调 daily-checkin
# 之前就退出，导致当日积分未领取、连续签到中断（第 7 天 1000 积分奖励作废）。
$Status = ""; $HttpCode = "000"
try { $r = Invoke-CheckinApi "/v2/billing/meter/checkin-status"; $HttpCode = $r[0]; $Status = $r[1] } catch { $HttpCode = "000"; $Status = "" }
if ($HttpCode -eq "000") { Write-Log "查询签到状态失败（网络异常）"; exit 1 }
if ($HttpCode -eq "401" -or $HttpCode -eq "403") { Write-Log "令牌已过期或无权限（HTTP $HttpCode），请打开 WorkBuddy 桌面端刷新登录态后重试"; exit 1 }
if ($HttpCode -ne "200") { Write-Log "查询签到状态失败（HTTP $HttpCode）"; exit 1 }
if (-not $Status) { Write-Log "查询签到状态失败（响应为空，HTTP $HttpCode）"; exit 1 }

# 注意：today_checked_in 字段在 v5.3.8 实测不可靠（签到成功后仍可能为 false）。
# 此处仅用于快速短路与 401 探测；真正的幂等兜底在下方 daily-checkin 的 code=10001 处理。
$Checked = $false
try { $Checked = [bool]($Status | ConvertFrom-Json).data.today_checked_in } catch {}
if ($Checked) { Write-Log "今日已签到，无需重复领取"; exit 0 }

# 3. 执行签到
$Result = ""; $HttpCode2 = "000"
try { $r2 = Invoke-CheckinApi "/v2/billing/meter/daily-checkin"; $HttpCode2 = $r2[0]; $Result = $r2[1] } catch { $HttpCode2 = "000"; $Result = "" }
if ($HttpCode2 -eq "000") { Write-Log "签到请求失败（网络异常）"; exit 1 }
if ($HttpCode2 -eq "401" -or $HttpCode2 -eq "403") { Write-Log "令牌已过期或无权限（HTTP $HttpCode2），请打开 WorkBuddy 桌面端刷新登录态后重试"; exit 1 }
if (-not $Result) { Write-Log "签到请求失败（响应为空，HTTP $HttpCode2）"; exit 1 }

$Credit = ""
try {
    $d = $Result | ConvertFrom-Json
    if ($d.code -eq 0) { $Credit = "OK credit=$($d.data.credit) streak_days=$($d.data.streak_days)" }
    elseif ($d.code -eq 10001) { $Credit = "ALREADY today" }   # 当日已签到：接口幂等拒绝，视为成功
    else { $Credit = "FAIL code=$($d.code) msg=$($d.msg)" }
} catch { $Credit = "PARSE_ERR" }

if ($Credit -like "OK*") { Write-Log "签到成功！领取 $Credit" }
elseif ($Credit -like "ALREADY*") { Write-Log "今日已签到，无需重复领取（接口返回已签到）" }
else { Write-Log ("签到未成功：" + $Credit) }
