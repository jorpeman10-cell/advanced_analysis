param(
    [int]$Port = 8765
)

$python = 'C:\Users\EDY\AppData\Local\Python\pythoncore-3.14-64\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = 'python'
}

$token = [Environment]::GetEnvironmentVariable('RECRUITER_FINANCE_MCP_TOKEN', 'User')
if (-not $token) {
    throw 'RECRUITER_FINANCE_MCP_TOKEN is not configured for this user.'
}

$env:RECRUITER_FINANCE_MCP_TOKEN = $token
$env:RECRUITER_FINANCE_MCP_HOST = '0.0.0.0'
$env:RECRUITER_FINANCE_MCP_PORT = $Port.ToString()

Set-Location -LiteralPath $PSScriptRoot
& $python mcp_server.py *> "$PSScriptRoot\mcp_server.background.log"
