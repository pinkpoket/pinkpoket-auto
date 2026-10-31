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
QUEUE = os.path.join(ROOT, "queue")
DONE = os.path.join(ROOT, "done")
WORK = os.path.join(ROOT, "_work")
OUT = os.path.join(ROOT, "_out")
LOG_FILE = os.path.join(REPO, "data", "shorts_log.json")
LINKS_FILE = os.path.join(REPO, "data", "coupang_links.txt")
LOGO = os.path.join(REPO, "brand", "icon.png")
W, H, FPS = 1080, 1920, 30

BLOG_HOME = "https://pinkpoket.blogspot.com"
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
PINK = (224, 85, 154)

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

TTS_RATE = os.environ.get("TTS_RATE", "+35%")


async def _tts(text, voice, path):
    """음성을 저장하고, 단어마다 (시작초, 끝초, 글자) 를 돌려준다."""
    import edge_tts
    words = []
    com = edge_tts.Communicate(text, voice, rate=TTS_RATE)
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

STYLE = ("bright cozy minimalist Korean apartment interior, soft natural daylight, pastel pink and "
         "warm white tones, photorealistic lifestyle photo, subject centered, vertical composition, "
         "no people, no text, no watermark")
AI_COUNT = [0]


def cloudflare_image(prompt, path):
    acc = os.environ.get("CF_ACCOUNT_ID", "").strip()
    tok = os.environ.get("CF_API_TOKEN", "").strip()
    if not (acc and tok):
        return False
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell",
            headers={"Authorization": f"Bearer {tok}"},
            json={"prompt": f"{prompt}, {STYLE}"[:1500], "steps": 8}, timeout=90)
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
    a, b = rnd.choice([((255, 236, 244), (246, 201, 220)), ((255, 245, 236), (240, 210, 222)),
                       ((250, 240, 248), (226, 196, 214))])
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

YELLOW = (255, 228, 92)


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
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(90 * (1 - y / 520))))
    # 위 제목: 노란 바탕 알약 상자, 글씨 크기에 맞춰 가운데
    f_hook = font(44)
    lines = wrap_ko(hook, 20)[:2]
    lh, pad_x, pad_y = 58, 40, 20
    tw_max = max(d.textlength(ln, font=f_hook) for ln in lines)
    box_w, box_h = tw_max + pad_x * 2, len(lines) * lh + pad_y * 2
    bx0, by0 = (W - box_w) / 2, 180
    d.rounded_rectangle([bx0 + 4, by0 + 6, bx0 + box_w + 4, by0 + box_h + 6], radius=box_h / 2, fill=(0, 0, 0, 70))
    d.rounded_rectangle([bx0, by0, bx0 + box_w, by0 + box_h], radius=box_h / 2, fill=YELLOW + (250,))
    y = by0 + pad_y - 4
    for line in lines:
        tw = d.textlength(line, font=f_hook)
        d.text(((W - tw) / 2, y), line, font=f_hook, fill=(70, 30, 45))
        y += lh
    # 채널 이름 + 로고 (작게)
    f_tag = font(26)
    tag = "핑포의 작은집 연구소"
    tw = d.textlength(tag, font=f_tag)
    logo_s = 44
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


CAP_SIZE, CAP_LH = 100, 136
CAP_MID = H // 2 + 120   # 자막 가운데 높이 (모든 장면 같음)


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
    lines = lines[:3]
    top = CAP_MID - len(lines) * CAP_LH // 2
    space = d.textlength(" ", font=f)
    for li, line in enumerate(lines):
        widths = [d.textlength(tokens[k], font=f) for k in line]
        x = (W - (sum(widths) + space * (len(line) - 1))) / 2
        y = top + li * CAP_LH
        for k, w in zip(line, widths):
            if k == active:
                d.rounded_rectangle([x - 14, y - 2, x + w + 14, y + CAP_LH - 14], radius=24, fill=PINK + (240,))
                d.text((x, y), tokens[k], font=f, fill=YELLOW, stroke_width=7, stroke_fill=(90, 20, 55))
            else:
                d.text((x, y), tokens[k], font=f, fill=(255, 255, 255), stroke_width=9, stroke_fill=(0, 0, 0))
            x += w + space
    # 진행 막대
    d.rectangle([0, 0, W, 14], fill=(255, 255, 255, 70))
    d.rectangle([0, 0, int(W * max(0.0, min(1.0, progress))), 14], fill=PINK + (255,))
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
    base_png(hook, base, outro=scene.get("outro", False))
    dur = duration(audio) + 0.05
    tokens, starts = word_times(scene["text"], words, dur)
    caps = []
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


