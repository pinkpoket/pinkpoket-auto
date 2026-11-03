#!/usr/bin/env python3
"""인생ON 긴 영상 썸네일 디자인 (1280x720).

thumbnail_text 에서 [대괄호] 안 낱말은 노란색으로 강조한다. 줄바꿈은 \\n.
thumb_badge: 왼쪽 위 작은 띠 문구 (예: "노후 인간관계"). 없으면 "인생ON 인생 이야기".
스타일: "left"(왼쪽 글씨 + 오른쪽 사진), "band"(위 노란 띠 + 가운데 큰 글씨), "number"(큰 숫자 원 + 글씨)
"""
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "shorts"))
os.environ.setdefault("CHANNEL", "life")
import make_short as ms  # noqa: E402

TW, TH = 1280, 720
YELLOW = (255, 230, 0)
WHITE = (255, 255, 255)
BLACK = (15, 15, 15)


def cover(src, w, h):
    img = Image.open(src).convert("RGB")
    sc = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * sc) + 1, int(img.height * sc) + 1), Image.LANCZOS)
    l, t = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((l, t, l + w, t + h))


def parse(text):
    """'[노후에] 끊을' → [(노후에, True), ( 끊을, False)] 줄 목록."""
    out = []
    for line in text.split("\n"):
        parts = [(m.group(1) or m.group(2), bool(m.group(1))) for m in re.finditer(r"\[([^\]]+)\]|([^\[]+)", line)]
        out.append([p for p in parts if p[0]])
    return out


def fit_font(d, lines, max_w, start, min_size=60):
    size = start
    while size > min_size:
        f = ms.font(size)
        if max(d.textlength("".join(t for t, _ in ln), font=f) for ln in lines) <= max_w:
            return f
        size -= 4
    return ms.font(min_size)


def draw_rich(d, x, y, line, f, align_w=None, stroke=10):
    if align_w is not None:
        x += (align_w - d.textlength("".join(t for t, _ in line), font=f)) / 2
    for text, hi in line:
        d.text((x, y), text, font=f, fill=YELLOW if hi else WHITE, stroke_width=stroke, stroke_fill=BLACK)
        x += d.textlength(text, font=f)


def badge(d, x, y, text, size=34):
    f = ms.font(size)
    w = d.textlength(text, font=f)
    d.rounded_rectangle([x, y, x + w + 40, y + size + 26], radius=(size + 26) // 2, fill=YELLOW)
    d.text((x + 20, y + 10), text, font=f, fill=BLACK)


def paste_logo(img, x, y, s=110):
    try:
        logo = Image.open(ms.LOGO).convert("RGBA").resize((s, s), Image.LANCZOS)
        img.alpha_composite(logo, (x, y))
    except Exception:  # noqa: BLE001
        pass


def style_left(photo, text, tag):
    img = cover(photo, TW, TH).convert("RGBA")
    shade = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for x in range(TW):  # 왼쪽은 진하게, 오른쪽으로 갈수록 사진이 보이게
        a = int(235 * max(0.0, 1 - x / (TW * 0.78)) ** 0.9)
        sd.line([(x, 0), (x, TH)], fill=(10, 10, 10, a))
    img.alpha_composite(shade)
    d = ImageDraw.Draw(img)
    lines = parse(text)
    f = fit_font(d, lines, 760, 150)
    lh = int(f.size * 1.18)
    y = (TH - lh * len(lines)) // 2 + 30
    badge(d, 56, y - 92, tag)
    for ln in lines:
        draw_rich(d, 56, y, ln, f)
        y += lh
    d.rectangle([56, y + 28, 56 + 220, y + 40], fill=YELLOW)
    paste_logo(img, TW - 140, TH - 140)
    return img.convert("RGB")


def style_band(photo, text, tag):
    img = cover(photo, TW, TH)
    img = Image.blend(img, Image.new("RGB", (TW, TH), (0, 0, 0)), 0.35).convert("RGBA")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, TW, 96], fill=YELLOW)
    ft = ms.font(54)
    tw = d.textlength(tag, font=ft)
    d.text(((TW - tw) / 2, 14), tag, font=ft, fill=BLACK)
    lines = parse(text)
    f = fit_font(d, lines, TW - 120, 160)
    lh = int(f.size * 1.18)
    y = 96 + (TH - 96 - lh * len(lines)) // 2
    for ln in lines:
        draw_rich(d, 0, y, ln, f, align_w=TW, stroke=12)
        y += lh
    paste_logo(img, TW - 130, TH - 130, 100)
    return img.convert("RGB")


def style_number(photo, text, tag):
    img = cover(photo, TW, TH)
    img = Image.blend(img, Image.new("RGB", (TW, TH), (0, 0, 0)), 0.45).convert("RGBA")
    d = ImageDraw.Draw(img)
    num = (re.findall(r"\d+", text) or ["!"])[0]
    cx, cy, r = 250, TH // 2 + 20, 190
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=YELLOW, outline=BLACK, width=10)
    fn = ms.font(250 if len(num) == 1 else 190)
    nw = d.textlength(num, font=fn)
    d.text((cx - nw / 2, cy - fn.size * 0.62), num, font=fn, fill=BLACK)
    lines = parse(text)
    f = fit_font(d, lines, TW - 520, 128)
    lh = int(f.size * 1.2)
    y = (TH - lh * len(lines)) // 2 + 20
    badge(d, 490, y - 90, tag)
    for ln in lines:
        draw_rich(d, 490, y, ln, f)
        y += lh
    paste_logo(img, TW - 130, 24, 100)
    return img.convert("RGB")


STYLES = {"left": style_left, "band": style_band, "number": style_number}


def make(photo, out, text, tag="", style="left"):
    tag = tag or "인생ON 인생 이야기"
    STYLES.get(style, style_left)(photo, text, tag).save(out, quality=92)
