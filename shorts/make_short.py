# -*- coding: utf-8 -*-
"""핑포의 작은집 연구소 — 유튜브 쇼츠 자동 제작기 (무료 도구만 사용).

shorts/queue/*.json 대본을 읽어
  1) 장면마다 무료 AI 음성(edge-tts)으로 내레이션을 만들고
  2) Cloudflare Workers AI(무료)로 장면 배경 그림을 그리고 (실패하면 분홍 그라데이션)
  3) 상단 제목·하단 큰 자막을 얹어 9:16 세로 영상(1080x1920)으로 합친 뒤
  4) 마지막에 구독·좋아요 장면을 붙이고
  5) YouTube Data API 로 핑포 채널에 업로드한다.
처리한 대본은 shorts/done/ 으로 옮기고, 결과는 data/shorts_log.json 에 남긴다.

대본 형식(JSON):
{
  "title": "유튜브 제목 (#shorts 는 자동으로 붙음)",
  "hook": "영상 위쪽에 계속 떠 있을 짧은 문구 (12자 안팎)",
  "voice": "ko-KR-SunHiNeural",
  "scenes": [{"text": "내레이션 겸 자막 한두 문장", "bg": "english scene prompt"}],
  "outro": "마지막 인사 (선택)",
  "description": "유튜브 설명란",
  "tags": ["#태그", ...],
  "blog_url": "관련 블로그 글 주소 (선택)",
  "coupang_keywords": ["수납함", ...]   (선택)
}
"""
import asyncio
import base64
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import textwrap
import time

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, REPO)
import channel as ch  # noqa: E402

QUEUE = os.path.join(REPO, os.environ["SHORTS_QUEUE"]) if os.environ.get("SHORTS_QUEUE") else ch.path("shorts", "queue")
DONE = ch.path("shorts", "done")
WORK = os.path.join(ROOT, "_work")
OUT = os.path.join(ROOT, "_out")
LOG_FILE = ch.path("data", "shorts_log.json")
LINKS_FILE = ch.path("data", "coupang_links.txt")
LOGO = ch.logo()
W, H, FPS = 1080, 1920, 30

BLOG_HOME = ch.P["blog_home"]
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
C = ch.P["colors"]
PINK = tuple(C["accent"])
BAR = tuple(C["bar"])

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            for idx in range(10):
                try:
                    f = ImageFont.truetype(path, size, index=idx)
                    if "KR" in " ".join(f.getname()):
                        return f
                except Exception:  # noqa: BLE001
                    break
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"명령 실패: {' '.join(cmd[:6])}...\n{p.stderr[-1500:]}")
    return p.stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", path]).strip())


# ---------------------------------------------------------------- 음성

TTS_RATE = os.environ.get("TTS_RATE") or ch.P.get("tts_rate", "+35%")
TTS_PITCH = ch.P.get("tts_pitch", "+0Hz")


async def _tts(text, voice, path):
    """음성을 저장하고, 단어마다 (시작초, 끝초, 글자) 를 돌려준다."""
    import edge_tts
    words = []
    com = edge_tts.Communicate(text, voice, rate=TTS_RATE, pitch=TTS_PITCH)
    with open(path, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                st = chunk["offset"] / 1e7
                words.append((st, st + chunk["duration"] / 1e7, chunk["text"]))
    return words


def tts(text, voice, path):
    for attempt in range(3):
        try:
            words = asyncio.run(_tts(text, voice, path))
            if os.path.getsize(path) > 1000:
                return words
        except Exception as e:  # noqa: BLE001
            print(f"[음성] 재시도 {attempt + 1}: {e}")
            time.sleep(3)
    raise RuntimeError("음성 생성 실패")


def word_times(text, words, dur):
    """자막 낱말(띄어쓰기 단위)마다 시작 시각을 구한다. 음성 단어 정보가 어긋나면 글자 수 비율로."""
    tokens = text.split()
    starts = []
    wi = 0
    for tok in tokens:
        core = re.sub(r"[^\w]", "", tok)
        found = None
        while wi < len(words):
            w = re.sub(r"[^\w]", "", words[wi][2])
            wi += 1
            if w and (w in core or core in w or core.startswith(w)):
                found = words[wi - 1][0]
                # 한 낱말이 음성 단어 여러 개로 쪼개진 경우 건너뛰기
                while wi < len(words) and re.sub(r"[^\w]", "", words[wi][2]) and \
                        re.sub(r"[^\w]", "", words[wi][2]) in core[len(w):]:
                    wi += 1
                break
        starts.append(found)
    if not words or sum(x is None for x in starts) > len(tokens) // 3:
        total = sum(len(t) for t in tokens) or 1
        acc, starts = 0, []
        for t in tokens:
            starts.append(dur * acc / total)
            acc += len(t)
        return tokens, starts
    last = 0.0
    for k, v in enumerate(starts):
        if v is None:
            starts[k] = last
        last = starts[k]
    return tokens, starts


# ---------------------------------------------------------------- 그림

STYLE = ch.P["shorts_style"]
AI_COUNT = [0]


PEXELS_USED = set()
# 풍경만: 동물·건물·물건 사진은 건너뛴다
NOT_SCENERY = re.compile(r"\b(cat|cats|kitten|dog|dogs|puppy|animal|animals|pet|bird|birds|insect|bee|butterfly|horse|cow|deer|"
                         r"squirrel|fish|duck|swan|wildlife|food|car|building|city|street|house|room|interior|text)\b", re.I)
NATURE_QUERIES = ["forest trees", "flower field", "mountain valley stream", "autumn leaves forest", "calm lake mountains",
                  "waterfall valley", "cherry blossom tree", "green meadow", "misty mountains", "river stones forest"]
PEOPLE = re.compile(r"\b(person|people|man|men|woman|women|girl|boy|child|children|kid|couple|face|portrait|hand|hands|selfie)\b", re.I)


def pexels_query(prompt):
    """영어 그림 설명에서 검색어만 남긴다 (no people 같은 말과 군더더기 빼기)."""
    q = re.split(r",", prompt)[0]
    q = re.sub(r"\b(no|without)\s+\w+", " ", q, flags=re.I)
    q = re.sub(r"\b(close up of|photo of|a|an|the|in|on|at|by|of|with|facing|quiet|centered|vertical|composition|soft|warm|light|golden)\b", " ", q, flags=re.I)
    return " ".join(q.split()[:5]) or "calm nature landscape"


def pexels_image(prompt, path):
    """무료 사진 사이트 Pexels 에서 세로 풍경 사진을 받는다 (사람 나온 사진은 건너뜀)."""
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return False
    for q in (pexels_query(prompt), "calm nature landscape"):
        try:
            r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key}, timeout=30,
                             params={"query": q, "orientation": "portrait", "per_page": 30, "size": "large"})
            photos = r.json().get("photos", []) if r.ok else []
        except Exception as e:  # noqa: BLE001
            print(f"[사진] Pexels 오류: {e}")
            return False
        for ph in photos:
            if ph["id"] in PEXELS_USED or PEOPLE.search(ph.get("alt") or ""):
                continue
            try:
                img = requests.get(ph["src"].get("portrait") or ph["src"]["large2x"], timeout=60).content
                with open(path, "wb") as f:
                    f.write(img)
                Image.open(path).verify()
            except Exception:  # noqa: BLE001
                continue
            PEXELS_USED.add(ph["id"])
            AI_COUNT[0] += 1
            print(f"[사진] Pexels '{q}' → {ph['id']}")
            return True
    return False


