# -*- coding: utf-8 -*-
"""네이버 원고 사진이 0장일 때(Cloudflare 무료 한도 초과) Pixabay 무료 사진으로 채운다."""
import glob
import json
import os
import re
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
STOP = set("a an the of in on at by with and or for to from no text logo people person realistic photo soft light "
           "lighting bright clean cozy tidy small modern minimal apartment interior centered close up natural "
           "warm sunlight daylight morning style shot view inside".split())
REPO = "pinkpoket/pinkpoket-auto"


def query(prompt):
    words = [w for w in re.findall(r"[a-z]+", prompt.lower()) if w not in STOP and len(w) > 2]
    return words[:4]


def search(words):
    for n in (len(words), 2, 1):
        q = " ".join(words[:n])
        if not q:
            continue
        r = requests.get("https://pixabay.com/api/", timeout=30, params={
            "key": KEY, "q": q, "image_type": "photo", "orientation": "horizontal",
            "safesearch": "true", "per_page": 20, "lang": "en"})
        hits = [h for h in r.json().get("hits", [])
                if not PEOPLE & {t.strip() for t in h.get("tags", "").split(",")}]
        if hits:
            return hits
    return []


PEOPLE = {"woman", "women", "man", "men", "girl", "boy", "model", "portrait", "people", "person", "child",
          "baby", "face", "female", "male", "fashion", "selfie", "couple", "family", "hand", "hands"}


def main():
    if not KEY:
        return
    body = json.loads(Path("/tmp/naver_body.json").read_text(encoding="utf-8"))
    for res_path in [str(ROOT / f"naver/jobs/{body['id']}.result.json")]:
        res = json.loads(Path(res_path).read_text(encoding="utf-8"))
        if res.get("images"):
            continue
        job = json.loads(Path(res_path.replace(".result.json", ".json")).read_text(encoding="utf-8"))
        jid = os.path.basename(res_path)[:-12]
        used, files = set(), []
        for i, it in enumerate(job.get("images", [])[:3], 1):
            for h in search(query(it.get("prompt", ""))):
                if h["id"] in used:
                    continue
                used.add(h["id"])
                out = ROOT / f"images/naver/{jid}-{i}.jpg"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(requests.get(h["largeImageURL"], timeout=60).content)
                files.append(out)
                print(f"[Pixabay] {jid} #{i}: {h['tags']}")
                break
        if not files:
            continue
        subprocess.run(["git", "add", *map(str, files)], cwd=ROOT, check=False)
        subprocess.run(["git", "commit", "-q", "-m", f"네이버 원고 사진 {jid} (Pixabay)"], cwd=ROOT, check=False)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        res["images"] = [f"https://cdn.jsdelivr.net/gh/{REPO}@{sha}/images/naver/{f.name}" for f in files]
        Path(res_path).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
