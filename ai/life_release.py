# -*- coding: utf-8 -*-
"""인생ON 보관함(bank)에서 대본을 하나씩 꺼내 대기열(queue)에 넣는다.

Claude 가 일요일에 한 주 치를 몰아서 써 두면 (life/shorts/bank, life/long/bank),
GitHub 이 매일 정해진 시간에 이 스크립트로 하나씩 꺼내 올린다. (2026-11-07, 크레딧 아끼기)
  MODE=short → 일반 쇼츠 1편
  MODE=pair  → 오늘 올라간 긴 영상의 짝 쇼츠 (긴 영상 대본의 "pair_short"), 없으면 일반 쇼츠
  MODE=long  → 긴 영상 1편
  MODE=sayeon → 인생ON 사연(숏드라마) 1편 (보관함이 비면 쉼)
보관함이 비면: 쇼츠는 Gemini 가 대신 쓰고, 긴 영상은 텔레그램으로 알린다.
"""
import datetime as dt
import glob
import json
import os
import re
import time
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
YB = ROOT / "life/shorts/sayeon"  # 인생ON 사연(숏드라마) 보관함, 밤 22:21 (2026-11-10 시작)
SQ, LQ = ROOT / "life/shorts/queue", ROOT / "life/long/queue"


def bank(d):
    return sorted(glob.glob(str(d / "*.json")))


# 시간대 규칙 (2026-11-12 핑포 결정): 아침 주제가 밤에 올라가지 않게.
# 제목·썸네일 글·도입부·첫 장면에 아침 말이 있으면 아침(12시 전)에만,
# 저녁·잠 말이 있으면 저녁(17시 이후)에만 꺼낸다. 맞는 게 없으면 이번 회차는 쉬고 다음 맞는 시간에 올린다.
MORNING_W = ("아침", "새벽", "기상", "일어나자마자", "눈 뜨자마자", "눈뜨자마자", "모닝")
EVENING_W = ("저녁", "잠들기", "잠자리", "자기 전", "밤에", "밤마다", "수면", "불면")


def topic_time(f):
    d = gw.load(Path(f), {}) or {}
    parts = [d.get("title", ""), d.get("thumbnail_text", ""), d.get("hook", "")]
    parts += list(d.get("intro") or [])
    sc = d.get("scenes") or []
    if sc:
        parts.append(sc[0].get("text", ""))
    t = " ".join(str(x) for x in parts)
    if any(w in t for w in MORNING_W):
        return "morning"
    if any(w in t for w in EVENING_W):
        return "evening"
    return ""


def slot():
    return "morning" if NOW.hour < 12 else ("evening" if NOW.hour >= 17 else "day")


def pick(files):
    """지금 시간대에 맞는 첫 대본. 아침 주제는 아침에만, 저녁 주제는 저녁에만."""
    now = slot()
    for f in files:
        tt = topic_time(f)
        if not tt or tt == now:
            return f
        print(f"시간대 안 맞아 미룸 ({tt} 주제, 지금 {now}):", os.path.basename(f))
    return None


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


def recent_short(minutes=75):
    """최근에 (옛 Claude 매일 쇼츠 작업이) 이미 쇼츠를 올렸으면 True — 두 번 올라가지 않게."""
    log = gw.load(ROOT / "life/data/shorts_log.json", []) or []
    lim = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")
    if any(str(e.get("at", "")) >= lim for e in log[-5:]):
        return True
    return bool(glob.glob(str(SQ / "*.json")))


def stuck_queue(hours=2):
    """큐에 오래(2시간 넘게) 남은 대본 — 제작이 실패해 걸린 것 (2026-11-19 도구 설치 시간 초과로 하루가 막힌 일).
    파일 이름의 YYYYMMDD-HHMM(한국 시간)으로 판단한다."""
    now_kst = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)
    out = []
    for f in glob.glob(str(SQ / "*.json")):
        m = re.match(r"(\d{8})-(\d{4})", os.path.basename(f))
        if not m:
            continue
        t = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").replace(tzinfo=dt.timezone.utc)
        if (now_kst.replace(tzinfo=dt.timezone.utc) - t).total_seconds() > hours * 3600:
            out.append(f)
    return out


# 올리는 시간 창 (2026-11-26 핑포 결정: 저녁 쇼츠가 새벽 4시·낮 1시에 올라간 일 — GitHub 예약이 최대 10시간 밀림).
# 예약을 창마다 30분 간격으로 여러 번 걸어 두고, 창 안에서 처음 도착한 실행만 올린다.
# 창 밖에 늦게 도착한 실행은 올리지 않는다 (새벽·한낮 업로드 막기).
WINDOWS = {"short": [("morning", 7, 11), ("evening", 18, 22)], "pair": [("morning", 7, 11), ("evening", 18, 22)],
           "long": [("long", 9, 13)]}


