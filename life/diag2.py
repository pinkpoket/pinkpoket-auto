#!/usr/bin/env python3
"""인생ON 채널 종합 분석용 데이터 (2026-11-14). 결과: life/data/diag2.json"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analytics as A  # noqa: E402
from diag import report  # noqa: E402

OUT = os.path.join(A.ROOT, "life", "data", "diag2.json")


def main():
    tok, _ = A.token()
    h = {"Authorization": f"Bearer {tok}"}
    end = dt.date.today()
    R = {}
    for label, days in (("d28", 28), ("d90", 90), ("d365", 365)):
        S = (end - dt.timedelta(days=days)).isoformat()
        E = end.isoformat()
        R[f"type_{label}"] = report(h, metrics="views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,likes,shares,comments",
                                    startDate=S, endDate=E, dimensions="creatorContentType")
        R[f"age_gender_{label}"] = report(h, metrics="viewerPercentage", startDate=S, endDate=E, dimensions="ageGroup,gender", sort="gender,ageGroup")
        for ct in ("SHORTS", "VIDEO_ON_DEMAND"):
            R[f"age_{ct}_{label}"] = report(h, metrics="viewerPercentage", startDate=S, endDate=E, dimensions="ageGroup",
                                            filters=f"creatorContentType=={ct}")
        R[f"sub_{label}"] = report(h, metrics="views,estimatedMinutesWatched,averageViewDuration", startDate=S, endDate=E,
                                   dimensions="subscribedStatus,creatorContentType")
        R[f"device_{label}"] = report(h, metrics="views,estimatedMinutesWatched", startDate=S, endDate=E, dimensions="deviceType")
        R[f"source_{label}"] = report(h, metrics="views,estimatedMinutesWatched", startDate=S, endDate=E,
                                      dimensions="insightTrafficSourceType,creatorContentType")
        R[f"country_{label}"] = report(h, metrics="views,estimatedMinutesWatched", startDate=S, endDate=E, dimensions="country",
                                       sort="-views", maxResults=10)
        R[f"share_{label}"] = report(h, metrics="shares", startDate=S, endDate=E, dimensions="sharingService", sort="-shares", maxResults=10)
    S365 = (end - dt.timedelta(days=365)).isoformat()
    R["videos_365"] = report(h, metrics="views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,shares,comments,subscribersGained",
                             startDate=S365, endDate=end.isoformat(), dimensions="video", sort="-views", maxResults=200)
    R["monthly"] = report(h, metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost", startDate="2025-12-01",
                          endDate=end.isoformat(), dimensions="month", sort="month")
    R["search_terms"] = report(h, metrics="views", startDate=S365, endDate=end.isoformat(), dimensions="insightTrafficSourceDetail",
                               filters="insightTrafficSourceType==YT_SEARCH", sort="-views", maxResults=25)
    # 긴 영상 상위 3편 시청 지속 곡선
    vids = json.load(open(A.OUT, encoding="utf-8"))["videos"]
    longs = [v for v in vids if "M" in v.get("duration", "") and not v["duration"].startswith("PT0M")
             and int(v["duration"].split("PT")[1].split("M")[0].split("H")[-1] or 0) >= 3]
    longs.sort(key=lambda v: -v.get("views", 0))
    R["long_curves"] = {}
    for v in longs[:4]:
        R["long_curves"][v["id"]] = [v["title"], report(h, metrics="audienceWatchRatio,relativeRetentionPerformance", startDate=S365,
                                                        endDate=end.isoformat(), dimensions="elapsedVideoTimeRatio", filters=f"video=={v['id']}")]
    R["titles"] = {v["id"]: [v.get("published"), v.get("title"), v.get("duration"), v.get("views")] for v in vids}
    json.dump(R, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[분석2] 저장", {k: ("err:" + v["error"][:80]) if isinstance(v, dict) and "error" in v else "ok" for k, v in R.items() if k not in ("titles", "long_curves")})


if __name__ == "__main__":
    main()
