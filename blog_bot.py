#!/usr/bin/env python3
"""핑포의 작은집 연구소(핑크포켓) 블로그 자동 발행 봇 (구글 블로거).

GitHub Actions에서 실행된다.
1) posts/ 폴더에서 아직 안 올린 글(JSON)을 이름순으로 찾는다.
2) 모바일에서 읽기 좋게 본문을 꾸미고, 목차·자주 묻는 질문·작성자 상자를 붙인다.
3) images/ 에 만들어 둔 대표 이미지가 있으면 넣는다 (make_images.py 가 만든다).
4) 쿠팡 파트너스 상품이 있으면 대가성 문구와 함께 넣는다.
5) 같은 시리즈 글끼리 서로 링크를 걸고, 유튜브·스레드 링크를 붙인다.
6) 영어 주소(slug)로 발행한 뒤 한글 제목으로 바꿔 검색에 좋은 주소를 만든다.

글 JSON 형식:
{
  "title": "한글 제목",
  "slug": "english-keywords-for-url",            (선택, 영어 소문자와 - 만)
  "description": "검색 결과용 요약 120자",       (선택)
  "labels": ["라벨", ...],
  "series": "시리즈 이름", "series_no": 1,        (선택)
  "images": [{"prompt": "english prompt", "alt": "한글 설명"}],   (선택, 최대 2)
  "faq": [{"q": "질문", "a": "답"}],              (선택)
  "category": "쿠팡 상품 분류" 또는 "없음",
  "coupang": [{"url": "https://link.coupang.com/a/...", "name": "상품명"}],   (선택)
  "notice": "글 끝 안내 문구",                    (선택)
  "html": "본문 HTML"
}

외부 패키지 없이 파이썬 표준 라이브러리만 쓴다.
"""

import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(ROOT, "posts")
IMAGES_DIR = os.path.join(ROOT, "images")
LINKS_FILE = os.path.join(ROOT, "data", "coupang_links.txt")
STATE_FILE = os.path.join(ROOT, "data", "posted.json")

KST = dt.timezone(dt.timedelta(hours=9))
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
USER_AGENT = "pinkpoket-blog-bot/1.1 (personal blog; github actions)"
NO_LINK = ("없음", "")
DEFAULT_NOTICE = "제품 가격·구성은 판매처 사정에 따라 바뀔 수 있어요. 구매 전 상세 페이지를 꼭 확인해 주세요 💗"
MAX_LINKS = 3
REPO = os.environ.get("GITHUB_REPOSITORY", "pinkpoket/pinkpoket-auto")

PINK = "#e0559a"
PINK_SOFT = "#fff5f9"
PINK_LINE = "#f6c9dc"


# ---------------------------------------------------------------- 공통 도구

def env(name, required=True):
    value = os.environ.get(name, "").strip()
    if required and not value:
        raise SystemExit(f"[설정 오류] GitHub 비밀값 {name} 이(가) 비어 있습니다.")
    return value


