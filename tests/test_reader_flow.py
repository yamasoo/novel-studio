# -*- coding: utf-8 -*-
"""讀者認知兩條模型流程的回歸測試（v3 P2：jsonkeys 反轉第二批）。

用假模型回傳固定 JSON，跑：
- native.act_reader_init（時間線 → 讀者認知草稿）
- native.act_reader_reconcile（回收比對）
- app 的 Claude Code 版本（claude_reader_job、claude_reader_recon_job 的收尾）
情境：繁中書中文鍵；英文書英文鍵與英文選項值（含大小寫不一的鍵、認不得的值）；英文書語言重試。
預期結果（reader_flow_golden.json）用改之前的程式產生，必須逐字相同。

重產預期結果：UPDATE_SNAPSHOT=1 python -m pytest tests/test_reader_flow.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import layout, native, project, prompts  # noqa: E402
from tests.test_writeback_flow import FakeCtx  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "snapshots", "reader_flow_golden.json")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"

ZH_INIT = {"items": [
    {"類型": "懸念", "內容": "誰拿走了帳本的缺頁", "作者真相": "周叔", "種下章": "第001章", "回收章": "", "相關角色": "林晚", "來源": "E001"},
    {"類型": "已知", "內容": "林晚被沈家退婚", "種下章": "第001章", "相關角色": "林晚、沈既白"},
    {"類型": "誤認", "內容": "讀者以為大伯母是主謀", "作者真相": "其實是沈仲廉", "種下章": "第002章"},
    {"類型": "懸念", "內容": "誰拿走了帳本的缺頁", "種下章": "第002章"},
    {"類型": "懸念", "內容": "玉珮另一半在哪", "種下章": "第002章", "來源": "E003"}]}
ZH_RECON = {"changes": [
    {"編號": "R001", "動作": "回收", "回收章": "第002章", "理由": "第2章揭曉"},
    {"編號": "R002", "動作": "部分", "內容": "讀者知道大伯母只是幫兇", "理由": "部分揭曉"},
    {"編號": "R003", "動作": "合併", "合併到": "R001", "理由": "重複"},
    {"編號": "R009", "動作": "回收", "回收章": "第002章"}]}

EN_INIT = {"Items": None, "items": [
    {"type": "question", "content": "Who moved the milestone?", "author_truth": "the toll-keeper", "planted_chapter": "Chapter 1",
     "resolved_in": "", "related_characters": "Mara", "source": "E001"},
    {"Type": "known", "Content": "Mara carries a letter", "planted_chapter": "Chapter 1"},
    {"type": "false belief", "content": "Readers think Hob is lying", "planted_chapter": "Chapter 2"},
    {"type": "riddle", "content": "What is in the letter?", "planted_chapter": "Chapter 2", "source": "E004"}]}
EN_RECON = {"changes": [
    {"id": "R001", "action": "pay off", "resolved_in": "Chapter 2", "grounds": "revealed in ch. 2"},
    {"ID": "R002", "Action": "partial", "content": "Readers learn the letter is sealed", "grounds": "partly"},
    {"id": "R003", "action": "merged", "merge_into": "R001", "grounds": "duplicate"},
    {"id": "R004", "action": "shrug", "grounds": "unknown action"}]}
EN_BAD = {"items": [{"type": "question", "content": "誰移動了里程碑？這是一段中文的懸念內容", "planted_chapter": "Chapter 1"},
                    {"type": "known", "content": "瑪拉帶著一封信上路，這也是中文", "planted_chapter": "Chapter 1"}]}
EN_GOOD = {"items": [{"type": "question", "content": "Who moved the milestone?", "planted_chapter": "Chapter 1"}]}


def _book(tmp, name):
    book = os.path.join(tmp, name)
    if os.path.isdir(book):
        shutil.rmtree(book)
    shutil.copytree(os.path.join(ROOT, "demo", name), book)
    return book


def _read(book):
    out = {}
    for rel in (layout.READER_KNOWLEDGE, layout.READER_KNOWLEDGE_DRAFT):
        p = layout.path(book, rel)
        if os.path.isfile(p):
            out[rel] = project.read_text(p)
    return out


def _act(book, fn, outputs):
    c = FakeCtx(book, [json.dumps(o, ensure_ascii=False) for o in outputs])
    c.job.result = None
    prompts.set_lang(c.lang)
    fn(c, {})
    return {"result": c.job.result, "logs": c.job.logs, "files": _read(book)}


class _J:
    def __init__(self, result):
        self.result, self.events = result, []

    def emit(self, kind, **kw):
        self.events.append(kw.get("text", ""))


def _claude(book, maker, data):
    import app
    job = maker("b", book, {"id": "cc", "type": "claude_code"}, {})
    j = _J(json.dumps(data, ensure_ascii=False))
    prompts.set_lang(native.lang_mod.book_lang(book))
    job.after(j)
    return {"result": j.result, "files": _read(book)}


def scenario():
    import app
    out = {}
    tmp = tempfile.mkdtemp()
    try:
        book = _book(tmp, "退婚之後")
        out["zh_init"] = _act(book, native.act_reader_init, [ZH_INIT])
        out["zh_recon"] = _act(book, native.act_reader_reconcile, [ZH_RECON])

        book = _book(tmp, "en_TheLanternRoad")
        out["en_init"] = _act(book, native.act_reader_init, [EN_INIT])
        out["en_recon"] = _act(book, native.act_reader_reconcile, [EN_RECON])

        book = _book(tmp, "en_TheLanternRoad")
        out["en_retry"] = _act(book, native.act_reader_init, [EN_BAD, EN_GOOD])

        book = _book(tmp, "退婚之後")
        out["cc_zh_init"] = _claude(book, app.claude_reader_job, ZH_INIT)
        out["cc_zh_recon"] = _claude(book, app.claude_reader_recon_job, ZH_RECON)
        book = _book(tmp, "en_TheLanternRoad")
        out["cc_en_init"] = _claude(book, app.claude_reader_job, EN_INIT)
        out["cc_en_recon"] = _claude(book, app.claude_reader_recon_job, EN_RECON)
    finally:
        shutil.rmtree(tmp)
        prompts.set_lang("zh-TW")
    return json.loads(json.dumps(out, ensure_ascii=False, default=str).replace(tmp, "<tmp>"))


class ReaderFlowTest(unittest.TestCase):
    maxDiff = None

    def test_matches_golden(self):
        got = scenario()
        if UPDATE or not os.path.exists(GOLDEN):
            with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
                json.dump(got, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.write("\n")
            if not UPDATE:
                self.skipTest("第一次執行：已產生預期結果，請確認後提交")
            return
        with open(GOLDEN, encoding="utf-8") as f:
            want = json.load(f)
        for k in sorted(set(want) | set(got)):
            for kk in sorted(set(want.get(k) or {}) | set(got.get(k) or {})):
                with self.subTest(part=k, item=kk):
                    self.assertEqual((want.get(k) or {}).get(kk), (got.get(k) or {}).get(kk))

    def test_scenario_reaches_the_paths(self):
        got = scenario()
        for k in ("zh_init", "cc_zh_init"):
            self.assertIn("共 4 條：懸念 2、誤認 1、已知 1", got[k]["result"], k)
            self.assertIn("（E001）", got[k]["files"][layout.READER_KNOWLEDGE_DRAFT], "來源要附在內容後面")
        for k in ("zh_recon", "cc_zh_recon"):
            self.assertIn("回收 1 條、部分揭曉 1 條、合併 1 條", got[k]["result"], k)
            self.assertIn("1 條判斷不合格式或不合理", got[k]["result"], k)
        self.assertIn("| question |", got["en_init"]["files"][layout.READER_KNOWLEDGE_DRAFT], "英文書：類型寫英文的標準寫法（v3 第六批）")
        self.assertTrue(any("riddle" in x for x in got["en_init"]["logs"]), "認不得的選項值要提醒")
        for k in ("en_recon", "cc_en_recon"):
            self.assertIn("回收 1 條、部分揭曉 1 條、合併 1 條", got[k]["result"], k)
        self.assertTrue(any("語言不對" in x for x in got["en_retry"]["logs"]))
        self.assertIn("共 1 條", got["en_retry"]["result"])


if __name__ == "__main__":
    unittest.main()
