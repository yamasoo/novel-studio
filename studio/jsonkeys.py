# -*- coding: utf-8 -*-
"""英文、日文書的 JSON 鍵：模型寫英文鍵，程式在解析後換回中文鍵，之後的程式照舊。

為什麼：鍵名是中文時，英文、日文書的模型很容易跟著把內容寫成中文。繁中書的提示詞不變（仍是中文鍵）。

- to_zh(data)：遞迴把 dict 的英文鍵換成中文鍵；認不得的鍵、本來就是中文的鍵原樣保留，所以新舊格式都能讀。
  同時把列舉值（定位、狀態、重要度……）交給 enums.norm 換回中文固定詞。
- 一張共用表：同一個中文鍵在各 schema 用同一個英文字。工作台原本就用英文的鍵（chapters、items、changes、
  summary、state_card、foreshadow、timeline、reader、characters、relations、new_entities、report）
  不能出現在表裡，test_keys() 會檢查。
- 一個中文鍵可以有兩個英文字（例如 名詞 的清單叫 terms、條目裡的欄位叫 term），換回來都是同一個中文鍵。
"""
from . import enums, prompts

# 英文鍵 → 中文鍵
KEYS = {
    # 逐章抽取（rev_extract_schema）
    "no": "章", "chapter_summary": "摘要", "what_happened": "發生了什麼", "situation_change": "局面變化",
    "new_elements": "新出現的人事物", "ends_on": "結尾停在", "chapter_card": "章綱", "protagonist_goal": "主角想做什麼",
    "obstacle": "阻礙", "new_situation": "局面變成", "why_read_on": "讀者為什麼往下看", "function": "功能", "emotion": "情緒",
    "plot_points": "情節點", "ending_hook": "章末鉤子", "people": "人物", "name": "名稱", "aliases": "別名", "identity": "身分",
    "this_chapter": "本章", "importance": "重要", "terms": "名詞", "term": "名詞", "kind": "類別", "subtype": "小類",
    "explanation": "說明", "plot_events": "事件", "story_time": "故事時間", "actual_event": "實際發生", "reader_knows": "讀者知道",
    "related_characters": "相關角色", "foreshadowing": "伏筆", "id": "編號", "action": "動作", "content": "內容",
    "priority": "重要度", "reader_knowledge": "讀者", "type": "類型", "author_truth": "作者真相",
    # 角色（rev_char_schema）
    "cast": "角色", "role": "定位", "one_line": "一句話", "age_identity": "年齡身分", "looks": "外貌", "wants": "想要",
    "fears": "害怕", "flaw": "缺陷", "bottom_line": "底線", "secret": "秘密", "voice": "說話方式", "relationships": "關係",
    "relationship": "關係", "arc": "角色弧線", "current_state": "目前狀態", "location": "位置", "goal": "目標",
    "physical_state": "身體狀態", "emotional_state": "情緒狀態", "abilities_resources": "能力與資源",
    "relationship_changes": "關係變化", "known_secrets": "知道的秘密", "unfinished_business": "未了結的事",
    # 世界觀（rev_world_schema）
    "world": "世界觀", "world_category": "分類", "labels": "標籤", "rules": "規則", "costs_limits": "代價與限制",
    "plot_relevance": "與劇情的關係",
    # 劇情段落（rev_arc_schema）
    "segment_summary": "段落摘要", "units": "單元", "chapter_range": "起訖", "starting_situation": "起點局面",
    "conflict": "衝突", "mini_climax": "小高潮", "outcome_cost": "結果與代價",
    # 故事核心、大綱與卷（rev_book_schema）
    "story_core": "故事核心", "title": "書名", "hook": "一句話鉤子", "genre": "題材", "target_readers": "目標讀者",
    "pov": "敘事視角", "selling_points": "賣點", "protagonist_wants": "主角想要", "protagonist_needs": "主角需要",
    "protagonist_flaw": "主角缺陷", "special_edge": "金手指", "story_engine": "故事引擎", "main_opponent": "主要對手",
    "conflict_root": "衝突根源", "reader_contract": "讀者契約", "endgame": "終局方向", "escalation_steps": "升級台階",
    "whole_book": "全書", "main_line": "主線一句話", "ending": "終局", "volumes": "卷", "volume_name": "卷名",
    "start": "起", "end": "訖", "volume_goal": "本卷目標", "volume_end_change": "卷末變化", "volume_climax": "卷末大高潮",
    "volume_new_hook": "卷末新鉤子", "character_arcs": "人物弧線",
    # 狀態卡的七節（rev_state_schema、writeback 的 state_card）
    "current_position": "目前位置", "main_progress": "主線進度", "present_characters": "在場角色",
    "next_chapter_promises": "下一章承諾", "long_term_constraints": "長期約束", "continuity_risks": "連續性風險",
    "active_foreshadowing": "活躍伏筆",
    # 名詞整理（gl_*_schema）
    "main_class": "大類", "topic": "主題", "handling": "處理", "factions": "勢力", "history": "沿革", "sub_units": "內部編組",
    "scale_territory": "規模與地盤", "leader": "首領", "key_members": "主要成員", "resources_means": "資源與手段",
    "faction_wants": "想要什麼", "conflicts_with": "和誰有衝突", "cooperates_with": "和誰有合作", "internal_rules": "內部規矩",
    "attitude_to_protagonist": "對主角的態度", "author_check": "需要作者確認", "not_factions": "不是勢力", "change_to": "改成",
    "reason": "原因", "sections": "分區", "heading": "標題", "entries": "條目", "rules_limits": "規則與限制", "traits": "特性",
    "origin": "來歷", "story_role": "在故事中的作用", "limits_costs": "限制與代價",
    # 回寫追蹤（writeback_schema 內層）
    "planted_in": "埋設章", "planned_payoff": "預計回收", "last_seen": "最後出現", "status": "狀態",
    "what_really_happened": "實際發生（作者真相）", "reader_knows_now": "讀者目前知道", "revealed_in": "揭示章",
    "planted_chapter": "種下章", "resolved_in": "回收章", "who": "誰", "toward": "對誰", "attitude": "態度",
    # 讀者認知（rl_schema、rl_recon_schema）
    "source": "來源", "merge_into": "合併到", "grounds": "理由",
}