def build_video(script, out_path):
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    AI_COUNT[0] = 0
    global TTS_RATE
    TTS_RATE = script.get("rate") or TTS_RATE
    voice = script.get("voice") or "ko-KR-SunHiNeural"
    hook = script.get("hook") or clean_title(script["title"])
    scenes = list(script["scenes"])
    # 좋아요·구독 마지막 화면은 시청 지속률을 떨어뜨려서 기본은 뺀다 (링크·구독 안내는 설명란·댓글로).
    # 대본에 "end_card": true 가 있을 때만 붙인다.
    if script.get("end_card"):
        outro = script.get("outro") or "자세한 건 블로그에! 구독하고 꿀팁 받아 가세요!"
        scenes.append({"text": outro, "bg": "cozy pink bedroom corner with soft lamp light", "outro": True})
    from concurrent.futures import ThreadPoolExecutor

    def _pre(i_s):
        i, sc = i_s
        cloudflare_image(sc.get("bg") or "cozy small apartment living room", os.path.join(WORK, f"raw{i}.jpg"))
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(_pre, enumerate(scenes)))
    whoosh(os.path.join(WORK, "whoosh.wav"))
    # 음성을 먼저 모두 만들어 전체 길이를 알아 둔다 (진행 막대용)
    voiced = []
    for i, sc in enumerate(scenes):
        audio = os.path.join(WORK, f"a{i}.mp3")
        words = tts(sc["text"], voice, audio)
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
             f"[1:a]volume=0.16,afade=t=out:st={max(0.0, d - 0.8):.2f}:d=0.8[b];"
             "[0:a][b]amix=inputs=2:duration=first:normalize=0[a]",
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
    product = pick_coupang(script)
    lines = []
    if product:
        lines += [DISCLOSURE, ""]
    lines.append(f"📖 블로그에서 자세히 보기 👉 {blog}")
    if product:
        lines.append(f"🛒 {product[1]} 👉 {product[0]}")
    lines += ["", script.get("description", "").strip(), "",
              "🏠 핑포의 작은집 연구소 · 핑포(핑크포켓, Pink Pocket)",
              "※ 이 영상은 AI 음성과 AI 이미지를 사용해 만들었어요."]
    return "\n".join(lines).strip(), product


def build_comment(script, product):
    """영상에 남길 링크 바로가기 댓글."""
    blog = script.get("blog_url") or BLOG_HOME
    lines = ["💗 링크 바로가기", f"📖 블로그 자세히 보기 👉 {blog}"]
    if product:
        lines.append(f"🛒 {product[1]} 👉 {product[0]}")
        lines += ["", DISCLOSURE]
    return "\n".join(lines)


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
        raise RuntimeError(f"연결된 채널({got})이 핑포 채널({want})이 아니라서 업로드를 멈췄어요")
    return got


def yt_upload(video, title, desc, tags):
    tok = yt_access_token()
    if not tok:
        return None
    check_channel(tok)
    title = yt_clean(title)
    if "#shorts" not in title.lower() and len(title) + 8 <= 100:
        title += " #shorts"
    clean_tags, total = [], 0
    for t in tags:
        t = yt_clean(t.lstrip("#")).strip()
        if t and total + len(t) + 2 < 450:
            clean_tags.append(t)
            total += len(t) + 2
    meta = {
        "snippet": {"title": title[:100], "description": yt_clean(desc)[:4900], "tags": clean_tags,
                    "categoryId": "26", "defaultLanguage": "ko", "defaultAudioLanguage": "ko"},
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
            video = os.path.join(OUT, f"{name}.mp4")
            secs = build_video(script, video)
            entry.update(seconds=round(secs, 1), ai_images=AI_COUNT[0])
            print(f"[완성] {name}: {secs:.1f}초, AI 그림 {AI_COUNT[0]}장")
            desc, product = build_description(script)
            if os.environ.get("DRY_RUN") == "1":
                print("[시험] 업로드 건너뜀\n" + desc + "\n--- 댓글 ---\n" + build_comment(script, product))
                continue
            yt = yt_upload(video, script["title"], desc, script.get("tags", []))
            if yt:
                vid, privacy = yt
                entry.update(video_id=vid, url=f"https://youtube.com/shorts/{vid}", privacy=privacy)
                print(f"[유튜브] 업로드 완료 ({privacy}): https://youtube.com/shorts/{vid}")
                try:
                    cid = yt_comment(vid, build_comment(script, product))
                    entry["comment"] = "ok"
                    print(f"[댓글] 링크 댓글 완료: {cid}")
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
