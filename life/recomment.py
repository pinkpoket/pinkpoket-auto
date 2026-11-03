#!/usr/bin/env python3
"""인생ON 긴 영상의 채널 댓글을 새 형식(감성 글 + 목차·구독·좋아요 안내)으로 고친다. VIDEO_IDS = 쉼표로."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "shorts"))
os.environ.setdefault("CHANNEL", "life")
import make_long as ml  # noqa: E402
import make_short as ms  # noqa: E402

log = json.load(open(os.path.join(HERE, "data", "long_log.json"), encoding="utf-8"))
tok = ms.yt_access_token()
h = {"Authorization": f"Bearer {tok}"}
me = ms.check_channel(tok)
for vid in [v.strip() for v in os.environ["VIDEO_IDS"].split(",") if v.strip()]:
    rec = next((x for x in log if x.get("video_id") == vid), None)
    if not rec:
        print(f"[댓글] {vid}: 긴 영상 기록 없음"); continue
    script = json.load(open(os.path.join(HERE, "long", "done", rec["file"]), encoding="utf-8"))
    text = ms.yt_clean(ml.long_comment(script))
    r = ms.requests.get("https://www.googleapis.com/youtube/v3/commentThreads", headers=h, timeout=30,
                        params={"part": "snippet", "videoId": vid, "maxResults": 100}).json()
    mine = [t for t in r.get("items", []) if t["snippet"]["topLevelComment"]["snippet"].get("authorChannelId", {}).get("value") == me]
    if mine:
        c = mine[0]["snippet"]["topLevelComment"]
        u = ms.requests.put("https://www.googleapis.com/youtube/v3/comments?part=snippet", headers=h, timeout=30,
                            json={"id": c["id"], "snippet": {"textOriginal": text}})
        print(f"[댓글] {vid}: {'고쳤어요' if u.ok else u.text[:200]}")
    else:
        ms.yt_comment(vid, text)
        print(f"[댓글] {vid}: 새로 달았어요")
