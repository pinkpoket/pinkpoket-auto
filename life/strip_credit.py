#!/usr/bin/env python3
"""인생ON 영상 설명란에서 '사진: Pixabay' 줄을 지운다. VIDEO_IDS = 쉼표로 구분한 영상 ID."""
import os
import requests

r = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
    "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30).json()
h = {"Authorization": f"Bearer {r['access_token']}"}
for vid in [v.strip() for v in os.environ["VIDEO_IDS"].split(",") if v.strip()]:
    it = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=h, timeout=30,
                      params={"part": "snippet", "id": vid}).json()["items"][0]
    sn = it["snippet"]
    if sn["channelId"] != os.environ["YT_CHANNEL_ID"]:
        print(f"{vid}: 인생ON 영상 아님"); continue
    desc = "\n".join(l for l in sn["description"].split("\n") if l.strip() != "사진: Pixabay")
    body = {"id": vid, "snippet": {k: sn[k] for k in ("title", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage") if k in sn} | {"description": desc}}
    u = requests.put("https://www.googleapis.com/youtube/v3/videos?part=snippet", headers=h, json=body, timeout=30)
    print(f"{vid}: {'출처 줄 삭제 완료' if u.ok else u.text[:200]}")
