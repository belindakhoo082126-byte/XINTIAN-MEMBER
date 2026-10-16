#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v49：改善群照片「分享 vs 提問」判斷（含 AI 判斷）"""
import re, sys, shutil, os
from datetime import datetime

P = "/opt/xintian/bot/bot.py"

if not os.path.exists(P):
    print("❌ 找不到", P); sys.exit(1)

bak = f"{P}.bak-v49-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(P, bak)
print(f"✅ 已備份：{bak}")

src = open(P, encoding="utf-8").read()

# ---------- 1) 新增「負面詞 / 讚美詞」清單（插在 Q_WORDS_ALL 之後）----------
neg_block = '''

# 負面／提問傾向詞（有這些 → 不當分享，走 AI/人工）
NEG_WORDS = ["软", "軟", "黄", "黃", "枯", "烂", "爛", "掉", "死", "病", "虫", "蟲",
             "怎么办", "怎麼辦", "这样", "這樣", "那样", "那樣", "正常", "可以吗", "可以嗎",
             "太多", "太少", "不够", "不夠", "失败", "失敗", "不会", "不會",
             "有没有", "有沒有", "是不是", "多久", "几次", "幾次", "怎么养", "怎麼養"]

# 正面／分享傾向詞（有這些 → 當分享給分）
POS_WORDS = ["美", "漂亮", "好看", "可爱", "可愛", "開花", "开花", "結果", "结果",
             "成功", "長大", "长大", "開心", "开心", "療癒", "疗愈", "讚", "赞",
             "終於", "终于", "收成", "豐收", "丰收", "香", "茂盛", "爆盆"]
'''

if "NEG_WORDS" not in src:
    # 插在第一個 '\n\n# =====' 之後（Q_WORDS_ALL 區塊結束後）
    m = re.search(r"(Q_WORDS_ALL\s*=\s*\[[^\]]*\]\n)", src, re.S)
    if m:
        src = src[:m.end()] + neg_block + src[m.end():]
        print("✅ 已加入 NEG_WORDS / POS_WORDS")
    else:
        print("⚠️ 找不到 Q_WORDS_ALL，改用插入檔頭")
        src = neg_block + "\n" + src
else:
    print("ℹ️ NEG_WORDS 已存在，略過")

# ---------- 2) 改 handle_group_media：加 AI 判斷 ----------
old_hgm = '''async def handle_group_media(context, msg, text, uid, name):
    """群組收到 圖片/影片（有無文字）。"""
    caption = text
    is_q = bool(caption) and any(k in caption for k in Q_WORDS_ALL)
    if is_q:
        _cancel_media_wait(msg)
        await _group_question_flow(context, msg, caption, uid, name)
        return True
    if caption:
        # 有文字但不像問句 → 直接當分享
        _cancel_media_wait(msg)
        await _group_share_flow(context, msg, uid, name)
        return True
    # 無文字 → 動態等 30 秒
    _schedule_media_wait(context, msg, uid, name, msg.from_user.username or "", "group")
    return True'''

new_hgm = '''async def handle_group_media(context, msg, text, uid, name):
    """群組收到 圖片/影片（有無文字）→ 判斷分享/提問（關鍵字 + AI）。"""
    caption = text

    # 1) 明確問句 → 提問
    if caption and any(k in caption for k in Q_WORDS_ALL):
        _cancel_media_wait(msg)
        await _group_question_flow(context, msg, caption, uid, name)
        return True

    if caption:
        # 2) 明確負面詞 → 提問（不給分）
        if any(k in caption for k in NEG_WORDS):
            _cancel_media_wait(msg)
            await _group_question_flow(context, msg, caption, uid, name)
            return True
        # 3) 明確讚美詞 → 分享（給分）
        if any(k in caption for k in POS_WORDS):
            _cancel_media_wait(msg)
            await _group_share_flow(context, msg, uid, name)
            return True
        # 4) 模糊 → 問 AI 判斷（分享 or 提問）
        _cancel_media_wait(msg)
        verdict = await _ai_classify_media(context, msg, caption)
        if verdict == "share":
            await _group_share_flow(context, msg, uid, name)
        elif verdict == "question":
            await _group_question_flow(context, msg, caption, uid, name)
        else:
            # AI 不確定 → 當分享（保守：保留花友體驗）
            await _group_share_flow(context, msg, uid, name)
        return True

    # 無文字 → 動態等 30 秒
    _schedule_media_wait(context, msg, uid, name, msg.from_user.username or "", "group")
    return True


async def _ai_classify_media(context, msg, caption):
    """用 AI 判斷這是「分享」還是「提問」。回 "share" / "question" / "unknown"。"""
    if not AI_ENABLED:
        return "unknown"
    try:
        img = await download_media_bytes(context.bot, msg) if (msg.photo or msg.video or msg.animation) else None
        prompt = (
            "花友在植物群組發了一張照片，文字是：" + repr(caption) + "\\n\\n"
            "請判斷他是『單純分享自己的植物（炫耀、報喜、曬成果）』"
            "還是『在問問題（植物出狀況、想知道怎麼處理、問是什麼）』。\\n"
            "只回一個英文字：share 或 question。"
        )
        can, ans = await ask_gemini(prompt, img)
        if not can or not ans:
            return "unknown"
        a = ans.strip().lower()
        if "share" in a:
            return "share"
        if "question" in a:
            return "question"
        return "unknown"
    except Exception as e:
        log.warning("_ai_classify_media: %s", e)
        return "unknown"'''

if old_hgm in src:
    src = src.replace(old_hgm, new_hgm)
    print("✅ 已更新 handle_group_media（加 AI 判斷）")
else:
    print("⚠️ 找不到 handle_group_media 原文（可能已改過）→ 略過")

# ---------- 3) 改 _group_share_flow：拿掉硬句式 ----------
old_share = '''        try:
            await msg.reply_text(f"🌿{name} {praise} +{pts} 分 🌸\\n跟大家分享一下你怎麼養的吧～")'''
new_share = '''        try:
            await msg.reply_text(f"🌿 {name} {praise} +{pts} 分 🌸")'''
if old_share in src:
    src = src.replace(old_share, new_share)
    print("✅ 已移除「跟大家分享一下」硬句式")
else:
    # 嘗試寬鬆匹配
    pat = re.compile(r'await msg\.reply_text\(f"🌿\{name\} \{praise\} \+{pts\} 分 🌸[^"]*"\)')
    new_src, n = pat.subn('await msg.reply_text(f"🌿 {name} {praise} +{pts} 分 🌸")', src)
    if n:
        src = new_src
        print(f"✅ 已移除硬句式（寬鬆匹配 {n} 處）")
    else:
        print("⚠️ 找不到分享回覆句 → 略過")

open(P, "w", encoding="utf-8").write(src)
print("\\n🎉 完成！請執行：python3 -m py_compile " + P + " && systemctl restart xintian-bot")
