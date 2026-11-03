$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Push-Location ..\frontend
npm.cmd run build
Pop-Location
if (Test-Path "app\static") { Remove-Item -Recurse -Force "app\static" }
Copy-Item -Recurse "..\frontend\dist" "app\static"
Write-Output "frontend copied to backend/app/static"
