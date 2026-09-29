#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"

echo "Smart Guided Troubleshooting Engine"
printf "OpenAI API key (leave empty to use the free NVIDIA Nemotron tier): "
stty -echo 2>/dev/null || true
read -r key
stty echo 2>/dev/null || true
echo

if [ -n "$key" ]; then
  export OPENAI_API_KEY="$key" OPENAI_BASE_URL="https://api.openai.com/v1" LLM_MODEL="gpt-4o-mini" GEMINI_API_KEY="" LLM_EXTRA_BODY="{}"
  echo "Using OpenAI (gpt-4o-mini)."
else
  export OPENAI_API_KEY="" GEMINI_API_KEY="" OPENAI_BASE_URL="" LLM_MODEL="" LLM_EXTRA_BODY="" LLM_FREE_TIER="true"
  echo "No key given: using the free NVIDIA Nemotron tier."
fi

echo "Starting API on http://localhost:8000 and UI on http://localhost:5500 (first build takes a few minutes)..."
docker compose up --build
