# -*- coding: utf-8 -*-
"""살림 쇼츠 주제별 쿠팡 상품을 골라 인포크에 붙일 목록(HTML)을 텔레그램으로 보낸다."""
import html
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ai"))
import coupang_api  # noqa: E402

os.environ.setdefault("GEMINI_API_KEY", "-")
from gemini_write import tg_chat  # noqa: E402

# 쇼츠 제목 일부 → (인포크에 쓸 이름, 쿠팡 검색어)
MAP = [
    ("고춧가루 얼룩", "김장 얼룩 지울 때 산소계 표백제", "산소계 표백제"),
    ("건조기 정전기", "건조기 정전기 줄이는 양모 건조볼", "건조기 양모볼"),
    ("테이프 자국", "벽지 안 뜯기는 스티커 제거제", "스티커 제거제"),
    ("못 없이 액자", "못 없이 액자 거는 벽지 핀", "벽지 액자걸이 핀"),
    ("가구 눌린 자국", "바닥 자국 막는 가구 다리 패드", "가구 다리 패드"),
    ("욕실 곰팡이", "욕실 곰팡이 제거제", "욕실 곰팡이 제거제"),
    ("하수구 냄새", "하수구 냄새 차단 트랩", "하수구 냄새차단 트랩"),
    ("수도계량기 동파", "수도계량기 동파 막는 보온재", "수도계량기 보온재"),
    ("전기히터 멀티탭", "전기히터용 고용량 멀티탭", "고용량 멀티탭 16A"),
    ("패딩 압축팩", "패딩 보관 부직포 커버", "패딩 보관 부직포 커버"),
    ("온수매트 물", "온수매트 전용수", "온수매트 전용수"),
    ("김치통 냄새", "김치통 냄새 빼는 베이킹소다", "베이킹소다 대용량"),
    ("김장 김치", "김치냉장고 김치통 누름판", "김치 누름판"),
]


def main():
    log = json.loads((ROOT / "data/shorts_log.json").read_text(encoding="utf-8"))
    shorts = {s["title"]: s["url"] for s in log if s.get("privacy") == "public" and s.get("url")}
    sub = os.environ.get("COUPANG_SUB_ID", "").strip()
    rows = []
    for key, label, kw in MAP:
        st = next(((t, u) for t, u in shorts.items() if key in t), None)
        try:
            items = coupang_api.search(kw, limit=5, sub_id=sub)
        except Exception as e:  # noqa
            print("검색 실패", kw, e)
            continue
        items.sort(key=lambda p: not p["rocket"])
        if not items:
            continue
        p = items[0]
        rows.append({"label": label, "kw": kw, "name": p["name"], "url": p["url"], "price": p["price"],
                     "image": p["image"], "rocket": p["rocket"], "short": st})
        print(f"- {label} | {p['name'][:40]} | {p['price']}원 | {p['url']}")
        time.sleep(1)

    cards = ""
    for i, r in enumerate(rows, 1):
        sh = f'<div class="s">🎬 연결 쇼츠: {html.escape(r["short"][0])}</div>' if r["short"] else ""
        cards += f"""<div class="c"><img src="{r['image']}"><div class="b">
<div class="n">{i}. <span id="t{i}">{html.escape(r['label'])}</span></div>
<div class="p">{html.escape(r['name'][:60])}<br>{r['price']:,}원{' · 🚀로켓' if r['rocket'] else ''}</div>{sh}
<button onclick="cp('t{i}')">이름 복사</button> <button onclick="cp('u{i}')">링크 복사</button>
<div class="u" id="u{i}">{r['url']}</div></div></div>"""
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>인포크 상품 목록</title><style>
body{{font-family:-apple-system,'Noto Sans KR',sans-serif;background:#fff8f0;margin:0;padding:14px;color:#222}}
h1{{color:#e0529a;font-size:22px}} .note{{background:#fff;border:2px dashed #f6c4de;border-radius:10px;padding:10px;font-size:14px}}
.c{{display:flex;gap:12px;background:#fff;border:2px solid #f6c4de;border-radius:12px;padding:10px;margin:12px 0}}
.c img{{width:96px;height:96px;object-fit:cover;border-radius:8px}} .b{{flex:1;min-width:0}}
.n{{font-weight:800;color:#962860}} .p{{font-size:13px;color:#555;margin:4px 0}} .s{{font-size:12px;color:#e0529a}}
.u{{font-size:11px;color:#999;word-break:break-all}} button{{background:#e0529a;color:#fff;border:0;border-radius:8px;padding:8px 10px;font-weight:700;margin:4px 0}}
</style></head><body><h1>🏠 인포크 상품 목록 ({len(rows)}개)</h1>
<div class="note">인포크 → <b>+ 링크 추가</b> → '이름 복사'를 제목에, '링크 복사'를 주소에 붙이세요.<br>
페이지 맨 위에 꼭: <b>이 페이지의 링크는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</b></div>
{cards}<script>function cp(id){{navigator.clipboard.writeText(document.getElementById(id).innerText).then(()=>alert('복사했어요'))}}</script>
</body></html>"""
    out = Path("/tmp/inpock-list.html")
    out.write_text(page, encoding="utf-8")
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = tg_chat(tok)
    with open(out, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument",
                          data={"chat_id": chat, "caption": f"🏠 인포크에 넣을 살림템 {len(rows)}개 목록이에요. 크롬으로 열어 주세요."},
                          files={"document": ("인포크-상품목록.html", f, "text/html")}, timeout=60)
    print("텔레그램:", r.status_code)


if __name__ == "__main__":
    main()
