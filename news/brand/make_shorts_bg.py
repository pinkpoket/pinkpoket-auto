"""핑포의 오늘뉴스 쇼츠 고정 배경(1080x1920) 만들기. 글자·로고 없이 무늬만.

    python3 news/brand/make_shorts_bg.py news/brand [blue|blue_black|green_black]

AI 그림 무료 한도와 상관없이 뉴스 쇼츠가 매일 올라가도록, 모든 장면에 이 그림 한 장을 쓴다.
(2026-11-03 핑포 결정: 뉴스는 사진보다 글 전달이 먼저)
"""
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
THEME = sys.argv[2] if len(sys.argv) > 2 else "blue"
W, H = 1080, 1920
# 테마: (위, 가운데, 아래 그라데이션, 빛1, 빛2, 띠 색, 앞 건물, 뒤 건물)
THEMES = {
    "blue": ((10, 38, 90), (25, 110, 235), (6, 22, 56), (120, 190, 255), (60, 214, 140), (40, 200, 120),
             (8, 26, 64), (20, 60, 130)),
    "blue_black": ((4, 6, 12), (12, 34, 84), (2, 3, 8), (40, 120, 255), (20, 70, 200), (30, 120, 255),
                   (4, 6, 14), (14, 26, 56)),
    "green_black": ((4, 8, 6), (8, 52, 34), (2, 5, 4), (40, 210, 120), (20, 140, 90), (40, 210, 120),
                    (3, 8, 6), (12, 40, 28)),
}
NAVY, BLUE, DEEP, GLOW1, GLOW2, GREEN, FRONT, BACK = THEMES[THEME]
rnd = random.Random(20261103)

# 1) 세로 그라데이션: 위 남색 → 가운데 파랑 → 아래 진한 남색
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img)
for y in range(H):
    t = y / (H - 1)
    if t < 0.45:
        a, b, k = NAVY, BLUE, t / 0.45
    else:
        a, b, k = BLUE, DEEP, (t - 0.45) / 0.55
    k = k * k * (3 - 2 * k)
    d.line([(0, y), (W, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3)))

# 2) 부드러운 빛 번짐 (스튜디오 조명 느낌)
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
g = ImageDraw.Draw(glow)
for cx, cy, r, col in [(220, 420, 520, GLOW1 + (90,)), (900, 1250, 600, GLOW2 + (55,)),
                       (540, 960, 700, GLOW1 + (50,))]:
    g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
glow = glow.filter(ImageFilter.GaussianBlur(160))
img = Image.alpha_composite(img.convert("RGBA"), glow)

# 3) 비스듬한 빛줄기
beams = Image.new("RGBA", (W, H), (0, 0, 0, 0))
bd = ImageDraw.Draw(beams)
for x0, wid, alpha in [(-200, 140, 26), (180, 70, 20), (520, 220, 16), (900, 90, 22)]:
    bd.polygon([(x0, 0), (x0 + wid, 0), (x0 + wid - 700, H), (x0 - 700, H)], fill=(255, 255, 255, alpha))
beams = beams.filter(ImageFilter.GaussianBlur(40))
img = Image.alpha_composite(img, beams)

# 4) 은은한 점 무늬 (세계지도·전광판 느낌), 가장자리일수록 진하게
dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
dd = ImageDraw.Draw(dots)
step = 36
for y in range(step // 2, H, step):
    for x in range(step // 2, W, step):
        edge = max(abs(x - W / 2) / (W / 2), abs(y - H / 2) / (H / 2))
        n = 0.5 + 0.5 * math.sin(x * 0.011 + math.cos(y * 0.007) * 2.3) * math.cos(y * 0.009)
        a = int(10 + 38 * edge * n)
        dd.ellipse([x - 3, y - 3, x + 3, y + 3], fill=tuple(min(255, c + 140) for c in GLOW1) + (a,))
img = Image.alpha_composite(img, dots)

# 5) 아래쪽 도시 실루엣 (건물, 창문 불빛)
city = Image.new("RGBA", (W, H), (0, 0, 0, 0))
cd = ImageDraw.Draw(city)
for layer, (base_y, col, hmin, hmax) in enumerate([(1700, BACK + (150,), 120, 330),
                                                   (1790, FRONT + (235,), 80, 240)]):
    x = -20
    while x < W:
        bw = rnd.randint(60, 150)
        bh = rnd.randint(hmin, hmax)
        cd.rectangle([x, base_y - bh, x + bw, H], fill=col)
        if layer == 1:
            for wy in range(base_y - bh + 20, base_y + 60, 34):
                for wx in range(x + 14, x + bw - 14, 26):
                    if rnd.random() < 0.28:
                        cd.rectangle([wx, wy, wx + 10, wy + 14], fill=(255, 226, 140, 120))
        x += bw + rnd.randint(4, 16)
img = Image.alpha_composite(img, city)

# 6) 위·아래 얇은 초록 띠 (채널 색)
top = ImageDraw.Draw(img)
top.rectangle([0, 0, W, 10], fill=GREEN + (255,))
top.rectangle([0, H - 10, W, H], fill=GREEN + (255,))

name = "shorts-bg.jpg" if THEME == "blue" else f"shorts-bg-{THEME}.jpg"
img.convert("RGB").save(os.path.join(OUT, name), quality=92)
print("saved", os.path.join(OUT, name))
