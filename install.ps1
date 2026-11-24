# Installs every Prop Firm Guard skill into %USERPROFILE%\.claude\skills (Claude Code personal skills).
$Dest = if ($args[0]) { $args[0] } else { Join-Path $env:USERPROFILE ".claude\skills" }
$Src = Join-Path $PSScriptRoot "plugins\prop-firm-guard\skills"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Get-ChildItem $Src -Directory | ForEach-Object {
  $t = Join-Path $Dest $_.Name
  if (Test-Path $t) { Remove-Item $t -Recurse -Force }
  Copy-Item $_.FullName $t -Recurse
  Write-Host "installed $($_.Name)"
}
Write-Host ""
Write-Host "Done. Restart Claude Code, then try: `"How much should I risk per trade on a 100k FTMO challenge?`""
