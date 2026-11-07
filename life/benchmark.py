#!/usr/bin/env python3
"""시니어 쇼츠 벤치마킹: 최근 N일 조회수 상위 쇼츠를 YouTube Data API 검색으로 모은다 (읽기만, 공개 정보).
결과: analysis/benchmark/shorts.json
"""
import datetime as dt
import json
import os
import re

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "analysis", "benchmark", "shorts.json")
DAYS = int(os.environ.get("DAYS", "60") or 60)
QUERIES = [q.strip() for q in os.environ.get("QUERIES", "").split(",") if q.strip()] or [
    "노후 인생조언", "나이 들수록 인간관계", "노후 건강 습관", "쇼펜하우어 명언", "부처님 말씀 인생",
    "50대 60대 좋은글", "사람 구별법 말투", "노년 지혜 명언", "시니어 건강 상식", "인연 끊어야 할 사람",
]


def dur(s):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0


def main():
    tok = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    after = (dt.datetime.utcnow() - dt.timedelta(days=DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = {}
    for q in QUERIES:
        r = requests.get("https://www.googleapis.com/youtube/v3/search", headers=h, timeout=30, params={
            "part": "snippet", "q": q, "type": "video", "videoDuration": "short", "order": "viewCount",
            "regionCode": "KR", "relevanceLanguage": "ko", "publishedAfter": after, "maxResults": 50}).json()
        if "error" in r:
            print(f"[벤치] {q}: 오류 {r['error'].get('message')}")
            continue
        for it in r.get("items", []):
            found.setdefault(it["id"]["videoId"], []).append(q)
        print(f"[벤치] {q}: {len(r.get('items', []))}개")
    ids = list(found)
    vids, chans = [], set()
    for i in range(0, len(ids), 50):
        r = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=h, timeout=30, params={
            "part": "snippet,contentDetails,statistics", "id": ",".join(ids[i:i + 50])}).json()
        for it in r.get("items", []):
            sn, st = it["snippet"], it.get("statistics", {})
            sec = dur(it["contentDetails"].get("duration"))
            if sec > 180:
                continue
            chans.add(sn["channelId"])
            vids.append({"id": it["id"], "title": sn.get("title"), "channel": sn.get("channelTitle"),
                         "channel_id": sn["channelId"], "published": sn.get("publishedAt"), "seconds": sec,
                         "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0) or 0),
                         "comments": int(st.get("commentCount", 0) or 0),
                         "description": (sn.get("description") or "")[:400], "tags": (sn.get("tags") or [])[:15],
                         "queries": found[it["id"]]})
    subs = {}
    cl = list(chans)
    for i in range(0, len(cl), 50):
        r = requests.get("https://www.googleapis.com/youtube/v3/channels", headers=h, timeout=30, params={
            "part": "statistics", "id": ",".join(cl[i:i + 50])}).json()
        for it in r.get("items", []):
            subs[it["id"]] = int(it["statistics"].get("subscriberCount", 0) or 0)
    for v in vids:
        v["channel_subs"] = subs.get(v["channel_id"])
    vids.sort(key=lambda v: -v["views"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"at": dt.datetime.utcnow().isoformat(), "days": DAYS, "queries": QUERIES, "videos": vids},
              open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"[벤치] 쇼츠 {len(vids)}개, 채널 {len(subs)}개 저장")


if __name__ == "__main__":
    main()
