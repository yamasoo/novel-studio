# -*- coding: utf-8 -*-
"""從正文反推設定的完整流程回歸測試（v3 P2：jsonkeys 反轉最後一批）。

用假模型跑 native.act_reverse：逐章抽取（分批）→ 本機累積 → 整理角色、背景、劇情段落、故事核心與大綱、狀態卡
→ 名詞整理 → 產生四組草稿。假模型看提示詞裡的 schema 判斷是哪一步，逐章抽取依提示詞裡的章號回應。
情境：
- 繁中書：中文鍵、中文選項值；一批的章號寫成文字（認不出來，照順序對應）
- 英文書：英文鍵、英文選項值、英文內容
- 中斷後續跑：第一次在逐章抽取第 2 批、第二次在整理角色之後停下，第三次跑完；
  .studio 裡的累積資料與步驟快取是前幾次寫的
- 舊版快取：用改之前的程式寫出的累積資料與步驟快取（fixtures/reverse_cache_v2），在目前的程式上續跑
預期結果（reverse_flow_golden.json）用改之前的程式產生，必須逐字相同。

重產預期結果：UPDATE_SNAPSHOT=1 python -m pytest tests/test_reverse_flow.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from studio import jsonkeys, layout, native, project, prompts, reverse  # noqa: E402
from tests.test_writeback_flow import FakeCtx  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "snapshots", "reverse_flow_golden.json")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "reverse_cache_v2")
UPDATE = os.environ.get("UPDATE_SNAPSHOT") == "1"

EN_VALUES = {"主要": "major", "次要": "minor", "路人": "extra", "主角": "protagonist", "配角": "supporting", "高": "high",
             "中": "medium", "埋": "plant", "推進": "advance", "回收": "pay off", "新": "new", "懸念": "question",
             "誤認": "misbelief", "組織": "organization", "物品": "item", "保留": "keep", "經濟與物資": "economy"}


def to_en(d):
    """中文鍵的答案換成英文書模型會寫的樣子：英文鍵（名詞、關係依型別選單複數）、英文選項值。"""
    plural = {"名詞": ("terms", "term"), "關係": ("relationships", "relationship")}
    rev = {}
    for en, zh in jsonkeys.KEYS.items():
        rev.setdefault(zh, en)
    if isinstance(d, list):
        return [to_en(x) for x in d]
    if not isinstance(d, dict):
        return EN_VALUES.get(d, d) if isinstance(d, str) else d
    out = {}
    for k, v in d.items():
        ek = (plural[k][0] if isinstance(v, list) else plural[k][1]) if k in plural else rev.get(k, k)
        out[ek] = to_en(v)
    return out


def tx(en, zh, eng):
    return eng if en else zh


def extract(nos, en, wrong_no=False):
    chs = []
    for n in nos:
        fs = {1: [{"編號": "新", "動作": "埋", "內容": tx(en, "玉珮只剩半塊", "The jade is broken in half"), "重要度": "高"}],
              3: [{"編號": "F001", "動作": "推進"}],
              5: [{"編號": "F001", "動作": "回收"}, {"編號": "新", "動作": "埋", "內容": tx(en, "後院的暗格", "A hidden niche"), "重要度": "很重要"}]}
        rd = {1: [{"編號": "新", "動作": "新", "類型": "懸念", "內容": tx(en, "誰拿走了缺頁", "Who took the missing page")}],
              2: [{"編號": "新", "類型": "誤認", "內容": tx(en, "讀者以為大伯母是主謀", "Readers think the aunt did it")}],
              4: [{"編號": "R001", "動作": "回收", "作者真相": tx(en, "周叔拿走的", "Uncle Zhou took it")}]}
        people = [{"名稱": tx(en, "林晚", "Lin Wan"), "別名": [tx(en, "二小姐", "Second Miss")], "身分": tx(en, "林家二小姐", "second daughter"),
                   "本章": tx(en, "查帳第%d天" % n, "audits the books, day %d" % n), "重要": "主要"},
                  {"名稱": tx(en, "周叔", "Uncle Zhou"), "身分": tx(en, "老掌櫃", "old shopkeeper"), "本章": tx(en, "幫忙查帳", "helps with the audit"),
                   "重要": "次要"}]
        if n == 2:
            people.append({"名稱": tx(en, "路人甲", "A passerby"), "重要": "路人"})
            people.append({"名稱": tx(en, "晚", "W"), "重要": "路人"})      # 名字太短，略過
        chs.append({
            "章": ("第%d章" % n) if wrong_no else n,     # 章號寫成文字：認不出來，照順序對應
            "摘要": {"發生了什麼": tx(en, "第%d章林晚查帳。" % n, "Chapter %d: Lin Wan checks the books." % n),
                   "局面變化": tx(en, "疑點變多", "More doubts"), "新出現的人事物": tx(en, "無", "none"),
                   "結尾停在": tx(en, "第%d章停在門外的腳步聲" % n, "Chapter %d ends on footsteps outside" % n)},
            "章綱": {"主角想做什麼": tx(en, "查清帳本", "Clear the ledger"), "阻礙": tx(en, "缺頁", "A missing page"),
                   "局面變成": tx(en, "懷疑周叔", "She suspects Zhou"), "讀者為什麼往下看": tx(en, "誰拿走缺頁", "Who took it"),
                   "功能": tx(en, "推進", "advance the plot"), "情緒": tx(en, "緊張", "tense"),
                   "情節點": [tx(en, "翻帳", "Reads the ledger"), "", tx(en, "發現缺頁", "Finds the gap")],
                   "章末鉤子": tx(en, "腳步聲", "Footsteps")},
            "人物": people,
            "名詞": [{"名詞": tx(en, "天機閣", "Tianji Pavilion"), "類別": "組織", "小類": tx(en, "情報", "intelligence"),
                    "說明": tx(en, "江湖情報組織", "an intelligence guild")},
                   {"名詞": tx(en, "青雲劍", "Azure Sword"), "類別": "物品",
                    "說明": tx(en, "佩劍" + ("，劍身青色" if n > 3 else ""), "a sword" + (" with a blue blade" if n > 3 else ""))},
                   {"名詞": tx(en, "林晚", "Lin Wan"), "類別": "人物"}],      # 已是人物：不列名詞
            "事件": [{"故事時間": tx(en, "退婚後第%d天" % n, "Day %d" % n), "實際發生": tx(en, "第%d章的真相" % n, "the truth of chapter %d" % n),
                    "讀者知道": tx(en, "一部分", "part of it"), "相關角色": tx(en, "林晚", "Lin Wan")}, {"故事時間": "x"}],
            "伏筆": fs.get(n, []),
            "讀者": rd.get(n, []),
        })
    return {"chapters": chs}


def answers(en):
    chars = {"角色": [
        {"名稱": tx(en, "林晚", "Lin Wan"), "別名": [tx(en, "晚丫頭", "Wannie")], "定位": "主角", "一句話": tx(en, "被退婚的二小姐", "a jilted daughter"),
         "年齡身分": tx(en, "十七歲", "seventeen"), "外貌": tx(en, "瘦", "slim"), "想要": tx(en, "查清帳", "the truth"),
         "害怕": tx(en, "失去鋪子", "losing the shop"), "缺陷": tx(en, "倔強", "stubborn"), "底線": tx(en, "不賣鋪子", "never sell"),
         "秘密": "", "說話方式": tx(en, "直接", "blunt"), "關係": [tx(en, "沈既白：前未婚夫", "Shen: ex-fiance"), tx(en, "周叔：掌櫃", "Zhou: shopkeeper")],
         "角色弧線": tx(en, "從被動到主動", "from passive to active"),
         "目前狀態": {"身分": tx(en, "鋪主", "shop owner"), "位置": tx(en, "鋪子", "the shop"), "目標": tx(en, "查帳", "audit"),
                  "身體狀態": tx(en, "疲倦", "tired"), "情緒狀態": tx(en, "警覺", "alert"), "能力與資源": [tx(en, "帳本", "the ledger"), tx(en, "玉珮", "jade")],
                  "關係變化": tx(en, "懷疑周叔", "doubts Zhou"), "知道的秘密": "", "未了結的事": tx(en, "缺頁", "the page")}},
        {"名稱": tx(en, "周叔", "Uncle Zhou"), "定位": "配角"},
        {"名稱": ""}]}
    world = {"世界觀": [
        {"名稱": tx(en, "青州鹽政", "Salt Law"), "分類": "經濟與物資", "標籤": [tx(en, "鹽", "salt"), ""], "規則": [tx(en, "官鹽專賣", "state monopoly")],
         "代價與限制": [tx(en, "私鹽重罪", "smuggling is a crime")], "一句話": tx(en, "鹽是命脈", "salt is everything"),
         "與劇情的關係": tx(en, "沈家靠鹽", "the Shens trade salt")},
        {"名稱": "", "分類": tx(en, "亂寫", "nonsense"), "標籤": "x"}]}
    arc = {"段落摘要": tx(en, "林晚查帳。", "Lin Wan audits."), "單元": [
        {"名稱": tx(en, "查帳", "The audit"), "起訖": tx(en, "第1～4章", "ch. 1-4"), "起點局面": tx(en, "退婚", "jilted"),
         "衝突": tx(en, "缺頁", "missing page"), "小高潮": tx(en, "發現暗格", "the niche"), "結果與代價": tx(en, "懷疑周叔", "doubts Zhou")},
        {"名稱": tx(en, "暗格", "The niche"), "起訖": tx(en, "第5～7章", "ch. 5-7"), "衝突": tx(en, "周叔", "Zhou")}]}
    book = {"故事核心": {"書名": tx(en, "退婚之後", "After"), "一句話鉤子": tx(en, "被退婚後查出家族帳本的秘密", "a ledger hides a secret"),
                     "題材": tx(en, "古言", "historical"), "目標讀者": tx(en, "女性向", "romance readers"), "敘事視角": tx(en, "第三人稱", "third person"),
                     "賣點": [tx(en, "查帳", "audits"), tx(en, "打臉", "payback")], "主角想要": tx(en, "保住鋪子", "keep the shop"),
                     "主角需要": tx(en, "相信別人", "trust"), "主角缺陷": tx(en, "多疑", "suspicious"), "金手指": "",
                     "故事引擎": tx(en, "一筆筆舊帳", "old debts"), "主要對手": tx(en, "沈家", "the Shens"), "衝突根源": tx(en, "鹽引", "salt licenses"),
                     "讀者契約": [tx(en, "每卷揭一個秘密", "a secret per volume")], "終局方向": tx(en, "掌家", "she runs the house"),
                     "升級台階": [tx(en, "鋪子", "shop"), tx(en, "家族", "family")]},
            "全書": {"主線一句話": tx(en, "查帳查出家族秘密", "the ledger reveals all"), "終局": tx(en, "掌家", "she wins")},
            "卷": [{"卷名": tx(en, "退婚", "Jilted"), "起": 1, "訖": 4, "本卷目標": tx(en, "查帳", "audit"), "主要對手": tx(en, "大伯母", "the aunt"),
                   "卷末變化": tx(en, "懷疑周叔", "doubt"), "卷末大高潮": tx(en, "暗格", "the niche"), "卷末新鉤子": tx(en, "腳步聲", "footsteps"),
                   "人物弧線": [tx(en, "林晚：主動", "Lin Wan: active")]},
                  {"卷名": "", "起": "5", "訖": 7}, "x"]}
    state = {"目前位置": [tx(en, "第7章", "chapter 7")], "主線進度": tx(en, "查帳中", "auditing"), "在場角色": [tx(en, "林晚", "Lin Wan"), ""],
             "下一章承諾": [], "長期約束": [tx(en, "玉珮只剩半塊", "half a jade")], "連續性風險": tx(en, "缺頁", "the page"),
             "活躍伏筆": [tx(en, "F002 暗格", "F002 niche")]}
    gl = {"cls": {"名詞": [{"名詞": tx(en, "天機閣", "Tianji Pavilion"), "大類": "組織", "處理": "保留"},
                         {"名詞": tx(en, "青雲劍", "Azure Sword"), "大類": "物品", "小類": tx(en, "兵器", "weapon"), "處理": "保留",
                          "主題": tx(en, "兵器", "Weapons")}]},
          "fac": {"勢力": [{"名稱": tx(en, "天機閣", "Tianji Pavilion"), "一句話": tx(en, "情報", "intel"), "別名": [],
                            "相關角色": [tx(en, "林晚", "Lin Wan")], "首領": tx(en, "閣主", "the master")}], "不是勢力": []},
          "topic": {"一句話": tx(en, "兵器", "weapons"), "分區": [{"標題": tx(en, "兵器", "Blades"), "條目": [
              {"名詞": tx(en, "青雲劍", "Azure Sword"), "說明": tx(en, "佩劍", "a sword")}]}]},
          "own": {"條目": [{"名稱": tx(en, "青雲劍", "Azure Sword"), "一句話": tx(en, "名劍", "a famous blade")}]}}
    out = {"chars": chars, "world": world, "arc": arc, "book": book, "state": state, **gl}
    return {k: (to_en(v) if en else v) for k, v in out.items()}


# 依 schema 裡才有的鍵判斷是哪一步（先比對較特別的）
MARKS = (("fac", ("不是勢力", "not_factions")), ("own", ("特性", "traits")), ("topic", ("分區", "sections")),
         ("cls", ("大類", "main_class")), ("extract", ("章綱", "chapter_card")), ("chars", ("年齡身分", "age_identity")),
         ("world", ("代價與限制", "costs_limits")), ("arc", ("段落摘要", "segment_summary")), ("book", ("故事核心", "story_core")),
         ("state", ("連續性風險", "continuity_risks")))
CH_RE = re.compile(r"(?:【第(\d+)章 |\[Chapter (\d+): )")


class RevCtx(FakeCtx):
    def __init__(self, book, en, stop_after=None, wrong_no_batch=None):
        super().__init__(book, [])
        self.en, self.ans, self.seen = en, answers(en), []
        self.stop_after, self.wrong_no_batch, self.n_extract = stop_after, wrong_no_batch, 0
        self.job.status = "running"
        self.job.book_id = "b"

    def call(self, messages, json_mode=False, max_tokens=None, label="", stage=None, recover=None):
        self.truncated = False
        text = messages[-1]["content"]
        k = next(k for k, ms in MARKS if any('"%s"' % m in text for m in ms))
        self.seen.append(k)
        if self.stop_after and k == self.stop_after[0] and self.seen.count(k) >= self.stop_after[1]:
            self.job.status = "cancelled"
        if k == "extract":
            self.n_extract += 1
            nos = sorted({int(a or b) for a, b in CH_RE.findall(text)})
            d = extract(nos, self.en, wrong_no=(self.n_extract == self.wrong_no_batch))
            return json.dumps(to_en(d) if self.en else d, ensure_ascii=False)
        return json.dumps(self.ans[k], ensure_ascii=False)


ZH_EXTRA = "林晚與周叔在鋪子查帳，沈既白的青雲劍掛在牆上。天機閣的人來過。"
EN_EXTRA = "Lin Wan and Uncle Zhou check the books. The Azure Sword hangs on the wall. "


def _book(tmp, name, extra):
    book = os.path.join(tmp, name)
    if os.path.isdir(book):
        shutil.rmtree(book)
    shutil.copytree(os.path.join(ROOT, "demo", name), book)
    for no in range(3, 8):
        with open(layout.path(book, layout.MANUSCRIPT, layout.chapter_md(no)), "w", encoding="utf-8", newline="\n") as f:
            f.write("# c%d\n\n%s\n" % (no, extra * 4))
    return book


def _drafts(book):
    root = os.path.join(book, reverse.DIR, layout.REVERSE_DRAFTS)
    out = {}
    for dp, _, fs in os.walk(root):
        for fn in sorted(fs):
            p = os.path.join(dp, fn)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = project.read_text(p)
    return out


def _run(book, en, **kw):
    c = RevCtx(book, en, **kw)
    c.job.result = None
    prompts.set_lang(c.lang)
    native.act_reverse(c, {})
    return {"result": c.job.result, "logs": c.job.logs, "steps": c.seen}


def _full(book, en, **kw):
    r = _run(book, en, **kw)
    r["drafts"] = _drafts(book)
    r["processed"] = reverse.state(book)["processed"]
    return r


def _copy_cache(src_book, dst):
    shutil.copytree(os.path.join(src_book, reverse.DIR), dst)


def _use_cache(book, cache):
    """放進改之前的程式寫的反推快取。快取是 v2 的檔名（累積.json、批次/）；P3 起書要先經移轉工具轉換，
    這裡照移轉工具的規則放到新位置、改寫裡面的路徑，等於「舊書轉換後續跑」。"""
    from studio import migrate
    d = os.path.join(book, reverse.DIR)
    if os.path.isdir(d):
        shutil.rmtree(d)
    old_dir = migrate.PATHS["STUDIO_REVERSE"][0]
    for base, _, files in os.walk(cache):
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), cache).replace(os.sep, "/")
            dst = os.path.join(book, *migrate.map_v3(old_dir + "/" + rel).split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(os.path.join(base, f), encoding="utf-8") as fh:
                data = json.load(fh)
            with open(dst, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(migrate._rewrite_json(data), fh, ensure_ascii=False, indent=1)


def scenario(write_fixture=False):
    out = {}
    tmp = tempfile.mkdtemp()
    try:
        out["zh"] = _full(_book(tmp, "退婚之後", ZH_EXTRA), False, wrong_no_batch=3)
        out["en"] = _full(_book(tmp, "en_TheLanternRoad", EN_EXTRA), True)
        # 中斷後續跑
        book = _book(tmp, "退婚之後", ZH_EXTRA)
        r1 = _run(book, False, stop_after=("extract", 2))
        if write_fixture:     # 只在用 v2 的程式產生舊快取時用（P3 起不再重產：fixture 必須是舊程式寫的）
            if os.path.isdir(FIXTURE):
                shutil.rmtree(FIXTURE)
            _copy_cache(book, os.path.join(FIXTURE, "after_extract"))
        r2 = _run(book, False, stop_after=("chars", 1))
        if write_fixture:
            _copy_cache(book, os.path.join(FIXTURE, "after_chars"))
        r3 = _full(book, False)
        out["resume"] = {"r1": r1, "r2": r2, "r3": r3}
        # 舊版快取：改之前的程式寫的累積資料與步驟快取
        for stage in ("after_extract", "after_chars"):
            book = _book(tmp, "退婚之後", ZH_EXTRA)
            _use_cache(book, os.path.join(FIXTURE, stage))
            out["v2cache_" + stage] = _full(book, False)
    finally:
        shutil.rmtree(tmp)
        prompts.set_lang("zh-TW")
    return json.loads(json.dumps(out, ensure_ascii=False, default=str).replace(tmp, "<tmp>"))


class ReverseFlowTest(unittest.TestCase):
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

        def cmp(a, b, path):
            if isinstance(a, dict) and isinstance(b, dict) and path.count("/") < 3:
                for k in sorted(set(a) | set(b)):
                    cmp(a.get(k), b.get(k), path + "/" + k)
            else:
                with self.subTest(part=path):
                    self.assertEqual(a, b)
        cmp(want, got, "")

    def test_scenario_reaches_the_paths(self):
        got = scenario()
        for k in ("zh", "en"):
            r, d = got[k]["result"], got[k]["drafts"]
            self.assertIn("從正文建立設定完成", r, k)
            self.assertEqual([1, 2, 3, 4, 5, 6, 7], got[k]["processed"], k)
            self.assertEqual(3, got[k]["steps"].count("extract"), k)
            for step in ("chars", "world", "arc", "book", "state", "cls", "fac", "topic", "own"):
                self.assertIn(step, got[k]["steps"], (k, step))
            self.assertTrue(any(p.startswith(layout.CHARACTER_STATES + "/") for p in d), k)
            self.assertTrue(any("第2卷" in p for p in d), (k, sorted(d)))
        zd = got["zh"]["drafts"]
        fs = next(v for p, v in zd.items() if p == layout.FORESHADOWING)
        self.assertIn("已回收", fs)
        self.assertIn("F002", fs)
        rk = next(v for p, v in zd.items() if p == layout.READER_KNOWLEDGE)
        self.assertIn("周叔拿走的", rk)
        self.assertIn("誤認", rk)
        lin = next(v for p, v in zd.items() if p == layout.entry(layout.CHARACTERS, "林晚"))
        self.assertIn("晚丫頭", lin)
        self.assertIn("二小姐", lin)
        self.assertIn("沈既白：前未婚夫", lin)
        card7 = next(v for p, v in zd.items() if p == layout.CHAPTER_CARDS + "/" + layout.chapter_md(7))
        self.assertIn("查清帳本", card7, "章號寫錯但數量對：照順序對應")
        gl = next(v for p, v in zd.items() if p == layout.GLOSSARY)
        self.assertIn("路人甲", gl)
        ef = got["en"]["drafts"]
        self.assertIn("已埋", next(v for p, v in ef.items() if p == layout.FORESHADOWING), "英文選項值要換回固定詞")
        res = got["resume"]
        self.assertIn("已停止", res["r1"]["result"])
        self.assertIn("已停止", res["r2"]["result"])
        self.assertEqual(["extract", "extract"], res["r1"]["steps"])
        self.assertNotIn("extract", res["r3"]["steps"])
        self.assertNotIn("chars", res["r3"]["steps"], "已整理的步驟要用快取")
        for stage in ("after_extract", "after_chars"):
            self.assertEqual(res["r3"]["drafts"], got["v2cache_" + stage]["drafts"], stage)


if __name__ == "__main__":
    unittest.main()
