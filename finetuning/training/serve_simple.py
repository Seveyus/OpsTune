#!/usr/bin/env python3
"""Lightweight OpenAI-compatible server using transformers instead of vLLM.

For low-VRAM GPUs where vLLM fails. Slower but works on 6GB.

Usage:
    python finetuning/training/serve_simple.py
    python finetuning/training/serve_simple.py --port 8000
"""
import argparse
import json
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

import torch
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from peft import PeftModel
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

# Import config
import sys
sys.path.insert(0, str(ROOT))
from finetuning.training import config as cfg

app = FastAPI(title="OpsTune Inference Server")

# Global model/tokenizer
model = None
tokenizer = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 512
    stream: bool = False


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list


@app.on_event("startup")
async def load_model():
    global model, tokenizer

    print(f"[serve] Loading base model: {cfg.BASE_MODEL_ID}")
    tokenizer = AutoTokenizer.from_pretrained(cfg.BASE_MODEL_ID, use_fast=True)

    # Load in 4-bit like training
    from transformers import BitsAndBytesConfig
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        llm_int8_enable_fp32_cpu_offload=True,
    )

    base_model = AutoModelForCausalLM.from_pretrained(
        cfg.BASE_MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        low_cpu_mem_usage=True,
        trust_remote_code=True,
        max_memory={0: "4.0GiB", "cpu": "12GiB"},
    )

    print(f"[serve] Loading LoRA adapter: {cfg.ADAPTER_DIR}")
    model = PeftModel.from_pretrained(base_model, str(cfg.ADAPTER_DIR))
    model.eval()

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("[serve] Model loaded successfully!")


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "opstune",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "opstune",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # Format messages using chat template
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    # Tokenize
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    # Generate
    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=request.max_tokens,
            temperature=request.temperature,
            do_sample=request.temperature > 0,
            pad_token_id=tokenizer.eos_token_id,
        )

    # Decode
    response_text = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True
    )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": inputs["input_ids"].shape[1],
            "completion_tokens": outputs.shape[1] - inputs["input_ids"].shape[1],
            "total_tokens": outputs.shape[1],
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print(f"[serve] Starting server on {args.host}:{args.port}")
    print(f"[serve] Adapter: {cfg.ADAPTER_DIR}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
