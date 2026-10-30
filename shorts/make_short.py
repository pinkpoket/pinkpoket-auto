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

async def _tts(text, voice, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="+6%").save(path)


def tts(text, voice, path):
    for attempt in range(3):
        try:
            asyncio.run(_tts(text, voice, path))
            if os.path.getsize(path) > 1000:
                return
        except Exception as e:  # noqa: BLE001
            print(f"[음성] 재시도 {attempt + 1}: {e}")
            time.sleep(3)
    raise RuntimeError("음성 생성 실패")


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
            json={"prompt": f"{prompt}, {STYLE}"[:1500], "steps": 6}, timeout=90)
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

def wrap_ko(text, width):
    lines = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, width=width, break_long_words=True) or [""]
    return lines


def overlay_png(hook, subtitle, path, outro=False):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(H - 900, H):
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(150 * (y - (H - 900)) / 900)))
    # 상단 제목 (분홍 상자)
    f_hook = font(78)
    lines = wrap_ko(hook, 11)[:2]
    box_h = 60 + len(lines) * 104
    d.rounded_rectangle([60, 170, W - 60, 170 + box_h], radius=40, fill=PINK + (235,))
    y = 200
    for line in lines:
        tw = d.textlength(line, font=f_hook)
        d.text(((W - tw) / 2, y), line, font=f_hook, fill=(255, 255, 255),
               stroke_width=3, stroke_fill=(150, 40, 95))
        y += 104
    # 채널 이름
    f_tag = font(40)
    tag = "핑포의 작은집 연구소"
    tw = d.textlength(tag, font=f_tag)
    d.text(((W - tw) / 2, 170 + box_h + 24), tag, font=f_tag, fill=(255, 255, 255),
           stroke_width=4, stroke_fill=(0, 0, 0))
    # 하단 자막
    f_sub = font(70)
    lines = wrap_ko(subtitle, 13)[:4]
    total = len(lines) * 98
    top = H - 620 - total // 2
    d.rounded_rectangle([60, top - 40, W - 60, top + total + 30], radius=32, fill=(0, 0, 0, 160))
    y = top
    for line in lines:
        tw = d.textlength(line, font=f_sub)
        d.text(((W - tw) / 2, y), line, font=f_sub, fill=(255, 255, 255),
               stroke_width=4, stroke_fill=(0, 0, 0))
        y += 98
    if outro:
        f_b = font(68)
        for k, label in enumerate(["좋아요", "구독"]):
            bx = W // 2 - 400 + k * 420
            by = H // 2 - 130
            d.rounded_rectangle([bx, by, bx + 380, by + 140], radius=70,
                                fill=(230, 30, 40, 240) if k == 1 else PINK + (240,))
            tw = d.textlength(label, font=f_b)
            d.text((bx + (380 - tw) / 2, by + 30), label, font=f_b, fill=(255, 255, 255))
    img.save(path)


# ---------------------------------------------------------------- 영상

def clean_title(t):
    return re.sub(r"\s*#\S+", "", t or "").strip()


def make_scene(i, scene, voice, hook):
    audio = os.path.join(WORK, f"a{i}.mp3")
    raw = os.path.join(WORK, f"raw{i}.jpg")
    bg = os.path.join(WORK, f"bg{i}.jpg")
    ov = os.path.join(WORK, f"ov{i}.png")
    clip = os.path.join(WORK, f"c{i:02d}.mp4")
    tts(scene["text"], voice, audio)
    if not os.path.exists(raw):
        gradient_bg(raw, i)
    prepare_image(raw, bg)
    overlay_png(hook, scene["text"], ov, outro=scene.get("outro", False))
    dur = duration(audio) + 0.35
    frames = int(dur * FPS) + 1
    z = "min(1+0.0008*on,1.10)" if i % 2 == 0 else "max(1.10-0.0008*on,1.0)"
    vf = (f"[0:v]scale={int(W * 1.1)}:{int(H * 1.1)},"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}[bg];"
          f"[bg][1:v]overlay=0:0,format=yuv420p[v]")
    run(["ffmpeg", "-y", "-loop", "1", "-i", bg, "-i", ov, "-i", audio,
         "-filter_complex", vf, "-map", "[v]", "-map", "2:a",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
         "-t", f"{dur:.2f}", "-r", str(FPS), clip])
    return clip


def build_video(script, out_path):
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    AI_COUNT[0] = 0
    voice = script.get("voice") or "ko-KR-SunHiNeural"
    hook = script.get("hook") or clean_title(script["title"])
    scenes = list(script["scenes"])
    outro = script.get("outro") or "오늘 꿀팁이 도움이 됐다면 구독과 좋아요 부탁드려요. 자세한 정리는 블로그에 있어요!"
    scenes.append({"text": outro, "bg": "cozy pink bedroom corner with soft lamp light", "outro": True})
    from concurrent.futures import ThreadPoolExecutor

    def _pre(i_s):
        i, sc = i_s
        cloudflare_image(sc.get("bg") or "cozy small apartment living room", os.path.join(WORK, f"raw{i}.jpg"))
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(_pre, enumerate(scenes)))
    clips = [make_scene(i, s, voice, hook) for i, s in enumerate(scenes)]
    listfile = os.path.join(WORK, "list.txt")
    with open(listfile, "w") as f:
        f.writelines(f"file '{c}'\n" for c in clips)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
         "-c", "copy", "-movflags", "+faststart", out_path])
    return duration(out_path)


# ---------------------------------------------------------------- 설명란·쿠팡

def pick_coupang(script):
    keys = [k.strip() for k in script.get("coupang_keywords", []) if k.strip()]
    if not keys or not os.path.exists(LINKS_FILE):
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
    desc = script.get("description", "").strip()
    desc += f"\n\n📖 자세한 정리는 블로그에서 👉 {script.get('blog_url') or BLOG_HOME}"
    desc += "\n🏠 핑포의 작은집 연구소 · 핑포(핑크포켓, Pink Pocket)"
    desc += "\n※ 이 영상은 AI 음성과 AI 이미지를 사용해 만들었어요."
    product = pick_coupang(script)
    if product:
        desc = f"{DISCLOSURE}\n\n{desc}\n\n🛒 {product[1]}\n{product[0]}"
    return desc, product


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
                print("[시험] 업로드 건너뜀\n" + desc)
                continue
            yt = yt_upload(video, script["title"], desc, script.get("tags", []))
            if yt:
                vid, privacy = yt
                entry.update(video_id=vid, url=f"https://youtube.com/shorts/{vid}", privacy=privacy)
                print(f"[유튜브] 업로드 완료 ({privacy}): https://youtube.com/shorts/{vid}")
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
