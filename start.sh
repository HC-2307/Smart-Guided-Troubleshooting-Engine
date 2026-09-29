#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"

echo "Smart Guided Troubleshooting Engine"
printf "OpenAI API key (leave empty to use the free NVIDIA tier or offline mode): "
stty -echo 2>/dev/null || true
read -r key
stty echo 2>/dev/null || true
echo

if [ -n "$key" ]; then
  export OPENAI_API_KEY="$key" OPENAI_BASE_URL="https://api.openai.com/v1" LLM_MODEL="gpt-4o-mini" GEMINI_API_KEY="" LLM_EXTRA_BODY="{}"
  echo "Using OpenAI (gpt-4o-mini)."
else
  export OPENAI_API_KEY="" GEMINI_API_KEY="" OPENAI_BASE_URL="" LLM_MODEL="" LLM_EXTRA_BODY="" LLM_FREE_TIER="true"
  if [ -n "$NVIDIA_API_KEY" ] || grep -Eq '^NVIDIA_API_KEY=.+' .env 2>/dev/null; then
    echo "Using the free NVIDIA Nemotron tier (key from your environment or .env)."
  else
    printf "NVIDIA API key (free at build.nvidia.com; leave empty to run offline without an LLM): "
    stty -echo 2>/dev/null || true
    read -r nvidia_key
    stty echo 2>/dev/null || true
    echo
    if [ -n "$nvidia_key" ]; then
      export NVIDIA_API_KEY="$nvidia_key"
      echo "Using the free NVIDIA Nemotron tier."
    else
      echo "No key given: running offline (deterministic pipeline, no LLM)."
    fi
  fi
fi

echo "Starting API on http://localhost:8000 and UI on http://localhost:5500 (first build takes a few minutes)..."
docker compose up --build
