# -*- coding: utf-8 -*-
"""구글 Gemini 무료 API로 글·대본(JSON)을 써서 대기열에 넣는다.

Claude 크레딧을 아끼려고 만든 글쓰기 봇 (2026-11-06).
JOB 환경변수로 무엇을 쓸지 고른다.
  salim-blog   → posts/YYYYMMDD-HHMM.json        (+ data/series.json 갱신)
  news-blog    → news/posts/YYYYMMDD-HHMM.json   (오늘 뉴스는 언론사 RSS 에서 모음)
  salim-shorts → shorts/queue/YYYYMMDD-HHMM.json (아직 쇼츠 안 만든 살림 글 바탕)
  news-shorts  → news/shorts/queue/...           (방금 올라간 뉴스 글 바탕)
  naver        → naver/jobs/ID.json (사진 프롬프트만) + /tmp/naver_body.json (본문, 저장소에 안 올림)
  life-shorts  → life/shorts/queue/...           (지금은 Claude 가 씀 — 시험용)

필요: GEMINI_API_KEY (GitHub Secret)
"""
import datetime as dt
import glob
import html as htmlmod
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
API = "https://generativelanguage.googleapis.com/v1beta"
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
OUT_FILE = os.environ.get("GITHUB_OUTPUT")

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")

NO_SEARCH = """[인터넷 검색을 못 하는 상황이라 꼭 지킬 것 — 아래 규칙 파일의 '웹 검색' 단계는 건너뛴다]
- 가격·할인·통계·퍼센트·법 조항·기관 발표 숫자는 쓰지 않는다 (아래에 '자료'로 준 내용에 있는 숫자만 쓸 수 있다).
- 특정 기관·병원·연구·기사 이름을 근거로 들지 않는다 (아래 '자료'에 있는 출처 이름만 쓸 수 있다).
- 제품 사용법은 "제품 설명서·표시를 꼭 확인하세요"처럼 쓴다. 직접 써 본 척 하지 않는다.
- 쿠팡은 지금 넣지 않는다: coupang_keywords 는 빈 목록 [].
- 파일 저장·커밋·dry-run 같은 작업 지시는 무시한다 (봇이 한다). 너는 JSON 만 답한다.
"""


# ================================================================ Gemini
def list_models():
    r = requests.get(f"{API}/models", params={"key": KEY, "pageSize": 200}, timeout=30)
    r.raise_for_status()
    return [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


def ver(name):
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0


def pick_models(pref):
    """pref='flash' → 좋은 Flash 먼저, 막히면 Flash-Lite. pref='lite' → Lite 먼저."""
    ok = [n for n in list_models() if n.startswith("gemini-") and "flash" in n
          and not any(b in n for b in ("image", "tts", "audio", "live", "embedding", "exp"))]
    key = lambda n: ("preview" not in n, ver(n))
    flash = sorted([n for n in ok if "lite" not in n], key=key, reverse=True)
    lite = sorted([n for n in ok if "lite" in n], key=key, reverse=True)
    order = (flash[:3] + lite[:3]) if pref == "flash" else (lite[:3] + flash[:3])
    print("쓸 수 있는 모델:", order)
    return order


def generate(models, prompt, temperature=0.9):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last = ""
    for m in models:
        for attempt in range(2):
            try:
                r = requests.post(f"{API}/models/{m}:generateContent", params={"key": KEY},
                                  json=body, timeout=240)
            except requests.RequestException as e:
                last = f"{m}: 응답 없음 ({type(e).__name__})"
                print(last)
                break
            if r.status_code == 200:
                try:
                    txt = "".join(p.get("text", "") for p in
                                  r.json()["candidates"][0]["content"]["parts"])
                    print(f"모델 {m} 사용")
                    return txt
                except Exception as e:  # noqa
                    last = f"{m}: 응답 형식 오류 {e}"
                    break
            last = f"{m}: {r.status_code} {r.text[:120]}"
            print(f"{m}: {r.status_code}")
            if r.status_code in (429, 500, 503) and attempt == 0:
                time.sleep(20)
                continue
            break
    raise RuntimeError("Gemini 호출 실패 — " + last)


def parse_json(txt):
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip()).strip()
    d = json.loads(txt)
    return d[0] if isinstance(d, list) and d else d


