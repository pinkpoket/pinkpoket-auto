#!/usr/bin/env python3
"""핑크포켓 블로그 자동 발행 봇 (구글 블로거).

GitHub Actions에서 실행된다.
1) posts/ 폴더에서 아직 안 올린 글(JSON)을 이름순으로 찾는다.
2) 위키미디어 공용에서 자유 이용 사진을 찾아 넣는다(선택).
3) 어울리는 쿠팡 파트너스 상품이 있으면 대가성 문구와 함께 넣는다.
4) 유튜브·스레드 채널 링크 상자를 글 끝에 붙인다.
5) Blogger API로 바로 발행하고, 텔레그램으로 알린다(선택).

글 JSON 형식:
{
  "title": "제목",
  "labels": ["라벨", ...],
  "html": "본문 HTML",
  "photo": "영어 사진 검색어" 또는 "없음",
  "category": "쿠팡 상품 분류" 또는 "없음",
  "coupang": [{"url": "https://link.coupang.com/a/...", "name": "상품명"}]   (선택, 직접 고른 상품)
}

외부 패키지 없이 파이썬 표준 라이브러리만 쓴다.
"""

import datetime as dt
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
LINKS_FILE = os.path.join(ROOT, "data", "coupang_links.txt")
STATE_FILE = os.path.join(ROOT, "data", "posted.json")

KST = dt.timezone(dt.timedelta(hours=9))
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
USER_AGENT = "pinkpoket-blog-bot/1.0 (personal blog; github actions)"
NO_LINK = ("없음", "")
DEFAULT_NOTICE = "제품 가격·구성은 판매처 사정에 따라 바뀔 수 있어요. 구매 전 상세 페이지를 꼭 확인해 주세요 💗"
MAX_LINKS = 3


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


# ---------------------------------------------------------------- 본문 정리

ALLOWED_TAGS = {"h2", "h3", "p", "ul", "ol", "li", "strong", "b", "em", "table",
                "thead", "tbody", "tr", "th", "td", "br", "blockquote"}


def sanitize_html(body):
    """허용하지 않는 태그는 지우고(내용은 남김), 모든 속성을 없앤다."""
    body = re.sub(r"<\s*(script|style|iframe)[^>]*>.*?<\s*/\s*\1\s*>", "", body, flags=re.S | re.I)

    def fix(match):
        closing, tag = match.group(1), match.group(2).lower()
        return f"<{closing}{tag}>" if tag in ALLOWED_TAGS else ""

    return re.sub(r"<\s*(/?)\s*([a-zA-Z0-9]+)[^>]*>", fix, body)


# ---------------------------------------------------------------- 사진(위키미디어 공용)

def find_photo(query):
    if not query or query == "없음":
        return None
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": "6", "gsrlimit": "10",
        "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": "1200",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        data = http_json(url, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"[사진] 검색 실패: {e}")
        return None
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        if not license_name or "fair use" in license_name.lower():
            continue
        if info.get("width", 0) < 800 or info.get("width", 0) < info.get("height", 0):
            continue
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip() or "작성자 미상"
        return {
            "src": info.get("thumburl") or info.get("url"),
            "page": info.get("descriptionurl", ""),
            "credit": f"사진: {artist[:60]} / {license_name} / 위키미디어 공용",
        }
    return None


# ---------------------------------------------------------------- 글 조립

def channel_box():
    youtube = os.environ.get("YOUTUBE_CHANNEL_URL", "").strip()
    threads = os.environ.get("THREADS_URL", "").strip()
    if not youtube and not threads:
        return ""
    rows = []
    if youtube:
        sub = youtube + ("&" if "?" in youtube else "?") + "sub_confirmation=1"
        rows.append(f'<p style="margin:0 0 8px"><a href="{html.escape(sub)}" target="_blank" rel="noopener">'
                    "▶ 유튜브에서 살림 꿀팁 쇼츠 보기 &amp; 구독하기</a></p>")
    if threads:
        rows.append(f'<p style="margin:0"><a href="{html.escape(threads)}" target="_blank" rel="noopener">'
                    "🧵 스레드에서 핑크포켓 매일 만나기</a></p>")
    return ('<div style="border:1px solid #f6c9dc;border-radius:12px;padding:16px;margin:28px 0;background:#fff5f9">'
            '<p style="margin:0 0 8px;font-weight:bold">💗 핑크포켓을 다른 곳에서도 만나요</p>'
            + "".join(rows) + "</div>")


