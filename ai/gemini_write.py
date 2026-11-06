# -*- coding: utf-8 -*-
"""구글 Gemini 무료 API로 대본(JSON)을 써서 대기열(queue)에 넣는다.

Claude 크레딧을 아끼려고 만든 글쓰기 봇 (2026-11-06).
  JOB=life-shorts  → life/shorts/queue/YYYYMMDD-HHMM.json

필요: GEMINI_API_KEY (GitHub Secret)
"""
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
KST = dt.timezone(dt.timedelta(hours=9))
API = "https://generativelanguage.googleapis.com/v1beta"
KEY = os.environ.get("GEMINI_API_KEY", "").strip()

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")


# ---------------------------------------------------------------- 모델 고르기
def list_models():
    r = requests.get(f"{API}/models", params={"key": KEY, "pageSize": 200}, timeout=30)
    r.raise_for_status()
    out = []
    for m in r.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            out.append(m["name"].split("/", 1)[1])
    return out


def ver(name):
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0


def pick_models(pref):
    """pref='flash' → 좋은 Flash 먼저, 막히면 Flash-Lite. pref='lite' → Lite 먼저."""
    names = list_models()
    ok = [n for n in names if n.startswith("gemini-") and "flash" in n
          and not any(b in n for b in ("image", "tts", "audio", "live", "embedding", "thinking-exp"))]
    stable = lambda n: ("preview" not in n and "exp" not in n, ver(n))
    flash = sorted([n for n in ok if "lite" not in n], key=stable, reverse=True)
    lite = sorted([n for n in ok if "lite" in n], key=stable, reverse=True)
    order = (flash[:3] + lite[:3]) if pref == "flash" else (lite[:3] + flash[:3])
    print("쓸 수 있는 모델:", order)
    return order


def generate(models, prompt, temperature=0.9):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last = ""
    for m in models:
        for attempt in range(2):
            try:
                r = requests.post(f"{API}/models/{m}:generateContent", params={"key": KEY},
                                  json=body, timeout=240)
            except requests.RequestException as e:
                last = f"{m}: 응답 없음 ({type(e).__name__})"
                print(last)
                break  # 다음 모델로
            if r.status_code == 200:
                try:
                    txt = "".join(p.get("text", "") for p in
                                  r.json()["candidates"][0]["content"]["parts"])
                    print(f"모델 {m} 사용")
                    return txt
                except Exception as e:  # noqa
                    last = f"{m}: 응답 형식 오류 {e}"
                    break
            last = f"{m}: {r.status_code} {r.text[:120]}"
            print(f"{m}: {r.status_code}")
            if r.status_code in (429, 500, 503) and attempt == 0:
                time.sleep(20)
                continue
            break  # 다음 모델로
    raise RuntimeError("Gemini 호출 실패 — " + last)


def parse_json(txt):
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt).strip()
    return json.loads(txt)


# ---------------------------------------------------------------- 공통
def recent_titles(log_path, n=40):
    try:
        log = json.loads(Path(log_path).read_text(encoding="utf-8"))
    except Exception:
        return []
    seen, out = set(), []
    for e in reversed(log):
        t = e.get("title")
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= n:
            break
    return out


def telegram(msg):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data={"chat_id": chat, "text": msg}, timeout=20)
        except Exception:
            pass