def write_loop(models, prompt, check, tries=3):
    fb, errs = "", []
    for _ in range(tries):
        try:
            d = parse_json(generate(models, prompt + fb))
        except json.JSONDecodeError as e:
            errs = [f"JSON 형식이 깨짐 ({e})"]
        else:
            errs = check(d)
            if not errs:
                return d
        print("고칠 점:", errs)
        fb = "\n\n[이전 답의 문제 — 반드시 고쳐서 JSON 전체를 다시 써라]\n- " + "\n- ".join(errs)
    raise RuntimeError("규칙에 맞는 글을 3번 안에 못 썼어요: " + "; ".join(errs))


# ================================================================ 공통 도구
def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", path.relative_to(ROOT))
    if OUT_FILE:
        with open(OUT_FILE, "a") as f:
            f.write(f"file={path.relative_to(ROOT)}\n")


def plain(html, n=None):
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = re.sub(r"\s+", " ", htmlmod.unescape(t)).strip()
    return t[:n] if n else t


def titles_from(*globs_or_lists, n=60):
    out = []
    for g in globs_or_lists:
        if isinstance(g, list):
            out += g
        else:
            for f in sorted(glob.glob(str(ROOT / g)))[-n:]:
                t = (load(f, {}) or {}).get("title")
                if t:
                    out.append(t)
    seen, res = set(), []
    for t in reversed(out):
        if t not in seen:
            seen.add(t)
            res.append(t)
    return res[:n]


def latest_example(pattern, drop=()):
    files = sorted(glob.glob(str(ROOT / pattern)))
    for f in reversed(files):
        d = load(f)
        if d and "title" in d:
            for k in drop:
                d.pop(k, None)
            return d
    return {}


def ascii_slug(s):
    s = re.sub(r"[^a-z0-9-]+", "-", (s or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:70] or f"post-{NOW:%Y%m%d%H%M}"


def tg_chat(tok):
    """TELEGRAM_CHAT_ID 가 없으면 봇에게 말 건 사람(핑포)의 대화방을 찾는다."""
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if chat or not tok:
        return chat
    try:
        ups = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=20).json().get("result", [])
        for u in reversed(ups):
            c = (u.get("message") or {}).get("chat") or {}
            if c.get("type") == "private":
                return str(c["id"])
    except Exception:
        pass
    return ""


def telegram(msg):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = tg_chat(tok)
    if tok and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": msg}, timeout=20)
        except Exception:
            pass


def header(role):
    wd = "월화수목금토일"[NOW.weekday()]
    return (f"너는 {role}.\n오늘: {NOW:%Y년 %-m월 %-d일} ({wd}요일), 한국 시간 {NOW:%H시 %M분}\n"
            "답은 설명 없이 JSON 하나만.\n\n")


def check_blog(d, min_html, need=("title", "slug", "description", "labels", "images", "faq", "html")):
    errs = [f"{k} 칸이 없음" for k in need if not d.get(k)]
    if errs:
        return errs
    h = d["html"]
    if len(plain(h)) < min_html:
        errs.append(f"본문(html) 글자가 {len(plain(h))}자로 짧음 — {min_html}자 넘게, 소제목마다 내용을 충분히")
    if h.count("<h2") < 4:
        errs.append("<h2> 소제목이 4개 미만")
    if not 15 <= len(d["title"]) <= 60:
        errs.append(f"제목 {len(d['title'])}자 — 28~45자로")
    if not isinstance(d["images"], list) or not all(isinstance(i, dict) and i.get("prompt") for i in d["images"]):
        errs.append('images 는 [{"prompt": "english", "alt": "한국어"}] 형식')
    return errs


