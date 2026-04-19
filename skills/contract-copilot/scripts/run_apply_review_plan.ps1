[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$PlanPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [string]$PythonCommand,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThruArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    $expanded = [Environment]::ExpandEnvironmentVariables($PathValue)
    if ([System.IO.Path]::IsPathRooted($expanded)) {
        return [System.IO.Path]::GetFullPath($expanded)
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $expanded))
}

function Ensure-ParentDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    $parent = Split-Path -Parent $PathValue
    if ([string]::IsNullOrWhiteSpace($parent)) {
        return
    }

    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}

function Copy-FileIfPresent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
        return
    }

    Ensure-ParentDirectory -PathValue $DestinationPath
    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
}

function Copy-DirectoryContentsIfPresent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceDir,

        [Parameter(Mandatory = $true)]
        [string]$DestinationDir
    )

    if (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) {
        return
    }

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {
        Copy-Item `
            -LiteralPath $_.FullName `
            -Destination (Join-Path $DestinationDir $_.Name) `
            -Recurse `
            -Force
    }
}

function Resolve-PythonInvocation {
    param(
        [string]$RequestedCommand
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedCommand)) {
        $command = Get-Command $RequestedCommand -ErrorAction Stop
        return @($command.Source)
    }

    $candidates = @(
        @("python"),
        @("python3"),
        @("py", "-3")
    )

    foreach ($candidate in $candidates) {
        if (Get-Command $candidate[0] -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }

    throw "未找到可用的 Python 解释器，请安装 python / python3，或通过 -PythonCommand 显式指定。"
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptRoot "apply_review_plan.py"

$resolvedInput = Resolve-AbsolutePath -PathValue $InputPath
$resolvedPlan = Resolve-AbsolutePath -PathValue $PlanPath
$resolvedOutput = Resolve-AbsolutePath -PathValue $OutputPath

if (-not (Test-Path -LiteralPath $resolvedInput -PathType Leaf)) {
    throw "输入 DOCX 不存在: $resolvedInput"
}

if (-not (Test-Path -LiteralPath $resolvedPlan -PathType Leaf)) {
    throw "审查计划文件不存在: $resolvedPlan"
}

$explicitPaths = @{}
$remainingArgs = New-Object System.Collections.Generic.List[string]
$pathSwitches = @{
    "--report"      = "report"
    "--report-docx" = "reportDocx"
    "--log"         = "log"
    "--archive-dir" = "archiveDir"
}

for ($index = 0; $index -lt $PassThruArgs.Count; $index++) {
    $arg = $PassThruArgs[$index]
    if ($pathSwitches.ContainsKey($arg)) {
        if ($index + 1 -ge $PassThruArgs.Count) {
            throw "参数 $arg 缺少路径值"
        }

        $explicitPaths[$pathSwitches[$arg]] = Resolve-AbsolutePath -PathValue $PassThruArgs[$index + 1]
        $index += 1
        continue
    }

    $remainingArgs.Add($arg)
}

$archiveDisabled = $remainingArgs.Contains("--no-archive")
$outputParent = Split-Path -Parent $resolvedOutput
$outputStem = [System.IO.Path]::GetFileNameWithoutExtension($resolvedOutput)

$reportDocxDestination = if ($explicitPaths.ContainsKey("reportDocx")) {
    [string]$explicitPaths["reportDocx"]
}
else {
    Join-Path $outputParent "${outputStem}_审查报告.docx"
}

$reportDestination = if ($explicitPaths.ContainsKey("report")) {
    [string]$explicitPaths["report"]
}
elseif ($archiveDisabled) {
    Join-Path $outputParent "${outputStem}_审查报告.md"
}
else {
    $null
}

$logDestination = if ($explicitPaths.ContainsKey("log")) {
    [string]$explicitPaths["log"]
}
elseif ($archiveDisabled) {
    Join-Path $outputParent "${outputStem}_执行日志.json"
}
else {
    $null
}

$archiveDestination = if ($explicitPaths.ContainsKey("archiveDir")) {
    [string]$explicitPaths["archiveDir"]
}
else {
    $null
}

$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("contract-copilot-" + [Guid]::NewGuid().ToString("N"))
$stageArchive = Join-Path $stageRoot "archive"
$stageInput = Join-Path $stageRoot ("input" + [System.IO.Path]::GetExtension($resolvedInput))
$stagePlan = Join-Path $stageRoot ("review-plan" + [System.IO.Path]::GetExtension($resolvedPlan))
$stageOutput = Join-Path $stageRoot "output.docx"
$stageReport = Join-Path $stageRoot "review-report.md"
$stageReportDocx = Join-Path $stageRoot "review-report.docx"
$stageLog = Join-Path $stageRoot "execution-log.json"

New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
$pythonInvocation = $null
$pythonArgs = @()
$exitCode = 1

try {
    Copy-Item -LiteralPath $resolvedInput -Destination $stageInput -Force
    Copy-Item -LiteralPath $resolvedPlan -Destination $stagePlan -Force

    $pythonArgs = @(
        $pythonScript,
        "--input", $stageInput,
        "--plan", $stagePlan,
        "--output", $stageOutput,
        "--report", $stageReport,
        "--report-docx", $stageReportDocx,
        "--log", $stageLog
    )

    if ($archiveDestination) {
        $pythonArgs += @("--archive-dir", $stageArchive)
    }

    $pythonArgs += $remainingArgs.ToArray()
    $pythonInvocation = Resolve-PythonInvocation -RequestedCommand $PythonCommand

    if ($pythonInvocation.Count -gt 1) {
        & $pythonInvocation[0] @($pythonInvocation[1..($pythonInvocation.Count - 1)]) @pythonArgs
    }
    else {
        & $pythonInvocation[0] @pythonArgs
    }

    if ($null -eq $LASTEXITCODE) {
        $exitCode = 0
    }
    else {
        $exitCode = [int]$LASTEXITCODE
    }
}
finally {
    Copy-FileIfPresent -SourcePath $stageOutput -DestinationPath $resolvedOutput
    Copy-FileIfPresent -SourcePath $stageReportDocx -DestinationPath $reportDocxDestination

    if ($reportDestination) {
        Copy-FileIfPresent -SourcePath $stageReport -DestinationPath $reportDestination
    }

    if ($logDestination) {
        Copy-FileIfPresent -SourcePath $stageLog -DestinationPath $logDestination
    }

    if ($archiveDestination) {
        Copy-DirectoryContentsIfPresent -SourceDir $stageArchive -DestinationDir $archiveDestination
    }

    Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
}

exit $exitCode
