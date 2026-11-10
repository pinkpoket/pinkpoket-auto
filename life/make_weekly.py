#!/usr/bin/env python3
"""인생ON 일요일 '몰아 듣기' 모음 영상 (2026-11-08 핑포 결정, 황금노후 벤치마킹).

이번 주(최근 7일) 공개된 긴 영상들을 이어 붙여 1편으로 올린다. 대본을 새로 쓰지 않는다.
- 영상 파일: long-life.yml 이 매일 보관한 Actions 아티팩트(long-video)를 ART 폴더에 내려받아 둔 것
- 이번 주 조회수 상위 7편만 (하루 2편이라 전부 넣으면 6시간이 넘음)
- 순서: 이번 주 조회수 1위를 맨 앞(첫인상), 나머지는 올린 순서대로
- 이야기 사이에 3초 제목 화면
- 설명란: 목차(시간) + 각 원본 영상 링크
결과 기록: life/data/weekly_log.json
"""
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys

os.environ.setdefault("CHANNEL", "life")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_long as ml  # noqa: E402

ms = ml.ms
ART = os.environ.get("ART", "/tmp/art")
WORK = os.path.join(HERE, "long", "_weekly")
LOG = os.path.join(HERE, "data", "weekly_log.json")
DAYS = int(os.environ.get("DAYS", "7") or 7)
MAX_PARTS = int(os.environ.get("MAX_PARTS", "7") or 7)  # 모음에 넣을 최대 편수 (약 3시간)


def run(cmd):
    print(" ".join(cmd[:6]), "...")
    subprocess.run(cmd, check=True)


def week_entries():
    log = json.load(open(ml.LOG, encoding="utf-8"))
    since = (dt.datetime.utcnow() - dt.timedelta(days=DAYS, hours=2)).strftime("%Y-%m-%d %H:%M")
    out = []
    for e in log:
        if e.get("privacy") != "public" or not e.get("video_id") or e.get("at", "") < since:
            continue
        stem = os.path.splitext(e["file"])[0]
        mp4 = glob.glob(os.path.join(ART, "**", f"{stem}.mp4"), recursive=True)
        if not mp4:
            print("영상 파일 없음(보관 전 영상):", e["title"])
            continue
        done = os.path.join(ml.DONE, e["file"])
        e["script"] = json.load(open(done, encoding="utf-8")) if os.path.exists(done) else {}
        e["mp4"] = mp4[0]
        out.append(e)
    return out


def views(ids):
    try:
        tok = ms.yt_access_token()
        r = ms.requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=30,
                            params={"part": "statistics", "id": ",".join(ids)},
                            headers={"Authorization": f"Bearer {tok}"}).json()
        return {it["id"]: int(it["statistics"].get("viewCount", 0)) for it in r.get("items", [])}
    except Exception as e:  # noqa: BLE001
        print("[조회수] 못 가져옴:", e)
        return {}


