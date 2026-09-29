Set-Location $PSScriptRoot

Write-Host "Smart Guided Troubleshooting Engine"
$secure = Read-Host "OpenAI API key (leave empty to use the free NVIDIA Nemotron tier)" -AsSecureString
$key = [System.Net.NetworkCredential]::new("", $secure).Password

if ($key) {
    $env:OPENAI_API_KEY = $key; $env:OPENAI_BASE_URL = "https://api.openai.com/v1"; $env:LLM_MODEL = "gpt-4o-mini"
    $env:GEMINI_API_KEY = ""; $env:LLM_EXTRA_BODY = "{}"
    Write-Host "Using OpenAI (gpt-4o-mini)."
} else {
    $env:OPENAI_API_KEY = ""; $env:GEMINI_API_KEY = ""; $env:OPENAI_BASE_URL = ""; $env:LLM_MODEL = ""; $env:LLM_EXTRA_BODY = ""
    $env:LLM_FREE_TIER = "true"
    Write-Host "No key given: using the free NVIDIA Nemotron tier."
}

Write-Host "Starting API on http://localhost:8000 and UI on http://localhost:5500 (first build takes a few minutes)..."
docker compose up --build