def check_scenes(d, n_lo, n_hi, c_lo, c_hi, hook_max=14):
    errs = [f"{k} 칸이 없음" for k in ("title", "hook", "scenes", "description", "tags", "comment") if not d.get(k)]
    if errs:
        return errs
    sc = d["scenes"]
    if not all(isinstance(s, dict) and s.get("text") and s.get("bg") for s in sc):
        return ['scenes 는 [{"text": "...", "bg": "english"}] 형식, text·bg 모두 채우기']
    total = sum(len(s["text"]) for s in sc)
    if not n_lo <= len(sc) <= n_hi:
        errs.append(f"장면이 {len(sc)}개 — {n_lo}~{n_hi}개로")
    if not c_lo <= total <= c_hi:
        errs.append(f"scenes text 합이 {total}자 — {c_lo}~{c_hi}자로 (장면마다 30~40자)")
    if len(d["hook"].replace("\\n", "").replace("\n", "")) > hook_max:
        errs.append(f"hook 이 {hook_max - 2}자를 넘음")
    if EMOJI.search(d["hook"] + "".join(s["text"] for s in sc)):
        errs.append("화면 글자(hook, scenes text)에 이모지가 있음")
    if re.search(r"https?://", d.get("comment", "")):
        errs.append("댓글에 링크가 있음")
    return errs


def unknown_numbers(text, source):
    """글에 나온 숫자 중 자료(source)에 없는 것 — 지어낸 숫자 막기."""
    src = re.sub(r"(?<=\d),(?=\d)", "", source)
    skip = {str(NOW.year), f"{NOW.year % 100}"}
    bad = []
    for n in re.findall(r"\d[\d,.]*\d|\d", re.sub(r"(?<=\d),(?=\d)", "", plain(text))):
        n = n.strip(".,")
        if len(n.replace(".", "")) < 3 or n in skip:
            continue
        if n not in src and n not in bad:
            bad.append(n)
    return bad


def dispatch(workflow):
    """GITHUB_TOKEN 으로 push 하면 다른 워크플로가 안 돌아서 직접 부른다 (워크플로 yml 에서)."""
    if OUT_FILE:
        with open(OUT_FILE, "a") as f:
            f.write(f"next={workflow}\n")


# ================================================================ 뉴스 모으기 (RSS)
RSS = {
    "top": ["https://www.yna.co.kr/rss/news.xml",
            "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"],
    "life": ["https://www.yna.co.kr/rss/economy.xml", "https://www.yna.co.kr/rss/society.xml",
             "https://news.google.com/rss/search?q=지원금+OR+환급+OR+신청+OR+제도+when:1d&hl=ko&gl=KR&ceid=KR:ko"],
    "money": ["https://www.yna.co.kr/rss/economy.xml", "https://www.yna.co.kr/rss/market.xml",
              "https://news.google.com/rss/search?q=부동산+OR+전세+OR+금리+OR+코스피+when:1d&hl=ko&gl=KR&ceid=KR:ko"],
}


def fetch_news(kind, limit=45):
    items, seen = [], set()
    for url in RSS[kind]:
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 (news-bot)"})
            root = ET.fromstring(r.content)
        except Exception as e:  # noqa
            print("RSS 실패", url, e)
            continue
        for it in root.iter("item"):
            title = plain(it.findtext("title", ""))
            src = plain(it.findtext("source", "")) or ("연합뉴스" if "yna.co.kr" in url else "")
            if " - " in title and "google" in url:
                title, src2 = title.rsplit(" - ", 1)
                src = src or src2
            key = re.sub(r"\W", "", title)[:25]
            if not title or key in seen:
                continue
            seen.add(key)
            desc = plain(it.findtext("description", ""), 300)
            if "google" in url:
                desc = ""
            items.append({"title": title, "source": src, "date": it.findtext("pubDate", ""), "summary": desc})
            if len(items) >= limit:
                return items
    return items


def news_text(items):
    return "\n".join(f"- [{i['source']}] {i['title']}" + (f" — {i['summary']}" if i["summary"] else "")
                     for i in items)


def news_corner():
    h = NOW.hour
    if h < 10:
        return "morning", "top", "☀️ 출근길 1분 뉴스 (아침 코너)"
    if h < 15:
        return "life", "life", "🛒 생활 꿀뉴스 (낮 코너)"
    return "money", "money", "💰 돈·부동산 뉴스 (저녁 코너)"


