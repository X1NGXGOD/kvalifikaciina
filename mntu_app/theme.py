
import re

from mntu_app.config import MEET_LINKS


def get_meet_link(subject: str) -> str | None:
    if not subject:
        return None

    subject_clean = subject.lower().strip()
    subject_clean = re.sub(r"\n+", " ", subject_clean)
    subject_clean = re.sub(r"\s+", " ", subject_clean)
    subject_clean = re.sub(r"[,;\.]+$", "", subject_clean).strip()

    if subject_clean in MEET_LINKS:
        return MEET_LINKS[subject_clean]

    for key, link in MEET_LINKS.items():
        key_clean = re.sub(r"[,;\.]+$", "", key).strip()
        subject_clean_no_punct = re.sub(r"[,;\.]+", "", subject_clean)
        key_clean_no_punct = re.sub(r"[,;\.]+", "", key_clean)

        if key_clean in subject_clean or subject_clean in key_clean:
            return link

        if key_clean_no_punct in subject_clean_no_punct or subject_clean_no_punct in key_clean_no_punct:
            return link

        if len(subject_clean) > 10:
            words_subject = set(re.findall(r"\b\w{3,}\b", subject_clean_no_punct))
            words_key = set(re.findall(r"\b\w{3,}\b", key_clean_no_punct))
            if len(words_key) > 0 and len(words_subject.intersection(words_key)) >= min(2, len(words_key)):
                return link

    return None


def hex_to_rgb(hex_str: str) -> tuple:
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) != 6:
        return (0, 0, 0)
    try:
        return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def rgb_to_hsl(r: int, g: int, b: int) -> tuple:
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        return (0, 0, round(l * 100))
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    s *= 100
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    h = (h / 6.0) * 360 % 360
    return (round(h), round(s), round(l * 100))


def hsl_to_rgb(h: float, s: float, l: float) -> tuple:
    s, l = s / 100.0, l / 100.0
    if s == 0:
        v = round(l * 255)
        return (v, v, v)
    h = h / 360.0

    def f(n):
        k = (n + h * 12) % 12
        a = s * min(l, 1 - l)
        return l - a * max(-1, min(k - 3, 9 - k, 1))

    r = round(f(0) * 255)
    g = round(f(8) * 255)
    b = round(f(4) * 255)
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = hsl_to_rgb(h, s, l)
    return rgb_to_hex(r, g, b)


def accent_text_color(hex_str: str) -> str:
    r, g, b = hex_to_rgb(hex_str)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return "#000000" if luminance > 0.45 else "#ffffff"
