from io import BytesIO
from unittest.mock import patch
import json
import unittest
from llm import LanguageModel, configured_model
from helpers import draft


class LlmAdapterTests(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_model_is_not_silently_enabled(self):
        self.assertIsNone(configured_model())

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-not-a-secret", "OPENAI_MODEL": "test-model"}, clear=True)
    def test_openai_generation_protocol(self):
        value = draft("X1 в наличии.", ["product"])
        payload = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(value)}]}]}
        with patch("llm.urlopen", return_value=BytesIO(json.dumps(payload).encode())) as mocked:
            result = configured_model().generate("Наличие?", "system instructions")
        self.assertEqual(result.value, value)
        sent = json.loads(mocked.call_args.args[0].data)
        self.assertFalse(sent["store"])
        self.assertEqual(sent["input"][0]["role"], "system")
        self.assertEqual(sent["text"]["format"]["schema"]["required"], ["answer", "source_ids", "needs_human"])

    @patch.dict("os.environ", {"LLM_PROVIDER": "local"}, clear=True)
    def test_local_generation_protocol(self):
        value = draft("Нет данных о заказе.", needs_human=True)
        data = {"id": "test-response", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}], "usage": {"total_tokens": 60}}
        with patch("llm.urlopen", return_value=BytesIO(json.dumps(data).encode())) as mocked:
            result = configured_model().generate("Заказ?", "rules")
        self.assertEqual(result.value, value)
        self.assertEqual(result.trace["purpose"], "answer")
        sent = json.loads(mocked.call_args.args[0].data)
        self.assertEqual(sent["response_format"]["json_schema"]["name"], "answer")

    def test_local_provider_rejects_external_host_and_incomplete_output(self):
        with self.assertRaises(ValueError):
            LanguageModel("local", "test", base="https://other.example")
        data = {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
        with patch("llm.urlopen", return_value=BytesIO(json.dumps(data).encode())), self.assertRaises(ValueError):
            LanguageModel("local", "test", base="http://127.0.0.1:8089").generate("hi", "system")

    def test_local_response_must_come_from_configured_model(self):
        data = {"model": "other-model"}
        with patch("llm.urlopen", return_value=BytesIO(json.dumps(data).encode())), self.assertRaises(ValueError):
            LanguageModel("local", "test", base="http://127.0.0.1:8089").generate("hi", "system")
