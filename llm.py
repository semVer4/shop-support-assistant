"""Real LLM adapters. Models classify requests; policy code supplies the facts."""
from dataclasses import dataclass
import json
import os
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SCHEMA = {
    "type": "object",
    "properties": {"topics": {"type": "array", "items": {"type": "string", "enum": ["product", "delivery", "return", "defect", "discount", "greeting", "unknown"]}, "minItems": 1, "maxItems": 7}},
    "required": ["topics"],
    "additionalProperties": False,
}


@dataclass
class RoutingDecision:
    plan: dict
    trace: dict


def local_router():
    base = os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8089").rstrip("/")
    if urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Local LLM URL must use a loopback address")
    model = os.environ.get("LOCAL_LLM_MODEL", "qwen2.5-1.5b-instruct")

    def classify(message, prompt):
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": message}],
            "temperature": 0,
            "seed": 42,
            "max_tokens": 160,
            "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": "support_topics", "strict": True, "schema": SCHEMA}},
        }
        request = Request(base + "/v1/chat/completions", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        started = time.monotonic()
        with urlopen(request, timeout=90) as response:
            data = json.load(response)
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Incomplete local model response")
        plan = json.loads(choice["message"]["content"])
        return RoutingDecision(plan, {
            "provider": "llama.cpp", "model": data.get("model", model),
            "response_id": data["id"], "usage": data.get("usage", {}),
            "duration_ms": round((time.monotonic() - started) * 1000),
            "model_topics": plan.get("topics"),
        })
    return classify


def configured_router():
    provider = os.environ.get("LLM_PROVIDER", "openai")
    if provider == "local":
        return local_router()
    if provider == "rules":
        return None
    if provider != "openai":
        raise ValueError("Unknown LLM_PROVIDER")
    key, model = os.environ.get("OPENAI_API_KEY"), os.environ.get("OPENAI_MODEL")
    if not key or not model:
        return None

    def classify(message, prompt):
        payload = {
            "model": model,
            "store": False,
            "input": [{"role": "system", "content": prompt}, {"role": "user", "content": message}],
            "text": {"format": {"type": "json_schema", "name": "support_topics", "strict": True, "schema": SCHEMA}},
        }
        request = Request("https://api.openai.com/v1/responses", data=json.dumps(payload).encode("utf-8"), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        started = time.monotonic()
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
        if data.get("status") != "completed":
            raise ValueError("Incomplete model response")
        chunks = [part["text"] for item in data.get("output", []) if item.get("type") == "message" for part in item.get("content", []) if part.get("type") == "output_text"]
        if not chunks:
            raise ValueError("No structured classifier output")
        plan = json.loads("".join(chunks))
        return RoutingDecision(plan, {
            "provider": "openai", "model": data.get("model", model),
            "response_id": data.get("id"), "usage": data.get("usage", {}),
            "duration_ms": round((time.monotonic() - started) * 1000),
            "model_topics": plan.get("topics"),
        })
    return classify