import threading as _threading
_USED_LOCK = _threading.Lock()


def pixabay_image(prompt, path, orientation="vertical"):
    """무료 사진 사이트 Pixabay 에서 세로 사진을 받아 저장한다 (사람이 나온 사진은 건너뜀)."""
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return False
    backup = random.choice(NATURE_QUERIES)
    for q in (pexels_query(prompt), backup, "forest trees"):
        try:
            r = requests.get("https://pixabay.com/api/", timeout=30, params={
                "key": key, "q": q, "image_type": "photo", "orientation": orientation, "safesearch": "true",
                "category": "nature", "per_page": 50, "order": "popular"})
            hits = r.json().get("hits", []) if r.ok else []
        except Exception as e:  # noqa: BLE001
            print(f"[사진] Pixabay 오류: {e}")
            return False
        for h in hits:
            if PEOPLE.search(h.get("tags") or "") or NOT_SCENERY.search(h.get("tags") or ""):
                continue
            with _USED_LOCK:  # 여러 장을 동시에 받을 때 같은 사진을 두 번 고르지 않게 먼저 찜한다
                if h["id"] in PEXELS_USED:
                    continue
                PEXELS_USED.add(h["id"])
            try:
                img = requests.get(h.get("largeImageURL") or h["webformatURL"], timeout=60).content
                with open(path, "wb") as f:
                    f.write(img)
                Image.open(path).verify()
            except Exception:  # noqa: BLE001
                with _USED_LOCK:
                    PEXELS_USED.discard(h["id"])
                continue
            AI_COUNT[0] += 1
            print(f"[사진] Pixabay '{q}' → {h['id']}")
            return True
    return False


def cloudflare_image(prompt, path, style=None):
    acc = os.environ.get("CF_ACCOUNT_ID", "").strip()
    tok = os.environ.get("CF_API_TOKEN", "").strip()
    if not (acc and tok):
        return False
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell",
            headers={"Authorization": f"Bearer {tok}"},
            json={"prompt": f"{prompt}, {style or STYLE}"[:1500], "steps": ch.P.get("image_steps", 8)}, timeout=90)
        img = (r.json().get("result") or {}).get("image") if r.ok else None
        if not img:
            print(f"[그림] Cloudflare 응답 {r.status_code}: {r.text[:200]}")
            return False
        with open(path, "wb") as f:
            f.write(base64.b64decode(img))
        Image.open(path).verify()
        AI_COUNT[0] += 1
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[그림] Cloudflare 오류: {e}")
        return False


def gradient_bg(path, seed):
    rnd = random.Random(seed)
    a, b = rnd.choice([tuple(map(tuple, g)) for g in C["gradients"]])
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    img.filter(ImageFilter.GaussianBlur(20)).save(path)


def prepare_image(src, dst):
    img = Image.open(src).convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left, top = (img.width - W) // 2, (img.height - H) // 2
    img.crop((left, top, left + W, top + H)).save(dst, quality=92)


# ---------------------------------------------------------------- 자막

YELLOW = tuple(C["hi_text"])
HOOK_BG = tuple(C["hook_bg"])


def wrap_tokens(d, tokens, f, max_w):
    lines, cur = [], []
    for k, t in enumerate(tokens):
        trial = " ".join(tokens[j] for j in cur + [k])
        if cur and d.textlength(trial, font=f) > max_w:
            lines.append(cur)
            cur = [k]
        else:
            cur.append(k)
    if cur:
        lines.append(cur)
    return lines


def hook_lines(d, hook, f, max_w):
    """위 제목 상자 글줄. 한 줄에 들어가면 한 줄, 아니면 띄어쓰기 자리에서 두 줄 길이가 비슷하게 나눈다.
    (예전처럼 11자에서 자르면 '흉보는 사람 거리 / 두기' 처럼 낱말 하나만 아래로 떨어진다.)
    대본에 '\\n' 을 넣으면 그 자리에서 나눈다."""
    hook = (hook or "").strip()
    if "\n" in hook:
        return [ln.strip() for ln in hook.split("\n") if ln.strip()][:2]
    if d.textlength(hook, font=f) <= max_w:
        return [hook]
    words = hook.split()
    if len(words) < 2:
        return wrap_ko(hook, 11)[:2]
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        wa, wb = d.textlength(a, font=f), d.textlength(b, font=f)
        score = (max(wa, wb) > max_w, abs(wa - wb))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1]


