# ServerPulse Bot Starter
# Double-click this file to start the bot!

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ServerPulse Bot Starter" -ForegroundColor Cyan  
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to project directory
Set-Location -Path "f:\Sahaj\Projects\ServerPulse"

Write-Host "Starting ServerPulse Discord Bot..." -ForegroundColor Yellow
Write-Host ""

# Start containers
docker compose up -d

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Bot Started!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Show status
Write-Host "Checking container status..." -ForegroundColor Yellow
docker compose ps

Write-Host ""
Write-Host "Commands you can use:" -ForegroundColor Cyan
Write-Host "  - To stop:    docker compose down" -ForegroundColor White
Write-Host "  - To restart: docker compose restart" -ForegroundColor White
Write-Host "  - To view logs: docker compose logs -f serverpulse" -ForegroundColor White
Write-Host ""

Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
