param(
    [string]$BaseUrl = "http://192.168.31.118:3456",
    [switch]$Machine
)

$ErrorActionPreference = "Stop"
$cliDir = $PSScriptRoot
if (-not (Test-Path (Join-Path $cliDir "browser-cli.cmd"))) {
    throw "browser-cli.cmd not found under $cliDir"
}

$target = if ($Machine) { "Machine" } else { "User" }
$currentPath = [Environment]::GetEnvironmentVariable("Path", $target)
if (-not $currentPath) {
    $currentPath = ""
}
$parts = $currentPath -split ";" | Where-Object { $_ -and $_.Trim() -ne "" }
if ($parts -notcontains $cliDir) {
    $newPath = if ($currentPath.Trim()) { "$currentPath;$cliDir" } else { $cliDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, $target)
}
[Environment]::SetEnvironmentVariable("BROWSER_SERVER_URL", $BaseUrl, $target)

Write-Output "Installed browser-cli to $target PATH: $cliDir"
Write-Output "Set BROWSER_SERVER_URL=$BaseUrl ($target)"
Write-Output "Open a new terminal and run: browser-cli health"
