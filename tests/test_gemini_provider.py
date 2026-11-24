# -*- coding: utf-8 -*-
"""Google Gemini API 供應商、.env 金鑰讀取與 Safety Settings 單元測試。"""
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from studio import providers


class _FakeResp:
    def __init__(self, raw_bytes, content_type="text/event-stream"):
        self._buf = io.BytesIO(raw_bytes)
        self.headers = {"Content-Type": content_type}

    def __iter__(self):
        return iter(self._buf)

    def read(self):
        return self._buf.read()

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeOpener:
    def __init__(self, resp):
        self.resp = resp
        self.last_req = None

    def open(self, req, timeout=None):
        self.last_req = req
        return self.resp


class GeminiProviderTests(unittest.TestCase):
    def _gemini_prov(self):
        return next(p for p in providers.DEFAULT_PROVIDERS if p["id"] == "gemini")

    def test_dotenv_key_loading_and_status(self):
        prov = self._gemini_prov()
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, ".env"), "w", encoding="utf-8") as f:
                f.write('# 測試註解\nexport GEMINI_API_KEY="AIzaTestKey123456"\n')
            with mock.patch.object(providers, "_kr_get", return_value=""), \
                 mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_API_KEY", None)
                self.assertEqual(providers.api_key(tmp, prov), "AIzaTestKey123456")
                st = providers.key_status(tmp, prov)
                self.assertIn(".env (GEMINI_API_KEY)", st)
                self.assertIn("3456", st)
                # 系統環境變數優先於 .env
                os.environ["GEMINI_API_KEY"] = "EnvWins9999"
                try:
                    self.assertEqual(providers.api_key(tmp, prov), "EnvWins9999")
                finally:
                    os.environ.pop("GEMINI_API_KEY", None)

    def test_default_gemini_choices_and_resolve(self):
        chs = providers.choices(providers.DEFAULT_PROVIDERS)
        ids = [c["id"] for c in chs]
        self.assertIn("gemini", ids)
        self.assertIn("gemini/gemini-4-neon", ids)
        p_def = providers.resolve(providers.DEFAULT_PROVIDERS, "gemini")
        p_neon = providers.resolve(providers.DEFAULT_PROVIDERS, "gemini/gemini-4-neon")
        self.assertEqual(p_def["model"], "gemini-3.8-flash")
        self.assertEqual(p_def["type"], "gemini")
        self.assertTrue(p_def["safety_relax"])
        self.assertEqual(p_neon["model"], "gemini-4-neon")
        self.assertEqual(p_neon["key_id"], "gemini")

    def test_gemini_build_body_safety_thinking_json(self):
        prov = self._gemini_prov()
        msgs = [
            {"role": "system", "content": "你是小說編輯"},
            {"role": "user", "content": "寫一段對決場景"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "繼續"},
        ]
        body = providers._gemini_build_body(prov, msgs, json_mode=True, max_tokens=2048, stage="plan")
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "你是小說編輯")
        self.assertEqual([c["role"] for c in body["contents"]], ["user", "model", "user"])
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 2048)
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["generationConfig"]["thinkingConfig"], {"thinkingBudget": 4096, "includeThoughts": True})
        self.assertEqual(len(body["safetySettings"]), 5)
        self.assertTrue(all(s["threshold"] == "BLOCK_NONE" for s in body["safetySettings"]))

        body_struct = providers._gemini_build_body(prov, msgs, json_mode=True, stage="structured")
        self.assertEqual(body_struct["generationConfig"]["thinkingConfig"], {"thinkingBudget": 0})

    def test_gemini_stream_chat_and_list_models(self):
        prov = providers.resolve(providers.DEFAULT_PROVIDERS, "gemini/gemini-4-neon")
        sse = (
            'data: {"candidates":[{"content":{"parts":[{"text":"先想情節","thought":true}]}}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":"第一段。"}]}}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":"第二段。"}]},"finishReason":"STOP"}],'
            '"usageMetadata":{"promptTokenCount":120,"candidatesTokenCount":45,"totalTokenCount":165}}\n\n'
        ).encode("utf-8")
        opener = _FakeOpener(_FakeResp(sse, "text/event-stream"))
        thoughts, deltas = [], []
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, ".env"), "w", encoding="utf-8") as f:
                f.write("GEMINI_API_KEY=TestSecretKey999\n")
            with mock.patch.object(providers, "_kr_get", return_value=""), \
                 mock.patch.object(providers, "_opener", return_value=opener):
                os.environ.pop("GEMINI_API_KEY", None)
                text, usage = providers.chat(
                    tmp, prov, [{"role": "user", "content": "hi"}],
                    on_delta=deltas.append, on_thinking=thoughts.append, stage="plan"
                )
        self.assertEqual(text, "第一段。第二段。")
        self.assertEqual(thoughts, ["先想情節"])
        self.assertEqual(deltas, ["第一段。", "第二段。"])
        self.assertEqual(usage["prompt_tokens"], 120)
        self.assertEqual(usage["completion_tokens"], 45)
        self.assertEqual(usage["finish_reason"], "stop")
        self.assertIn("models/gemini-4-neon:streamGenerateContent?alt=sse", opener.last_req.full_url)
        self.assertEqual(opener.last_req.get_header("X-goog-api-key"), "TestSecretKey999")

        # list_models 過濾 generateContent 並移除 models/ 前綴
        m_json = json.dumps({
            "models": [
                {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-4-neon", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
            ]
        }).encode("utf-8")
        m_opener = _FakeOpener(_FakeResp(m_json, "application/json"))
        with mock.patch.object(providers, "_opener", return_value=m_opener):
            models = providers.list_models("", prov)
        self.assertEqual(models, ["gemini-3.8-flash", "gemini-4-neon"])

    def test_gemini_safety_block_error(self):
        prov = self._gemini_prov()
        sse = 'data: {"candidates":[{"finishReason":"SAFETY"}]}\n\n'.encode("utf-8")
        opener = _FakeOpener(_FakeResp(sse, "text/event-stream"))
        with mock.patch.object(providers, "_opener", return_value=opener):
            with self.assertRaises(providers.ProviderError) as ctx:
                providers.chat("", prov, [{"role": "user", "content": "hi"}])
        self.assertIn("SAFETY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
