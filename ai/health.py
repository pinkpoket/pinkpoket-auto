# -*- coding: utf-8 -*-
"""매일 밤 자동 점검 (Claude 없이). 문제가 있을 때만 텔레그램으로 알린다."""
import datetime as dt
import glob
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ai"))
os.environ.setdefault("GEMINI_API_KEY", "-")
import gemini_write as gw  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
TODAY = f"{NOW:%Y-%m-%d}"
REPO = os.environ.get("GITHUB_REPOSITORY", "pinkpoket/pinkpoket-auto")
H = {"Authorization": f"Bearer {os.environ.get('GH_TOKEN', '')}", "Accept": "application/vnd.github+json"}
NAMES = {"blog.yml": "살림 블로그", "blog-news.yml": "오늘뉴스 블로그", "shorts.yml": "살림 쇼츠",
         "shorts-news.yml": "오늘뉴스 쇼츠", "shorts-life.yml": "인생ON 쇼츠", "long-life.yml": "인생ON 긴 영상",
         "ai-write.yml": "Gemini 글쓰기", "life-release.yml": "인생ON 보관함", "naver.yml": "네이버 사진"}


def failed_runs():
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs", headers=H, timeout=30,
                     params={"created": f">={since}", "per_page": 100, "status": "failure"})
    out = {}
    for run in r.json().get("workflow_runs", []):
        name = NAMES.get(os.path.basename(run.get("path", "")), run.get("name"))
        out[name] = out.get(name, 0) + 1
    return out


def count_posted(path):
    d = gw.load(ROOT / path, {}) or {}
    return [p for p in d.get("posted", []) if str(p.get("at", "")).startswith(TODAY)]


def main():
    issues = []
    for name, n in failed_runs().items():
        issues.append(f"❌ {name} 실패 {n}번")
    for path, label, want in (("data/posted.json", "살림 블로그", 3), ("news/data/posted.json", "오늘뉴스 블로그", 3)):
        posts = count_posted(path)
        if len(posts) < want:
            issues.append(f"📝 {label} 오늘 {len(posts)}편 (목표 {want}편)")
        no_img = [p["title"] for p in posts if not p.get("images")]
        if no_img:
            issues.append(f"🖼 {label} 사진 0장 글: {no_img[0][:30]}")
    for path, label in (("data/shorts_log.json", "살림"), ("news/data/shorts_log.json", "오늘뉴스"),
                        ("life/data/shorts_log.json", "인생ON")):
        errs = [s for s in (gw.load(ROOT / path, []) or [])
                if str(s.get("at", "")).startswith(TODAY) and s.get("error")]
        if errs:
            issues.append(f"🎬 {label} 쇼츠 오류: {str(errs[-1]['error'])[:60]}")
    sb = len(glob.glob(str(ROOT / "life/shorts/bank/*.json")))
    lb = len(glob.glob(str(ROOT / "life/long/bank/*.json")))
    if lb <= 1 or sb <= 3:
        issues.append(f"📦 인생ON 보관함 부족: 쇼츠 {sb}편, 긴 영상 {lb}편")
    print("\n".join(issues) or "문제 없음")
    if issues:
        gw.telegram("🔎 오늘 밤 자동 점검\n" + "\n".join(issues[:8]))


if __name__ == "__main__":
    main()