def assemble(title, body, photo, links, notice):
    parts = []
    if links:
        # 대가성 문구: 본문과 분리된 회색 상자로 맨 위에
        parts.append('<div style="font-size:13px;color:#777;background:#f5f5f5;border-radius:8px;'
                     f'padding:10px 14px;margin:0 0 24px">📢 {html.escape(DISCLOSURE)}</div>')
    if photo:
        parts.append(
            '<div style="text-align:center;margin:0 0 20px">'
            f'<img src="{html.escape(photo["src"])}" alt="{html.escape(title)}" '
            'style="max-width:100%;height:auto;border-radius:10px" loading="lazy">'
            f'<div style="font-size:12px;color:#888;margin-top:6px"><a href="{html.escape(photo["page"])}" '
            f'rel="nofollow noopener" target="_blank">{html.escape(photo["credit"])}</a></div></div>')
    parts.append(body)
    if links:
        items = "".join(
            f'<p style="margin:0 0 10px">🛒 <strong>{html.escape(l["name"])}</strong><br>'
            f'<a href="{html.escape(l["url"])}" rel="sponsored nofollow noopener" target="_blank">쿠팡에서 보기 &rarr;</a></p>'
            for l in links)
        parts.append('<div style="border:1px solid #f6c9dc;border-radius:12px;padding:16px;margin:28px 0;background:#fffafc">'
                     '<p style="margin:0 0 10px;font-weight:bold">🎀 핑크포켓이 골라 본 아이템</p>' + items + "</div>")
    parts.append(channel_box())
    parts.append(f'<p style="font-size:13px;color:#888">{html.escape(notice or DEFAULT_NOTICE)}</p>')
    return "\n".join(p for p in parts if p)


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


def publish(token, title, content, labels):
    blog_id = env("BLOGGER_BLOG_ID")
    body = {"kind": "blogger#post", "title": title, "content": content, "labels": labels}
    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/?isDraft=false"
    res = http_json(url, data=body, headers={"Authorization": f"Bearer {token}"}, method="POST")
    return res.get("url", ""), res.get("id", "")


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


def build(name, state):
    with open(os.path.join(POSTS_DIR, name), encoding="utf-8") as f:
        obj = json.load(f)
    title = str(obj.get("title", "")).strip()
    body = sanitize_html(str(obj.get("html", "")))
    if not title or not body.strip():
        raise ValueError("title 또는 html 이 비어 있습니다")
    labels = [str(x).strip() for x in obj.get("labels", []) if str(x).strip()][:8]
    photo = find_photo(str(obj.get("photo", "")).strip())
    links = pick_links(obj, state)
    content = assemble(title, body, photo, links, str(obj.get("notice", "")).strip())
    return title, labels, content, links


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
            title, labels, content, links = build(name, state)
        except Exception as e:  # noqa: BLE001
            print(f"[대기 글] {name} 읽기 실패, 건너뜀: {e}")
            state["posted"].append({"file": name, "skipped": str(e)[:200]})
            save_state(state)
            continue

        if dry_run:
            out = os.path.join(ROOT, "preview.html")
            with open(out, "w", encoding="utf-8") as f:
                f.write(f'<meta charset="utf-8"><h1>{html.escape(title)}</h1>\n{content}')
            print(f"[시험] {name} → preview.html 저장 (발행 안 함)")
            return 0

        try:
            post_url, post_id = publish(token, title, content, labels)
        except Exception as e:  # noqa: BLE001
            failed += 1
            msg = f"[블로그] 발행 실패\n글: {title}\n원인: {str(e)[:300]}"
            print(msg)
            notify(msg)
            continue

        state["posted"].append({"file": name, "title": title, "url": post_url, "post_id": post_id,
                                "at": now.strftime("%Y-%m-%d %H:%M"),
                                "links": [l["url"] for l in links]})
        for l in links:
            used = [u for u in state.get("used_links", []) if u != l["url"]]
            used.append(l["url"])
            state["used_links"] = used
        save_state(state)
        msg = f"[핑크포켓 블로그] 새 글 발행 💗\n{title}\n{post_url}"
        print(msg)
        notify(msg)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
