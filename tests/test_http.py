from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
import unittest
from server import Handler


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.worker = Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    def test_chat_and_policy(self):
        request = Request(self.base + "/api/chat", data=json.dumps({"message": "доставка заказа 1842"}).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            result = json.load(response)
            self.assertIn("нет доступа к базе", result["answer"])
            self.assertEqual(result["sources"], ["delivery"])
        with urlopen(self.base + "/api/policy") as response:
            self.assertEqual(len(json.load(response)["knowledge_base"]["rules"]), 6)

    def test_files_outside_allowlist_are_not_served(self):
        for path in ("/.env", "/assistant.py", "/../.env", "/.git/config"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as result:
                urlopen(self.base + path)
            self.assertEqual(result.exception.code, 404)

    def test_bad_input_and_cross_origin(self):
        for body, origin, code in ((b"[]", None, 400), (b"broken", None, 400), (b'{"message":null}', None, 400), (b'{"message":"hi"}', "https://other.example", 403)):
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            with self.subTest(code=code), self.assertRaises(HTTPError) as result:
                urlopen(Request(self.base + "/api/chat", data=body, headers=headers))
            self.assertEqual(result.exception.code, code)


if __name__ == "__main__":
    unittest.main()

