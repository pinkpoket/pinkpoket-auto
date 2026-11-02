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
        "base": "",
        "blog_home": "https://pinkpoket.blogspot.com",
        "yt_link_text": "▶ 유튜브에서 살림 꿀팁 쇼츠 보기 &amp; 구독하기",
        "author_box": ("<strong style=\"color:#333\">✍️ 핑포의 작은집 연구소</strong> · 핑포(핑크포켓, Pink Pocket)가 "
                       "작은 집도 예쁘고 편하게 가꾸는 인테리어·살림 방법을 정리해요. "
                       "공식 자료와 확인된 정보를 바탕으로 AI 도구의 도움을 받아 쓰고 있어요."),
        "default_notice": "제품 가격·구성은 판매처 사정에 따라 바뀔 수 있어요. 구매 전 상세 페이지를 꼭 확인해 주세요 💗",
        "items_title": "🎀 핑포가 골라 본 아이템",
        "image_style": ("bright cozy minimalist Korean apartment interior, soft natural daylight, "
                        "pastel pink and warm white tones, clean, photorealistic, lifestyle magazine photo, "
                        "no people, no text, no watermark"),
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
        "colors": {"accent": (224, 85, 154), "bar": (224, 85, 154), "hook_bg": (255, 228, 92),
                   "hook_text": (70, 30, 45), "hi_text": (255, 228, 92), "hi_stroke": (90, 20, 55),
                   "gradients": [((255, 236, 244), (246, 201, 220)), ((255, 245, 236), (240, 210, 222)),
                                 ((250, 240, 248), (226, 196, 214))]},
    },
    "news": {
        "name": "핑포의 오늘뉴스",
        "base": "news",
        "blog_home": "https://pinkpoket-news.blogspot.com",
        "yt_link_text": "▶ 유튜브에서 오늘 뉴스 1분 요약 쇼츠 보기 &amp; 구독하기",
        "author_box": ("<strong style=\"color:#333\">✍️ 핑포의 오늘뉴스</strong> · 핑포(핑크포켓, Pink Pocket)가 "
                       "매일 꼭 알아야 할 뉴스와 생활 정보를 쉽게 풀어 정리해요. "
                       "여러 언론 보도와 정부·기관 공식 발표를 확인해 AI 도구의 도움을 받아 새로 쓰고 있어요."),
        "default_notice": "뉴스 내용은 이후 보도·발표에 따라 바뀔 수 있어요. 신청 기간·금액처럼 중요한 정보는 공식 누리집에서 꼭 다시 확인해 주세요 📰",
        "items_title": "🛒 오늘 뉴스와 함께 보면 좋은 아이템",
        "image_style": ("clean editorial news illustration photo, soft natural light, calm pastel pink and white tones, "
                        "photorealistic, magazine style, no people, no faces, no text, no letters, no logo, no watermark"),
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
        # 파랑 + 초록: 제목 상자 초록, 강조 자막 파란 상자에 연두 글씨, 진행 막대 초록
        "colors": {"accent": (25, 110, 235), "bar": (40, 200, 120), "hook_bg": (60, 214, 140),
                   "hook_text": (8, 36, 84), "hi_text": (170, 255, 200), "hi_stroke": (8, 30, 80),
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
        # 시니어 시청자용: 말은 천천히(기본 속도), 그림은 4장만 만들어 장면끼리 나눠 씀, 화면 이름은 "인생온"
        "tts_rate": "+0%", "image_steps": 4, "max_images": 4, "tag": "인생온",
        # 따뜻한 주황·갈색 (마음의 불): 제목 상자 주황, 강조 자막 진한 주황 상자에 크림 글씨
        "colors": {"accent": (214, 96, 32), "bar": (240, 150, 40), "hook_bg": (255, 196, 92),
                   "hook_text": (70, 30, 10), "hi_text": (255, 240, 200), "hi_stroke": (70, 30, 10),
                   "gradients": [((255, 240, 220), (240, 200, 160)), ((255, 236, 210), (230, 180, 140)),
                                 ((250, 232, 214), (226, 190, 160))]},
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
