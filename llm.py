"""Optional OpenAI Responses API classifier. It never supplies customer-facing facts."""
import json
import os
from urllib.request import Request, urlopen

SCHEMA = {
    "type": "object",
    "properties": {"topics": {"type": "array", "items": {"type": "string", "enum": ["product", "delivery", "return", "defect", "discount", "greeting", "unknown"]}, "minItems": 1, "maxItems": 7}},
    "required": ["topics"],
    "additionalProperties": False,
}


def configured_router():
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
        with urlopen(request, timeout=15) as response:
            data = json.load(response)
        if data.get("status") != "completed":
            raise ValueError("Incomplete model response")
        chunks = [part["text"] for item in data.get("output", []) if item.get("type") == "message" for part in item.get("content", []) if part.get("type") == "output_text"]
        if not chunks:
            raise ValueError("No structured classifier output")
        return json.loads("".join(chunks))
    return classify

