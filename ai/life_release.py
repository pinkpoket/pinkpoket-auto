# -*- coding: utf-8 -*-
"""인생ON 보관함(bank)에서 대본을 하나씩 꺼내 대기열(queue)에 넣는다.

Claude 가 일요일에 한 주 치를 몰아서 써 두면 (life/shorts/bank, life/long/bank),
GitHub 이 매일 정해진 시간에 이 스크립트로 하나씩 꺼내 올린다. (2026-11-07, 크레딧 아끼기)
  MODE=short → 일반 쇼츠 1편
  MODE=pair  → 오늘 올라간 긴 영상의 짝 쇼츠 (긴 영상 대본의 "pair_short"), 없으면 일반 쇼츠
  MODE=long  → 긴 영상 1편
보관함이 비면: 쇼츠는 Gemini 가 대신 쓰고, 긴 영상은 텔레그램으로 알린다.
"""
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ai"))
os.environ.setdefault("GEMINI_API_KEY", "")
import gemini_write as gw  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
SB, LB = ROOT / "life/shorts/bank", ROOT / "life/long/bank"
SQ, LQ = ROOT / "life/shorts/queue", ROOT / "life/long/queue"


def bank(d):
    return sorted(glob.glob(str(d / "*.json")))


def out(k, v):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"{k}={v}\n")


def move(src, qdir):
    qdir.mkdir(parents=True, exist_ok=True)
    dst = qdir / f"{NOW:%Y%m%d-%H%M}.json"
    shutil.move(src, dst)
    print("꺼냄:", os.path.basename(src), "→", dst.relative_to(ROOT))
    return dst


def pair_short():
    log = gw.load(ROOT / "life/data/long_log.json", []) or []
    today = [e for e in log if e.get("url") and e.get("privacy") == "public"
             and e.get("at", "")[:10] in (f"{NOW:%Y-%m-%d}", f"{NOW - dt.timedelta(days=1):%Y-%m-%d}")]
    if not today:
        return None
    e = today[-1]
    done = ROOT / "life/long/done" / e["file"]
    d = gw.load(done, {}) or {}
    p = d.get("pair_short")
    if not p or d.get("pair_used"):
        return None
    p["long_url"] = e["url"]
    d["pair_used"] = True
    done.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    SQ.mkdir(parents=True, exist_ok=True)
    dst = SQ / f"{NOW:%Y%m%d-%H%M}.json"
    dst.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    print("짝 쇼츠:", p.get("title"), "←", e["title"])
    return dst


def main():
    mode = os.environ.get("MODE", "short")
    if mode == "long":
        b = bank(LB)
        if not b:
            gw.telegram("[인생ON] 긴 영상 보관함이 비었어요. 오늘 긴 영상은 쉬어요. (일요일 몰아쓰기 확인 필요)")
            return
        move(b[0], LQ)
        out("next", "long-life.yml")
    else:
        if mode == "pair" and pair_short():
            out("next", "shorts-life.yml")
        else:
            b = bank(SB)
            if b:
                move(b[0], SQ)
                out("next", "shorts-life.yml")
            elif os.environ.get("GEMINI_FALLBACK") == "1" and os.environ.get("GEMINI_API_KEY"):
                print("보관함이 비어 Gemini 가 대신 씀")
                gw.life_shorts(gw.pick_models("flash"))
                out("next", "shorts-life.yml")
            else:
                print("쇼츠 보관함이 비어서 이번엔 건너뜀")
                return
    left_s, left_l = len(bank(SB)), len(bank(LB))
    print(f"남은 보관함: 쇼츠 {left_s}편, 긴 영상 {left_l}편")
    if mode == "long" and left_l <= 1:
        gw.telegram(f"[인생ON] 보관함이 거의 비었어요 (쇼츠 {left_s}편, 긴 영상 {left_l}편 남음).")


if __name__ == "__main__":
    main()
