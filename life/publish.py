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
    if u.ok:  # 비공개일 때 못 단 감성 댓글을 공개하면서 단다
        try:
            import json, glob
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log = json.load(open(os.path.join(root, "life", "data", "shorts_log.json"), encoding="utf-8"))
            rec = next((x for x in log if x.get("video_id") == vid), None)
            llog_p = os.path.join(root, "life", "data", "long_log.json")
            llog = json.load(open(llog_p, encoding="utf-8")) if os.path.exists(llog_p) else []
            lrec = next((x for x in llog if x.get("video_id") == vid), None)
            if lrec:  # 긴 영상: 기록을 공개로 바꾸고(쇼츠 설명란 링크용) 대본의 댓글을 단다
                lrec["privacy"] = "public"
                json.dump(llog, open(llog_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                ls = json.load(open(os.path.join(root, "life", "long", "done", lrec["file"]), encoding="utf-8"))
                if lrec.get("comment") != "ok":
                    sys.path.insert(0, os.path.join(root, "shorts"))
                    sys.path.insert(0, os.path.join(root, "life"))
                    os.environ.setdefault("CHANNEL", "life")
                    import make_short as m
                    import make_long as ml
                    m.yt_comment(vid, ml.long_comment(ls))
                    lrec["comment"] = "ok"
                    json.dump(llog, open(llog_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                    print(f"[공개] {vid}: 긴 영상 댓글 완료")
            if rec and rec.get("comment") != "ok":
                os.environ.setdefault("CHANNEL", "life")
                sys.path.insert(0, os.path.join(root, "shorts"))
                import make_short as m
                script = json.load(open(os.path.join(root, "life", "shorts", "done", rec["file"]), encoding="utf-8"))
                m.yt_comment(vid, m.build_comment(script, None))
                print(f"[공개] {vid}: 감성 댓글 완료")
        except Exception as e:  # noqa: BLE001
            print(f"[공개] {vid}: 댓글 실패 {e}")
    failed += 0 if u.ok else 1
sys.exit(1 if failed else 0)
