"""本機執行者（llama.cpp）不需要金鑰；遠端的照舊要。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from studio import providers  # noqa: E402


class NeedsKeyTest(unittest.TestCase):
    def test_local_and_remote(self):
        self.assertFalse(providers.needs_key({"base_url": "http://127.0.0.1:8080/v1"}))
        self.assertFalse(providers.needs_key({"base_url": "http://localhost:1234/v1"}))
        self.assertTrue(providers.needs_key({"base_url": "https://api.deepseek.com"}))
        llama = next(p for p in providers.DEFAULT_PROVIDERS if p["id"] == "llamacpp")
        self.assertFalse(providers.needs_key(llama))


if __name__ == "__main__":
    unittest.main()
