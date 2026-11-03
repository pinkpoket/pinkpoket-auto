#!/usr/bin/env python3
"""이미 올린 인생ON 긴 영상의 썸네일을 지금 디자인(왼쪽 글씨형)으로 다시 만든다. VIDEO_IDS = 쉼표로."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("CHANNEL", "life")
import make_long as ml  # noqa: E402
import thumbs  # noqa: E402

log = json.load(open(os.path.join(HERE, "data", "long_log.json"), encoding="utf-8"))
for vid in [v.strip() for v in os.environ["VIDEO_IDS"].split(",") if v.strip()]:
    rec = next((x for x in log if x.get("video_id") == vid), None)
    if not rec:
        print(f"[썸네일] {vid}: 기록 없음"); continue
    s = json.load(open(os.path.join(HERE, "long", "done", rec["file"]), encoding="utf-8"))
    photo, out = f"/tmp/{vid}.jpg", f"/tmp/{vid}-thumb.jpg"
    if not ml.fetch_photo(s.get("intro_bg") or "misty mountains", photo):
        print(f"[썸네일] {vid}: 사진 못 받음"); continue
    thumbs.make(photo, out, s.get("thumbnail_text") or s["title"][:16], s.get("thumb_badge", ""), "left")
    ml.set_thumbnail(vid, out)
    print(f"[썸네일] {vid}: 새 디자인으로 바꿈")
