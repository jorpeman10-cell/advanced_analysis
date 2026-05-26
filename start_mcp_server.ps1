param(
    [int]$Port = 8765
)

$python = 'C:\Users\EDY\AppData\Local\Python\pythoncore-3.14-64\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = 'python'
}

if (-not $env:RECRUITER_FINANCE_MCP_TOKEN) {
    $env:RECRUITER_FINANCE_MCP_TOKEN = [Environment]::GetEnvironmentVariable(
        'RECRUITER_FINANCE_MCP_TOKEN',
        'User'
    )
}
if (-not $env:RECRUITER_FINANCE_MCP_TOKEN) {
    throw 'RECRUITER_FINANCE_MCP_TOKEN is not configured for this user.'
}

$env:RECRUITER_FINANCE_MCP_HOST = '0.0.0.0'
$env:RECRUITER_FINANCE_MCP_PORT = $Port.ToString()

Start-Process `
    -FilePath $python `
    -ArgumentList @('mcp_server.py') `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden

Write-Output "Recruiter Finance MCP starting at http://localhost:$Port/mcp"
