# -*- coding: utf-8 -*-
"""네이버 원고를 노트북용 Claude 페이지(아티팩트) HTML 로 만든다.

사용: python ai/naver_page.py 본문.html "제목" "카테고리" 사진1.jpg 사진2.jpg 사진3.jpg 출력.html
- 본문 HTML 은 /tmp 같은 저장소 밖에 둔다 (본문은 저장소에 올리지 않음 — 네이버 유사문서 방지).
- 아티팩트는 바깥 사진을 못 불러오므로 사진·서명 그림을 페이지 안에 넣는다.
  '본문 복사' 할 때는 서명 그림 주소를 원래 jsDelivr 주소로 바꿔서 복사한다.
"""
import base64
import html
import io
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SIG_URL_RE = re.compile(r'src="(https://cdn\.jsdelivr\.net/gh/pinkpoket/pinkpoket-auto@[0-9a-f]+/brand/naver/naver-signature\.png)"')


def data_uri(path, max_side=1024, quality=85):
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def png_uri(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def build(body, title, cat, photos, orig_urls=None):
    m = SIG_URL_RE.search(body)
    if m:
        sig_local = ROOT / "brand/naver/naver-signature.png"
        body = body.replace(m.group(0), f'src="{png_uri(sig_local)}" data-orig="{m.group(1)}"')
    ph = []
    for i, p in enumerate(photos, 1):
        link = ""
        if orig_urls and i <= len(orig_urls):
            link = f' · <a href="{orig_urls[i-1]}">원본 열기</a>'
        ph.append(f'<div class="ph"><b>사진 {i}</b> (오른쪽 클릭 → 이미지 저장){link}<br>'
                  f'<img src="{data_uri(p)}" alt="사진 {i}"></div>')
    t = html.escape(title)
    c = html.escape(cat)
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>네이버 원고 · {t}</title>
<style>
body{{font-family:-apple-system,'Noto Sans KR','Malgun Gothic',sans-serif;margin:0;padding:18px;background:#fff7fa;color:#222;line-height:1.7}}
.wrap{{max-width:760px;margin:0 auto}}
.cat{{font-size:22px;font-weight:800;color:#d9488b;margin:6px 0 12px}}
.box{{background:#fff;border:2px solid #f3c1d6;border-radius:12px;padding:14px;margin:14px 0}}
.btn{{display:block;width:100%;padding:13px;font-size:17px;font-weight:700;border:0;border-radius:10px;background:#d9488b;color:#fff;margin:8px 0;cursor:pointer}}
.btn:hover{{background:#c23a7a}}
#body p,#body h3{{margin:0}} #body img{{max-width:100%}}
.ph img{{width:100%;border-radius:8px;margin:6px 0 16px}}
.ok{{color:#2a8a4a;font-weight:700;text-align:center;min-height:1.4em}}
.note{{font-size:13px;color:#888}}
</style></head><body><div class="wrap">
<div class="cat">📁 카테고리: {c}</div>
<div class="box"><b>제목</b><div id="title" style="font-size:20px;font-weight:700;margin-top:6px">{t}</div>
<button class="btn" onclick="cp('title')">제목 복사</button></div>
<div class="box"><button class="btn" onclick="cp('body')">본문 복사</button><div class="ok" id="msg"></div>
<div id="body">{body}</div>
<button class="btn" onclick="cp('body')">본문 복사</button></div>
<div class="box"><b>사진 {len(photos)}장</b> — 본문의 📷 [사진 N] 자리에 넣어 주세요<br>{''.join(ph)}</div>
<p class="note">발행 전에 한 번 읽어 봐 주세요.</p>
</div>
<script>
function say(t){{document.getElementById('msg').textContent=t;}}
async function cp(id){{
  var el=document.getElementById(id);
  var imgs=el.querySelectorAll('img[data-orig]'), keep=[];
  imgs.forEach(function(i){{keep.push(i.getAttribute('src'));i.setAttribute('src',i.getAttribute('data-orig'));}});
  var h=el.innerHTML, txt=el.innerText;
  imgs.forEach(function(i,k){{i.setAttribute('src',keep[k]);}});
  try{{
    if(window.ClipboardItem&&navigator.clipboard&&navigator.clipboard.write){{
      await navigator.clipboard.write([new ClipboardItem({{'text/html':new Blob([h],{{type:'text/html'}}),'text/plain':new Blob([txt],{{type:'text/plain'}})}})]);
      say('복사했어요! 네이버 글쓰기 창에 붙여 넣으세요 (Ctrl+V)');return;
    }}
  }}catch(e){{}}
  imgs.forEach(function(i){{i.setAttribute('src',i.getAttribute('data-orig'));}});
  var r=document.createRange();r.selectNodeContents(el);var s=window.getSelection();s.removeAllRanges();s.addRange(r);
  var ok=false;try{{ok=document.execCommand('copy');}}catch(e){{}}
  imgs.forEach(function(i,k){{i.setAttribute('src',keep[k]);}});
  if(ok){{s.removeAllRanges();say('복사했어요! 네이버 글쓰기 창에 붙여 넣으세요 (Ctrl+V)');}}
  else say('선택해 두었어요 — Ctrl+C 를 눌러 복사해 주세요');
}}
</script></body></html>"""


if __name__ == "__main__":
    body_f, title, cat, *rest = sys.argv[1:]
    *photos, out = rest
    urls = []
    for p in photos:  # images/naver/ID-N.jpg → result.json 의 jsDelivr 주소
        jid = re.sub(r"-\d+\.jpg$", "", Path(p).name)
        rj = ROOT / f"naver/jobs/{jid}.result.json"
        if rj.exists():
            import json
            urls = json.loads(rj.read_text(encoding="utf-8")).get("images", [])
    Path(out).write_text(build(Path(body_f).read_text(encoding="utf-8"), title, cat, photos, urls), encoding="utf-8")
    print("만듦:", out)