# ================================================================ 살림 블로그
def salim_blog(models):
    guide = (ROOT / "WRITING_GUIDE.md").read_text(encoding="utf-8")
    series = load(ROOT / "data/series.json", {"series": []})
    posted = [p.get("title") for p in (load(ROOT / "data/posted.json", {}) or {}).get("posted", [])]
    titles = titles_from(posted, "posts/*.json", n=60)
    cur = next((s for s in series["series"] if not s.get("done") and s.get("next", 1) <= len(s.get("plan", []))), None)
    if cur:
        task = (f"진행 중인 시리즈 「{cur['name']}」의 {cur['next']}편을 쓴다.\n"
                f"시리즈 계획: {json.dumps(cur['plan'], ensure_ascii=False)}\n"
                f"이번 편: {cur['plan'][cur['next'] - 1]}\n"
                f'JSON 의 series 는 "{cur["name"]}", series_no 는 {cur["next"]}.')
    else:
        task = ("진행 중인 시리즈가 없다. 계절(지금 날짜)에 맞는 새 시리즈를 3~5편으로 계획하고 1편을 쓴다.\n"
                'JSON 에 "new_series": {"name": "...", "plan": ["1. ...", "2. ..."]} 를 함께 넣고, series_no 는 1.')
    ex = latest_example("posts/*.json")
    prompt = header("살림·인테리어 블로그 「핑포의 작은집 연구소」의 글 작가") + f"""[할 일]
{task}

[이미 쓴 제목 — 겹치지 않게]
{chr(10).join('- ' + t for t in titles)}

{NO_SEARCH}
- notice 칸: 출처 기관 이름 없이 "제품 표시와 설명서를 꼭 함께 확인해 주세요" 류의 안내 한두 문장.
- category 는 "없음".

[형식 예시 — 최근 글 (키 이름·구조·html 모양을 이대로, 내용은 완전히 새로)]
{json.dumps(ex, ensure_ascii=False)}

[규칙]
{guide}
"""

    def check(d):
        e = check_blog(d, 2000)  # WRITING_GUIDE: 2,000~3,000자
        if not cur and not (d.get("new_series") or {}).get("plan"):
            e.append("new_series 칸(name, plan)이 없음")
        return e

    d = write_loop(models, prompt, check)
    d["slug"] = ascii_slug(d["slug"])
    d["coupang_keywords"] = []
    d["category"] = d.get("category") or "없음"
    if cur:
        d["series"], d["series_no"] = cur["name"], cur["next"]
        cur["next"] += 1
        if cur["next"] > len(cur["plan"]):
            cur["done"] = True
    else:
        ns = d.pop("new_series")
        series["series"].append({"name": ns["name"], "plan": ns["plan"], "next": 2, "done": len(ns["plan"]) < 2})
        d["series"], d["series_no"] = ns["name"], 1
    d["writer"] = "gemini"
    save(ROOT / f"posts/{NOW:%Y%m%d-%H%M}.json", d)
    save(ROOT / "data/series.json", series)
    dispatch("blog.yml")


