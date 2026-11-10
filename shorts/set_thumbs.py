#!/usr/bin/env python3
"""life/shorts/thumbs/<영상ID>.jpg 를 그 영상의 썸네일로 올리고 지운다. 결과는 life/data/thumb_log.json."""
import glob, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_short as ms  # noqa: E402

LOG = os.path.join(ms.REPO, "life", "data", "thumb_log.json")
log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else []
for img in sorted(glob.glob(os.path.join(ms.REPO, "life", "shorts", "thumbs", "*.jpg"))):
    vid = os.path.splitext(os.path.basename(img))[0]
    tok = ms.yt_access_token()
    with open(img, "rb") as f:
        r = ms.requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
                             headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"}, data=f, timeout=60)
    res = "ok" if r.status_code < 300 else f"{r.status_code}: {r.text[:300]}"
    print(f"[썸네일] {vid}: {res}")
    log.append({"at": time.strftime("%Y-%m-%d %H:%M"), "video_id": vid, "result": res})
    os.remove(img)
json.dump(log[-100:], open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