def http_json(url, data=None, headers=None, method=None, timeout=120):
    headers = dict(headers or {})
    headers.setdefault("User-Agent", USER_AGENT)
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
            headers.setdefault("Content-Type", "application/json; charset=utf-8")
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = data
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        raise RuntimeError(f"HTTP {e.code} {url.split('?')[0]}: {detail}") from None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"posted": [], "used_links": []}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_post(name):
    with open(os.path.join(POSTS_DIR, name), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- 쿠팡 링크

def read_links():
    """data/coupang_links.txt 형식: 링크 | 상품명 | 분류"""
    links = []
    if not os.path.exists(LINKS_FILE):
        return links
    with open(LINKS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2 or not parts[0].startswith("https://link.coupang.com/"):
                continue
            links.append({"url": parts[0], "name": parts[1],
                          "category": parts[2] if len(parts) > 2 else ""})
    return links


def pick_links(obj, state):
    """글에 직접 고른 상품이 있으면 그것을, 없으면 분류에 맞는 상품 1개."""
    chosen = []
    for item in obj.get("coupang") or []:
        url = str(item.get("url", "")).strip()
        name = str(item.get("name", "")).strip()
        if url.startswith("https://link.coupang.com/") and name:
            chosen.append({"url": url, "name": name})
    if chosen:
        return chosen[:MAX_LINKS]
    category = str(obj.get("category", "")).strip()
    if category in NO_LINK:
        return []
    links = read_links()
    pool = [l for l in links if l["category"] == category] or \
           [l for l in links if l["category"] in ("", "공통")]
    if not pool:
        return []
    used = state.get("used_links", [])
    pool.sort(key=lambda l: used.index(l["url"]) if l["url"] in used else -1)
    return pool[:1]


# ---------------------------------------------------------------- 본문 정리·꾸미기

ALLOWED_TAGS = {"h2", "h3", "p", "ul", "ol", "li", "strong", "b", "em", "table",
                "thead", "tbody", "tr", "th", "td", "br", "blockquote"}

STYLES = {
    "p": "font-size:16px;line-height:1.85;margin:0 0 16px;word-break:keep-all",
    "h2": (f"font-size:20px;line-height:1.5;margin:36px 0 14px;padding:10px 14px;"
           f"background:{PINK_SOFT};border-left:5px solid {PINK};border-radius:6px;word-break:keep-all"),
    "h3": f"font-size:17px;line-height:1.5;margin:24px 0 10px;color:{PINK};word-break:keep-all",
    "ul": "margin:0 0 18px;padding-left:22px",
    "ol": "margin:0 0 18px;padding-left:22px",
    "li": "font-size:16px;line-height:1.8;margin:0 0 6px;word-break:keep-all",
    "strong": "color:#333",
    "blockquote": (f"margin:20px 0;padding:14px 16px;background:#fafafa;border-left:4px solid {PINK_LINE};"
                   "border-radius:6px;font-size:15px;line-height:1.8"),
    "table": "width:100%;border-collapse:collapse;font-size:15px;line-height:1.6;min-width:300px",
    "th": f"background:{PINK_SOFT};border:1px solid {PINK_LINE};padding:10px 8px;text-align:left;word-break:keep-all",
    "td": f"border:1px solid {PINK_LINE};padding:10px 8px;vertical-align:top;word-break:keep-all",
}


def sanitize_html(body):
    """허용하지 않는 태그는 지우고(내용은 남김), 모든 속성을 없앤다."""
    body = re.sub(r"<\s*(script|style|iframe)[^>]*>.*?<\s*/\s*\1\s*>", "", body, flags=re.S | re.I)

    def fix(match):
        closing, tag = match.group(1), match.group(2).lower()
        return f"<{closing}{tag}>" if tag in ALLOWED_TAGS else ""

    return re.sub(r"<\s*(/?)\s*([a-zA-Z0-9]+)[^>]*>", fix, body)


def style_html(body):
    """모바일에서 읽기 좋게 태그마다 인라인 스타일을 넣고, 표는 가로 스크롤 상자로 감싼다."""
    def add(match):
        tag = match.group(1)
        return f'<{tag} style="{STYLES[tag]}">'
    body = re.sub(r"<(%s)>" % "|".join(STYLES), add, body)
    body = re.sub(r'(<table style="[^"]*">)', r'<div style="overflow-x:auto;margin:0 0 20px">\1', body)
    return body.replace("</table>", "</table></div>")


def add_toc(body):
    """h2 소제목에 앵커를 달고, 첫 소제목 앞에 목차를 넣는다."""
    heads = []

    def anchor(match):
        text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        hid = f"s{len(heads) + 1}"
        heads.append((hid, text))
        return f'<h2 id="{hid}"{match.group(1)}>{match.group(2)}</h2>'

    body = re.sub(r"<h2([^>]*)>(.*?)</h2>", anchor, body, flags=re.S)
    if len(heads) < 3:
        return body
    items = "".join(
        f'<li style="margin:0 0 6px;font-size:15px;line-height:1.6"><a href="#{hid}" '
        f'style="color:#555;text-decoration:none">{html.escape(text)}</a></li>' for hid, text in heads)
    toc = (f'<div style="border:1px solid {PINK_LINE};border-radius:12px;padding:14px 16px;margin:8px 0 28px;'
           f'background:#fff">'
           f'<p style="margin:0 0 8px;font-weight:bold;font-size:15px">📌 이 글의 목차</p>'
           f'<ol style="margin:0;padding-left:20px">{items}</ol></div>')
    first = body.find("<h2")
    return body[:first] + toc + body[first:]


def faq_html(faq):
    rows = []
    for item in faq or []:
        q, a = str(item.get("q", "")).strip(), str(item.get("a", "")).strip()
        if q and a:
            rows.append(
                f'<div style="margin:0 0 14px"><p style="margin:0 0 4px;font-size:16px;font-weight:bold">'
                f'Q. {html.escape(q)}</p><p style="margin:0;font-size:15px;line-height:1.8;color:#444">'
                f'A. {html.escape(a)}</p></div>')
    if not rows:
        return ""
    return (f'<h2 style="{STYLES["h2"]}">🙋 자주 묻는 질문</h2>' + "".join(rows))


# ---------------------------------------------------------------- 이미지

def image_file(name, idx):
    stem = os.path.splitext(name)[0]
    return f"{stem}-{idx + 1}.jpg"


def image_url(fname):
    sha = os.environ.get("IMAGES_SHA", "").strip() or "main"
    return f"https://cdn.jsdelivr.net/gh/{REPO}@{sha}/images/{fname}"


def images_for(name, obj, state=None):
    """이미 만들어 둔 이미지 파일이 있으면 (url, alt) 목록을 돌려준다."""
    saved = {}
    if state:
        for p in state["posted"]:
            if p.get("file") == name and p.get("images"):
                saved = {i: u for i, u in enumerate(p["images"])}
    out = []
    for idx, item in enumerate((obj.get("images") or [])[:2]):
        alt = str(item.get("alt", "")).strip() or str(obj.get("title", ""))
        if idx in saved:
            out.append((saved[idx], alt))
        elif os.path.exists(os.path.join(IMAGES_DIR, image_file(name, idx))):
            out.append((image_url(image_file(name, idx)), alt))
    return out


def figure(url, alt):
    return ('<div style="text-align:center;margin:0 0 24px">'
            f'<img src="{html.escape(url)}" alt="{html.escape(alt)}" width="1024" height="1024" '
            'style="width:100%;height:auto;border-radius:12px" loading="lazy">'
            '<div style="font-size:12px;color:#999;margin-top:6px">AI로 만든 이미지예요</div></div>')


def insert_mid_image(body, fig):
    """두 번째 이미지는 본문 가운데쯤 소제목 앞에 넣는다."""
    starts = [m.start() for m in re.finditer(r"<h2", body)]
    if len(starts) < 3:
        return body + fig
    pos = starts[len(starts) // 2]
    return body[:pos] + fig + body[pos:]


# ---------------------------------------------------------------- 글 조립

def channel_box():
    youtube = os.environ.get("YOUTUBE_CHANNEL_URL", "").strip()
    threads = os.environ.get("THREADS_URL", "").strip()
    if not youtube and not threads:
        return ""
    rows = []
    if youtube:
        sub = youtube + ("&" if "?" in youtube else "?") + "sub_confirmation=1"
        rows.append(f'<p style="margin:0 0 8px;font-size:15px"><a href="{html.escape(sub)}" target="_blank" rel="noopener">'
                    "▶ 유튜브에서 살림 꿀팁 쇼츠 보기 &amp; 구독하기</a></p>")
    if threads:
        rows.append(f'<p style="margin:0;font-size:15px"><a href="{html.escape(threads)}" target="_blank" rel="noopener">'
                    "🧵 스레드에서 핑크포켓 매일 만나기</a></p>")
    return (f'<div style="border:1px solid {PINK_LINE};border-radius:12px;padding:16px;margin:28px 0;background:{PINK_SOFT}">'
            '<p style="margin:0 0 8px;font-weight:bold;font-size:15px">💗 핑포를 다른 곳에서도 만나요</p>'
            + "".join(rows) + "</div>")


def series_box(obj, name, state):
    series = str(obj.get("series", "")).strip()
    if not series:
        return ""
    items = []
    for p in state["posted"]:
        if p.get("series") == series and p.get("url") and p.get("file") != name:
            items.append((p.get("series_no") or 99, p["title"], p["url"]))
    if not items:
        return ""
    items.sort()
    lis = "".join(
        f'<li style="margin:0 0 8px;font-size:15px;line-height:1.6"><a href="{html.escape(u)}">'
        f'{html.escape(t)}</a></li>' for _, t, u in items)
    return (f'<div style="border:1px solid {PINK_LINE};border-radius:12px;padding:16px;margin:28px 0;background:#fff">'
            f'<p style="margin:0 0 10px;font-weight:bold;font-size:15px">📚 「{html.escape(series)}」 시리즈 다른 글</p>'
            f'<ul style="margin:0;padding-left:20px">{lis}</ul></div>')


AUTHOR_BOX = (
    '<div style="border-top:1px solid #eee;margin:32px 0 0;padding:16px 0 0;font-size:14px;line-height:1.7;color:#666">'
    '<strong style="color:#333">✍️ 핑포의 작은집 연구소</strong> · 핑포(핑크포켓, Pink Pocket)가 작은 집도 예쁘고 편하게 가꾸는 인테리어·살림 방법을 정리해요. '
    '공식 자료와 확인된 정보를 바탕으로 AI 도구의 도움을 받아 쓰고 있어요.</div>')


def assemble(name, obj, state, links, images):
    title = str(obj.get("title", "")).strip()
    body = sanitize_html(str(obj.get("html", "")))
    body = add_toc(style_html(body))
    if len(images) > 1:
        body = insert_mid_image(body, figure(*images[1]))
    parts = []
    if links:
        parts.append('<div style="font-size:13px;color:#777;background:#f5f5f5;border-radius:8px;'
                     f'padding:10px 14px;margin:0 0 24px">📢 {html.escape(DISCLOSURE)}</div>')
    if images:
        parts.append(figure(*images[0]))
    parts.append(body)
    parts.append(faq_html(obj.get("faq")))
    if links:
        items = "".join(
            f'<p style="margin:0 0 12px;font-size:15px">🛒 <strong>{html.escape(l["name"])}</strong><br>'
            f'<a href="{html.escape(l["url"])}" rel="sponsored nofollow noopener" target="_blank">쿠팡에서 보기 &rarr;</a></p>'
            for l in links)
        parts.append(f'<div style="border:1px solid {PINK_LINE};border-radius:12px;padding:16px;margin:28px 0;background:#fffafc">'
                     '<p style="margin:0 0 10px;font-weight:bold;font-size:15px">🎀 핑포가 골라 본 아이템</p>' + items + "</div>")
    parts.append(series_box(obj, name, state))
    parts.append(channel_box())
    notice = str(obj.get("notice", "")).strip() or DEFAULT_NOTICE
    parts.append(f'<p style="font-size:13px;color:#888;line-height:1.7">{html.escape(notice)}</p>')
    parts.append(AUTHOR_BOX)
    return title, "\n".join(p for p in parts if p)


def build(name, state):
    obj = read_post(name)
    title = str(obj.get("title", "")).strip()
    if not title or not str(obj.get("html", "")).strip():
        raise ValueError("title 또는 html 이 비어 있습니다")
    labels = [str(x).strip() for x in obj.get("labels", []) if str(x).strip()][:8]
    links = pick_links(obj, state)
    images = images_for(name, obj, state)
    title, content = assemble(name, obj, state, links, images)
    return title, labels, content, links


# ---------------------------------------------------------------- Blogger

def google_access_token():
    data = urllib.parse.urlencode({
        "client_id": env("GOOGLE_CLIENT_ID"),
        "client_secret": env("GOOGLE_CLIENT_SECRET"),
        "refresh_token": env("GOOGLE_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    })
    res = http_json("https://oauth2.googleapis.com/token", data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    token = res.get("access_token")
    if not token:
        raise RuntimeError(f"구글 토큰 발급 실패: {res}")
    return token


def clean_slug(slug):
    slug = re.sub(r"[^a-z0-9-]+", "-", str(slug).lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:60]


def publish(token, title, content, labels, slug=""):
    """slug 가 있으면 영어 제목으로 먼저 발행해 주소를 만들고, 바로 한글 제목으로 바꾼다."""
    blog_id = env("BLOGGER_BLOG_ID")
    headers = {"Authorization": f"Bearer {token}"}
    first_title = slug.replace("-", " ") if slug else title
    body = {"kind": "blogger#post", "title": first_title, "content": content, "labels": labels}
    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/?isDraft=false"
    res = http_json(url, data=body, headers=headers, method="POST")
    post_id, post_url = res.get("id", ""), res.get("url", "")
    if slug and post_id:
        put_post(token, post_id, title, content, labels)
    return post_url, post_id


def put_post(token, post_id, title, content, labels):
    blog_id = env("BLOGGER_BLOG_ID")
    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/{post_id}"
    body = {"kind": "blogger#post", "id": post_id, "title": title, "content": content, "labels": labels}
    return http_json(url, data=body, headers={"Authorization": f"Bearer {token}"}, method="PUT")


def refresh_series(token, name, obj, state):
    """같은 시리즈의 예전 글들에 새 글 링크가 보이도록 다시 올린다."""
    series = str(obj.get("series", "")).strip()
    if not series:
        return
    for p in state["posted"]:
        if p.get("series") == series and p.get("post_id") and p.get("file") != name:
            try:
                t, labels, content, _ = build(p["file"], state)
                put_post(token, p["post_id"], t, content, labels)
                print(f"[시리즈] 링크 갱신: {t}")
            except Exception as e:  # noqa: BLE001
                print(f"[시리즈] {p.get('file')} 갱신 실패: {e}")


# ---------------------------------------------------------------- 텔레그램

def notify(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        http_json(f"https://api.telegram.org/bot{token}/sendMessage",
                  data={"chat_id": chat_id, "text": message}, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"[텔레그램] 알림 실패: {e}")


# ---------------------------------------------------------------- 실행

def pending_posts(state):
    if not os.path.isdir(POSTS_DIR):
        return []
    done = {p.get("file") for p in state["posted"]}
    return [n for n in sorted(os.listdir(POSTS_DIR)) if n.endswith(".json") and n not in done]


def main():
    dry_run = "--dry-run" in sys.argv
    now = dt.datetime.now(KST)
    state = load_state()
    names = pending_posts(state)
    if not names:
        print("[블로그] 올릴 대기 글이 없습니다.")
        return 0

    token = None if dry_run else google_access_token()
    failed = 0
    for name in names:
        try:
            obj = read_post(name)
            title, labels, content, links = build(name, state)
        except Exception as e:  # noqa: BLE001
            print(f"[대기 글] {name} 읽기 실패, 건너뜀: {e}")
            state["posted"].append({"file": name, "skipped": str(e)[:200]})
            save_state(state)
            continue

        if dry_run:
            out = os.path.join(ROOT, "preview.html")
            with open(out, "w", encoding="utf-8") as f:
                f.write('<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                        f'<div style="max-width:720px;margin:auto;padding:16px;font-family:sans-serif">'
                        f'<h1 style="font-size:22px;line-height:1.4">{html.escape(title)}</h1>\n{content}</div>')
            print(f"[시험] {name} → preview.html 저장 (발행 안 함)")
            return 0

        try:
            post_url, post_id = publish(token, title, content, labels, clean_slug(obj.get("slug", "")))
        except Exception as e:  # noqa: BLE001
            failed += 1
            msg = f"[블로그] 발행 실패\n글: {title}\n원인: {str(e)[:300]}"
            print(msg)
            notify(msg)
            continue

        state["posted"].append({
            "file": name, "title": title, "url": post_url, "post_id": post_id,
            "at": now.strftime("%Y-%m-%d %H:%M"), "links": [l["url"] for l in links],
            "series": str(obj.get("series", "")).strip(), "series_no": obj.get("series_no"),
            "images": [u for u, _ in images_for(name, obj)],
        })
        for l in links:
            used = [u for u in state.get("used_links", []) if u != l["url"]]
            used.append(l["url"])
            state["used_links"] = used
        save_state(state)
        refresh_series(token, name, obj, state)
        msg = f"[핑포의 작은집 연구소] 새 글 발행 💗\n{title}\n{post_url}"
        print(msg)
        notify(msg)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
