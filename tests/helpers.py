from copy import deepcopy
from llm import ModelResult


class FakeModel:
    def __init__(self, answer):
        self.answer = answer
        self.generation_calls = []

    def generate(self, message, system):
        self.generation_calls.append((message, system))
        return ModelResult(deepcopy(self.answer), {"provider": "test", "model": "test-model", "response_id": "generated-test-id", "usage": {"total_tokens": 60}})

def draft(answer, source_ids=None, needs_human=False):
    return {"answer": answer, "source_ids": source_ids or [], "needs_human": needs_human}
