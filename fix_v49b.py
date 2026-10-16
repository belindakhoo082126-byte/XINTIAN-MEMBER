#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v49b：用行號定位改 handle_group_media（不依賴文字比對）"""
import sys, shutil, os, re
from datetime import datetime

P = "/opt/xintian/bot/bot.py"
if not os.path.exists(P):
    print("找不到", P); sys.exit(1)

bak = f"{P}.bak-v49b-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(P, bak)
print(f"已備份：{bak}")

lines = open(P, encoding="utf-8").read().split("\n")

# 找 handle_group_media 的起點與 _group_share_flow 的起點
start = None
end = None
for i, ln in enumerate(lines):
    if ln.startswith("async def handle_group_media("):
        start = i
    if start is not None and ln.startswith("async def _group_share_flow("):
        end = i
        break

if start is None or end is None:
    print("找不到函式邊界 → 中止"); sys.exit(1)

print(f"handle_group_media: 第 {start+1} 行 → 第 {end} 行（替換 {end-start} 行）")

new_func = '''async def handle_group_media(context, msg, text, uid, name):
    """群裡收到 圖片/影片（有無文字）→ 判斷分享/提問（關鍵字 + AI）。"""
    caption = text

    # 1) 明確問句 → 提問
    if caption and any(k in caption for k in Q_WORDS_ALL):
        _cancel_media_wait(msg)
        await _group_question_flow(context, msg, caption, uid, name)
        return True

    if caption:
        # 2) 負面／問題傾向詞 → 提問（不給分）
        if any(k in caption for k in NEG_WORDS):
            _cancel_media_wait(msg)
            await _group_question_flow(context, msg, caption, uid, name)
            return True
        # 3) 正面／分享傾向詞 → 分享（給分）
        if any(k in caption for k in POS_WORDS):
            _cancel_media_wait(msg)
            await _group_share_flow(context, msg, uid, name)
            return True
        # 4) 模糊 → 問 AI 判斷
        _cancel_media_wait(msg)
        verdict = await _ai_classify_media(context, msg, caption)
        if verdict == "question":
            await _group_question_flow(context, msg, caption, uid, name)
        else:
            await _group_share_flow(context, msg, uid, name)
        return True

    # 無文字 → 動態等 30 秒
    _schedule_media_wait(context, msg, uid, name, msg.from_user.username or "", "group")
    return True


async def _ai_classify_media(context, msg, caption):
    """用 AI 判斷這是「分享」還是「提問」。"""
    if not AI_ENABLED:
        return "unknown"
    try:
        img = await download_media_bytes(context.bot, msg) if (msg.photo or msg.video or msg.animation) else None
        prompt = (
            "花友在植物群組發了一張照片，文字是：" + repr(caption) + "\\n\\n"
            "請判斷他是『單純分享自己的植物（炫耀、報喜、曬成果）』"
            "還是『在問問題（植物出狀況、想知道怎麼處理、問這是什麼）』。\\n"
            "只回一個英文字：share 或 question。"
        )
        can, ans = await ask_gemini(prompt, img)
        if not can or not ans:
            return "unknown"
        a = ans.strip().lower()
        if "question" in a:
            return "question"
        if "share" in a:
            return "share"
        return "unknown"
    except Exception as e:
        log.warning("_ai_classify_media: %s", e)
        return "unknown"'''.split("\n")

lines[start:end] = new_func
src = "\n".join(lines)

# 移除「跟大家分享一下」硬句式
pat = re.compile(r'f"🌿\s*\{name\}\s*\{praise\}\s*\+{pts}\s*分\s*🌸[^"]*"')
src, n = pat.subn('f"🌿 {name} {praise} +{pts} 分 🌸"', src)
print("已移除硬句式" if n else "找不到分享句（可能格式不同）")

# 確保 NEG_WORDS / POS_WORDS 存在
if "NEG_WORDS" not in src:
    block = '''

NEG_WORDS = ["软", "軟", "黄", "黃", "枯", "烂", "爛", "掉", "死", "病", "虫", "蟲",
             "怎么办", "怎麼辦", "这样", "這樣", "那样", "那樣", "正常",
             "太多", "太少", "不够", "不夠", "失败", "失敗", "不会", "不會",
             "有没有", "有沒有", "是不是", "多久", "几次", "幾次", "怎么养", "怎麼養"]

POS_WORDS = ["美", "漂亮", "好看", "可爱", "可愛", "開花", "开花", "結果", "结果",
             "成功", "長大", "长大", "開心", "开心", "療癒", "疗愈", "讚", "赞",
             "終於", "终于", "收成", "豐收", "丰收", "香", "茂盛", "爆盆"]
'''
    m = re.search(r"(Q_WORDS_ALL\s*=\s*\[[^\]]*\]\n)", src, re.S)
    if m:
        src = src[:m.end()] + block + src[m.end():]
        print("已補上 NEG_WORDS / POS_WORDS")
    else:
        src = block + "\n" + src
        print("已補上（檔頭）")
else:
    print("NEG_WORDS 已存在")

open(P, "w", encoding="utf-8").write(src)
print("完成！")
