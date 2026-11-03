#!/usr/bin/env python3
"""인생ON 채널의 지정한 영상만 삭제한다 (공개 영상은 지우지 않음). VIDEO_IDS = 쉼표로 구분."""
import os
import sys
import requests

r = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
    "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30).json()
h = {"Authorization": f"Bearer {r['access_token']}"}
bad = 0
for vid in [v.strip() for v in os.environ["VIDEO_IDS"].split(",") if v.strip()]:
    items = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=h, timeout=30,
                         params={"part": "snippet,status", "id": vid}).json().get("items", [])
    if not items:
        print(f"[삭제] {vid}: 영상 없음 (이미 지워졌을 수 있음)"); continue
    sn, st = items[0]["snippet"], items[0]["status"]
    if sn["channelId"] != os.environ["YT_CHANNEL_ID"]:
        print(f"[삭제] {vid}: 인생ON 영상 아님 — 건너뜀"); bad += 1; continue
    if st["privacyStatus"] == "public":
        print(f"[삭제] {vid}: 공개 영상이라 안전을 위해 건너뜀 ({sn['title']})"); bad += 1; continue
    d = requests.delete("https://www.googleapis.com/youtube/v3/videos", headers=h, params={"id": vid}, timeout=30)
    print(f"[삭제] {vid} ({st['privacyStatus']}) {sn['title'][:40]}: {'삭제 완료' if d.status_code == 204 else d.text[:200]}")
    bad += 0 if d.status_code == 204 else 1
sys.exit(1 if bad else 0)
