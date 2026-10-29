#!/usr/bin/env python3
"""아직 발행 안 된 글의 대표 이미지를 무료 AI 이미지(pollinations)로 만들어 images/ 에 저장한다.

글 JSON 의 "images": [{"prompt": "english prompt", "alt": "..."}] (최대 2개)를 읽는다.
만든 파일은 워크플로가 커밋하고, blog_bot.py 가 jsDelivr 주소로 글에 넣는다.
실패해도 글 발행은 막지 않는다(이미지 없이 올라간다).
"""
import os
import sys
import time
import urllib.parse
import urllib.request

import blog_bot as bb

STYLE = ("bright cozy minimalist Korean apartment interior, soft natural daylight, "
         "pastel pink and warm white tones, clean, photorealistic, lifestyle magazine photo, "
         "no people, no text, no watermark")


def fetch(prompt, path, seed):
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(f"{prompt}, {STYLE}")
           + f"?width=1200&height=675&nologo=true&seed={seed}")
    req = urllib.request.Request(url, headers={"User-Agent": bb.USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    if "image" not in ctype or len(data) < 20000:
        raise RuntimeError(f"이미지가 아님({ctype}, {len(data)} bytes)")
    with open(path, "wb") as f:
        f.write(data)


def main():
    os.makedirs(bb.IMAGES_DIR, exist_ok=True)
    state = bb.load_state()
    made = 0
    for name in bb.pending_posts(state):
        try:
            obj = bb.read_post(name)
        except Exception:  # noqa: BLE001
            continue
        for idx, item in enumerate((obj.get("images") or [])[:2]):
            prompt = str(item.get("prompt", "")).strip()
            path = os.path.join(bb.IMAGES_DIR, bb.image_file(name, idx))
            if not prompt or os.path.exists(path):
                continue
            seed = int(bb.hashlib.md5(f"{name}{idx}".encode()).hexdigest()[:6], 16)
            for attempt in range(3):
                try:
                    fetch(prompt, path, seed + attempt)
                    made += 1
                    print(f"[이미지] {os.path.basename(path)} 저장")
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"[이미지] {name} #{idx + 1} 실패({attempt + 1}/3): {e}")
                    time.sleep(10)
    print(f"[이미지] 새로 만든 이미지 {made}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
