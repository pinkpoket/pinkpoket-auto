#!/usr/bin/env python3
"""인생ON 채널 성적 모으기 (주간 분석용).

1) 토큰이 인생ON 채널인지 확인
2) 최근 영상 목록 + 공개 숫자 (YouTube Data API)
3) 시청 지속률·평균 시청 시간·구독 증가 (YouTube Analytics API, yt-analytics.readonly 권한 필요)
결과: life/data/analytics.json
"""
import datetime as dt
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "life", "data", "analytics.json")
WANT = os.environ.get("YT_CHANNEL_ID", "").strip()


def token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30).json()
    if "access_token" not in r:
        raise SystemExit(f"[분석] 토큰 오류: {r}")
    return r["access_token"], r.get("scope", "")


def main():
    tok, scope = token()
    h = {"Authorization": f"Bearer {tok}"}
    ch = requests.get("https://www.googleapis.com/youtube/v3/channels",
                      params={"part": "snippet,statistics,contentDetails", "mine": "true"}, headers=h, timeout=30).json()
    item = (ch.get("items") or [{}])[0]
    if WANT and item.get("id") != WANT:
        raise SystemExit(f"[분석] 연결된 채널({item.get('id')})이 인생ON({WANT})이 아니에요")
    print(f"[분석] 채널 확인: {item['snippet']['title']} / 구독자 {item['statistics'].get('subscriberCount')}")
    uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while len(ids) < 400:
        pl = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", headers=h, timeout=30, params={
            "part": "contentDetails", "playlistId": uploads, "maxResults": 50, **({"pageToken": page} if page else {})}).json()
        ids += [x["contentDetails"]["videoId"] for x in pl.get("items", [])]
        page = pl.get("nextPageToken")
        if not page:
            break
    videos = {}
    for i in range(0, len(ids), 50):
        r = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=h, timeout=30, params={
            "part": "snippet,contentDetails,statistics", "id": ",".join(ids[i:i + 50])}).json()
        for it in r.get("items", []):
            st = it.get("statistics", {})
            videos[it["id"]] = {"id": it["id"], "title": it["snippet"]["title"], "published": it["snippet"]["publishedAt"],
                                "duration": it["contentDetails"]["duration"], "views": int(st.get("viewCount", 0)),
                                "likes": int(st.get("likeCount", 0) or 0), "comments": int(st.get("commentCount", 0) or 0)}
    analytics_ok = "yt-analytics" in scope
    if analytics_ok:
        end = dt.date.today()
        start = end - dt.timedelta(days=int(os.environ.get("DAYS", "90")))
        r = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", headers=h, timeout=60, params={
            "ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(),
            "metrics": "views,averageViewDuration,averageViewPercentage,likes,shares,subscribersGained",
            "dimensions": "video", "sort": "-views", "maxResults": 200}).json()
        cols = [c["name"] for c in r.get("columnHeaders", [])]
        for row in r.get("rows", []):
            rec = dict(zip(cols, row))
            v = videos.setdefault(rec["video"], {"id": rec["video"]})
            v.update({"avg_view_sec": rec.get("averageViewDuration"), "avg_view_pct": rec.get("averageViewPercentage"),
                      "shares": rec.get("shares"), "subs_gained": rec.get("subscribersGained"), "views_period": rec.get("views")})
        if "error" in r:
            print(f"[분석] Analytics 오류: {str(r['error'])[:300]}")
    else:
        print("[분석] 토큰에 yt-analytics.readonly 권한이 없어 시청 지속률은 빼고 모았어요")
    out = {"at": dt.datetime.utcnow().isoformat() + "Z", "channel": item["snippet"]["title"],
           "subscribers": item["statistics"].get("subscriberCount"), "analytics": analytics_ok,
           "videos": sorted(videos.values(), key=lambda v: v.get("published", ""), reverse=True)}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[분석] 영상 {len(videos)}개 저장, 시청 지속률 {'있음' if analytics_ok else '없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
