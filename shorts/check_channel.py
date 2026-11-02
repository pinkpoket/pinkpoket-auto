#!/usr/bin/env python3
"""유튜브 토큰이 맞는 채널에 연결됐는지만 확인한다 (영상은 올리지 않음)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_short as m  # noqa: E402

tok = m.yt_access_token()
if not tok:
    raise SystemExit("[확인] YOUTUBE_REFRESH_TOKEN 비밀값이 비어 있어요")
got = m.check_channel(tok)
print(f"[확인] 토큰 OK — 연결된 채널 {got} = {m.ch.P['name']} 채널이 맞아요 ✅")
