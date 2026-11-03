from io import BytesIO
from unittest.mock import patch
import json
import unittest
from llm import configured_router


class LlmAdapterTests(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_model_is_not_silently_enabled(self):
        self.assertIsNone(configured_router())

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key-not-a-secret", "OPENAI_MODEL": "test-model"}, clear=True)
    def test_protocol_and_separate_system_message(self):
        payload = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"topics":["delivery"]}'}]}]}
        with patch("llm.urlopen", return_value=BytesIO(json.dumps(payload).encode())) as mocked:
            result = configured_router()("Доставка?", "system instructions")
            self.assertEqual(result, {"topics": ["delivery"]})
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


if __name__ == "__main__":
    unittest.main()