def window(mode):
    for name, lo, hi in WINDOWS.get(mode, []):
        if lo <= NOW.hour <= hi:
            return name, lo, hi
    return None


def done_in_window(mode, lo, hi):
    """오늘 이 창(한국 lo시~hi시 59분)에 이미 올렸거나 만드는 중이면 True."""
    logf = "life/data/long_log.json" if mode == "long" else "life/data/shorts_log.json"
    log = gw.load(ROOT / logf, []) or []
    for e in log[-6:]:
        try:  # 기록의 at 은 UTC "YYYY-MM-DD HH:MM"
            k = dt.datetime.strptime(str(e.get("at", ""))[:16], "%Y-%m-%d %H:%M") + dt.timedelta(hours=9)
        except ValueError:
            continue
        if k.date() == NOW.date() and lo <= k.hour <= hi:
            return True
    q = LQ if mode == "long" else SQ
    for f in glob.glob(str(q / "*.json")):
        m = re.match(r"(\d{8})-(\d{2})", os.path.basename(f))
        if m and m.group(1) == f"{NOW:%Y%m%d}" and lo <= int(m.group(2)) <= hi:
            return True
    return False


def main():
    mode = os.environ.get("MODE") or "short"
    if mode in WINDOWS and os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        w = window(mode)
        if not w:
            print(f"예약이 늦게 도착함 (지금 한국 {NOW:%H:%M}) — 올리는 시간 창 밖이라 이번엔 건너뜀")
            return
        if done_in_window(mode, w[1], w[2]):
            print(f"오늘 {w[0]} 칸은 이미 올렸거나 만드는 중 — 건너뜀")
            return
    # ⏸ 쉬는 기간 (2026-11-13 핑포 결정: 쇼츠 조회수가 10회 안팎으로 막혀 사흘 쉼). life/PAUSE 첫 줄 날짜(한국) 전까지 아무것도 안 올림
    pf = ROOT / "life/PAUSE"
    if pf.exists():
        until = pf.read_text(encoding="utf-8").split()[0]
        today = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 9 * 3600))
        if today < until:
            print(f"⏸ 쉬는 중 ({until} 부터 다시 올림) — 이번엔 건너뜀")
            return
    if mode == "sayeon":
        if recent_short():
            print("방금 다른 쇼츠가 올라가서 이번엔 건너뜀")
            return
        b = bank(YB)
        if not b:
            print("사연 보관함이 비어서 이번엔 쉼")
            return
        move(b[0], SQ)
        out("next", "shorts-life.yml")
        print(f"남은 사연: {len(bank(YB))}편")
        if len(bank(YB)) <= 1:
            gw.telegram(f"[인생ON] 사연 쇼츠 보관함이 거의 비었어요 ({len(bank(YB))}편 남음).")
        return
    if mode in ("short", "pair") and stuck_queue():
        # 지난번 제작이 실패해 큐에 걸린 대본이 있으면, 새로 꺼내지 않고 그걸 다시 만든다 (이번 칸을 대신함)
        print("큐에 걸린 대본을 다시 만듭니다:", [os.path.basename(f) for f in stuck_queue()])
        out("next", "shorts-life.yml")
        return
    if mode in ("short", "pair") and recent_short():
        print("방금 다른 쇼츠가 올라가서 이번엔 건너뜀")
        return
    if mode == "long":
        b = bank(LB)
        if not b:
            gw.telegram("[인생ON] 긴 영상 보관함이 비었어요. 오늘 긴 영상은 쉬어요. (일요일 몰아쓰기 확인 필요)")
            return
        f = pick(b)
        if not f:
            print("지금 시간대에 맞는 긴 영상이 없어 이번엔 쉼")
            gw.telegram("[인생ON] 보관함 긴 영상이 모두 다른 시간대 주제라 이번 회차는 쉬어요. (아침 주제는 아침에, 저녁 주제는 저녁에 올라가요)")
            return
        move(f, LQ)
        out("next", "long-life.yml")
    else:
        if mode == "pair" and pair_short():
            out("next", "shorts-life.yml")
        else:
            b = bank(SB)
            f = pick(b) if b else None
            if b and not f:
                print("지금 시간대에 맞는 쇼츠가 없어 이번엔 쉼")
                return
            if f:
                move(f, SQ)
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
