# -*- coding: utf-8 -*-
"""이미 올라간 쇼츠 설명란에서 쿠팡 대가성 문구·상품 링크 줄을 지운다 (수동 실행: Actions → shorts-strip-coupang).

CHANNEL 환경변수로 채널을 고르고, 그 채널 shorts_log.json 에 있는 영상만 손댄다.
지우는 줄: '쿠팡 파트너스' 대가성 문구, link.coupang.com 링크가 든 줄(🛒 상품 줄).
다른 줄(블로그 링크·요약·서명)은 그대로 둔다. DRY_RUN=1 이면 바꿀 내용만 보여 준다.
"""
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import channel as ch  # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
DRY = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")


def is_coupang(line):
    s = line.strip()
    return ("쿠팡 파트너스" in s and "수수료" in s) or "link.coupang.com" in s or "coupang.com/" in s


def clean(desc):
    lines = [l for l in desc.split("\n") if not is_coupang(l)]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out


def main():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30).json()
    tok = r.get("access_token")
    if not tok:
        print("[오류] 유튜브 토큰을 못 받았어요:", str(r)[:200])
        return 1
    h = {"Authorization": f"Bearer {tok}"}
    want = os.environ.get("YT_CHANNEL_ID", "").strip()
    log = json.load(open(ch.path("data", "shorts_log.json"), encoding="utf-8"))
    ids = list(dict.fromkeys(e["video_id"] for e in log if e.get("video_id")))
    print(f"[{ch.CHANNEL}] 쇼츠 {len(ids)}개 확인")
    done = skip = fail = 0
    for i in range(0, len(ids), 50):
        res = requests.get(f"{API}/videos", headers=h, timeout=30,
                           params={"part": "snippet", "id": ",".join(ids[i:i + 50])})
        if not res.ok:
            print("[오류] 영상 정보 읽기 실패:", res.text[:300])
            return 1
        for it in res.json().get("items", []):
            vid, sn = it["id"], it["snippet"]
            if want and sn.get("channelId") != want:
                print(f"{vid}: 다른 채널 영상이라 건너뜀"); skip += 1; continue
            old = sn.get("description", "")
            new = clean(old)
            if new == old.strip():
                skip += 1; continue
            gone = [l for l in old.split("\n") if is_coupang(l)]
            print(f"{vid} ({sn.get('title', '')[:30]}): 지울 줄 {len(gone)}개 → {gone}")
            if DRY:
                done += 1; continue
            body = {"id": vid, "snippet": {k: sn[k] for k in ("title", "categoryId", "tags", "defaultLanguage",
                                                             "defaultAudioLanguage") if k in sn} | {"description": new}}
            u = requests.put(f"{API}/videos?part=snippet", headers=h, json=body, timeout=30)
            if u.ok:
                done += 1
            else:
                fail += 1
                print(f"  └ 실패: {u.text[:300]}")
    print(f"[결과] {'(시험) ' if DRY else ''}정리 {done}개 · 이미 깨끗 {skip}개 · 실패 {fail}개")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
