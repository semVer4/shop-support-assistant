from io import BytesIO
from unittest.mock import patch
import json
import unittest
from llm import configured_router, local_router


class LlmAdapterTests(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_model_is_not_silently_enabled(self):
        self.assertIsNone(configured_router())

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-not-a-secret", "OPENAI_MODEL": "test-model"}, clear=True)
    def test_protocol_and_separate_system_message(self):
        payload = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"topics":["delivery"]}'}]}]}
        with patch("llm.urlopen", return_value=BytesIO(json.dumps(payload).encode())) as mocked:
            result = configured_router()("Доставка?", "system instructions")
            self.assertEqual(result.plan, {"topics": ["delivery"]})
            self.assertEqual(result.trace["provider"], "openai")
            request = mocked.call_args.args[0]
            sent = json.loads(request.data)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
            self.assertFalse(sent["store"])
            self.assertEqual(sent["input"][0]["role"], "system")
            self.assertEqual(sent["input"][1]["role"], "user")
            self.assertTrue(sent["text"]["format"]["strict"])

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-not-a-secret", "OPENAI_MODEL": "test-model"}, clear=True)
    def test_incomplete_output_is_not_used(self):
        with patch("llm.urlopen", return_value=BytesIO(b'{"status":"incomplete","output":[]}')):
            with self.assertRaises(ValueError):
                configured_router()("hi", "system")

    @patch.dict("os.environ", {"LLM_PROVIDER": "local"}, clear=True)
    def test_real_local_api_adapter(self):
        data = {"id": "local-test-response", "model": "qwen2.5-1.5b-instruct", "choices": [{"finish_reason": "stop", "message": {"content": '{"topics":["return"]}'}}], "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}}
        with patch("llm.urlopen", return_value=BytesIO(json.dumps(data).encode())) as mocked:
            result = configured_router()("вернуть товар", "rules")
            self.assertEqual(result.plan, {"topics": ["return"]})
            self.assertEqual(result.trace["response_id"], "local-test-response")
            self.assertEqual(result.trace["usage"]["total_tokens"], 60)
            request = mocked.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:8089/v1/chat/completions")
            self.assertEqual(json.loads(request.data)["response_format"]["type"], "json_schema")

    @patch.dict("os.environ", {"LOCAL_LLM_URL": "https://other.example"}, clear=True)
    def test_local_provider_cannot_send_to_external_host(self):
        with self.assertRaises(ValueError):
            local_router()


if __name__ == "__main__":
    unittest.main()