# ================================================================ 오늘뉴스 블로그
def news_blog(models):
    guide = (ROOT / "news/WRITING_GUIDE.md").read_text(encoding="utf-8")
    corner, kind, name = news_corner()
    items = fetch_news(kind)
    if len(items) < 8:
        raise RuntimeError(f"오늘 뉴스를 {len(items)}개밖에 못 모았어요 (RSS)")
    posted = [p.get("title") for p in (load(ROOT / "news/data/posted.json", {}) or {}).get("posted", [])]
    titles = titles_from(posted, "news/posts/*.json", n=40)
    ex = latest_example("news/posts/*.json")
    prompt = header("뉴스 블로그 「핑포의 오늘뉴스」의 글 작가") + f"""[할 일]
지금은 {name} 차례다. 규칙 파일의 이 코너 형식대로 글 1편을 쓴다.

[오늘 모은 뉴스 — 이 목록에 있는 사실만 쓴다]
{news_text(items)}

[뉴스 사실 규칙 — 검색을 못 하므로 아주 엄격하게]
- 위 목록에 없는 사실·숫자·날짜·인물 발언을 지어내지 않는다. 목록의 제목·요약에 나온 숫자만 쓴다.
- 확실하지 않은 내용은 "~로 알려졌어요", "자세한 내용은 공식 발표를 확인하세요"로 쓴다.
- 기사 문장을 그대로 옮기지 말고 핑포의 말로 새로 쓴다.
- 마지막 문단 '참고한 곳'에는 위 목록의 언론사 이름만 적는다.
- 생활 꿀뉴스·돈부동산 뉴스는 목록에서 소식 하나를 골라, 목록에 있는 사실 + 누구나 아는 일반 상식(신청은 공식 누리집에서 확인 등)으로만 깊게 쓴다.
- coupang_keywords 는 빈 목록 [].

[이미 쓴 제목 — 겹치지 않게]
{chr(10).join('- ' + t for t in titles)}

[형식 예시 — 최근 글 (키 이름·구조·html 모양을 이대로, 내용은 완전히 새로)]
{json.dumps(ex, ensure_ascii=False)}

[규칙]
{guide}
"""
    label = {"morning": "출근길뉴스", "life": "생활꿀뉴스", "money": "돈부동산뉴스"}[corner]

    def check(d):
        e = check_blog(d, 1800)  # news/WRITING_GUIDE: 1,800~2,800자 (모든 코너)
        if label not in (d.get("labels") or []):
            e.append(f'labels 에 "{label}" 이 없음')
        if "참고한 곳" not in d.get("html", ""):
            e.append("본문 끝 '참고한 곳' 문단이 없음")
        bad = unknown_numbers(d.get("html", "") + " " + json.dumps(d.get("faq", []), ensure_ascii=False)
                              + " " + d.get("title", ""), news_text(items))
        if len(bad) > 1:
            e.append(f"뉴스 목록에 없는 숫자를 썼음: {', '.join(bad[:8])} — 지우거나 목록에 있는 숫자로만")
        return e

    d = write_loop(models, prompt, check)
    d["slug"] = ascii_slug(d["slug"])
    d["coupang_keywords"] = []
    d["writer"] = "gemini"
    save(ROOT / f"news/posts/{NOW:%Y%m%d-%H%M}.json", d)
    dispatch("blog-news.yml")


# ================================================================ 살림 쇼츠
def salim_shorts(models):
    guide = (ROOT / "SHORTS_GUIDE.md").read_text(encoding="utf-8")
    used = {(load(f, {}) or {}).get("blog_url") for f in glob.glob(str(ROOT / "shorts/done/*.json"))}
    used |= {(load(f, {}) or {}).get("blog_url") for f in glob.glob(str(ROOT / "shorts/queue/*.json"))}
    posted = (load(ROOT / "data/posted.json", {}) or {}).get("posted", [])
    pick = next((p for p in reversed(posted[-20:]) if p.get("url") and p["url"] not in used), None)
    if pick:
        src = load(ROOT / "posts" / pick["file"], {}) or {}
        task = (f"아래 블로그 글을 바탕으로 쇼츠 대본을 쓴다 (블로그로 다시 들어오게).\n"
                f"글 제목: {pick['title']}\n글 내용: {plain(src.get('html', ''), 3500)}")
    else:
        task = "블로그 글에 없는 짧은 살림·인테리어 꿀팁 하나로 쓴다 (계절에 맞게, 숫자·가격 없이)."
    titles = titles_from("shorts/done/*.json", n=30)
    ex = latest_example("shorts/done/*.json")
    prompt = header("유튜브 쇼츠 채널 「핑포의 작은집 연구소」의 대본 작가") + f"""[할 일]
{task}

[최근 쇼츠 제목 — 겹치지 않게]
{chr(10).join('- ' + t for t in titles)}

{NO_SEARCH}
- 쇼츠는 22~28초 (30초 미만): 장면 5~6개, 장면당 30~40자(첫 장면 훅만 15~25자), scenes text 합 170~200자.
- 블로그 글 내용에 있는 사실만 쓴다.

[형식 예시 — 최근 대본 (키 이름·구조를 이대로, 내용은 새로)]
{json.dumps(ex, ensure_ascii=False)}

[규칙]
{guide}
"""
    d = write_loop(models, prompt, lambda d: check_scenes(d, 5, 6, 170, 200))  # SHORTS_GUIDE: 170~200자
    d["blog_url"] = pick["url"] if pick else ""
    d["voice"] = ex.get("voice", "ko-KR-SunHiNeural")
    d["coupang_keywords"] = []
    d["writer"] = "gemini"
    save(ROOT / f"shorts/queue/{NOW:%Y%m%d-%H%M}.json", d)
    dispatch("shorts.yml")