def base_png(hook, path, outro=False):
    """장면 내내 고정되는 부분: 위 제목 상자, 로고·채널 이름, 아래 그늘, (마지막 장면) 좋아요·구독 버튼."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 가운데 자막 뒤를 부드럽게 어둡게 (위아래로 옅어지는 띠)
    mid, half = H // 2 + 120, 420
    for y in range(mid - half, mid + half):
        a = 1 - abs(y - mid) / half
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(120 * a ** 0.8)))
    for y in range(0, 520):
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(C.get("top_shade", 90) * (1 - y / 520))))
    # 위 제목: 노란 바탕 알약 상자, 글씨 크기에 맞춰 가운데
    f_hook = font(88)
    lh, pad_x, pad_y = 112, 56, 26
    lines = hook_lines(d, hook, f_hook, W - 2 * pad_x - 80)
    tw_max = max(d.textlength(ln, font=f_hook) for ln in lines)
    box_w, box_h = tw_max + pad_x * 2, len(lines) * lh + pad_y * 2
    bx0, by0 = (W - box_w) / 2, 180
    d.rounded_rectangle([bx0 + 4, by0 + 6, bx0 + box_w + 4, by0 + box_h + 6], radius=box_h / 2, fill=(0, 0, 0, 70))
    d.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h], radius=box_h / 2, fill=HOOK_BG + (250,))
    y = by0 + pad_y - 8
    for line in lines:
        tw = d.textlength(line, font=f_hook)
        d.text(((W - tw) / 2, y), line, font=f_hook, fill=tuple(C["hook_text"]))
        y += lh
    # 채널 이름 + 로고 (작게)
    f_tag = font(32)
    tag = ch.P.get("tag") or ch.P["name"]
    tw = d.textlength(tag, font=f_tag)
    logo_s = 54
    lx = int((W - tw - logo_s - 10) / 2)
    ty = by0 + box_h + 20
    if os.path.exists(LOGO):
        logo = Image.open(LOGO).convert("RGBA").resize((logo_s, logo_s), Image.LANCZOS)
        img.alpha_composite(logo, (lx, ty - 7))
        tx = lx + logo_s + 10
    else:
        tx = (W - tw) / 2
    d.text((tx, ty), tag, font=f_tag, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
    if outro:
        f_b = font(70)
        for k, label in enumerate(["좋아요", "구독"]):
            bx = W // 2 - 400 + k * 420
            by = H // 2 - 150
            d.rounded_rectangle([bx + 6, by + 10, bx + 386, by + 150], radius=70, fill=(0, 0, 0, 90))
            d.rounded_rectangle([bx, by, bx + 380, by + 140], radius=70,
                                fill=(230, 30, 40, 245) if k == 1 else PINK + (245,))
            tw = d.textlength(label, font=f_b)
            d.text((bx + (380 - tw) / 2, by + 28), label, font=f_b, fill=(255, 255, 255))
    img.save(path)


CAP_SIZE, CAP_LH = ch.P.get("cap_size", 72), ch.P.get("cap_lh", 100)
CAP_MAX_LINES = ch.P.get("cap_lines", 3)
CAP_MID = H // 2 + 120   # 자막 가운데 높이 (모든 장면 같음)


def split_long_scenes(scenes):
    """자막이 CAP_MAX_LINES 줄을 넘는 장면은 문장 중간(문장부호 우선)에서 두 장면으로 나눈다 — 글자가 잘리지 않게."""
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f = font(CAP_SIZE)
    out = []
    todo = list(scenes)
    while todo:
        sc = todo.pop(0)
        toks = sc["text"].split()
        if sc.get("outro") or len(toks) < 4 or len(wrap_tokens(d, toks, f, W - 150)) <= CAP_MAX_LINES:
            out.append(sc)
            continue
        mid = len(toks) // 2
        cut = min(range(1, len(toks)), key=lambda k: (0 if toks[k - 1][-1] in ".,!?" else 1, abs(k - mid)))
        a, b = dict(sc), dict(sc)
        a["text"], b["text"] = " ".join(toks[:cut]), " ".join(toks[cut:])
        print(f"[자막] 긴 장면을 둘로 나눔: {sc['text'][:20]}…")
        todo[0:0] = [a, b]
    return out


def caption_png(tokens, active, path, progress):
    """자막: 모든 장면에서 같은 크기·같은 위치(화면 가운데). 문장 전체를 보여 주고 읽는 낱말만 노란색."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(CAP_SIZE)
    lines = wrap_tokens(d, tokens, f, W - 150)
    if len(lines) > 1:  # 줄 길이를 고르게 (마지막 줄에 한 낱말만 남지 않게)
        n, full = len(lines), d.textlength(" ".join(tokens), font=f)
        for mw in range(int(full / n), W - 149, 20):
            trial = wrap_tokens(d, tokens, f, mw)
            if len(trial) <= n:
                lines = trial
                break
    lines = lines[:CAP_MAX_LINES]
    top = CAP_MID - len(lines) * CAP_LH // 2
    space = d.textlength(" ", font=f)
    for li, line in enumerate(lines):
        widths = [d.textlength(tokens[k], font=f) for k in line]
        x = (W - (sum(widths) + space * (len(line) - 1))) / 2
        y = top + li * CAP_LH
        for k, w in zip(line, widths):
            if k == active:
                d.rounded_rectangle([x - 14, y - 2, x + w + 14, y + CAP_LH - 14], radius=24, fill=PINK + (240,))
                d.text((x, y), tokens[k], font=f, fill=YELLOW, stroke_width=7, stroke_fill=tuple(C["hi_stroke"]))
            else:
                d.text((x, y), tokens[k], font=f, fill=(255, 255, 255), stroke_width=9, stroke_fill=(0, 0, 0))
            x += w + space
    # 진행 막대
    d.rectangle([0, 0, W, 14], fill=(255, 255, 255, 70))
    d.rectangle([0, 0, int(W * max(0.0, min(1.0, progress))), 14], fill=BAR + (255,))
    img.save(path)


