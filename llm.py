"""Generate customer-facing text with a constrained JSON response format."""
from dataclasses import dataclass
import json
import os
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SOURCE_IDS = ["product", "delivery", "return", "opened", "defect", "discount"]
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "string", "enum": SOURCE_IDS}, "maxItems": 6},
        "needs_human": {"type": "boolean"},
    },
    "required": ["answer", "source_ids", "needs_human"],
    "additionalProperties": False,
}


@dataclass
class ModelResult:
    value: dict
    trace: dict


class LanguageModel:
    def __init__(self, provider, model, key=None, base=None):
        self.provider, self.model, self._key = provider, model, key
        self.base = base
        if provider == "local" and (urlsplit(base).scheme != "http" or urlsplit(base).hostname not in {"127.0.0.1", "localhost", "::1"}):
            raise ValueError("Local model must use HTTP on a loopback address")

    def request(self, system, message, schema, purpose):
        headers = {"Content-Type": "application/json"}
        if self.provider == "local":
            url = self.base.rstrip("/") + "/v1/chat/completions"
            payload = {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": message}],
                "temperature": 0,
                "top_p": 0.95, "repeat_penalty": 1.05,
                "seed": 42, "max_tokens": 320, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "reasoning_effort": "none",
                "response_format": {"type": "json_schema", "json_schema": {"name": purpose, "strict": True, "schema": schema}},
            }
        else:
            url = "https://api.openai.com/v1/responses"
            headers["Authorization"] = "Bearer " + self._key
            payload = {
                "model": self.model, "store": False,
                "input": [{"role": "system", "content": system}, {"role": "user", "content": message}],
                "text": {"format": {"type": "json_schema", "name": purpose, "strict": True, "schema": schema}},
            }
        request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        started = time.monotonic()
        with urlopen(request, timeout=45) as response:
            data = json.load(response)
        if self.provider == "local":
            if data.get("model") and data["model"] != self.model:
                raise ValueError("Unexpected local model")
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete model output")
            value = json.loads(choice["message"]["content"])
        else:
            if data.get("status") != "completed":
                raise ValueError("Incomplete model output")
            chunks = [p["text"] for item in data.get("output", []) if item.get("type") == "message" for p in item.get("content", []) if p.get("type") == "output_text"]
            if not chunks:
                raise ValueError("Model refused or returned no text")
            value = json.loads("".join(chunks))
        return ModelResult(value, {
            "provider": "llama.cpp" if self.provider == "local" else "openai",
            "model": data.get("model", self.model), "response_id": data.get("id"),
            "usage": data.get("usage", {}), "purpose": purpose,
            "duration_ms": round((time.monotonic() - started) * 1000),
        })

    def generate(self, message, system):
        return self.request(system, message, ANSWER_SCHEMA, "answer")

def configured_model():
    provider = os.environ.get("LLM_PROVIDER", "openai")
    if provider == "local":
        return LanguageModel("local", os.environ.get("LOCAL_LLM_MODEL", "qwen3.5-2b"), base=os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8089"))
    if provider == "rules":
        return None
    if provider != "openai":
        raise ValueError("Unknown LLM_PROVIDER")
    key, model = os.environ.get("OPENAI_API_KEY"), os.environ.get("OPENAI_MODEL")
    return LanguageModel("openai", model, key=key) if key and model else None
