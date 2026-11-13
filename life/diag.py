#!/usr/bin/env python3
"""인생ON 조회수 급감 원인 진단 (2026-11-13). 결과: life/data/diag.json
- 날짜별 조회수(쇼츠/긴 영상), 시청 경로별(쇼츠 피드 등), 평균 시청률
- 최근 쇼츠별 조회수·참여 조회수(engagedViews)·시청률·좋아요·공유·구독
"""
import datetime as dt
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analytics as A  # noqa: E402

OUT = os.path.join(A.ROOT, "life", "data", "diag.json")


def report(h, **p):
    base = {"ids": "channel==MINE"}
    r = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", headers=h, timeout=60, params={**base, **p}).json()
    if "error" in r:
        return {"error": str(r["error"])[:400], "params": p}
    cols = [c["name"] for c in r.get("columnHeaders", [])]
    return {"cols": cols, "rows": r.get("rows", [])}


def tryreport(h, metric_sets, **p):
    for m in metric_sets:
        res = report(h, metrics=m, **p)
        if "error" not in res:
            return res
        print(f"[진단] {m} 실패: {res['error'][:150]}")
    return res


def main():
    tok, scope = A.token()
    h = {"Authorization": f"Bearer {tok}"}
    end = dt.date.today()
    start = end - dt.timedelta(days=45)
    S, E = start.isoformat(), end.isoformat()
    out = {"at": dt.datetime.utcnow().isoformat() + "Z", "scope": scope}
    out["daily"] = tryreport(h, ["views,engagedViews,averageViewPercentage,likes,subscribersGained",
                                 "views,averageViewPercentage,likes,subscribersGained"],
                             startDate=S, endDate=E, dimensions="day", sort="day")
    out["daily_type"] = tryreport(h, ["views,engagedViews", "views"], startDate=S, endDate=E,
                                  dimensions="day,creatorContentType", sort="day")
    out["daily_source"] = tryreport(h, ["views,engagedViews", "views"], startDate=S, endDate=E,
                                    dimensions="day,insightTrafficSourceType", sort="day")
    # 최근 쇼츠별
    since = (end - dt.timedelta(days=21)).isoformat()
    vids = [v for v in json.load(open(A.OUT, encoding="utf-8"))["videos"] if v.get("published", "") >= since]
    ids = ",".join(v["id"] for v in vids[:200])
    out["videos"] = tryreport(h, ["views,engagedViews,averageViewPercentage,averageViewDuration,likes,shares,subscribersGained",
                                  "views,averageViewPercentage,averageViewDuration,likes,shares,subscribersGained"],
                              startDate=since, endDate=E, dimensions="video", filters=f"video=={ids}", sort="-views",
                              maxResults=200)
    out["titles"] = {v["id"]: [v.get("published"), v.get("title"), v.get("duration")] for v in vids}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[진단] 저장:", {k: (len(v.get("rows", [])) if isinstance(v, dict) and "rows" in v else v if k == "at" else "err")
                          for k, v in out.items() if k not in ("titles", "scope")})


if __name__ == "__main__":
    main()