def norm(src, out):
    """모든 조각을 같은 규격으로 (이어 붙일 때 소리·화면 어긋남 방지)."""
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", f"scale={ml.W}:{ml.H},fps={ml.FPS},format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
         out])


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    es = week_entries()
    if len(es) < 3:
        print(f"이번 주 영상이 {len(es)}편뿐이라 모음은 쉬어요 (3편 이상일 때만)")
        return 0
    v = views([e["video_id"] for e in es])
    # 하루 2편이면 한 주 14편(6시간 넘음) → 조회수 상위 MAX_PARTS 편만, 1위를 맨 앞에 두고 나머지는 올린 순서대로
    top = sorted(es, key=lambda e: -v.get(e["video_id"], 0))[:MAX_PARTS]
    best = top[0]
    order = [best] + [e for e in es if e in top and e is not best]
    parts, marks, t = [], [], 0.0
    for i, e in enumerate(order):
        bg = os.path.join(WORK, f"bg{i}.jpg")
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "40", "-i", e["mp4"], "-frames:v", "1", bg])
        if i > 0:  # 두 번째 이야기부터 3초 제목 화면
            card = os.path.join(WORK, f"card{i}.jpg")
            ml.title_card(bg, card, e["title"], f"{i + 1}번째 이야기")
            seg = os.path.join(WORK, f"c{i}.mp4")
            ml.silent_segment(card, seg, 3.0)
            parts.append(seg)
            t += 3.0
        marks.append((t, e["title"]))
        body = os.path.join(WORK, f"v{i}.mp4")
        norm(e["mp4"], body)
        parts.append(body)
        t += ms.duration(body)
    normed = []
    for k, p in enumerate(parts):
        if os.path.basename(p).startswith("c"):
            q = os.path.join(WORK, f"n{k}.mp4")
            norm(p, q)
            normed.append(q)
        else:
            normed.append(p)
    lst = os.path.join(WORK, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in normed)
    final = os.path.join(WORK, "weekly.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
         "-movflags", "+faststart", final])
    secs = ms.duration(final)
    hours = secs / 3600
    print(f"[완성] {len(order)}편, {secs / 60:.0f}분")

    base = best["title"].split("|")[0].strip()
    title = f"{base} (이번 주 이야기 {len(order)}편 몰아 듣기)"
    if len(title) > 95:
        title = f"{base[:60]} ({len(order)}편 몰아 듣기)"
    st = best.get("script") or {}
    dur_txt = f"{int(secs // 3600)}시간 {int(secs % 3600 // 60)}분" if secs >= 3600 else f"{int(secs // 60)}분"
    lines = [f"🔴 이번 주 인생ON 이야기 {len(order)}편을 한 번에 이어 들으세요 ({dur_txt})",
             "", "틀어 두고 집안일하시면서, 산책하시면서, 잠들기 전에 편하게 들으세요.", "",
             "📌 목차", *[f"{ml.stamp(tt)} {name.split('|')[0].strip()}" for tt, name in marks],
             "", "📺 한 편씩 따로 보기", *[f"▶ {e['title'].split('|')[0].strip()} 👉 {e['url']}" for e in order],
             "", "💬 이번 주 이야기 중 가장 마음에 남은 이야기는 무엇이었나요? 댓글로 남겨 주세요.",
             "", "#인생온 #오디오북 #몰아듣기 #노후지혜 #인생조언 #노후행복 #시니어 #좋은글 #마음공부 #잠잘때듣는",
             "", "🔥 인생ON : 마음의 불을 켜다",
             "※ 이 영상은 AI 음성을 사용해 만들었어요. 건강 관련 내용은 일반 정보이며, 지병이 있으면 의사와 상의하세요."]
    desc = "\n".join(lines)
    tags = ["인생온", "인생ON", "오디오북", "몰아 듣기", "노후지혜", "인생조언", "잠잘 때 듣는", "시니어"]
    for e in order:
        tags += (e.get("script") or {}).get("tags", [])
    tags = list(dict.fromkeys(tags))
    thumb = os.path.join(WORK, "thumb.jpg")
    import thumbs
    thumbs.make(os.path.join(WORK, "bg0.jpg"), thumb, st.get("thumbnail_text") or base[:12],
                f"몰아 듣기 {dur_txt}", "left")
    entry = {"at": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "title": title, "seconds": round(secs, 1),
             "parts": [e["video_id"] for e in order]}
    if os.environ.get("DRY_RUN") == "1":
        print(title)
        print(desc)
        shutil.copy(thumb, os.path.join(ml.OUT, "weekly-thumb.jpg")) if os.path.isdir(ml.OUT) else None
        return 0
    vid, privacy = ms.yt_upload(final, title, desc, tags, shorts=False)
    entry.update(video_id=vid, url=f"https://youtu.be/{vid}", privacy=privacy)
    print(f"[유튜브] 업로드 완료 ({privacy}): https://youtu.be/{vid}")
    try:
        ml.set_thumbnail(vid, thumb)
    except Exception as e:  # noqa: BLE001
        entry["thumb_error"] = str(e)[:200]
    if privacy == "public":
        try:
            ms.yt_comment(vid, "이번 주 인생ON 이야기를 한 번에 모았어요 🔥\n영상 아래 '더보기'를 누르시면 이야기별 목차가 있어요.\n"
                               "가장 마음에 남은 이야기는 몇 번째였나요? 댓글로 들려주세요.\n"
                               "소중한 분께 카톡으로 나눠 주시면 인생ON에 큰 힘이 됩니다 🙏")
        except Exception as e:  # noqa: BLE001
            print("[댓글]", e)
    data = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
    data.append(entry)
    json.dump(data[-100:], open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