# ================================================================ 오늘뉴스 쇼츠
def news_shorts(models):
    guide = (ROOT / "news/SHORTS_GUIDE.md").read_text(encoding="utf-8")
    corner, kind, name = news_corner()
    today = f"{NOW:%Y%m%d}"
    latest = sorted(glob.glob(str(ROOT / f"news/posts/{today}-*.json")))
    post, src = None, {}
    if latest:  # 방금 쓴 뉴스 글이 블로그에 올라갈 때까지 최대 20분 기다림
        fname = os.path.basename(latest[-1])
        for _ in range(20):
            posted = (load(ROOT / "news/data/posted.json", {}) or {}).get("posted", [])
            post = next((p for p in posted if p.get("file") == fname), None)
            if post:
                break
            print("블로그 글이 올라가길 기다리는 중…")
            time.sleep(60)
            subprocess.run(["git", "pull", "-q", "--rebase", "origin", "main"], cwd=ROOT, check=False)
        src = load(latest[-1], {}) or {}
    if post:
        task = (f"지금은 {name} 차례. 아래 방금 올린 블로그 글을 바탕으로 쓴다.\n"
                f"글 제목: {post['title']}\n글 내용: {plain(src.get('html', ''), 3500)}")
        facts = "블로그 글 내용에 있는 사실·숫자만 쓴다."
        source = plain(src.get("html", "")) + " " + post["title"]
    else:
        items = fetch_news(kind, 30)
        task = f"지금은 {name} 차례. 아래 오늘 뉴스 목록으로 쓴다.\n{news_text(items)}"
        facts = "위 뉴스 목록에 있는 사실·숫자만 쓴다."
        source = news_text(items)
    titles = titles_from("news/shorts/done/*.json", n=30)
    ex = latest_example("news/shorts/done/*.json")
    LEN = {"morning": "장면 7개(훅 1장면 15~25자 + 첫째~다섯째 소식 한 장면씩 30~40자 + 마무리 1장면), scenes text 합 230~280자, 60초 미만.",
           "life": "22~28초, 30초 미만. 장면 5~6개, 장면당 30~40자(첫 장면 훅만 15~25자), scenes text 합 170~200자.",
           "money": "22~28초, 30초 미만. 장면 5~6개, 장면당 30~40자(첫 장면 훅만 15~25자), scenes text 합 170~200자. 마지막 장면이나 설명란에 \"투자 판단은 본인 몫\"."}
    rng = (7, 7, 220, 290) if corner == "morning" else (5, 6, 160, 215)
    prompt = header("유튜브 쇼츠 채널 「핑포의 오늘뉴스」의 대본 작가") + f"""[할 일]
{task}

[사실 규칙] {facts} 지어내지 않는다. 투자 권유·예측 금지. 정치 중립.
- 길이: {LEN[corner]}
- coupang_keywords 는 빈 목록 [].

[최근 쇼츠 제목 — 겹치지 않게]
{chr(10).join('- ' + t for t in titles)}

[형식 예시 — 최근 대본 (키 이름·구조를 이대로, 내용은 새로)]
{json.dumps(ex, ensure_ascii=False)}

[규칙]
{guide}
"""
    def check(d):
        e = check_scenes(d, *rng)
        if not e:
            bad = unknown_numbers(" ".join(x["text"] for x in d["scenes"]) + " " + d["title"]
                                  + " " + d.get("description", ""), source)
            if len(bad) > 1:
                e.append(f"자료에 없는 숫자를 썼음: {', '.join(bad[:8])} — 지우거나 자료의 숫자로만")
        return e

    d = write_loop(models, prompt, check)
    d["blog_url"] = post["url"] if post else ""
    d["voice"] = ex.get("voice", "ko-KR-SunHiNeural")
    d["coupang_keywords"] = []
    d.pop("rate", None)
    if corner == "morning":
        d["rate"] = "+40%"
    for s in d["scenes"]:
        s["bg"] = ""  # 오늘뉴스는 고정 배경 한 장
    d["writer"] = "gemini"
    save(ROOT / f"news/shorts/queue/{NOW:%Y%m%d-%H%M}.json", d)
    dispatch("shorts-news.yml")


