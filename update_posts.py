#!/usr/bin/env python3
"""data/update_queue.txt 에 적힌 posts/ 파일 이름의 글을 다시 만들어 블로거에 덮어쓴다.

한 줄에 하나씩 파일 이름(예: 20261030-01.json). 처리가 끝나면 큐를 비운다.
"""
import json
import os
import sys

import blog_bot as bb

QUEUE = os.path.join(bb.ROOT, "data", "update_queue.txt")


def main():
    if not os.path.exists(QUEUE):
        return 0
    names = [l.strip() for l in open(QUEUE, encoding="utf-8") if l.strip() and not l.startswith("#")]
    if not names:
        return 0
    state = bb.load_state()
    by_file = {p.get("file"): p for p in state["posted"] if p.get("post_id")}
    token = bb.google_access_token()
    blog_id = bb.env("BLOGGER_BLOG_ID")
    failed = 0
    for name in names:
        rec = by_file.get(name)
        if not rec:
            print(f"[수정] {name}: 발행 기록이 없어 건너뜀")
            continue
        try:
            title, labels, content, links = bb.build(name, state)
            url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/{rec['post_id']}"
            body = {"kind": "blogger#post", "id": rec["post_id"], "title": title,
                    "content": content, "labels": labels}
            bb.http_json(url, data=body, headers={"Authorization": f"Bearer {token}"}, method="PUT")
            obj = bb.read_post(name)
            rec["images"] = [u for u, _ in bb.images_for(name, obj, state)]
            rec["products"] = links
            bb.save_state(state)
            print(f"[수정] {title} → {rec.get('url')}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[수정] {name} 실패: {e}")
    with open(QUEUE, "w", encoding="utf-8") as f:
        f.write("# 다시 올릴 글 파일 이름을 한 줄에 하나씩\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
