# ============================================================
# WorkBuddy 每日签到 - 环境安装脚本（Windows PowerShell 版）
# 检测运行时并验证令牌读取链路。
#
# v5.3.8+ 新版登录态为明文 JSON，纯 Node 即可读取，无需 Electron。
# 仅当使用旧版 WorkBuddy/CodeBuddy（state.vscdb 加密登录态）时才需要 Electron。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File setup.ps1
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -ElectronPath C:\path\to\electron.exe
# ============================================================
param(
    [string]$ElectronPath = ""
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Split-Path -Parent $ScriptDir
$RuntimeDir = Join-Path $SkillRoot ".runtime"
$DefaultElectron = Join-Path $RuntimeDir "electron\electron.exe"
$DecryptJs = Join-Path $ScriptDir "decrypt-token.js"

Write-Output "== WorkBuddy 每日签到 · 环境检查 =="

# ---------- 探测 Node（v5.3.8+ 新版明文登录态优先用 Node 直读）----------
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
    if ($ElectronPath -and (Test-Path $ElectronPath)) { return $ElectronPath }
    if ($env:WB_CHECKIN_ELECTRON -and (Test-Path $env:WB_CHECKIN_ELECTRON)) { return $env:WB_CHECKIN_ELECTRON }
    $cands = @(
        (Join-Path $HOME ".workbuddy\tools\electron\electron.exe"),
        $DefaultElectron,
        (Join-Path $HOME ".workbuddy\skills\workbuddy-checkin\.runtime\electron\electron.exe")
    )
    foreach ($c in $cands) { if ($c -and (Test-Path $c)) { return $c } }
    return ""
}

# ---------- 用 Node 探测新版明文登录态是否可用（不输出 token 内容） ----------
$NodeBin = Find-Node
$Token = ""
if ($NodeBin) {
    try {
        $out = & $NodeBin $DecryptJs 2>$null | Select-String "^DECRYPT_RESULT:"
        if ($out) { $Token = (($out | Select-Object -First 1).Line -replace "^DECRYPT_RESULT:", "").Trim() }
    } catch { $Token = "" }
}

# ============================================================
# 路径 A：新版明文登录态（v5.3.8+）→ 纯 Node 即可，无需 Electron
# ============================================================
if ($NodeBin -and $Token -and -not $Token.StartsWith("ERR")) {
    Write-Output "✅ 检测到新版登录态（WorkBuddy v5.3.8+ 明文存储），Node 可直接读取。"
    Write-Output "✅ 令牌读取链路可用（运行时：$NodeBin），无需安装 Electron。"
    Write-Output ""
    Write-Output "== 完成 =="
    $CheckinPs1 = Join-Path $ScriptDir "checkin.ps1"
    Write-Output "运行签到：  powershell -ExecutionPolicy Bypass -File `"$CheckinPs1`""
    exit 0
}

# ============================================================
# 路径 B：旧版 state.vscdb 加密登录态 → 需要 Electron 运行时
# ============================================================
Write-Output "（未检测到新版明文登录态，按旧版 state.vscdb 流程处理，需要 Electron 运行时。）"
Write-Output ""

$Electron = Find-Electron
if (-not $Electron) {
    # 供应链安全：自动从 npm 下载第三方运行时（约 100MB）默认关闭，需显式开启。
    if (-not $env:WB_CHECKIN_AUTO_INSTALL_ELECTRON) {
        Write-Output "⚠️ 未检测到 Node 可读的新版登录态，也未找到 Electron 运行时。"
        Write-Output "   大多数用户应先确认：已安装 WorkBuddy 桌面端 v5.3.8+ 并登录（新版登录态优先用 Node 读取）。"
        Write-Output "   仅旧版 WorkBuddy/CodeBuddy（state.vscdb）账户才需要 Electron，二选一："
        Write-Output "   1) 手动指定已校验的 Electron：  setup.ps1 -ElectronPath C:\path\to\electron.exe"
        Write-Output "   2) 确认要从官方 npm 下载（约 100MB），先执行："
        Write-Output "        `$env:WB_CHECKIN_AUTO_INSTALL_ELECTRON=1"
        Write-Output "      再运行本脚本。"
        exit 1
    }
    Write-Output "⚠️ 未检测到 Electron，尝试通过 npm 下载（约 100MB，需要 Node.js）..."
    Write-Output "   ⚠️ 供应链提示：将从官方 npm registry 下载 electron@37 并执行，请确认网络可信。"
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Write-Output "❌ 未找到 npm。请先安装 Node.js（https://nodejs.org 下载 LTS 版），"
        Write-Output "   或手动下载 Electron 并执行 setup.ps1 -ElectronPath <electron.exe>。"
        exit 1
    }
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    Push-Location $RuntimeDir
    npm init -y | Out-Null
    npm install electron@37 2>$null | Out-Null
    if (-not (Test-Path (Join-Path $RuntimeDir "node_modules\electron\dist\electron.exe"))) {
        Write-Output "❌ Electron 下载失败（网络/代理问题）。可配置 npm 镜像后重试："
        Write-Output "   npm config set registry https://registry.npmmirror.com"
        Pop-Location
        exit 1
    }
    Move-Item -Force (Join-Path $RuntimeDir "node_modules\electron\dist") (Join-Path $RuntimeDir "electron")
    Remove-Item -Recurse -Force (Join-Path $RuntimeDir "node_modules") -ErrorAction SilentlyContinue
    Remove-Item -Force (Join-Path $RuntimeDir "package.json"), (Join-Path $RuntimeDir "package-lock.json") -ErrorAction SilentlyContinue
    Pop-Location
    $Electron = $DefaultElectron
    Write-Output "✅ Electron 安装完成：$Electron"
} else {
    Write-Output "✅ 已检测到 Electron：$Electron"
}

# ---------- 验证旧版解密链路 ----------
Write-Output "== 验证令牌解密 =="
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$Token = ""
try {
    $out = & $Electron $DecryptJs 2>$null | Select-String "^DECRYPT_RESULT:"
    if ($out) { $Token = (($out | Select-Object -First 1).Line -replace "^DECRYPT_RESULT:", "").Trim() }
} catch { $Token = "" }

if (-not $Token -or $Token.StartsWith("ERR")) {
    Write-Output "❌ 解密失败（$Token）。请确认：1) 已安装并登录 WorkBuddy 桌面端；"
    Write-Output "   2) 旧版账户应用名若为 CodeBuddy，设置环境变量 WB_CHECKIN_APP_NAME=CodeBuddy 后重试；"
    Write-Output "   3) 新版 v5.3.8+ 账户应安装 Node.js 用 Node 直读。"
    exit 1
}

Write-Output "✅ 令牌解密成功（长度 $($Token.Length)）"
Write-Output ""
Write-Output "== 完成 =="
$CheckinPs1 = Join-Path $ScriptDir "checkin.ps1"
Write-Output "运行签到：  powershell -ExecutionPolicy Bypass -File `"$CheckinPs1`""
Write-Output "设置定时（每天 09:00，示例）："
Write-Output "  schtasks /Create /TN WorkBuddyDailyCheckin /TR `"powershell -ExecutionPolicy Bypass -File `"$CheckinPs1`"`" /SC DAILY /ST 09:00 /F"
