#!/usr/bin/env python3
"""채널 설정 모음. 한 저장소에서 여러 채널을 돌리기 위한 파일이다.

GitHub Actions 워크플로에서 환경변수 CHANNEL 로 고른다.
  CHANNEL 없음 / "salim" → 핑포의 작은집 연구소 (기존 그대로)
  CHANNEL = "news"       → 핑포의 오늘뉴스 (news/ 폴더)
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

PROFILES = {
    "salim": {
        "name": "핑포의 작은집 연구소",
        "max_images": 3,  # 쇼츠 그림 3장을 장면 2개씩 나눠 쓴다 (AI 무료 한도 아끼기, 2026-11-02 핑포 결정)
        "base": "",
        "blog_home": "https://pinkpoket.blogspot.com",
        "yt_link_text": "▶ 유튜브에서 살림 꿀팁 쇼츠 보기 &amp; 구독하기",
        "author_box": ("<strong style=\"color:#333\">✍️ 핑포의 작은집 연구소</strong> · 핑포(핑크포켓, Pink Pocket)가 "
                       "작은 집도 예쁘고 편하게 가꾸는 인테리어·살림 방법을 정리해요. "
                       "공식 자료와 확인된 정보를 바탕으로 AI 도구의 도움을 받아 쓰고 있어요."),
        "default_notice": "제품 가격·구성은 판매처 사정에 따라 바뀔 수 있어요. 구매 전 상세 페이지를 꼭 확인해 주세요 💗",
        "items_title": "🎀 핑포가 골라 본 아이템",
        "image_style": ("photorealistic lifestyle magazine photo, no people, no text, no watermark"),
        # 글마다 분위기·구도를 바꿔서 메인 사진이 다 비슷해 보이지 않게 (글 파일 이름으로 하나 고름)
        "image_styles": [
            "bright Scandinavian small apartment, white walls and light oak wood, clear natural daylight, wide angle interior",
            "close-up detail shot of the main object, shallow depth of field, soft warm window light",
            "top-down flat lay on a light wooden floor, neatly arranged, soft daylight, clean composition",
            "modern Korean apartment, beige and sage green tones, morning sunlight, eye-level view",
            "cozy winter evening mood, warm lamp light, soft shadows, calm atmosphere",
            "minimal white studio-style scene, single object centered, soft even light, lots of empty space",
        ],
        "shorts_style": ("bright cozy minimalist Korean apartment interior, soft natural daylight, pastel pink and "
                         "warm white tones, photorealistic lifestyle photo, subject centered, vertical composition, "
                         "no people, no text, no watermark"),
        "shorts_default_bg": "cozy small apartment living room",
        "shorts_signature": "🏠 핑포의 작은집 연구소 · 핑포(핑크포켓, Pink Pocket)",
        "shorts_outro": "자세한 건 블로그에! 구독하고 꿀팁 받아 가세요!",
        "shorts_outro_bg": "cozy pink bedroom corner with soft lamp light",
        "comment_fallback": "오늘은 '{hook}' 이야기였어요 🏠\n작은 집도 조금만 손보면 훨씬 포근해지더라고요 💛",
        "yt_category": "26",
        "voice_gain": 1.8, "bgm_volume": 0.07,
        # 목소리 속도: 기본 +35% → +45% (2026-11-03 핑포 요청 '더 빠르게')
        "tts_rate": "+45%",
        "colors": {"accent": (224, 85, 154), "bar": (224, 85, 154), "hook_bg": (255, 228, 92),
                   "hook_text": (70, 30, 45), "hi_text": (255, 228, 92), "hi_stroke": (90, 20, 55),
                   "gradients": [((255, 236, 244), (246, 201, 220)), ((255, 245, 236), (240, 210, 222)),
                                 ((250, 240, 248), (226, 196, 214))]},
    },
    "news": {
        "name": "핑포의 오늘뉴스",
        "max_images": 3,  # 쇼츠 그림 3장을 장면 2개씩 나눠 쓴다 (AI 무료 한도 아끼기, 2026-11-02 핑포 결정)
        "base": "news",
        # 뉴스 쇼츠는 AI 그림 대신 고정 배경 한 장 (글 전달이 먼저, 무료 한도 걱정 없이 매일 업로드, 2026-11-03 핑포 결정)
        "fixed_bg": "news/brand/shorts-bg-blue_black.jpg",
        "blog_home": "https://pinkpoket-news.blogspot.com",
        "yt_link_text": "▶ 유튜브에서 오늘 뉴스 1분 요약 쇼츠 보기 &amp; 구독하기",
        "author_box": ("<strong style=\"color:#333\">✍️ 핑포의 오늘뉴스</strong> · 핑포(핑크포켓, Pink Pocket)가 "
                       "매일 꼭 알아야 할 뉴스와 생활 정보를 쉽게 풀어 정리해요. "
                       "여러 언론 보도와 정부·기관 공식 발표를 확인해 AI 도구의 도움을 받아 새로 쓰고 있어요."),
        "default_notice": "뉴스 내용은 이후 보도·발표에 따라 바뀔 수 있어요. 신청 기간·금액처럼 중요한 정보는 공식 누리집에서 꼭 다시 확인해 주세요 📰",
        "items_title": "🛒 오늘 뉴스와 함께 보면 좋은 아이템",
        "image_style": ("photorealistic editorial photo, no people, no faces, no text, no letters, no logo, no watermark"),
        "image_styles": [
            "clean editorial photo, soft natural light, calm blue and white tones, magazine style",
            "wide shot, clear daylight, documentary style, natural colors",
            "close-up detail, shallow depth of field, soft warm light",
            "top-down flat lay, neutral background, even light",
            "dusk city or nature mood, soft gradient sky, calm atmosphere",
        ],
        "shorts_style": ("clean editorial photo, soft natural light, calm pastel pink and white tones, photorealistic, "
                         "subject centered, vertical composition, no people, no faces, no text, no letters, no logo, no watermark"),
        "shorts_default_bg": "morning newspaper and coffee cup on a bright table",
        "shorts_signature": "📰 핑포의 오늘뉴스 · 핑포(핑크포켓, Pink Pocket)",
        "shorts_outro": "내일도 오늘뉴스로 만나요! 구독하고 매일 받아 보세요!",
        "shorts_outro_bg": "sunrise over a quiet city skyline, soft pink sky",
        "comment_fallback": "오늘은 '{hook}' 소식이었어요 📰\n바쁜 하루, 핑포가 대신 챙겨 드릴게요 💛",
        "yt_category": "25",
        # 목소리는 크게(+ 찢어지지 않게 리미터), 배경음악은 작게
        "voice_gain": 1.8, "bgm_volume": 0.07,
        # 파랑 + 검정 (2026-11-03 핑포 결정): 검정 배경, 제목 상자 파랑에 흰 글씨, 강조 자막 파란 상자, 진행 막대 파랑
        "colors": {"accent": (30, 120, 255), "bar": (30, 120, 255), "hook_bg": (30, 120, 255),
                   "hook_text": (255, 255, 255), "hi_text": (255, 255, 255), "hi_stroke": (0, 20, 70),
                   "gradients": [((232, 244, 255), (196, 222, 250)), ((232, 252, 242), (190, 236, 214)),
                                 ((236, 248, 255), (200, 236, 228))]},
    },
    "life": {
        "name": "인생ON : 마음의 불을 켜다",
        "base": "life",
        "blog_home": "",
        "yt_link_text": "",
        "author_box": "",
        "default_notice": "",
        "items_title": "🛒 함께 보면 좋은 아이템",
        "image_style": "",
        "shorts_style": ("warm cinematic photo, soft golden hour light, calm hopeful mood, nature scenery or cozy everyday "
                         "objects, subject centered, vertical composition, no people, no faces, no text, no letters, no logo, no watermark"),
        "shorts_default_bg": "warm candle light by a window at dusk",
        "shorts_signature": "🔥 인생ON : 마음의 불을 켜다",
        "shorts_outro": "오늘 이야기가 도움 되셨다면 구독으로 함께해 주세요.",
        "shorts_outro_bg": "sunrise over calm mountains, warm golden light",
        "comment_fallback": "오늘 '{hook}' 이야기, 마음에 닿으셨나요? 🔥\n소중한 분께 카톡으로 나눠 주시면 큰 힘이 돼요 💛",
        "yt_category": "22",
        "voice_gain": 1.8, "bgm_volume": 0.07,
        # 시니어 시청자용: 쇼츠 목소리 D(여성 선희, 낮게, 기본 속도), 긴 영상은 남성 인준(낮게, 기본 속도), 그림은 장면마다 새로(2026-11-10), 화면 이름은 "인생온"
        "voice": "ko-KR-SunHiNeural", "long_voice": "ko-KR-InJoonNeural", "tts_pitch": "-6Hz", "tts_rate": "+0%",
        # 쇼츠 남성 목소리(인준)가 느려서 빠르게 (2026-11-05 핑크포켓님 요청). 대본의 "rate" 가 있으면 그게 먼저.
        "voice_rates": {"ko-KR-InJoonNeural": "+15%"},
        "image_steps": 4, "max_images": 12, "tag": "인생온", "bg_cache": 80, "image_source": "stock", "link_long": True,
        # 2026-11-10 벤치마킹 반영(핑포 결정): 그림을 장면마다 새로(4장 → 장면 수만큼, 무료 사진이라 한도 걱정 없음),
        # 첫 장면은 위 노란 상자·자막 대신 화면 가운데 큰 제목 카드
        "title_card": True,
        # 인생ON 사연(숏드라마) 그림 스타일 — 수채화 그림책 느낌의 어르신 인물 (실사 아님), 2026-11-10 시작
        "sayeon_style": ("soft watercolor and ink illustration, warm Korean picture-book style, gentle muted colors, "
                         "elderly Korean family members, expressive but kind faces, single clear moment, characters centered, "
                         "medium close-up, vertical 9:16 composition, plenty of space around faces, "
                         "no text, no letters, no speech bubbles, no logo, no watermark"),
        # 시니어용 큰 자막 (기본 72 → 92), 4줄까지
        "cap_size": 92, "cap_lh": 124, "cap_lines": 4,
        # 채널 로고(노란 원 + 검정 글씨)와 통일: 제목 상자 노랑+검정 글씨(2026-11 밝게 바꿈, 위 그늘도 옅게), 강조 자막은 검정 상자에 노란 글씨, 진행 막대 노랑
        "colors": {"accent": (20, 20, 20), "bar": (255, 230, 0), "hook_bg": (255, 222, 0),
                   "hook_text": (25, 25, 25), "top_shade": 40, "hi_text": (255, 236, 0), "hi_stroke": (0, 0, 0),
                   "gradients": [((255, 250, 220), (245, 230, 160)), ((252, 246, 214), (236, 222, 170)),
                                 ((250, 244, 220), (230, 215, 170))]},
    },
}

CHANNEL = os.environ.get("CHANNEL", "").strip() or "salim"
if CHANNEL not in PROFILES:
    raise SystemExit(f"[설정 오류] 모르는 채널 이름: {CHANNEL}")
P = PROFILES[CHANNEL]


def path(*parts):
    """채널 폴더 기준 경로. salim 은 저장소 맨 위, news 는 news/ 아래."""
    return os.path.join(ROOT, P["base"], *parts) if P["base"] else os.path.join(ROOT, *parts)


def logo():
    own = path("brand", "icon.png")
    return own if os.path.exists(own) else os.path.join(ROOT, "brand", "icon.png")
