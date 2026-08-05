# ============================================================
# WorkBuddy 每日签到 - 环境安装脚本（Windows PowerShell 版）
# 自动检测/下载 Electron 运行时，并验证令牌解密链路。
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

Write-Output "== WorkBuddy 每日签到 · 环境检查 =="

function Find-Electron {
    if ($ElectronPath -and (Test-Path $ElectronPath)) { return $ElectronPath }
    $cands = @(
        (Join-Path $HOME ".workbuddy\tools\electron\electron.exe"),
        $DefaultElectron,
        (Join-Path $HOME ".workbuddy\skills\workbuddy-checkin\.runtime\electron\electron.exe")
    )
    foreach ($c in $cands) { if ($c -and (Test-Path $c)) { return $c } }
    return ""
}

$Electron = Find-Electron
if (-not $Electron) {
    Write-Output "⚠️ 未检测到 Electron，尝试通过 npm 下载（约 100MB，需要 Node.js）..."
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

# ---------- 验证解密链路 ----------
Write-Output "== 验证令牌解密 =="
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$Token = ""
try {
    $out = & $Electron (Join-Path $ScriptDir "decrypt-token.js") 2>$null | Select-String "^DECRYPT_RESULT:"
    if ($out) { $Token = (($out | Select-Object -First 1).Line -replace "^DECRYPT_RESULT:", "").Trim() }
} catch { $Token = "" }

if (-not $Token -or $Token.StartsWith("ERR")) {
    Write-Output "❌ 解密失败（$Token）。请确认：1) 已安装并登录 WorkBuddy 桌面端；"
    Write-Output "   2) 若为旧版应用名（CodeBuddy），设置环境变量 WB_CHECKIN_APP_NAME=CodeBuddy 后重试。"
    exit 1
}

Write-Output "✅ 令牌解密成功（长度 $($Token.Length)）"
Write-Output ""
Write-Output "== 完成 =="
$CheckinPs1 = Join-Path $ScriptDir "checkin.ps1"
Write-Output "运行签到：  powershell -ExecutionPolicy Bypass -File `"$CheckinPs1`""
Write-Output "设置定时（每天 09:00，示例）："
Write-Output "  schtasks /Create /TN WorkBuddyDailyCheckin /TR `"powershell -ExecutionPolicy Bypass -File `"$CheckinPs1`"`" /SC DAILY /ST 09:00 /F"
