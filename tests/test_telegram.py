from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError
import json
import unittest
from assistant import Reply
from telegram_bot import TelegramAPI, TelegramError, handle_update, startup
from llm import ModelResult
from token_store import validate_token


def private_message(text=None, **fields):
    message = {"chat": {"id": 123, "type": "private"}, "from": {"is_bot": False}, **fields}
    if text is not None:
        message["text"] = text
    return {"update_id": 7, "message": message}


class TelegramTests(unittest.TestCase):
    def test_start_shows_three_examples_without_calling_llm(self):
        api, router = Mock(), Mock()
        handle_update(private_message("/start"), api, router)
        router.assert_not_called()
        method, params = api.call.call_args.args
        self.assertEqual(method, "sendMessage")
        self.assertEqual(len(params["reply_markup"]["keyboard"]), 3)
        self.assertIn("Здравствуйте", params["text"])

    def test_transport_uses_same_assistant_and_sends_its_answer(self):
        api, router = Mock(), Mock()
        reply = Reply("Ответ по регламенту", ["return"], "llm+policy", False, {"model": "test"})
        with patch("telegram_bot.answer_question", return_value=reply) as answer:
            handle_update(private_message("Вернуть наушники"), api, router)
        answer.assert_called_once_with("Вернуть наушники", router)
        self.assertEqual(api.call.call_args.args[1]["text"], "Ответ по регламенту")

    def test_unavailable_model_is_not_presented_as_ai_response(self):
        api = Mock()
        with patch("telegram_bot.answer_question", return_value=Reply("fallback", [], "model-unavailable", True)):
            response = handle_update(private_message("Доставка?"), api, Mock())
        self.assertIn("не получается обратиться к нейросети", response)
        self.assertNotIn("fallback", response)

    def test_safety_rejection_is_delivered_as_safety_message(self):
        with patch("telegram_bot.answer_question", return_value=Reply("Ответ не подтверждён, уточните у сотрудника.", [], "safety-fallback", True, {"model": "test"})):
            result = handle_update(private_message("Доставка?"), Mock(), Mock())
        self.assertEqual(result, "Ответ не подтверждён, уточните у сотрудника.")

    def test_group_and_bot_messages_are_ignored(self):
        for update in (private_message("Hello", chat={"id": 42, "type": "group"}), private_message("Hello", **{"from": {"is_bot": True}}), {"edited_message": {}}):
            with self.subTest(update=update):
                api = Mock()
                handle_update(update, api, Mock())
                api.call.assert_not_called()

    def test_non_text_and_invalid_size_have_clear_response(self):
        for update in (private_message(photo=[]), private_message("x" * 2001), private_message("   ")):
            with self.subTest(update_id=update["update_id"]):
                response = handle_update(update, Mock(), None)
                self.assertTrue("текст" in response)

    def test_token_never_appears_in_transport_errors(self):
        token = "123456:" + "A" * 35
        error = HTTPError("https://api.telegram.org/bot" + token + "/getMe", 401, "invalid", {}, None)
        with patch("telegram_bot.urlopen", side_effect=error), self.assertRaises(TelegramError) as caught:
            TelegramAPI(token).call("getMe")
        self.assertEqual(caught.exception.code, 401)
        self.assertNotIn(token, str(caught.exception))

    def test_bot_api_request_format_and_result(self):
        with patch("telegram_bot.urlopen", return_value=BytesIO(b'{"ok":true,"result":{"username":"test_bot"}}')) as mocked:
            result = TelegramAPI("123456:" + "A" * 35).call("getUpdates", {"timeout": 25})
        self.assertEqual(result["username"], "test_bot")
        self.assertEqual(json.loads(mocked.call_args.args[0].data), {"timeout": 25})

    def test_existing_webhook_is_not_removed(self):
        api = Mock()
        api.call.side_effect = [{"username": "existing_bot"}, {"url": "https://existing.example/webhook"}]
        with self.assertRaises(RuntimeError):
            startup(api, Mock())
        self.assertEqual([call.args[0] for call in api.call.call_args_list], ["getMe", "getWebhookInfo"])

    def test_token_validation(self):
        self.assertEqual(validate_token("123456:" + "A" * 35), "123456:" + "A" * 35)
        for value in ("", "not-token", None):
            with self.assertRaises(ValueError):
                validate_token(value)


if __name__ == "__main__":
    unittest.main()
