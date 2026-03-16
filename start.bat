@echo off
chcp 65001
cls

set ROOT=%~dp0
cd /d %ROOT%

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
) else (
    echo Virtual environment not found, using system python
)

set BROWSER_HOST=0.0.0.0
set BROWSER_PORT=3456
set BROWSER_USER_DATA_DIR=%ROOT%user_data
set BROWSER_HEADLESS=false
set BROWSER_AUTO_START=false

start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0; $i -lt 20; $i++){ try { Invoke-RestMethod -Uri 'http://127.0.0.1:3456/health' -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Milliseconds 500 } }; if($ok){ try { Invoke-RestMethod -Uri 'http://127.0.0.1:3456/mcp/open' -Method Post -ContentType 'application/json' -Body '{\"url\":\"https://example.org/\",\"timeout_ms\":30000}' | Out-Null; Write-Host 'MCP open triggered https://example.org/' } catch { Write-Host ('MCP open trigger failed: ' + $_.Exception.Message) }; Start-Sleep -Milliseconds 800; try { Invoke-RestMethod -Uri 'http://127.0.0.1:3456/start' -Method Post -ContentType 'application/json' -Body '{}' | Out-Null; Write-Host 'Playwright browser start triggered' } catch { Write-Host ('Playwright start trigger failed: ' + $_.Exception.Message) } } else { Write-Host 'Service health check timeout before startup sequence' }"

python browser_server.py

pause
