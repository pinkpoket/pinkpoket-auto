#!/usr/bin/env python3
"""data/comment_fix.json {video_id: 감성 본문} 대로 내 채널이 단 댓글을 새 문구로 바꾼다 (없으면 새로 단다)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
import make_short as m

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fix = json.load(open(os.path.join(ROOT, "data", "comment_fix.json"), encoding="utf-8"))
tok = m.yt_access_token()
H = {"Authorization": f"Bearer {tok}"}
me = os.environ.get("YT_CHANNEL_ID", "").strip()
for vid, body in fix.items():
    text = m.yt_clean(m.build_comment({"comment": body}, None))
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/commentThreads",
                         params={"part": "snippet", "videoId": vid, "maxResults": 100}, headers=H, timeout=30)
        r.raise_for_status()
        mine = [t["snippet"]["topLevelComment"] for t in r.json().get("items", [])
                if t["snippet"]["topLevelComment"]["snippet"].get("authorChannelId", {}).get("value") == me]
        if mine:
            for c in mine:
                u = requests.put("https://www.googleapis.com/youtube/v3/comments?part=snippet", headers=H, timeout=30,
                                 json={"id": c["id"], "snippet": {"textOriginal": text}})
                print(vid, "수정", u.status_code, u.text[:150] if u.status_code >= 300 else "")
        else:
            print(vid, "새 댓글", m.yt_comment(vid, text))
    except Exception as e:  # noqa: BLE001
        print(vid, "실패", e)
