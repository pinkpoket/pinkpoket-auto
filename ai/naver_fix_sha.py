# -*- coding: utf-8 -*-
"""naver/jobs/*.result.json 의 jsDelivr 주소 커밋 번호를 실제 커밋으로 고친다.

naver_bot.py 는 사진을 커밋한 직후의 HEAD 번호를 result.json 에 적는데,
그 뒤 'git pull --rebase' 로 커밋 번호가 바뀌면 주소가 없는 커밋을 가리킨다
(2026-11-10 n2r 사진이 안 보였던 원인). naver.yml 의 push 가 끝난 뒤 이 스크립트를 돌려,
주소 속 커밋에 그 사진이 없으면 그 사진을 마지막으로 바꾼 실제 커밋 번호로 바꾼다.
고친 파일이 있으면 경로를 출력한다 (커밋·push 는 워크플로가 함).
"""
import glob
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL_RE = re.compile(r"^(https://cdn\.jsdelivr\.net/gh/[^@]+@)([0-9a-f]{7,40})/(.+)$")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def has_file(sha, path):
    return git("cat-file", "-e", f"{sha}:{path}").returncode == 0


def main():
    # 얕은 clone 이면 옛 커밋이 없어 멀쩡한 주소도 틀렸다고 보므로 건너뜀 (naver.yml 은 fetch-depth: 0)
    if git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        print("[주소 확인] 얕은 clone 이라 건너뜀 (git fetch --unshallow 필요)")
        return
    for rp in sorted(glob.glob(str(ROOT / "naver/jobs/*.result.json"))):
        try:
            res = json.loads(Path(rp).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        changed = False
        new = []
        for u in res.get("images") or []:
            m = URL_RE.match(u)
            if m and not has_file(m.group(2), m.group(3)):
                real = git("log", "-1", "--format=%H", "HEAD", "--", m.group(3)).stdout.strip()
                if real:
                    u = f"{m.group(1)}{real}/{m.group(3)}"
                    changed = True
            new.append(u)
        if changed:
            res["images"] = new
            Path(rp).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            print("고침:", Path(rp).name)


if __name__ == "__main__":
    main()
