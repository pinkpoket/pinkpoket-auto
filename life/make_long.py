#!/usr/bin/env python3
"""인생ON 긴 영상(가로 16:9, 약 25분 이야기형 — 2026-11-08 부터, LONG_GUIDE ⭐) 자동 제작 + 유튜브 업로드.

life/long/queue/*.json 대본:
{
  "title": "유튜브 제목",
  "thumbnail_text": "썸네일 큰 글씨 (두 줄은 \\n, 줄당 8자 안팎)",
  "intro": ["시작 문장", ...],                         (2문장: 단정형 훅 + 바로 본론, LONG_GUIDE 3번)
  "chapters": [{"title": "1. 소제목", "bg": "nature words",
                "sentences": ["한 문장씩", ...]}],
  "outro": ["마무리 문장", ...],
  "description": "설명 (챕터 시간표는 봇이 붙임)",
  "tags": ["..."],
  "comment": "고정 댓글 2~3줄"
}
화면: 자연 풍경 사진(Pixabay 가로) + 아래쪽 큰 자막(문장 단위) + 왼쪽 위 챕터 이름 + 오른쪽 위 인생온 로고.
챕터가 바뀔 때 3초 제목 화면. 목소리·색은 channel.py 의 life 프로필.
"""
import glob
import json
import os
import random
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("CHANNEL", "life")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "shorts"))
sys.path.insert(0, REPO)
import make_short as ms  # noqa: E402
import channel as ch  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

W, H, FPS = 1920, 1080, 25
QUEUE = os.environ.get("LONG_QUEUE") or os.path.join(HERE, "long", "queue")
DONE = os.path.join(HERE, "long", "done")
WORK = os.path.join(HERE, "long", "_work")
OUT = os.path.join(HERE, "long", "_out")
LOG = os.path.join(HERE, "data", "long_log.json")
VOICE = ch.P.get("long_voice") or ch.P.get("voice") or "ko-KR-SunHiNeural"  # 긴 영상: 남성 인준
C = ch.P["colors"]
BOX, YEL = tuple(C["hook_bg"]), tuple(C["hook_text"])
CAP = 110         # 자막 글씨 크기 (시니어용, 74 → 88 → 110, 2026-11-08 핑포 요청)
CAP_LH = 145
VOICE_GAIN = 2.3  # 긴 영상 목소리 크게 (쇼츠 1.8)
BGM_VOL = 0.05
MOVES = ["zoom_in", "pan_right", "zoom_out", "pan_down", "pan_left", "pan_up"]
PER_IMAGE = 4     # 문장 몇 개마다 사진을 바꿀지


# ---------------------------------------------------------------- 그림

def fetch_photo(prompt, path):
    if ms.pixabay_image(prompt, path, orientation="horizontal"):
        return True
    return ms.cloudflare_image(prompt, path)


def fit(src, dst, dim=0.0, blur=0):
    img = Image.open(src).convert("RGB")
    sc = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * sc) + 1, int(img.height * sc) + 1), Image.LANCZOS)
    l, t = (img.width - W) // 2, (img.height - H) // 2
    img = img.crop((l, t, l + W, t + H))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if dim:
        img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), dim)
    img.save(dst, quality=92)


def wrap(d, text, f, max_w):
    toks = text.split()
    return [[toks[k] for k in line] for line in ms.wrap_tokens(d, toks, f, max_w)]


