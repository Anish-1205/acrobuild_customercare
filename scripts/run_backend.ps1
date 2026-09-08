$ErrorActionPreference = "Stop"
Set-Location -LiteralPath "E:\customer-support-agent"
$env:PYTHONUNBUFFERED = "1"
& "C:\Python312\python.exe" -m uvicorn app:api --host 127.0.0.1 --port 8000 *>> "E:\customer-support-agent\backend-task.log"
exit $LASTEXITCODE
