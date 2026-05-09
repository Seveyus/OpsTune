#!/usr/bin/env bash
# OpenAI-compatible vLLM server for the OpsTune fine-tuned model.
#
# Defaults to LoRA mode (loads base + adapter on the fly).
# Pass --merged to load runs/<RUN_NAME>/merged/ instead (faster, larger).
#
#   bash finetuning/training/serve_vllm.sh
#   bash finetuning/training/serve_vllm.sh --merged
#   bash finetuning/training/serve_vllm.sh --port 8001 --merged
#
# After the server is up:
#   curl http://localhost:8000/v1/models
#   curl http://localhost:8000/v1/chat/completions \
#     -H 'Content-Type: application/json' \
#     -d '{"model":"opstune", "messages":[{"role":"user","content":"..."}]}'
#
# Backend integration: point agent_workflow at it via env vars
#   export OPENAI_BASE_URL=http://localhost:8000/v1
#   export OPENAI_API_KEY=dummy
#   export OPENAI_MODEL=opstune
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_NAME="${OPSTUNE_RUN_NAME:-opstune-llama31-8b-lora-v1}"
BASE_MODEL="${OPSTUNE_BASE_MODEL:-meta-llama/Llama-3.1-8B-Instruct}"
RUN_DIR="${ROOT}/finetuning/training/runs/${RUN_NAME}"
ADAPTER_DIR="${RUN_DIR}/adapter"
MERGED_DIR="${RUN_DIR}/merged"

PORT=8000
MODE="lora"
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --merged) MODE="merged"; shift ;;
    --port)   PORT="$2"; shift 2 ;;
    *)        EXTRA+=("$1"); shift ;;
  esac
done

if [[ "$MODE" == "merged" ]]; then
  if [[ ! -d "$MERGED_DIR" ]]; then
    echo "[serve] merged dir missing: $MERGED_DIR" >&2
    echo "        run: python finetuning/training/merge_adapter.py" >&2
    exit 1
  fi
  echo "[serve] merged weights from $MERGED_DIR on :$PORT"
  exec python -m vllm.entrypoints.openai.api_server \
    --model "$MERGED_DIR" \
    --served-model-name opstune \
    --dtype bfloat16 \
    --port "$PORT" \
    "${EXTRA[@]}"
else
  if [[ ! -d "$ADAPTER_DIR" ]]; then
    echo "[serve] adapter dir missing: $ADAPTER_DIR" >&2
    echo "        run: python finetuning/training/train.py" >&2
    exit 1
  fi
  echo "[serve] base $BASE_MODEL + LoRA adapter from $ADAPTER_DIR on :$PORT"
  exec python -m vllm.entrypoints.openai.api_server \
    --model "$BASE_MODEL" \
    --served-model-name opstune \
    --dtype bfloat16 \
    --enable-lora \
    --lora-modules "opstune=$ADAPTER_DIR" \
    --max-loras 1 \
    --max-lora-rank 16 \
    --port "$PORT" \
    "${EXTRA[@]}"
fi
