# ServerPulse Bot Stopper
# Double-click this file to stop the bot!

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ServerPulse Bot Stopper" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to project directory
Set-Location -Path "f:\Sahaj\Projects\ServerPulse"

Write-Host "Stopping ServerPulse Discord Bot..." -ForegroundColor Yellow
Write-Host ""

# Stop containers
docker compose down

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Bot Stopped!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
