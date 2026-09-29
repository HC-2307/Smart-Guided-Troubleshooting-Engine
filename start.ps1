Set-Location $PSScriptRoot

Write-Host "Smart Guided Troubleshooting Engine"
$secure = Read-Host "OpenAI API key (leave empty to use the free NVIDIA tier or offline mode)" -AsSecureString
$key = [System.Net.NetworkCredential]::new("", $secure).Password

if ($key) {
    $env:OPENAI_API_KEY = $key; $env:OPENAI_BASE_URL = "https://api.openai.com/v1"; $env:LLM_MODEL = "gpt-4o-mini"
    $env:GEMINI_API_KEY = ""; $env:LLM_EXTRA_BODY = "{}"
    Write-Host "Using OpenAI (gpt-4o-mini)."
} else {
    $env:OPENAI_API_KEY = ""; $env:GEMINI_API_KEY = ""; $env:OPENAI_BASE_URL = ""; $env:LLM_MODEL = ""; $env:LLM_EXTRA_BODY = ""
    $env:LLM_FREE_TIER = "true"
    $inEnvFile = (Test-Path .env) -and (Select-String -Path .env -Pattern '^NVIDIA_API_KEY=.+' -Quiet)
    if ($env:NVIDIA_API_KEY -or $inEnvFile) {
        Write-Host "Using the free NVIDIA Nemotron tier (key from your environment or .env)."
    } else {
        $nvidiaSecure = Read-Host "NVIDIA API key (free at build.nvidia.com; leave empty to run offline without an LLM)" -AsSecureString
        $nvidiaKey = [System.Net.NetworkCredential]::new("", $nvidiaSecure).Password
        if ($nvidiaKey) {
            $env:NVIDIA_API_KEY = $nvidiaKey
            Write-Host "Using the free NVIDIA Nemotron tier."
        } else {
            Write-Host "No key given: running offline (deterministic pipeline, no LLM)."
        }
    }
}

Write-Host "Starting API on http://localhost:8000 and UI on http://localhost:5500 (first build takes a few minutes)..."
docker compose up --build