# ================================================================ 네이버 원고
def naver(models):
    guide = (ROOT / "NAVER_GUIDE.md").read_text(encoding="utf-8")
    log = (ROOT / "naver/log.txt").read_text(encoding="utf-8")
    posted = (load(ROOT / "data/posted.json", {}) or {}).get("posted", [])
    week_ago = (NOW - dt.timedelta(days=7)).strftime("%Y-%m-%d")
    recent_google = [p["title"] for p in posted if p.get("at", "") >= week_ago]
    series = load(ROOT / "data/series.json", {"series": []})
    upcoming = [x for s in series["series"] if not s.get("done") for x in s["plan"][s.get("next", 1) - 1:]]
    used_ids = set(re.findall(r"쇼츠:([\w-]+)", log))
    last_id = (re.findall(r"쇼츠:([\w-]+)", log) or [""])[-1]
    blog_of = {}
    for f in glob.glob(str(ROOT / "shorts/done/*.json")):
        d = load(f, {}) or {}
        blog_of[d.get("title")] = d.get("blog_url", "")
    shorts = [s for s in (load(ROOT / "data/shorts_log.json", []) or [])
              if s.get("privacy") == "public" and s.get("url") and s.get("video_id") != last_id]
    old_blog = {p["url"]: p.get("at", "") for p in posted}
    lines = []
    for s in shorts[-40:]:
        b = blog_of.get(s["title"], "")
        age = "블로그 글 8일 이상 지남" if b and old_blog.get(b, "9999") < (NOW - dt.timedelta(days=8)).strftime("%Y-%m-%d") else ""
        lines.append(f"- {s['video_id']} | {s['title']} | {s['url']}"
                     + (" | 이미 네이버에 씀" if s["video_id"] in used_ids else "") + (f" | {age}" if age else ""))
    prompt = header("네이버 블로그 「핑포의 작은집 연구소」의 원고 작가") + f"""[할 일]
규칙대로 네이버 원고 1편을 쓴다.

[네이버에 이미 쓴 제목 (log)]
{log}

[최근 7일 구글 블로그 제목 — 겹치지 않게]
{chr(10).join('- ' + t for t in recent_google)}

[구글 블로그에 곧 올라갈 주제 — 피하기]
{chr(10).join('- ' + t for t in upcoming) or '- 없음'}

[고를 수 있는 공개 쇼츠 (video_id | 제목 | 주소)]
{chr(10).join(lines)}

{NO_SEARCH}
- 네이버 인기 키워드는 검색 대신 계절(지금 날짜)·자취·전셋집·다이소·청소법 같은 일반적으로 많이 찾는 주제에서 고른다.

[답 JSON 형식]
{{"category": "정리·수납|청소·세탁|주방 살림|집꾸미기·인테리어|계절 살림 중 하나",
 "title": "25~35자",
 "body_html": "본문 복사 영역에 들어갈 HTML 전체 (규칙의 STEP 소제목, 문단 사이 <p>&nbsp;</p>, 📷 [사진 1]~[사진 3] 자리, 쇼츠 링크, 채널 링크, 서명 그림, 마지막 줄 태그 10개까지)",
 "images": [{{"prompt": "english, 사람·글자·로고 없는 집 안 장면"}}, {{...}}, {{...}}],
 "shorts_video_id": "본문에 넣은 쇼츠의 video_id (채널 쇼츠 링크만 넣었으면 빈 문자열)"}}

[규칙]
{guide}
"""
    sig = "naver-signature.png"
    ids = {s["video_id"]: s for s in shorts}

    def check(d):
        e = [f"{k} 칸이 없음" for k in ("category", "title", "body_html", "images") if not d.get(k)]
        if e:
            return e
        b = d["body_html"]
        n = len(plain(b))
        if not 1400 <= n <= 2800:
            e.append(f"본문 글자 {n}자 — 1,500~2,200자로")
        if b.count("STEP") < 3:
            e.append("STEP 말머리 소제목이 3개 미만")
        if "<p>&nbsp;</p>" not in b:
            e.append("문단 사이 <p>&nbsp;</p> 빈 줄이 없음")
        if sig not in b:
            e.append("서명 그림(naver-signature.png)이 없음")
        if "UCF2kFXxCID0pGH0l8RD0iKA" not in b:
            e.append("채널 링크가 없음")
        for k in (1, 2, 3):
            if f"[사진 {k}]" not in b:
                e.append(f"📷 [사진 {k}] 자리 표시가 없음")
        vid = d.get("shorts_video_id", "")
        if vid and (vid not in ids or ids[vid]["url"] not in b):
            e.append("shorts_video_id 가 목록에 없거나 본문에 그 쇼츠 주소가 없음")
        if not vid and "/shorts\"" not in b and "/shorts'" not in b:
            e.append("쇼츠 링크(또는 채널 쇼츠 링크)가 없음")
        if len(d["images"]) != 3:
            e.append("images 는 3개")
        return e

    d = write_loop(models, prompt, check)
    n = 1 + len(glob.glob(str(ROOT / f"naver/jobs/{NOW:%Y%m%d}-n*[0-9].json")))
    jid = f"{NOW:%Y%m%d}-n{n}"
    save(ROOT / f"naver/jobs/{jid}.json", {"images": d["images"][:3], "coupang_keywords": []})
    d["id"] = jid
    Path("/tmp/naver_body.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    with open(ROOT / "naver/log.txt", "a", encoding="utf-8") as f:
        f.write(f"{NOW:%Y-%m-%d} | {d['category']} | {d['title']}"
                + (f" | 쇼츠:{d['shorts_video_id']}" if d.get("shorts_video_id") else "") + "\n")


# ================================================================ 인생ON 쇼츠 (시험용)
def life_shorts(models):
    guide = (ROOT / "life/SHORTS_GUIDE.md").read_text(encoding="utf-8")
    titles = titles_from([e.get("title") for e in load(ROOT / "life/data/shorts_log.json", []) or []], n=40)
    prompt = header("유튜브 채널 「인생ON : 마음의 불을 켜다」의 쇼츠 대본 작가") + f"""최근에 올린 제목들 (겹치지 않게):
{chr(10).join('- ' + t for t in titles)}

{NO_SEARCH}
- 명언은 쓰지 마라. scenes text 합 340~400자, 장면 9~11개. 첫 장면 8~15자 단정형 훅.
- JSON 키: title, hook, scenes([{{"text","bg"}}]), description, tags, comment, coupang_keywords([]).

[규칙]
{guide}
"""
    d = write_loop(models, prompt, lambda d: check_scenes(d, 9, 12, 330, 410))
    d["coupang_keywords"] = []
    d["writer"] = "gemini"
    save(ROOT / f"life/shorts/queue/{NOW:%Y%m%d-%H%M}.json", d)
    dispatch("shorts-life.yml")


JOBS = {
    "salim-blog": ("flash", salim_blog),
    "news-blog": ("flash", news_blog),
    "salim-shorts": ("lite", salim_shorts),
    "news-shorts": ("lite", news_shorts),
    "naver": ("flash", naver),
    "life-shorts": ("flash", life_shorts),
}


def main():
    job = os.environ.get("JOB", "")
    if job not in JOBS:
        sys.exit(f"JOB 이 이상해요: {job!r}")
    if not KEY:
        sys.exit("GEMINI_API_KEY 가 없어요")
    pref, fn = JOBS[job]
    try:
        fn(pick_models(os.environ.get("MODEL_PREF", pref)))
    except Exception as e:
        telegram(f"[Gemini 글쓰기 실패] {job}\n{e}")
        raise


if __name__ == "__main__":
    main()
