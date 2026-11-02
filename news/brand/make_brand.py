import os, sys
from PIL import Image, ImageDraw, ImageFont
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
BLACK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
KR = 1  # KR face index in ttc
def F(path, size):
    for i in range(10):
        f = ImageFont.truetype(path, size, index=i)
        if "KR" in f.getname()[0]: return f
    return ImageFont.truetype(path, size)
BLUE = (25, 110, 235); NAVY = (10, 38, 90); GREEN = (40, 200, 120); MINT = (200, 242, 222)
SKY = (236, 246, 255); PAPER = (255, 255, 255); LINE = (190, 214, 245)

def newspaper(d, cx, cy, s):
    """신문 아이콘: 파란 테두리 종이 + 초록 머리띠 + 줄 + 작은 해."""
    w, h = 1.0 * s, 0.82 * s
    x0, y0 = cx - w / 2, cy - h / 2
    d.rounded_rectangle([x0 + s*0.04, y0 + s*0.05, x0 + w + s*0.04, y0 + h + s*0.05], radius=s*0.09, fill=(205, 218, 235))
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=s*0.09, fill=PAPER, outline=BLUE, width=max(3, int(s*0.05)))
    d.rounded_rectangle([x0 + s*0.1, y0 + s*0.1, x0 + w - s*0.1, y0 + s*0.27], radius=s*0.04, fill=GREEN)
    # 사진 칸 + 해
    px0, py0 = x0 + s*0.1, y0 + s*0.36
    d.rounded_rectangle([px0, py0, px0 + s*0.36, py0 + s*0.32], radius=s*0.03, fill=MINT)
    r = s*0.07; d.ellipse([px0 + s*0.18 - r, py0 + s*0.16 - r, px0 + s*0.18 + r, py0 + s*0.16 + r], fill=BLUE)
    for k in range(4):
        y = y0 + s*0.38 + k * s*0.09
        d.rounded_rectangle([x0 + s*0.54, y, x0 + w - s*0.1, y + s*0.04], radius=s*0.02, fill=LINE)

# --- 로고 800x800 (원형으로 잘려도 안전하게 가운데) ---
L = 800
img = Image.new("RGBA", (L, L), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
d.ellipse([0, 0, L, L], fill=SKY)
newspaper(d, L/2, 300, 330)
f1, f2 = F(BLACK, 150), F(BOLD, 72)
for t, f, y, c in [("핑포", f1, 470, BLUE), ("오늘뉴스", f2, 640, NAVY)]:
    tw = d.textlength(t, font=f); d.text(((L - tw) / 2, y), t, font=f, fill=c)
img.save(f"{OUT}/logo-800.png")
# 쇼츠 화면용 작은 아이콘 1024 (글자 없이 아이콘만)
ic = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)); di = ImageDraw.Draw(ic)
di.ellipse([0, 0, 1024, 1024], fill=SKY); newspaper(di, 512, 512, 640)
ic.save(f"{OUT}/icon.png")

# --- 배너 2560x1440 (글자는 가운데 안전 영역 1546x423 안에) ---
W, H = 2560, 1440
b = Image.new("RGBA", (W, H), SKY + (255,)); d = ImageDraw.Draw(b)
for row, y in enumerate([440, 1020]):
    for k in range(12):
        x = 100 + k * 220 + (110 if row else 0)
        c = GREEN if (k + row) % 2 else BLUE
        d.ellipse([x - 20, y - 20, x + 20, y + 20], fill=tuple(int(v * 0.35 + 255 * 0.65) for v in c))
cy = H // 2
ft, fs, fp = F(BLACK, 112), F(BOLD, 56), F(BOLD, 48)
title, sub, pill = "핑포의 오늘뉴스", "바쁜 하루, 꼭 알아야 할 소식만 쏙쏙", "출근길 1분 뉴스 · 생활 꿀뉴스 · 오늘의 화제"
textw = max(d.textlength(title, font=ft), d.textlength(sub, font=fs), d.textlength(pill, font=fp) + 70)
R, gap = 150, 60
total = 2 * R + gap + textw
x0 = (W - total) / 2
d.ellipse([x0, cy - R, x0 + 2 * R, cy + R], fill=(255, 255, 255))
newspaper(d, x0 + R, cy, 200)
tx = x0 + 2 * R + gap
d.text((tx, cy - 165), title, font=ft, fill=NAVY)
d.text((tx, cy - 20), sub, font=fs, fill=BLUE)
pw = d.textlength(pill, font=fp)
d.rounded_rectangle([tx, cy + 70, tx + pw + 70, cy + 155], radius=42, fill=GREEN)
d.text((tx + 35, cy + 80), pill, font=fp, fill=(255, 255, 255))
print("group x", x0, x0 + total, "safe 507-2053")
b.convert("RGB").save(f"{OUT}/banner-2560x1440.png")
print("ok")
