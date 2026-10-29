#!/usr/bin/env python3
"""pages/*.json 을 블로거 '페이지'(소개·개인정보처리방침·문의)로 만든다.

이미 만든 페이지는 data/pages.json 에 기록해 두고, 다시 실행하면 내용만 고쳐 올린다.
본문의 {CONTACT_EMAIL} 은 GitHub 변수 CONTACT_EMAIL 값으로 바뀐다.
"""
import glob
import json
import os
import sys

import blog_bot as bb

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "data", "pages.json")


def main():
    blog_id = bb.env("BLOGGER_BLOG_ID")
    email = os.environ.get("CONTACT_EMAIL", "").strip() or "(문의 이메일 준비 중)"
    done = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    token = bb.google_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    for path in sorted(glob.glob(os.path.join(ROOT, "pages", "*.json"))):
        name = os.path.basename(path)
        obj = json.load(open(path, encoding="utf-8"))
        body = {"kind": "blogger#page", "title": obj["title"],
                "content": obj["html"].replace("{CONTACT_EMAIL}", email)}
        if name in done:
            url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/pages/{done[name]['id']}"
            res = bb.http_json(url, data=body, headers=headers, method="PUT")
        else:
            url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/pages?isDraft=false"
            res = bb.http_json(url, data=body, headers=headers, method="POST")
        done[name] = {"id": res.get("id"), "url": res.get("url"), "title": obj["title"]}
        print(f"[페이지] {obj['title']} → {res.get('url')}")
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
