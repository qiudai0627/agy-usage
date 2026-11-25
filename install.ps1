$ErrorActionPreference = "Stop"

# 支持两种模式：
# 1. 本地目录执行：.\install.ps1 或双击 Start-Windows.bat
# 2. 远程一键安装：$env:AGY_USAGE_REPO="<owner>/agy-usage"; irm https://raw.githubusercontent.com/<owner>/agy-usage/main/install.ps1 | iex

$Port = if ($env:AGY_USAGE_PORT) { $env:AGY_USAGE_PORT } else { "18420" }
$BinDir = Join-Path $env:USERPROFILE ".local\bin"

$ScriptParent = if ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { "" }
if ($ScriptParent -and (Test-Path (Join-Path $ScriptParent "src\cli.py"))) {
    $RootDir = $ScriptParent
} else {
    $RepoSlug = if ($env:AGY_USAGE_REPO) { $env:AGY_USAGE_REPO } else { "qiudai0627/agy-usage" }
    $RootDir = Join-Path $env:LOCALAPPDATA "agy-usage\app"
    $ZipUrl = "https://github.com/$RepoSlug/archive/refs/heads/main.zip"
    $TmpZip = Join-Path $env:TEMP "agy-usage-main.zip"
    $TmpExt = Join-Path $env:TEMP "agy-usage-extract"
    Write-Host "==> 正在从 GitHub 下载 $RepoSlug..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $ZipUrl -OutFile $TmpZip
    if (Test-Path $TmpExt) { Remove-Item -Recurse -Force $TmpExt }
    Expand-Archive -Path $TmpZip -DestinationPath $TmpExt -Force
    if (Test-Path $RootDir) { Remove-Item -Recurse -Force $RootDir }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RootDir) | Out-Null
    Move-Item -Path (Get-ChildItem $TmpExt | Select-Object -First 1).FullName -Destination $RootDir
    Remove-Item -Force $TmpZip -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $TmpExt -ErrorAction SilentlyContinue
}

$SrcDir = Join-Path $RootDir "src"
$WinWidget = Join-Path $RootDir "windows\tray_widget.pyw"

Write-Host "==> 安装 agy-usage (Windows)" -ForegroundColor Cyan

$PyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PyCmd) {
    throw "未找到 python，请先安装 Python 3.9+ 并勾选 Add Python to PATH。"
}
$PyExe = $PyCmd.Source
$PywCandidate = Join-Path (Split-Path -Parent $PyExe) "pythonw.exe"
$PywExe = if (Test-Path $PywCandidate) { $PywCandidate } else { $PyExe }

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$WrapperPath = Join-Path $BinDir "agy-usage.cmd"
@"
@echo off
"$PyExe" "$SrcDir\cli.py" %*
"@ | Set-Content -Path $WrapperPath -Encoding UTF8
Write-Host "✓ 已创建命令: $WrapperPath" -ForegroundColor Green

& $PyExe "$SrcDir\cli.py" install-statusline --stack
& $PyExe "$SrcDir\cli.py" daemon restart --port $Port

if (Test-Path $WinWidget) {
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*tray_widget.pyw*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Process -FilePath $PywExe -ArgumentList "`"$WinWidget`""
    Write-Host "✓ 已启动右下角桌面迷你悬浮胶囊 (双击展开详情 / 右键菜单)" -ForegroundColor Green
}

Write-Host ""
Write-Host "安装完成！Web 监控台: http://127.0.0.1:$Port" -ForegroundColor Cyan
