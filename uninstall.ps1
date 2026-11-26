$ErrorActionPreference = "Continue"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcDir = Join-Path $RootDir "src"
$WrapperPath = Join-Path $env:USERPROFILE ".local\bin\agy-usage.cmd"

Write-Host "==> 卸载 agy-usage (Windows)" -ForegroundColor Cyan

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*tray_widget.pyw*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$PyCmd = Get-Command python -ErrorAction SilentlyContinue
if ($PyCmd) {
    & $PyCmd.Source "$SrcDir\cli.py" daemon stop
    & $PyCmd.Source "$SrcDir\cli.py" uninstall-statusline
}

if (Test-Path $WrapperPath) {
    Remove-Item -Force $WrapperPath
    Write-Host "OK: 已移除 $WrapperPath" -ForegroundColor Green
}

Write-Host "卸载完成（如需彻底删除缓存可移除 %LOCALAPPDATA%\agy-usage）。"
