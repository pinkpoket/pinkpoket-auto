# -*- coding: utf-8 -*-
"""Gemini 가 쓴 네이버 원고(/tmp/naver_body.json) + 사진 주소(naver/jobs/ID.result.json)를
휴대폰용 HTML(복사 버튼)로 만들어 텔레그램으로 보낸다. 본문은 저장소에 올리지 않는다."""
import html
import json
import os
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
d = json.loads(Path("/tmp/naver_body.json").read_text(encoding="utf-8"))
res = json.loads((ROOT / f"naver/jobs/{d['id']}.result.json").read_text(encoding="utf-8"))
imgs = res.get("images", [])

photos = "".join(
    f'<div class="ph"><b>사진 {i}</b> (꾹 눌러 저장)<br><img src="{u}"></div>' for i, u in enumerate(imgs, 1))
body = d["body_html"]
title = html.escape(d["title"])
cat = html.escape(d["category"])

page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:-apple-system,'Noto Sans KR',sans-serif;margin:0;padding:14px;background:#fff7fa;color:#222;line-height:1.7}}
.cat{{font-size:22px;font-weight:800;color:#d9488b;margin:6px 0 12px}}
.box{{background:#fff;border:2px solid #f3c1d6;border-radius:12px;padding:12px;margin:12px 0}}
.btn{{display:block;width:100%;padding:14px;font-size:17px;font-weight:700;border:0;border-radius:10px;background:#d9488b;color:#fff;margin:8px 0}}
#body p,#body h3{{margin:0}} #body img{{max-width:100%}}
.ph img{{width:100%;border-radius:8px;margin:6px 0 14px}}
.ok{{color:#2a8a4a;font-weight:700;text-align:center;min-height:1.4em}}
</style></head><body>
<div class="cat">📁 카테고리: {cat}</div>
<div class="box"><b>제목</b><div id="title" style="font-size:19px;font-weight:700;margin-top:6px">{title}</div>
<button class="btn" onclick="cp('title')">제목 복사</button></div>
<div class="box"><button class="btn" onclick="cp('body')">본문 복사</button><div class="ok" id="msg"></div>
<div id="body">{body}</div>
<button class="btn" onclick="cp('body')">본문 복사</button></div>
<div class="box"><b>사진 3장</b> — 본문의 📷 [사진 N] 자리에 넣어 주세요<br>{photos}</div>
<p style="font-size:13px;color:#888">Gemini가 쓴 원고예요. 발행 전에 한 번 읽어 봐 주세요.</p>
<script>
function cp(id){{var el=document.getElementById(id),r=document.createRange();r.selectNodeContents(el);
var s=window.getSelection();s.removeAllRanges();s.addRange(r);var ok=false;try{{ok=document.execCommand('copy')}}catch(e){{}}
s.removeAllRanges();document.getElementById('msg').textContent=ok?'복사했어요! 네이버 앱에 붙여 넣으세요':'복사가 안 되면 글을 꾹 눌러 전체 선택해 주세요';}}
</script></body></html>"""

out = Path(f"/tmp/naver-{d['id']}.html")
out.write_text(page, encoding="utf-8")
import sys
sys.path.insert(0, str(ROOT / "ai"))
os.environ.setdefault("GEMINI_API_KEY", "-")
from gemini_write import tg_chat  # noqa: E402
tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
chat = tg_chat(tok)
if not (tok and chat):
    sys.exit("텔레그램 봇 토큰(TELEGRAM_BOT_TOKEN)이 없거나, 봇에게 아직 말을 건 적이 없어요")
cap = f"📝 네이버 원고 도착 ({cat})\n{d['title']}\n\n파일을 눌러 크롬(브라우저)으로 열고 '본문 복사' → 네이버 앱에 붙여 넣기"
with open(out, "rb") as f:
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument",
                      data={"chat_id": chat, "caption": cap[:1000]},
                      files={"document": (f"네이버원고-{d['id']}.html", f, "text/html")}, timeout=60)
print("텔레그램:", r.status_code, r.text[:200])
r.raise_for_status()