# 工作台原本就是英文的鍵：不能拿來當新的英文鍵
NATIVE = {"chapters", "items", "changes", "summary", "state_card", "foreshadow", "timeline", "reader", "characters",
          "relations", "new_entities", "report"}

# 這些中文鍵的值是列舉值，交給 enums.norm
VALUE_KINDS = {"定位": "role", "重要": "importance", "狀態": "fs_status", "重要度": "level", "類型": "type",
               "動作": "action", "類別": "term_cat", "大類": "term_big", "處理": "handling", "改成": "change_to",
               "分類": "world_cat", "編號": "id"}


def _key(k):
    if not isinstance(k, str):
        return k
    return KEYS.get(k) or KEYS.get(k.strip().lower()) or k


def to_zh(data, unknown=None, values=None):
    """unknown：list，收集認不得的列舉值（(中文鍵, 原值)），給任務紀錄提醒用。
    values：要不要換列舉值；預設只有英文、日文書換（繁中書的值原樣，行為和以前相同）。"""
    if values is None:
        values = prompts.cur_lang() != "zh-TW"
    if isinstance(data, list):
        return [to_zh(x, unknown, values) for x in data]
    if not isinstance(data, dict):
        return data
    out = {}
    for k, v in data.items():
        zk = _key(k)
        if values and zk in VALUE_KINDS and isinstance(v, str):
            nv = enums.norm(VALUE_KINDS[zk], v)
            if nv is None:
                if unknown is not None and v.strip():
                    unknown.append((zk, v))
                nv = v
            v = nv
        elif not isinstance(v, str):
            v = to_zh(v, unknown, values)
        if zk in out and k != zk:      # 新舊鍵同時出現：中文鍵優先
            continue
        out[zk] = v
    return out


def to_en(data):
    """測試用：把中文鍵換成英文鍵（一個中文鍵有兩個英文字時用表裡先出現的那個）。"""
    rev = {}
    for en, zh in KEYS.items():
        rev.setdefault(zh, en)
    if isinstance(data, list):
        return [to_en(x) for x in data]
    if not isinstance(data, dict):
        return data
    return {rev.get(k, k): to_en(v) for k, v in data.items()}


def test_keys():
    bad = sorted(set(KEYS) & NATIVE)
    if bad:
        raise AssertionError("這些英文鍵和工作台原本的英文鍵相撞：%s" % bad)
    return True