def card_lines(text):
    """첫 화면 제목 카드 글줄. 대본 "card" 에 '\\n' 이 있으면 그 자리에서, 없으면 낱말을 모아 한 줄 약 7자로.
    [낱말] 은 노란색으로 칠할 자리 (괄호는 화면에 안 보임)."""
    text = (text or "").strip().rstrip(".")
    if "\n" in text:
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    else:
        lines, cur = [], ""
        for w in text.split():
            plain = re.sub(r"[\[\]]", "", cur + " " + w).strip()
            if cur and len(plain.replace(" ", "")) > 7:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
    lines = lines[:4]
    marked = any("[" in ln for ln in lines)
    out = []
    for li, ln in enumerate(lines):
        segs = [(s, s.startswith("[")) for s in re.split(r"(\[[^\]]*\])", ln) if s]
        segs = [(s.strip("[]"), hi) for s, hi in segs]
        if not marked:  # 표시가 없으면 숫자가 있는 줄, 숫자가 없으면 첫 줄을 노랗게
            has_num = any(re.search(r"\d", x) for x in lines)
            hi = bool(re.search(r"\d", ln)) if has_num else li == 0
            segs = [(re.sub(r"[\[\]]", "", ln), hi)]
        out.append(segs)
    return out


def title_card_png(text, path):
    """첫 장면 화면: 위 노란 상자·자막 대신, 화면 가운데에 주제를 큰 글씨 4줄 이내로 (피드에서 넘기지 않게)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lines = card_lines(text)
    size = 170
    while size > 90:
        f = font(size)
        if max(sum(d.textlength(s, font=f) for s, _ in ln) for ln in lines) <= W - 150:
            break
        size -= 6
    f = font(size)
    lh = int(size * 1.25)
    block = lh * len(lines)
    top = (H - block) // 2 - 40
    # 글씨 뒤 배경을 고르게 어둡게 (사진이 밝아도 잘 읽히게)
    pad = 260
    for y in range(max(0, top - pad), min(H, top + block + pad)):
        e = max(0.0, min(1.0, min(y - (top - pad), (top + block + pad) - y) / pad))
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(140 * e * e * (3 - 2 * e))))  # 가장자리가 띠처럼 보이지 않게 부드럽게
    for li, segs in enumerate(lines):
        x = (W - sum(d.textlength(s, font=f) for s, _ in segs)) / 2
        y = top + li * lh
        for s, hi in segs:
            d.text((x, y), s, font=f, fill=YELLOW if hi else (255, 255, 255),
                   stroke_width=max(8, size // 14), stroke_fill=(0, 0, 0))
            x += d.textlength(s, font=f)
    # 채널 이름 + 로고 (작게, 카드 아래)
    f_tag = font(40)
    tag = ch.P.get("tag") or ch.P["name"]
    tw = d.textlength(tag, font=f_tag)
    logo_s = 64
    lx = int((W - tw - logo_s - 12) / 2)
    ty = top + block + 70
    tx = (W - tw) / 2
    if os.path.exists(LOGO):
        logo = Image.open(LOGO).convert("RGBA").resize((logo_s, logo_s), Image.LANCZOS)
        img.alpha_composite(logo, (lx, ty - 8))
        tx = lx + logo_s + 12
    d.text((tx, ty), tag, font=f_tag, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
    img.save(path)


def wrap_ko(text, width):
    lines = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, width=width, break_long_words=True) or [""]
    return lines


# ---------------------------------------------------------------- 영상

def clean_title(t):
    return re.sub(r"\s*#\S+", "", t or "").strip()


def whoosh(path):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.4:c=pink:a=0.6",
         "-af", "highpass=f=500,lowpass=f=5000,afade=t=in:d=0.12,afade=t=out:st=0.15:d=0.25,volume=0.22",
         "-ar", "44100", "-ac", "2", path])


def make_scene(i, scene, hook, audio, words, t0, total):
    raw = os.path.join(WORK, f"raw{i}.jpg")
    bg = os.path.join(WORK, f"bg{i}.jpg")
    base = os.path.join(WORK, f"base{i}.png")
    clip = os.path.join(WORK, f"c{i:02d}.mp4")
    if not os.path.exists(raw):
        gradient_bg(raw, i)
    prepare_image(raw, bg)
    dur = duration(audio) + 0.05
    caps = []
    if scene.get("card"):
        # 첫 화면 제목 카드: 위 상자·자막 없이 카드 한 장만 (2026-11-10 벤치마킹 반영)
        title_card_png(scene["card"], base)
        starts = []
    else:
        base_png(hook, base, outro=scene.get("outro", False))
        tokens, starts = word_times(scene["text"], words, dur)
    for k, st in enumerate(starts):
        cp = os.path.join(WORK, f"cap{i}_{k}.png")
        caption_png(tokens, k, cp, (t0 + st) / total)
        end = starts[k + 1] if k + 1 < len(starts) else dur + 1
        caps.append((cp, st if k else 0.0, end))
    frames = int(dur * FPS) + 1
    # 모든 장면 같은 움직임: 천천히 확대
    z = "min(1.0+0.0015*on,1.12)"
    inputs = ["-loop", "1", "-i", bg, "-i", base]
    for cp, _, _ in caps:
        inputs += ["-i", cp]
    inputs += ["-i", audio, "-i", os.path.join(WORK, "whoosh.wav")]
    n = len(caps)
    a_idx, w_idx = 2 + n, 3 + n
    fc = (f"[0:v]scale={int(W * 1.2)}:{int(H * 1.2)},"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}[bg];"
          f"[bg][1:v]overlay=0:0[v0]")
    for k, (_, st, en) in enumerate(caps):
        fc += f";[v{k}][{2 + k}:v]overlay=0:0:enable='between(t,{st:.3f},{en:.3f})'[v{k + 1}]"
    fc += f";[v{n}]format=yuv420p[v]"
    if i > 0:
        fc += f";[{a_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[va];[{w_idx}:a][va]amix=inputs=2:duration=longest:normalize=0[a]"
    else:
        fc += f";[{a_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[a]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
         "-t", f"{dur:.2f}", "-r", str(FPS), clip])
    return clip, dur


def blog_images(url):
    """posted.json 에서 블로그 글의 사진(저장소 images/ 안 파일)을 찾는다."""
    try:
        posted = json.load(open(ch.path("data", "posted.json"), encoding="utf-8")).get("posted", [])
    except Exception:  # noqa: BLE001
        return []
    for p in posted:
        if url and p.get("url") == url:
            files = [os.path.join(ch.path("images"), u.rsplit("/", 1)[-1]) for u in p.get("images", [])]
            return [f for f in files if os.path.exists(f)]
    return []


def build_video(script, out_path):
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    AI_COUNT[0] = 0
    global TTS_RATE, TTS_PITCH
    voice = script.get("voice") or ch.P.get("voice") or "ko-KR-SunHiNeural"
    TTS_RATE = (script.get("rate") or (ch.P.get("voice_rates") or {}).get(voice)
                or os.environ.get("TTS_RATE") or ch.P.get("tts_rate", "+35%"))
    TTS_PITCH = script.get("pitch") or ch.P.get("tts_pitch", "+0Hz")
    hook = script.get("hook") or clean_title(script["title"])
    scenes = list(script["scenes"])
    # 좋아요·구독 마지막 화면은 시청 지속률을 떨어뜨려서 기본은 뺀다 (링크·구독 안내는 설명란·댓글로).
    # 대본에 "end_card": true 가 있을 때만 붙인다.
    if script.get("end_card"):
        outro = script.get("outro") or ch.P["shorts_outro"]
        scenes.append({"text": outro, "bg": ch.P["shorts_outro_bg"], "outro": True})
    if ch.P.get("cap_lines"):
        scenes = split_long_scenes(scenes)
    if ch.P.get("title_card") and scenes:
        # 첫 장면은 화면 가운데 큰 제목 카드로 (대본 "card" 가 있으면 그것, 없으면 첫 장면 말)
        scenes[0] = dict(scenes[0], card=script.get("card") or scenes[0]["text"])
    from concurrent.futures import ThreadPoolExecutor

    # 채널 설정 max_images 가 있으면 그림 수를 줄이고, 이어지는 장면끼리 같은 그림을 나눠 쓴다
    n_img = min(len(scenes), ch.P.get("max_images") or len(scenes))
    # 인생ON 사연(숏드라마, 2026-11-10): 장면마다 AI 그림(수채화 인물), 등장인물 {이름} 은 대본 "characters" 설명으로 바꿔 같은 얼굴로
    sayeon = script.get("format") == "sayeon"
    if sayeon:
        n_img = len(scenes)
        chars = script.get("characters") or {}

        def expand(prompt):
            for k, v in chars.items():
                prompt = prompt.replace("{" + k + "}", f"({v})")
            return prompt
    group = [i * n_img // len(scenes) for i in range(len(scenes))]
    leaders = {g: group.index(g) for g in range(n_img)}

    def _pre(i_s):
        i, sc = i_s
        prompt, path = sc.get("bg") or ch.P["shorts_default_bg"], os.path.join(WORK, f"raw{i}.jpg")
        keep = os.path.join(REPO, script["image_dir"], f"{i}.jpg") if script.get("image_dir") else ""
        if sayeon and keep and os.path.exists(keep) and i not in (script.get("redraw") or []):
            shutil.copy(keep, path)  # 미리보기에서 괜찮았던 그림은 그대로 쓴다
            print(f"[그림] 사연 {i}: 미리보기 그림 그대로")
            return
        if sayeon:
            for _ in range(2):
                if cloudflare_image(expand(prompt), path, style=ch.P.get("sayeon_style")):
                    print(f"[그림] 사연 {i}: {prompt[:60]}")
                    return
            return
        if ch.P.get("image_source") == "stock" and (pixabay_image(prompt, path) or pexels_image(prompt, path)):
            return
        cloudflare_image(prompt, path)
    fixed = os.path.join(REPO, ch.P["fixed_bg"]) if ch.P.get("fixed_bg") else ""
    if fixed and os.path.exists(fixed):
        # 고정 배경 채널(뉴스): AI 그림 없이 모든 장면에 같은 배경 한 장을 쓴다 → 무료 한도와 상관없이 매일 올라간다
        for i in range(len(scenes)):
            shutil.copy(fixed, os.path.join(WORK, f"raw{i}.jpg"))
        print(f"[그림] 고정 배경 사용: {ch.P['fixed_bg']}")
        leaders = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(_pre, [(i, scenes[i]) for i in leaders.values()]))
    # 사연 그림(사람)은 풍경 예비 그림 모음에 넣지 않는다
    cache_dir = ch.path("data", "bg_cache") if ch.P.get("bg_cache") and not sayeon else ""
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d%H%M")
        for i in leaders.values():
            src = os.path.join(WORK, f"raw{i}.jpg")
            if os.path.exists(src):
                small = Image.open(src).convert("RGB")
                small.thumbnail((768, 1365))
                small.save(os.path.join(cache_dir, f"{stamp}-{i}.jpg"), quality=82)
        old = sorted(glob.glob(os.path.join(cache_dir, "*.jpg")))[:-ch.P["bg_cache"]]
        for f in old:
            os.remove(f)
    for i, g in enumerate(group):
        if g not in leaders:
            continue
        src = os.path.join(WORK, f"raw{leaders[g]}.jpg")
        if i != leaders[g] and os.path.exists(src):
            shutil.copy(src, os.path.join(WORK, f"raw{i}.jpg"))
    missing = [i for i in range(len(scenes)) if not os.path.exists(os.path.join(WORK, f"raw{i}.jpg"))]
    if sayeon and missing:
        have = [i for i in range(len(scenes)) if i not in missing]
        if len(have) < max(3, len(scenes) // 2):
            raise RuntimeError(f"사연 그림을 {len(have)}장밖에 못 만들었어요 (그림 한도 초과일 수 있음). 풍경으로 채우지 않고 대본은 남겨 둘게요")
        for i in missing:  # 못 만든 장면은 가장 가까운 장면 그림을 같이 쓴다
            near = min(have, key=lambda h: (abs(h - i), h))
            shutil.copy(os.path.join(WORK, f"raw{near}.jpg"), os.path.join(WORK, f"raw{i}.jpg"))
        print(f"[그림] 사연 그림 {len(have)}장, 빈 장면 {len(missing)}개는 이웃 그림으로")
        missing = []
    if missing:
        # AI 그림이 모자라면(무료 한도 초과 등) 같은 블로그 글의 사진으로 채운다
        blog_imgs = blog_images(script.get("blog_url"))
        if not blog_imgs and cache_dir:
            # 무료 한도 초과일 때: 예전에 만든 같은 채널 그림 중에서 골라 쓴다 (장면 묶음끼리는 같은 그림)
            pool = sorted(glob.glob(os.path.join(cache_dir, "*.jpg")))
            if pool:
                rnd = random.Random(script.get("title", ""))
                pick = {g: rnd.choice(pool) for g in set(group)}
                for i in missing:
                    shutil.copy(pick[group[i]], os.path.join(WORK, f"raw{i}.jpg"))
                print(f"[그림] AI 한도 초과 → 예전 그림 {len(pick)}장으로 채움")
                missing = []
        for n, i in enumerate(missing):
            if blog_imgs:
                shutil.copy(blog_imgs[n % len(blog_imgs)], os.path.join(WORK, f"raw{i}.jpg"))
        if not blog_imgs and len(missing) == len(scenes):
            raise RuntimeError("그림을 하나도 못 만들었어요 (Cloudflare 무료 한도 초과일 수 있음). "
                               "분홍 배경 영상은 올리지 않고 대본은 대기열에 남겨 둘게요")
        print(f"[그림] AI 그림 {len(scenes) - len(missing)}장 + 블로그 사진으로 {len(missing) if blog_imgs else 0}장 채움")
    if sayeon and os.environ.get("PREVIEW_DIR"):
        # 미리보기: 장면 그림을 따로 남겨 두고, 이상한 장면만 다시 그릴 수 있게 한다 ("image_dir" + "redraw")
        kd = os.path.join(REPO, os.environ["PREVIEW_DIR"], "img", script.get("_name", "x"))
        os.makedirs(kd, exist_ok=True)
        for i in range(len(scenes)):
            src = os.path.join(WORK, f"raw{i}.jpg")
            if os.path.exists(src):
                im = Image.open(src).convert("RGB")
                im.save(os.path.join(kd, f"{i}.jpg"), quality=92)
    whoosh(os.path.join(WORK, "whoosh.wav"))
    # 음성을 먼저 모두 만들어 전체 길이를 알아 둔다 (진행 막대용)
    voiced = []
    base_rate, base_pitch = TTS_RATE, TTS_PITCH
    for i, sc in enumerate(scenes):
        audio = os.path.join(WORK, f"a{i}.mp3")
        # 사연 쇼츠: 장면마다 목소리를 바꿀 수 있다 (등장인물 대사). "voice"/"rate"/"pitch" 가 없으면 기본 목소리
        v = sc.get("voice") or voice
        TTS_RATE = sc.get("rate") or ((ch.P.get("voice_rates") or {}).get(v) if sc.get("voice") else None) or base_rate
        TTS_PITCH = sc.get("pitch") or base_pitch
        words = tts(sc["text"], v, audio)
        voiced.append((audio, words, duration(audio) + 0.05))
    total = sum(v[2] for v in voiced)
    clips, t0 = [], 0.0
    for i, sc in enumerate(scenes):
        audio, words, dur = voiced[i]
        clip, _ = make_scene(i, sc, hook, audio, words, t0, total)
        clips.append(clip)
        t0 += dur
    listfile = os.path.join(WORK, "list.txt")
    with open(listfile, "w") as f:
        f.writelines(f"file '{c}'\n" for c in clips)
    bgm = sorted(glob.glob(os.path.join(REPO, "brand", "bgm", "*.mp3")))
    joined = out_path if not bgm else os.path.join(WORK, "joined.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
         "-c", "copy", "-movflags", "+faststart", joined])
    if bgm:
        # brand/bgm/ 에 넣어 둔 저작권 걱정 없는 음악(유튜브 오디오 보관함 등)을 작게 깔아 준다
        song = random.Random(script.get("title", "")).choice(bgm)
        d = duration(joined)
        run(["ffmpeg", "-y", "-i", joined, "-stream_loop", "-1", "-i", song, "-filter_complex",
             f"[1:a]volume={ch.P['bgm_volume']},afade=t=out:st={max(0.0, d - 0.8):.2f}:d=0.8[b];"
             + ("[0:a][b]amix=inputs=2:duration=first:normalize=0[a]" if ch.P["voice_gain"] == 1.0 else
                f"[0:a]volume={ch.P['voice_gain']}[v];[v][b]amix=inputs=2:duration=first:normalize=0,"
                "alimiter=limit=0.95:level=disabled[a]"),
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart", out_path])
        print(f"[음악] {os.path.basename(song)}")
    return duration(out_path)


# ---------------------------------------------------------------- 설명란·쿠팡

def pick_coupang(script):
    keys = [k.strip() for k in script.get("coupang_keywords", []) if k.strip()]
    if not keys:
        return None
    try:
        sys.path.insert(0, REPO)
        import coupang_api
        found = coupang_api.pick(keys, count=1, sub_id=os.environ.get("COUPANG_SUB_ID", "").strip())
        if found:
            return (found[0]["url"], found[0]["name"], found[0]["keyword"])
    except Exception as e:  # noqa: BLE001
        print(f"[쿠팡] API 사용 실패: {e}")
    if not os.path.exists(LINKS_FILE):
        return None
    rows = []
    for line in open(LINKS_FILE, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) >= 2 and parts[0].startswith("https://link.coupang.com/"):
            rows.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    scored = [(sum(1 for k in keys if k in r[1] + " " + r[2]), r) for r in rows]
    scored = [s for s in scored if s[0] > 0]
    return max(scored)[1] if scored else None


def build_description(script):
    """링크를 맨 위쪽에 둔다 (쇼츠 설명란은 접혀 있어서 위쪽만 바로 보임)."""
    blog = script.get("blog_url") or BLOG_HOME
    # 쿠팡 대가성 문구·상품 링크는 넣지 않는다 (구독자 모으기 우선, 쇼츠 설명란 링크는 바로 안 열림)
    product = None
    lines = []
    long_log = ch.path("data", "long_log.json")
    if ch.P.get("link_long") and script.get("long_url"):
        # 짝 쇼츠: 대본이 이어 줄 긴 영상을 직접 지정 (맨 첫 줄)
        lines.append(f"📺 전체 이야기(긴 영상) 👉 {script['long_url']}")
    elif ch.P.get("link_long") and os.path.exists(long_log):
        try:  # 쇼츠 → 긴 영상으로 시청 시간 모으기: 가장 최근 공개 긴 영상 링크 (맨 첫 줄)
            pub = [x for x in json.load(open(long_log, encoding="utf-8")) if x.get("privacy") == "public" and x.get("url")]
            if pub:
                lines.append(f"📺 더 깊은 이야기(긴 영상) 👉 {pub[-1]['url']}")
        except Exception:  # noqa: BLE001
            pass
    if blog:
        lines.append(f"📖 블로그에서 자세히 보기 👉 {blog}")
    lines += ["", script.get("description", "").strip(), ""]
    if script.get("format") == "sayeon":  # 사연 쇼츠는 가상 인물·창작 이야기임을 밝힌다
        lines += ["※ AI로 만든 가상 인물이 나오는 창작 이야기입니다. #AI가상인물", ""]
    lines += [ch.P["shorts_signature"]]  # AI 안내 문구는 넣지 않음 (업로드 시 합성 콘텐츠 표시는 그대로)
    return "\n".join(lines).strip(), product


def build_comment(script, product):
    """영상에 남길 감성 댓글 (링크 없음). 대본의 "comment"(그날 내용에 맞춘 2~3줄)를 쓰고,
    없으면 훅으로 짧게 만든다. 끝에는 더보기·구독·좋아요 안내."""
    body = (script.get("comment") or "").strip()
    if not body:
        hook = (script.get("hook") or script.get("title") or "").strip()
        body = ch.P["comment_fallback"].format(hook=hook)
    tail = ["", "더 궁금하신 분은 영상 아래 ‘더보기’를 눌러 봐 주세요 👀",
            "도움이 되셨다면 구독과 좋아요 꾹 부탁드려요 🙏💗"]
    return body + "\n" + "\n".join(tail)


# ---------------------------------------------------------------- 유튜브

def yt_clean(text):
    return (text or "").replace("<", "〈").replace(">", "〉")


def yt_access_token():
    rt = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if not rt:
        return ""
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        "refresh_token": rt, "grant_type": "refresh_token"}, timeout=30)
    tok = r.json().get("access_token")
    if not tok:
        raise RuntimeError(f"유튜브 연결 토큰 오류: {r.text[:300]}")
    return tok


def check_channel(tok):
    """엉뚱한 채널에 올리지 않도록 채널 ID를 확인한다."""
    want = os.environ.get("YT_CHANNEL_ID", "").strip()
    r = requests.get("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    items = r.json().get("items", []) if r.ok else []
    got = items[0]["id"] if items else ""
    if want and got != want:
        raise RuntimeError(f"연결된 채널({got})이 {ch.P['name']} 채널({want})이 아니라서 업로드를 멈췄어요")
    return got


def yt_upload(video, title, desc, tags, shorts=True):
    tok = yt_access_token()
    if not tok:
        return None
    check_channel(tok)
    title = yt_clean(title)
    if shorts and "#shorts" not in title.lower() and len(title) + 8 <= 100:
        title += " #shorts"
    clean_tags, total = [], 0
    for t in tags:
        t = yt_clean(t.lstrip("#")).strip()
        if t and total + len(t) + 2 < 450:
            clean_tags.append(t)
            total += len(t) + 2
    meta = {
        "snippet": {"title": title[:100], "description": yt_clean(desc)[:4900], "tags": clean_tags,
                    "categoryId": ch.P["yt_category"], "defaultLanguage": "ko", "defaultAudioLanguage": "ko"},
        "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"),
                   "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
    }
    size = os.path.getsize(video)
    r = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        data=json.dumps(meta), timeout=60)
    if r.status_code >= 300 or "Location" not in r.headers:
        raise RuntimeError(f"유튜브 업로드 시작 실패 {r.status_code}: {r.text[:300]}")
    with open(video, "rb") as f:
        up = requests.put(r.headers["Location"], data=f,
                          headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"}, timeout=600)
    if up.status_code >= 300:
        raise RuntimeError(f"유튜브 업로드 실패 {up.status_code}: {up.text[:300]}")
    info = up.json()
    return info.get("id"), info.get("status", {}).get("privacyStatus", "")


def set_short_thumb(vid, video):
    """제목 카드(영상 1초 화면)를 쇼츠 썸네일로 (채널 페이지·검색·홈에 보이는 그림, 2026-11-10).
    쇼츠 피드에서는 썸네일 대신 영상이 바로 재생되니 첫 화면 카드는 그대로 중요하다."""
    img = os.path.join(WORK, "thumb.jpg")
    run(["ffmpeg", "-y", "-ss", "1.0", "-i", video, "-frames:v", "1", "-q:v", "3", img])
    tok = yt_access_token()
    with open(img, "rb") as f:
        r = requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
                          headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"}, data=f, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"썸네일 실패 {r.status_code}: {r.text[:200]}")


def yt_comment(video_id, text):
    """채널 이름으로 댓글을 단다. 토큰에 youtube.force-ssl 권한이 없으면 실패하고 영상은 그대로 둔다."""
    tok = yt_access_token()
    body = {"snippet": {"videoId": video_id,
                        "topLevelComment": {"snippet": {"textOriginal": yt_clean(text)[:9000]}}}}
    r = requests.post("https://www.googleapis.com/youtube/v3/commentThreads?part=snippet",
                      headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"},
                      data=json.dumps(body), timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"댓글 실패 {r.status_code}: {r.text[:200]}")
    return r.json().get("id")


# ---------------------------------------------------------------- 기록

def log(entry):
    data = []
    if os.path.exists(LOG_FILE):
        try:
            data = json.load(open(LOG_FILE, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = []
    data.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data[-200:], f, ensure_ascii=False, indent=1)


def main():
    os.makedirs(DONE, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(QUEUE, "*.json")))
    if not files:
        print("대기 중인 쇼츠 대본 없음")
        return 0
    failed = 0
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        entry = {"file": os.path.basename(path), "at": time.strftime("%Y-%m-%d %H:%M")}
        try:
            script = json.load(open(path, encoding="utf-8"))
            entry["title"] = script.get("title", "")
            entry["voice"] = script.get("voice") or ch.P.get("voice") or "ko-KR-SunHiNeural"
            video = os.path.join(OUT, f"{name}.mp4")
            script["_name"] = name
            approved = os.path.join(REPO, script["video_file"]) if script.get("video_file") else ""
            if approved and os.path.exists(approved):
                # 핑포가 미리보기로 보고 허락한 영상을 그대로 올린다 (다시 만들지 않음)
                shutil.copy(approved, video)
                secs = duration(video)
                print(f"[영상] 허락받은 미리보기 영상 그대로 사용: {script['video_file']}")
            else:
                secs = build_video(script, video)
            entry.update(seconds=round(secs, 1), ai_images=AI_COUNT[0])
            print(f"[완성] {name}: {secs:.1f}초, AI 그림 {AI_COUNT[0]}장")
            desc, product = build_description(script)
            if os.environ.get("DRY_RUN") == "1":
                print("[시험] 업로드 건너뜀\n" + desc + "\n--- 댓글 ---\n" + build_comment(script, product))
                pdir = os.environ.get("PREVIEW_DIR")
                if pdir:  # 미리보기: 영상에서 8장면을 뽑아 저장 (사람이 보고 확인)
                    pdir = os.path.join(REPO, pdir)
                    os.makedirs(pdir, exist_ok=True)
                    for k in range(8):
                        t = 1.0 if k == 0 else secs * (k + 0.5) / 8  # 첫 장은 제목 카드
                        run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", "scale=540:-1",
                             os.path.join(pdir, f"{name}-{k}.jpg")])
                    os.remove(path)
                continue
            yt = yt_upload(video, script["title"], desc, script.get("tags", []))
            if yt:
                vid, privacy = yt
                entry.update(video_id=vid, url=f"https://youtube.com/shorts/{vid}", privacy=privacy)
                print(f"[유튜브] 업로드 완료 ({privacy}): https://youtube.com/shorts/{vid}")
                if ch.P.get("title_card"):
                    try:
                        set_short_thumb(vid, video)
                        entry["thumb"] = "ok"
                        print("[썸네일] 제목 카드로 설정")
                    except Exception as te:  # noqa: BLE001
                        entry["thumb_error"] = str(te)[:300]
                        print(f"[썸네일] {te}")
                try:
                    cid = yt_comment(vid, build_comment(script, product))
                    entry["comment"] = "ok"
                    print(f"[댓글] 감성 댓글 완료: {cid}")
                except Exception as ce:  # noqa: BLE001
                    entry["comment_error"] = str(ce)[:300]
                    print(f"[댓글] {ce}")
            else:
                entry["error"] = "YOUTUBE_REFRESH_TOKEN 없음 — 영상은 Actions 보관함에만 있음"
                print(entry["error"])
            shutil.move(path, os.path.join(DONE, os.path.basename(path)))
        except Exception as e:  # noqa: BLE001
            failed += 1
            entry["error"] = str(e)[:400]
            print(f"[실패] {name}: {e}")
        log(entry)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
