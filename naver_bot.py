#!/usr/bin/env python3
"""네이버 블로그 원고용 사진·쿠팡 링크 준비 (GitHub Actions 에서 실행).

naver/jobs/ID.json  : {"images": [{"prompt": "english"}...], "coupang_keywords": [...]}
  → 글 본문은 저장소에 올리지 않는다 (네이버 유사문서 방지). 사진 프롬프트·상품 검색어만.
결과: images/naver/ID-N.jpg, naver/jobs/ID.result.json
  {"images": [jsDelivr 주소...], "products": [{"name","url"}...]}
"""
import glob
import json
import os
import subprocess

import coupang_api
import make_images

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "images", "naver")
REPO = "pinkpoket/pinkpoket-auto"


def main():
    os.makedirs(OUT, exist_ok=True)
    for job in sorted(glob.glob(os.path.join(ROOT, "naver", "jobs", "*.json"))):
        if job.endswith(".result.json") or os.path.exists(job[:-5] + ".result.json"):
            continue
        jid = os.path.basename(job)[:-5]
        obj = json.load(open(job, encoding="utf-8"))
        files = []
        for i, it in enumerate((obj.get("images") or [])[:3], 1):
            path = os.path.join(OUT, f"{jid}-{i}.jpg")
            for attempt in range(2):
                try:
                    make_images.fetch(str(it.get("prompt", "")), path, i + attempt)
                    files.append(path)
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"[네이버 사진] {jid} #{i} 실패: {e}")
        products = []
        try:
            products = coupang_api.pick(obj.get("coupang_keywords") or [], count=2,
                                        sub_id=os.environ.get("COUPANG_SUB_ID", "").strip())
        except Exception as e:  # noqa: BLE001
            print(f"[쿠팡] {e}")
        if files:
            subprocess.run(["git", "add", OUT], check=False)
            subprocess.run(["git", "commit", "-q", "-m", f"네이버 원고 사진 {jid}"], check=False)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        res = {"images": [f"https://cdn.jsdelivr.net/gh/{REPO}@{sha}/images/naver/{os.path.basename(f)}" for f in files],
               "products": products}
        json.dump(res, open(job[:-5] + ".result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"[네이버] {jid}: 사진 {len(files)}장, 상품 {len(products)}개")


if __name__ == "__main__":
    main()