def frame(bg, out, sentence, chapter):
    """사진 위에 얹을 투명 그림: 아래 자막 + 챕터 이름 + 로고 (사진은 영상에서 움직인다)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(H - 560, H):  # 아래쪽을 부드럽게 어둡게 (자막이 커져 440 → 560)
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(215 * ((y - (H - 560)) / 560) ** 1.2)))
    f = ms.font(CAP)
    lines = [" ".join(l) for l in wrap(d, sentence, f, W - 160)][:3]
    y = H - 70 - len(lines) * CAP_LH
    for ln in lines:
        tw = d.textlength(ln, font=f)
        d.text(((W - tw) / 2, y), ln, font=f, fill=(255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0))
        y += CAP_LH
    if chapter:
        fc = ms.font(40)
        tw = d.textlength(chapter, font=fc)
        d.rounded_rectangle([40, 36, 40 + tw + 48, 36 + 70], radius=35, fill=BOX + (235,))
        d.text((64, 46), chapter, font=fc, fill=YEL)
    img.alpha_composite(ov)
    try:
        logo = Image.open(ms.LOGO).convert("RGBA").resize((96, 96), Image.LANCZOS)
        img.alpha_composite(logo, (W - 136, 26))
    except Exception:  # noqa: BLE001
        pass
    img.save(out)


def title_card(bg, out, title, sub=""):
    img = Image.open(bg).convert("RGB").filter(ImageFilter.GaussianBlur(8))
    img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
    d = ImageDraw.Draw(img)
    f = ms.font(96)
    lines = [" ".join(l) for l in wrap(d, title, f, W - 300)][:2]
    bh = len(lines) * 130 + 90
    y0 = (H - bh) // 2
    bw = max(d.textlength(l, font=f) for l in lines) + 140
    d.rounded_rectangle([(W - bw) / 2, y0, (W + bw) / 2, y0 + bh], radius=40, fill=BOX)
    y = y0 + 40
    for ln in lines:
        tw = d.textlength(ln, font=f)
        d.text(((W - tw) / 2, y), ln, font=f, fill=YEL)
        y += 130
    if sub:
        fs = ms.font(44)
        tw = d.textlength(sub, font=fs)
        d.text(((W - tw) / 2, y0 + bh + 30), sub, font=fs, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
    img.save(out, quality=92)


def thumbnail(bg, out, text):
    img = Image.open(bg).convert("RGB")
    sc = max(1280 / img.width, 720 / img.height)
    img = img.resize((int(img.width * sc) + 1, int(img.height * sc) + 1), Image.LANCZOS)
    l, t = (img.width - 1280) // 2, (img.height - 720) // 2
    img = img.crop((l, t, l + 1280, t + 720))
    img = Image.blend(img, Image.new("RGB", (1280, 720), (0, 0, 0)), 0.25)
    d = ImageDraw.Draw(img)
    lines = text.split("\n")[:3]
    f = ms.font(118 if max(len(x) for x in lines) <= 8 else 96)
    lh = int(f.size * 1.25)
    y = (720 - lh * len(lines)) // 2
    for i, ln in enumerate(lines):
        tw = d.textlength(ln, font=f)
        x = (1280 - tw) / 2
        d.rounded_rectangle([x - 26, y - 8, x + tw + 26, y + lh - 8], radius=18, fill=BOX)
        d.text((x, y - 4), ln, font=f, fill=YEL if i % 2 == 0 else (255, 255, 255))
        y += lh + 10
    try:
        logo = Image.open(ms.LOGO).convert("RGBA").resize((130, 130), Image.LANCZOS)
        base = img.convert("RGBA")
        base.alpha_composite(logo, (1280 - 160, 24))
        img = base.convert("RGB")
    except Exception:  # noqa: BLE001
        pass
    img.save(out, quality=90)


# ---------------------------------------------------------------- 영상

def moving_segment(photo, overlay, audio, out, move, start, total, fade_in=False, pad=0.35):
    """사진을 천천히 확대·이동시키며 그 위에 자막 그림을 얹는다.
    같은 사진이 여러 문장에 걸치면 start/total(초)로 움직임을 이어 간다."""
    dur = ms.duration(audio) + pad
    n = max(1, int(round(dur * FPS)))
    off, tot = int(start * FPS), max(1, int(round(total * FPS)))
    p = f"(on+{off})/{tot}"
    z, cx, cy = "1.12", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    expr = {
        "zoom_in": (f"1.0+0.12*{p}", cx, cy),
        "zoom_out": (f"1.12-0.12*{p}", cx, cy),
        "pan_right": (z, f"(iw-iw/zoom)*{p}", cy),
        "pan_left": (z, f"(iw-iw/zoom)*(1-{p})", cy),
        "pan_down": (z, cx, f"(ih-ih/zoom)*{p}"),
        "pan_up": (z, cx, f"(ih-ih/zoom)*(1-{p})"),
    }[move]
    fade = ",fade=t=in:st=0:d=0.5" if fade_in else ""
    fc = (f"[0:v]scale=2880:1620,zoompan=z='{expr[0]}':x='{expr[1]}':y='{expr[2]}':d={n}:s={W}x{H}:fps={FPS}[bg];"
          f"[bg][1:v]overlay=0:0,format=yuv420p{fade}[v];[2:a]apad=pad_dur={pad},aresample=44100[a]")
    ms.run(["ffmpeg", "-y", "-i", photo, "-i", overlay, "-i", audio, "-filter_complex", fc,
            "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out])
    return dur


def segment(png, audio, out, fade_in=False, pad=0.35):
    dur = ms.duration(audio) + pad
    vf = "format=yuv420p" + (",fade=t=in:st=0:d=0.5" if fade_in else "")
    ms.run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", png, "-i", audio,
            "-filter_complex", f"[1:a]apad=pad_dur={pad},aresample=44100[a]",
            "-map", "0:v", "-map", "[a]", "-vf", vf, "-t", f"{dur:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out])
    return dur


def silent_segment(png, out, secs):
    ms.run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", png,
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{secs:.2f}",
            "-vf", "format=yuv420p,fade=t=in:st=0:d=0.4", "-c:v", "libx264", "-preset", "veryfast",
            "-tune", "stillimage", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", out])
    return secs


# 구독 부탁 문장 (2026-11-14 핑포 문구). 영상 맨 끝 목소리·설명란·고정 댓글에 같은 말로 넣는다.
SUB_LINE = "구독과 좋아요 눌러 주시고, 작지만 따뜻한 복 하나 받아 가세요."
SUB_TEXT = "💛 구독과 좋아요 눌러 주시고, 작지만 따뜻한 복 하나 받아 가세요 🙏"


def outro_with_sub(script):
    """outro 맨 끝에 구독 부탁 한 문장 (대본에 이미 구독 말이 있으면 그대로)."""
    out = [x for x in (script.get("outro") or []) if x.strip()]
    if not any("구독" in x for x in out):
        out.append(SUB_LINE)
    return out


def build(script, out_path):
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    # 1) 문장 목록 만들기: (챕터 이름, 문장, 사진 번호)
    items, photos = [], []
    def add_block(sentences, chapter, bg):
        for k, s in enumerate(sentences):
            if k % PER_IMAGE == 0:
                photos.append(bg)
            items.append({"chapter": chapter, "text": s.strip(), "photo": len(photos) - 1, "new_photo": k % PER_IMAGE == 0})
    add_block(script.get("intro", []), "", script.get("intro_bg", "sunrise mountain lake"))
    chapters = script["chapters"]
    for c in chapters:
        items.append({"card": c["title"], "photo": len(photos)})
        add_block(c["sentences"], c["title"], c.get("bg") or random.choice(ms.NATURE_QUERIES))
    add_block(outro_with_sub(script), "", script.get("outro_bg", "sunset calm lake"))
    # 2) 사진 받기 (같은 대표 낱말로 여러 장이면 서로 다른 사진)
    raw = [os.path.join(WORK, f"p{i}.jpg") for i in range(len(photos))]
    with ThreadPoolExecutor(max_workers=4) as ex:
        ok = list(ex.map(lambda a: fetch_photo(*a), zip(photos, raw)))
    good = [r for r, o in zip(raw, ok) if o]
    if not good:
        raise RuntimeError("사진을 하나도 못 받았어요")
    for r, o in zip(raw, ok):
        if not o:
            shutil.copy(random.choice(good), r)
    for r in raw:
        fit(r, r)
    # 3) 음성 (문장마다)
    def speak(i_it):
        i, it = i_it
        text = it.get("card") or it["text"]
        path = os.path.join(WORK, f"a{i}.mp3")
        ms.tts(text, VOICE, path)
        return path
    with ThreadPoolExecutor(max_workers=4) as ex:
        audios = list(ex.map(speak, enumerate(items)))
    # 4) 장면 영상 + 챕터 시간표 (사진마다 움직임 하나: 확대·축소·좌우·상하 번갈아)
    lens = [ms.duration(a) + 0.35 for a in audios]
    photo_total, photo_start = {}, {}
    for it, ln in zip(items, lens):
        if not it.get("card"):
            photo_total[it["photo"]] = photo_total.get(it["photo"], 0) + ln
    segs, t, marks = [], 0.0, []
    for i, it in enumerate(items):
        seg = os.path.join(WORK, f"s{i:04d}.mp4")
        bg = raw[min(it["photo"], len(raw) - 1)]
        if it.get("card"):
            png = os.path.join(WORK, f"f{i}.jpg")
            marks.append((t, it["card"]))
            title_card(bg, png, it["card"])
            t += segment(png, audios[i], seg, fade_in=True, pad=1.2)
        else:
            png = os.path.join(WORK, f"f{i}.png")
            frame(bg, png, it["text"], it["chapter"])
            ph = it["photo"]
            start = photo_start.get(ph, 0.0)
            t += moving_segment(bg, png, audios[i], seg, MOVES[ph % len(MOVES)], start, photo_total[ph],
                                fade_in=it.get("new_photo", False))
            photo_start[ph] = start + lens[i]
        segs.append(seg)
    lst = os.path.join(WORK, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    joined = os.path.join(WORK, "joined.mp4")
    ms.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    # 5) 배경음악 작게
    bgm = sorted(glob.glob(os.path.join(REPO, "brand", "bgm", "*.mp3")))
    if bgm:
        song = random.Random(script["title"]).choice(bgm)
        ms.run(["ffmpeg", "-y", "-i", joined, "-stream_loop", "-1", "-i", song, "-filter_complex",
                f"[1:a]volume={BGM_VOL},afade=t=out:st={max(0.0, t - 2):.2f}:d=2[b];"
                f"[0:a]volume={VOICE_GAIN}[v];[v][b]amix=inputs=2:duration=first:normalize=0,"
                "alimiter=limit=0.95:level=disabled[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", out_path])
    else:
        shutil.copy(joined, out_path)
    thumb = os.path.join(WORK, "thumb.jpg")
    import thumbs  # 왼쪽 글씨형(A) 썸네일
    thumbs.make(raw[0], thumb, script.get("thumbnail_text") or script["title"][:16],
                script.get("thumb_badge", ""), "left")
    return ms.duration(out_path), marks, thumb


def stamp(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def recent_long(n=2):
    """이미 공개된 지난 긴 영상 (최근 것부터) — 설명란·고정 댓글에서 다음 영상으로 이어 보게."""
    try:
        data = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    except Exception:  # noqa: BLE001
        return []
    pub = [x for x in data if x.get("privacy") == "public" and x.get("url") and x.get("title")]
    return list(reversed(pub))[:n]


def description(script, marks):
    lines = [script.get("description", "").strip()]
    prev = recent_long(2)
    if prev:
        lines += ["", "📺 함께 들으면 좋은 이야기"]
        lines += [f"▶ {x['title'].split('|')[0].strip()} 👉 {x['url']}" for x in prev]
    lines += ["", "📌 목차", "0:00 시작"]
    lines += [f"{stamp(t)} {title}" for t, title in marks]
    lines += ["", SUB_TEXT, "", "🔥 인생ON : 마음의 불을 켜다",
              "※ 이 영상은 AI 음성을 사용해 만들었어요. 건강 관련 내용은 일반 정보이며, 지병이 있으면 의사와 상의하세요."]
    return "\n".join(lines).strip()


def long_comment(script):
    """긴 영상 고정 댓글: 대본의 감성 글 + 목차·구독·좋아요 안내."""
    body = (script.get("comment") or "").strip() or f"오늘 '{script['title'].split('|')[0].strip()}' 이야기, 마음에 닿으셨나요? 🔥"
    tail = ["", "📌 영상 아래 '더보기'를 누르시면 목차가 있어요. 다시 듣고 싶은 부분만 골라 보실 수 있어요.",
            SUB_TEXT,
            *([f"📺 지난 이야기도 들어 보세요 👉 {p[0]['url']}"] if (p := recent_long(1)) else []),
            "소중한 분께 카톡으로 나눠 주시면 인생ON에 큰 힘이 됩니다."]
    return body + "\n" + "\n".join(tail)


def set_thumbnail(vid, path):
    tok = ms.yt_access_token()
    with open(path, "rb") as f:
        r = ms.requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
                             headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"}, data=f, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"썸네일 실패 {r.status_code}: {r.text[:200]}")


def log(entry):
    data = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    data.append(entry)
    json.dump(data[-300:], open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    os.makedirs(DONE, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(os.path.join(QUEUE, "*.json")))
    if not files:
        print("대기 중인 긴 영상 대본 없음")
        return 0
    failed = 0
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        entry = {"file": os.path.basename(path), "at": time.strftime("%Y-%m-%d %H:%M")}
        try:
            script = json.load(open(path, encoding="utf-8"))
            entry["title"] = script["title"]
            video = os.path.join(OUT, f"{name}.mp4")
            secs, marks, thumb = build(script, video)
            entry["seconds"] = round(secs, 1)
            print(f"[완성] {name}: {secs / 60:.1f}분, 챕터 {len(marks)}개")
            desc = description(script, marks)
            if os.environ.get("DRY_RUN") == "1":
                print(desc)
                shutil.copy(thumb, os.path.join(OUT, f"{name}-thumb.jpg"))
                continue
            vid, privacy = ms.yt_upload(video, script["title"], desc, script.get("tags", []), shorts=False)
            entry.update(video_id=vid, url=f"https://youtu.be/{vid}", privacy=privacy)
            print(f"[유튜브] 업로드 완료 ({privacy}): https://youtu.be/{vid}")
            try:
                set_thumbnail(vid, thumb)
                print("[썸네일] 완료")
            except Exception as e:  # noqa: BLE001
                entry["thumb_error"] = str(e)[:200]
                print(f"[썸네일] {e}")
            if privacy == "public":
                try:
                    ms.yt_comment(vid, long_comment(script))
                    entry["comment"] = "ok"
                except Exception as e:  # noqa: BLE001
                    print(f"[댓글] {e}")
            shutil.move(path, os.path.join(DONE, os.path.basename(path)))
        except Exception as e:  # noqa: BLE001
            failed += 1
            entry["error"] = str(e)[:400]
            print(f"[실패] {name}: {e}")
        log(entry)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
