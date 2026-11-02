#!/usr/bin/env python3
"""인생ON 일부공개 영상을 공개(public)로 바꾼다. VIDEO_IDS = 쉼표로 구분한 영상 ID."""
import os
import sys

import requests

ids = [v.strip() for v in os.environ.get("VIDEO_IDS", "").replace("https://youtube.com/shorts/", "").split(",") if v.strip()]
r = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
    "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30).json()
h = {"Authorization": f"Bearer {r['access_token']}"}
failed = 0
for vid in ids:
    cur = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=h, timeout=30,
                       params={"part": "status,snippet", "id": vid}).json().get("items", [])
    if not cur or cur[0]["snippet"]["channelId"] != os.environ["YT_CHANNEL_ID"]:
        print(f"[공개] {vid}: 인생ON 채널 영상이 아니에요 — 건너뜀"); failed += 1; continue
    st = cur[0]["status"]
    st["privacyStatus"] = "public"
    u = requests.put("https://www.googleapis.com/youtube/v3/videos?part=status", headers=h, timeout=30,
                     json={"id": vid, "status": {k: st[k] for k in ("privacyStatus", "selfDeclaredMadeForKids", "containsSyntheticMedia") if k in st}})
    print(f"[공개] {vid}: {'공개 완료 ✅' if u.ok else '실패 ' + u.text[:200]}")
    failed += 0 if u.ok else 1
sys.exit(1 if failed else 0)
