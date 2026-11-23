# -*- coding: utf-8 -*-
"""v3 結構改版的安全網（寫入面）：開新書、補骨架、spawn 建書產生的檔案清單與內容要跟快照一樣。

- 快照檔：tests/snapshots/skeleton_snapshot.json
- 內容只記 sha1（範本全文已經在 repo 裡，不必再存一份）。
- 重產：UPDATE_SNAPSHOT=1 python -m pytest tests/test_skeleton_snapshot.py
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import lang as lang_mod
from studio import native_files, project, spawn

SNAP = os.path.join(ROOT, "tests", "snapshots", "skeleton_snapshot.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"
PLUGIN = os.path.join(ROOT, "plugin")


def _tree(d):
    out = {}
    for base, dirs, files in os.walk(d):
        dirs.sort()
        rel_base = os.path.relpath(base, d).replace("\\", "/")
        if rel_base == ".":
            rel_base = ""
        for f in sorted(files):
            rel = (rel_base + "/" if rel_base else "") + f
            with open(os.path.join(base, f), "rb") as fh:
                data = fh.read().replace(b"\r\n", b"\n")
            if rel == "book.json":     # 建立日期每天不同：記內容（日期換成固定字）
                meta = json.loads(data.decode("utf-8"))
                meta["created"] = "<date>" if meta.get("created") else meta.get("created")
                out[rel] = meta
                continue
            out[rel] = hashlib.sha1(data).hexdigest()[:12]
        if not files and not dirs:
            out[rel_base + "/"] = "<empty dir>"
    return out


class SkeletonSnapshotTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self):
        got = {}
        for lang in ("zh-TW", "en", "ja"):
            d = project.create_book(self.lib, "skeleton-" + lang)
            lang_mod.set_book_lang(d, lang)
            created = native_files.ensure_skeleton(d, PLUGIN)
            again = native_files.ensure_skeleton(d, PLUGIN)       # 第二次不該再建任何東西
            got["ensure_skeleton/" + lang] = {
                "created": sorted(created),
                "second_run": sorted(again),
                "tree": _tree(d),
                "blank_files": sorted(native_files.blank_files(d)),
            }
        target = os.path.join(self.lib, "spawned")
        res = spawn.create(target, "示範新書", cards=2)
        got["spawn.create"] = {
            "result": {k: sorted(v) if isinstance(v, list) else v for k, v in res.items()},
            "tree": _tree(target),
        }
        return json.loads(json.dumps(got, ensure_ascii=False, default=str).replace(self.lib, "<LIB>"))

    def test_skeleton_matches_snapshot(self):
        got = self.collect()
        if UPDATE or not os.path.exists(SNAP):
            os.makedirs(os.path.dirname(SNAP), exist_ok=True)
            with open(SNAP, "w", encoding="utf-8", newline="\n") as f:
                json.dump(got, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.write("\n")
            if not UPDATE:
                self.skipTest("第一次執行：已產生快照，請確認後提交")
            return
        with open(SNAP, encoding="utf-8") as f:
            want = json.load(f)
        for k in sorted(set(want) | set(got)):
            with self.subTest(part=k):
                self.assertEqual(want.get(k), got.get(k))


if __name__ == "__main__":
    unittest.main()
