# -*- coding: utf-8 -*-
"""이미 올라간 쇼츠 정리 (한 번씩 수동 실행: Actions → yt-fix → Run workflow).

1) 유튜브 토큰 권한(scope)을 확인해 로그에 보여 준다.
2) 링크 댓글이 없는 기존 쇼츠에 '링크 바로가기' 댓글을 단다.
3) 채널 소개글에 블로그 주소가 없으면 맨 앞에 넣는다.
권한이 모자라면 무엇이 필요한지만 알려 주고 끝낸다 (영상은 건드리지 않음).
"""
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_short as m  # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
BLOG_LINE = f"📖 블로그: {m.BLOG_HOME}"


def scopes(tok):
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": tok}, timeout=30)
    return r.json().get("scope", "").split()


def video_desc(tok, vid):
    r = requests.get(f"{API}/videos", params={"part": "snippet", "id": vid},
                     headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    items = r.json().get("items", []) if r.ok else []
    return items[0]["snippet"].get("description", "") if items else ""


def main():
    tok = m.yt_access_token()
    if not tok:
        print("YOUTUBE_REFRESH_TOKEN 없음")
        return 1
    sc = scopes(tok)
    print("[권한]", " ".join(sc) or "(알 수 없음)")
    can_write = any(s.endswith("/youtube") or s.endswith("/youtube.force-ssl") for s in sc)
    if not can_write:
        print("[권한 부족] 댓글·채널 소개 수정에는 youtube.force-ssl 권한이 필요해요. "
              "유튜브 연결 토큰(YOUTUBE_REFRESH_TOKEN)을 이 권한을 넣어 다시 만들어야 해요.")
        return 1
    m.check_channel(tok)

    # 2) 기존 쇼츠에 링크 댓글
    log = json.load(open(m.LOG_FILE, encoding="utf-8"))
    changed = False
    for e in log:
        vid = e.get("video_id")
        if not vid or e.get("comment") == "ok":
            continue
        script = {}
        p = os.path.join(m.DONE, e.get("file", ""))
        if os.path.exists(p):
            script = json.load(open(p, encoding="utf-8"))
        desc = video_desc(tok, vid)
        cp = re.search(r"https://link\.coupang\.com/\S+", desc)
        product = None
        if cp:
            nm = re.search(r"🛒\s*(.+?)\s*(?:👉|\n)", desc)
            product = (cp.group(0), nm.group(1).strip() if nm else "추천 상품", "")
        try:
            cid = m.yt_comment(vid, m.build_comment(script, product))
            e["comment"] = "ok"
            e.pop("comment_error", None)
            print(f"[댓글] {vid} 완료 ({cid})")
        except Exception as ce:  # noqa: BLE001
            e["comment_error"] = str(ce)[:300]
            print(f"[댓글] {vid} 실패: {ce}")
        changed = True
    if changed:
        with open(m.LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=1)

    # 2-1) 다시 만든 영상의 예전 버전은 비공개로 (지우지 않음 — 스튜디오에서 언제든 되돌릴 수 있게)
    for vid in os.environ.get("HIDE_VIDEO_IDS", "").split():
        u = requests.put(f"{API}/videos", params={"part": "status"},
                         headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"},
                         data=json.dumps({"id": vid, "status": {"privacyStatus": "private",
                                                                "selfDeclaredMadeForKids": False}}), timeout=30)
        print(f"[비공개] {vid} " + ("완료" if u.ok else f"실패 {u.status_code}: {u.text[:200]}"))
        for e in log:
            if e.get("video_id") == vid and u.ok:
                e["privacy"] = "private"
                changed = True
    if changed:
        with open(m.LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=1)

    # 3) 채널 소개글에 블로그 주소
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
    r = requests.get(f"{API}/channels", params={"part": "brandingSettings", "mine": "true"}, headers=h, timeout=30)
    items = r.json().get("items", []) if r.ok else []
    if not items:
        print(f"[채널] 정보 읽기 실패: {r.text[:200]}")
        return 0
    ch = items[0]
    bs = ch.get("brandingSettings", {})
    about = bs.get("channel", {}).get("description", "") or ""
    if m.BLOG_HOME in about:
        print("[채널] 소개글에 블로그 주소가 이미 있어요")
        return 0
    bs.setdefault("channel", {})["description"] = (BLOG_LINE + "\n\n" + about).strip()[:1000]
    u = requests.put(f"{API}/channels", params={"part": "brandingSettings"}, headers=h,
                     data=json.dumps({"id": ch["id"], "brandingSettings": bs}), timeout=30)
    print("[채널] 소개글에 블로그 주소 추가 " + ("완료" if u.ok else f"실패 {u.status_code}: {u.text[:200]}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
