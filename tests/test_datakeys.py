"""P4d：風格指紋、結構 DNA、衍生新書骨架的 JSON 改英文鍵。

舊檔（中文鍵）與模型偶爾回的中文鍵都讀得懂；寫出一律英文鍵；
spawn／直接開書時語言只記在 book.json；移轉工具把舊檔換成英文鍵。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from studio import bookmeta, datakeys, fingerprint, lang as lang_mod, layout, migrate, providers, sdna, spawn, spinoff  # noqa: E402

DEMO_EN = os.path.join(ROOT, "demo", "en_TheLanternRoad")
CJK = lambda obj: datakeys.has_cjk_key(obj)   # noqa: E731

OLD_FP = {"版本": 1, "語言": "en", "章節": {"章數": 3, "總字數": 9000, "平均章長": 3000, "中位章長": 3000,
                                         "最短章長": 2800, "最長章長": 3200, "章長變異": 0.05},
          "文字指標": {"對白比例": 0.3, "平均句長": 14, "單句成段": 0.2}, "指標來源": "作者正文",
          "代表句": ["某 went home."], "說明": "x"}
OLD_DNA = {"版本": 1, "語言": "en", "視角": {"人稱": "第三人稱", "依據": "y"},
           "章節": {"章數": 3, "平均": 3000, "最短": 2800, "最長": 3200, "變異": 0.05, "最長/最短": 1.1},
           "對白": {"比例": 0.3, "章間變異": 0.1}, "段落": {"平均段長": 40, "單句成段": 0.2},
           "章長曲線": [1.0, 0.9], "排除": ["人名", "地名", "專有名詞", "事件序列"], "說明": "z"}
OLD_SKEL = {"書名建議": "霧港", "一句話前提": "領航員想找回航線", "賣點": ["霧"],
            "主角": [{"名字": "沈渡", "定位": "主角", "動機": "找航線", "弱點": "怕水"}],
            "世界觀要點": ["港口有霧"], "語感說明": "冷",
            "卷綱": [{"卷": 1, "名稱": "起霧", "章數": 20, "主線": "找船", "卷末狀態": "上船"}],
            "骨架來源": "src", "護欄": {"撞到名字": [], "禁用名單數": 3}, "語言": "en"}


class DataKeysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_build_writes_english_keys(self):
        fp = fingerprint.build(DEMO_EN)
        dna = sdna.build(DEMO_EN, fp)
        self.assertFalse(CJK(fp), fp.keys())
        self.assertFalse(CJK(dna), dna.keys())
        self.assertIn("avg_sentence_length", fp["metrics"])
        self.assertEqual(["names", "places", "proper_nouns", "event_order"], dna["excluded"])

    def test_old_files_read_as_english(self):
        fp = datakeys.to_en(OLD_FP, datakeys.FINGERPRINT)
        dna = datakeys.to_en(OLD_DNA, datakeys.DNA)
        self.assertEqual(3000, fp["chapters"]["mean"])
        self.assertEqual({"dialogue_ratio": 0.3, "avg_sentence_length": 14, "single_sentence_paragraphs": 0.2}, fp["metrics"])
        self.assertEqual({"avg_paragraph_length": 40, "single_sentence_paragraphs": 0.2}, dna["paragraphs"])
        self.assertEqual(1.1, dna["chapters"]["max_min_ratio"])
        self.assertEqual(datakeys.to_en(fp, datakeys.FINGERPRINT), fp, "已是英文鍵的原樣")
        # show() 舊檔、新檔印出來一樣
        self.assertEqual(fingerprint.show(OLD_FP), fingerprint.show(fp))
        self.assertEqual(sdna.show(OLD_DNA), sdna.show(dna))
        self.assertEqual(spinoff.show(OLD_SKEL), spinoff.show(datakeys.to_en(OLD_SKEL, datakeys.SKELETON)))
        # spawn 收舊的 dict 也寫出同樣的文風檔
        self.assertEqual(spawn.style_md("t", OLD_FP, OLD_DNA), spawn.style_md("t", fp, dna))
        self.assertIn("| 平均句長 | 14 |", spawn.style_md("t", fp, dna), "文風檔的指標表照舊用中文名稱")

    def test_skeleton_chapter_count_vs_count(self):
        sk = datakeys.to_en(OLD_SKEL, datakeys.SKELETON)
        self.assertEqual(20, sk["volumes"][0]["chapter_count"], "骨架卷綱的章數 = chapter_count")
        self.assertEqual(3, datakeys.to_en(OLD_FP, datakeys.FINGERPRINT)["chapters"]["count"], "指紋的章數 = count")

    def test_model_chinese_keys_accepted(self):
        replies = iter([json.dumps({k: OLD_SKEL[k] for k in ("書名建議", "一句話前提", "賣點", "主角", "世界觀要點")},
                                   ensure_ascii=False),
                        json.dumps({"卷綱": OLD_SKEL["卷綱"]}, ensure_ascii=False)])
        with mock.patch.object(providers, "chat", lambda *a, **k: (next(replies), {})):
            data = spinoff.generate({"id": "fake"}, DEMO_EN, "", lang="en")
        self.assertFalse(CJK(data))
        self.assertEqual("領航員想找回航線", data["premise"])
        self.assertEqual(20, data["volumes"][0]["chapter_count"])
        self.assertEqual("en", data["lang"])

    def test_spawn_and_apply_new_put_lang_in_book_json(self):
        fp = fingerprint.build(DEMO_EN)
        dna = sdna.build(DEMO_EN, fp)
        t = os.path.join(self.tmp, "new")
        spawn.create(t, "New", fp=fp, dna=dna, cards=1)
        self.assertEqual("en", bookmeta.read(t)["lang"])
        self.assertEqual("en", lang_mod.book_lang(t))
        self.assertNotIn("\nlang:", open(layout.path(t, layout.STORY_CORE), encoding="utf-8").read())
        with open(layout.path(t, layout.STYLE_FINGERPRINT), encoding="utf-8") as f:
            self.assertFalse(CJK(json.load(f)))
        nb = os.path.join(self.tmp, "nb")
        os.makedirs(nb)
        spinoff.apply_new(nb, OLD_SKEL, title="nb", lang="ja")   # 舊骨架（中文鍵）也能直接開書
        self.assertEqual("ja", bookmeta.read(nb)["lang"])
        self.assertNotIn("\nlang:", open(layout.path(nb, layout.STORY_CORE), encoding="utf-8").read())

    def test_migrate_step(self):
        b = os.path.join(self.tmp, "book")
        shutil.copytree(DEMO_EN, b)
        for rel, data in ((layout.STYLE_FINGERPRINT, OLD_FP), (layout.STRUCTURE_DNA, OLD_DNA),
                          (layout.SPINOFF_DRAFTS + "/" + layout.SPINOFF_SKELETON_JSON, OLD_SKEL)):
            p = layout.path(b, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        self.assertFalse(migrate.needs_migration(b), "讀的時候兩種鍵都認：不擋開書")
        r = migrate.migrate(b)
        self.assertEqual("done", r["status"], r.get("message"))
        self.assertEqual(["datakeys"], [s["key"] for s in r["steps"]])
        with open(layout.path(b, layout.STRUCTURE_DNA), encoding="utf-8") as f:
            self.assertEqual(datakeys.to_en(OLD_DNA, datakeys.DNA), json.load(f))
        self.assertEqual("skipped", migrate.migrate(b)["status"])


if __name__ == "__main__":
    unittest.main()