# ---------------------------------------------------------------- 인생ON 쇼츠
def check_life_short(d):
    errs = []
    for k in ("title", "hook", "scenes", "description", "tags", "comment"):
        if k not in d:
            errs.append(f"{k} 칸이 없음")
    if errs:
        return errs
    sc = d["scenes"]
    total = sum(len(s.get("text", "")) for s in sc)
    if not 9 <= len(sc) <= 12:
        errs.append(f"장면이 {len(sc)}개 — 9~11개로")
    if not 330 <= total <= 410:
        errs.append(f"scenes text 합이 {total}자로 너무 {'짧음' if total < 340 else '김'} — "
                    f"장면마다 35자 안팎으로 써서 합계 340~400자로 (첫 장면만 8~15자)")
    if len(d["hook"].replace("\\n", "").replace("\n", "")) > 14:
        errs.append("hook 이 12자를 넘음")
    if not 20 <= len(d["title"]) <= 50:
        errs.append(f"제목이 {len(d['title'])}자 — 30~45자로")
    for s in sc:
        if not s.get("bg"):
            errs.append("bg 가 빈 장면이 있음")
            break
    if EMOJI.search(d["hook"] + "".join(s.get("text", "") for s in sc)):
        errs.append("화면 글자에 이모지가 있음")
    if re.search(r"https?://", d.get("comment", "")):
        errs.append("댓글에 링크가 있음")
    return errs


def life_shorts(models):
    guide = (ROOT / "life/SHORTS_GUIDE.md").read_text(encoding="utf-8")
    titles = recent_titles(ROOT / "life/data/shorts_log.json")
    now = dt.datetime.now(KST)
    weekday = "월화수목금토일"[now.weekday()]
    prompt = f"""너는 유튜브 채널 「인생ON : 마음의 불을 켜다」의 쇼츠 대본 작가다.
아래 [규칙]을 하나도 빠짐없이 지켜서 쇼츠 대본 1편을 JSON 하나로만 답하라. 설명 문장 없이 JSON만.

오늘: {now:%Y-%m-%d} ({weekday}요일), 한국 시간 {now:%H시}
최근에 올린 제목들 (이것과 겹치지 않는 새 주제·새 각도로):
{chr(10).join('- ' + t for t in titles) or '- (없음)'}

추가 규칙 (인터넷 검색을 못 하므로):
- 특정 병원·기관·연구·통계 숫자·사람 이름을 출처로 들지 마라 ("서울대병원에 따르면", "연구 결과 37%" 등 금지).
  널리 알려진 상식 수준의 생활·건강 조언만, 단정적인 의학 효과는 쓰지 말 것.
- 명언은 쓰지 마라.
- JSON 키: title, hook, scenes([{{"text","bg"}}]), description, tags, comment, coupang_keywords([]).
- scenes text 글자 수 합계 340~400자, 장면 9~11개. 첫 장면 8~15자 단정형 훅.

[규칙]
{guide}
"""
    fb = ""
    for i in range(3):
        d = parse_json(generate(models, prompt + fb))
        if isinstance(d, list):
            d = d[0]
        errs = check_life_short(d)
        if not errs:
            break
        print("고칠 점:", errs)
        fb = "\n\n[이전 답의 문제 — 반드시 고쳐서 다시 써라]\n- " + "\n- ".join(errs)
    else:
        raise RuntimeError("규칙에 맞는 대본을 3번 안에 못 썼어요: " + "; ".join(errs))
    d["coupang_keywords"] = []
    d.pop("long_url", None)
    d.pop("end_card", None)
    d["writer"] = "gemini"
    q = ROOT / "life/shorts/queue"
    q.mkdir(parents=True, exist_ok=True)
    path = q / f"{now:%Y%m%d-%H%M}.json"
    path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", path.relative_to(ROOT), "/", d["title"],
          "/", sum(len(s["text"]) for s in d["scenes"]), "자")
    return path


JOBS = {"life-shorts": ("flash", life_shorts)}


def main():
    job = os.environ.get("JOB", "life-shorts")
    if not KEY:
        sys.exit("GEMINI_API_KEY 가 없어요")
    pref, fn = JOBS[job]
    try:
        models = pick_models(os.environ.get("MODEL_PREF", pref))
        if not models:
            raise RuntimeError("쓸 수 있는 Gemini 모델이 없어요")
        fn(models)
    except Exception as e:
        telegram(f"[Gemini 글쓰기 실패] {job}\n{e}")
        raise


if __name__ == "__main__":
    main()
