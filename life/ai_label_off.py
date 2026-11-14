#!/usr/bin/env python3
"""인생ON: 2026-11-08 부터 모든 영상에 붙은 AI(합성) 표시를 끈다 (2026-11-14 핑포 결정).
풍경 사진 + AI 목소리는 표시 의무가 없다. 사람 그림이 나오는 사연 쇼츠(pFns1NiU6sc)는 그대로 둔다."""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analytics as A  # noqa: E402

KEEP = {"pFns1NiU6sc"}
tok, _ = A.token()
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
vids = [v for v in json.load(open(A.OUT, encoding="utf-8"))["videos"] if v.get("published", "") >= "2026-11-08" and v["id"] not in KEEP]
done = 0
for v in vids:
    r = requests.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "status", "id": v["id"]}, headers=h, timeout=30).json()
    it = (r.get("items") or [{}])[0]
    st = it.get("status") or {}
    if not st:
        print(f"[AI표시] {v['id']} 상태 못 읽음: {str(r)[:150]}")
        continue
    if st.get("containsSyntheticMedia") is False:
        continue
    body = {"id": v["id"], "status": {"privacyStatus": st.get("privacyStatus", "public"), "selfDeclaredMadeForKids": False,
                                      "containsSyntheticMedia": False, "embeddable": st.get("embeddable", True),
                                      "publicStatsViewable": st.get("publicStatsViewable", True), "license": st.get("license", "youtube")}}
    u = requests.put("https://www.googleapis.com/youtube/v3/videos", params={"part": "status"}, headers=h, data=json.dumps(body), timeout=30)
    print(f"[AI표시 끔] {v['id']} {v['title'][:30]} " + ("완료" if u.ok else f"실패 {u.status_code} {u.text[:200]}"))
    done += u.ok
print(f"[AI표시] {done}/{len(vids)}편 끔")
