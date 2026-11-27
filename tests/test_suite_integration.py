# -*- coding: utf-8 -*-
"""t2x-suite 整合測試：suite URL 注入、單獨啟動優雅降級與 T2X_* 環境變數 fallback。"""
import json
import os
import tempfile
import unittest
from unittest import mock

import app as ns_app


class TestSuiteIntegration(unittest.TestCase):
    def test_get_config_suite_urls_and_standalone_fallback(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("T2VN_URL", None)
            os.environ.pop("SUITE_URL", None)
            res = ns_app.get_config()
            self.assertEqual(res["suite"], {"t2vn_url": "", "suite_url": ""})

        with mock.patch.dict(
            os.environ,
            {"T2VN_URL": "http://127.0.0.1:7866/", "SUITE_URL": "http://127.0.0.1:8700/"},
            clear=False,
        ):
            res = ns_app.get_config()
            self.assertEqual(
                res["suite"],
                {"t2vn_url": "http://127.0.0.1:7866", "suite_url": "http://127.0.0.1:8700"},
            )

    def test_load_config_t2x_library_fallback_does_not_override(self):
        with tempfile.TemporaryDirectory() as td:
            blank_cfg = os.path.join(td, "blank.json")
            with open(blank_cfg, "w", encoding="utf-8") as f:
                json.dump({"library": ""}, f)

            set_cfg = os.path.join(td, "set.json")
            with open(set_cfg, "w", encoding="utf-8") as f:
                json.dump({"library": "/my/library"}, f)

            with mock.patch.dict(os.environ, {"T2X_LIBRARY_DIR": "/env/library"}, clear=False):
                with mock.patch.object(ns_app, "CONFIG_PATH", blank_cfg):
                    loaded = ns_app.load_config()
                    self.assertEqual(loaded["library"], "/env/library")

                with mock.patch.object(ns_app, "CONFIG_PATH", set_cfg):
                    loaded = ns_app.load_config()
                    self.assertEqual(loaded["library"], "/my/library")

    def test_illust_cfg_t2x_fallbacks_do_not_override(self):
        with mock.patch.dict(
            os.environ,
            {"T2X_COMFYUI_URL": "http://127.0.0.1:9199", "T2X_TAGCOMPLETE_CSV": "/env/tags.csv"},
            clear=False,
        ):
            with mock.patch.dict(ns_app.CONFIG, {"illust": {}}, clear=False):
                ic = ns_app.illust_cfg()
                self.assertEqual(ic["comfy_url"], "http://127.0.0.1:9199")
                self.assertEqual(ic["tag_csv"], "/env/tags.csv")

            with mock.patch.dict(
                ns_app.CONFIG,
                {"illust": {"comfy_url": "http://127.0.0.1:8188", "tag_csv": "/my/tags.csv"}},
                clear=False,
            ):
                ic = ns_app.illust_cfg()
                self.assertEqual(ic["comfy_url"], "http://127.0.0.1:8188")
                self.assertEqual(ic["tag_csv"], "/my/tags.csv")


if __name__ == "__main__":
    unittest.main()
