import re
from datetime import date, timedelta

def extract_teacher_from_text(text: str) -> tuple[str, str]:

    teacher = ""
    subject = text
    platform_pattern = r"\s+(Google\s+meet|Zoom|Meet|Teams)\s*$"

    def _cleanup_subject(base: str) -> str:
        cleaned = re.sub(r"[,;\.]\s*$", "", (base or "").strip()).strip()
        platform_match = re.search(platform_pattern, text, re.IGNORECASE)
        if platform_match and platform_match.group(0).strip().lower() not in cleaned.lower():
            cleaned = f"{cleaned} {platform_match.group(0).strip()}".strip()
        return cleaned

    surname = r"[А-ЯІЇЄҐ][а-яіїєґ'’`\-]+"
    initials = r"[А-ЯІЇЄҐ]\.\s*[А-ЯІЇЄҐ]\."
    title = r"(?:проф\.?|професор|доц\.?|доцент|ст\.\s*викл\.?|викл\.?|асс\.?|ас\.)"
    teacher_full = rf"{title}\s*{surname}\s*{initials}"

    pattern1 = rf",\s*({teacher_full})\s*(?:,|$)"
    match1 = re.search(pattern1, text, re.IGNORECASE)
    if match1:
        teacher = re.sub(r"\s+", " ", match1.group(1)).strip()
        subject = _cleanup_subject(text[:match1.start()])
        return (subject, teacher)

    pattern2 = rf",\s*({surname}\s*{initials})\s*(?:,|$)"
    match2 = re.search(pattern2, text)
    if match2:
        teacher = match2.group(1).strip()
        subject = _cleanup_subject(text[:match2.start()])
        return (subject, teacher)

    pattern3 = rf"\.\s*({teacher_full})\s*(?:,|$)"
    match3 = re.search(pattern3, text, re.IGNORECASE)
    if match3:
        teacher = re.sub(r"\s+", " ", match3.group(1)).strip()
        subject = _cleanup_subject(text[:match3.start()])
        return (subject, teacher)

    if re.search(platform_pattern, text, re.IGNORECASE):

        before_platform = re.sub(platform_pattern, '', text, flags=re.IGNORECASE)
        match4 = re.search(rf",\s*({teacher_full}|{surname}\s*{initials})\s*,", before_platform, re.IGNORECASE)
        if match4:
            teacher = match4.group(1).strip()
            subject = _cleanup_subject(before_platform[:match4.start()])

            return (subject, teacher)

    return (subject, teacher)

def parse_schedule_date_str(date_str: str) -> date | None:
    if not date_str or not isinstance(date_str, str):
        return None
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', date_str.strip())
    if not match:
        return None
    try:
        d, mo = int(match.group(1)), int(match.group(2))
        y_str = match.group(3).strip()
        y = int(y_str) if len(y_str) > 2 else 2000 + int(y_str)
        return date(y, mo, d)
    except (ValueError, TypeError):
        return None


def extract_date_from_text(date_str: str, today: date = None) -> date | None:
    if today is None:
        today = date.today()

    day_names = ["ПОНЕДІЛОК", "ВІВТОРОК", "СЕРЕДА", "ЧЕТВЕР", "П'ЯТНИЦЯ", "ПЯТНИЦЯ", "СУБОТА", "НЕДІЛЯ"]
    cleaned = date_str.upper()
    for day_name in day_names:
        cleaned = cleaned.replace(day_name, "")

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    cleaned = re.sub(r'р\.?\s*$', '', cleaned, flags=re.IGNORECASE).strip()

    date_pattern = r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})'
    match = re.search(date_pattern, cleaned)

    if match:
        try:
            day = int(match.group(1))
            month = int(match.group(2))
            year_str = match.group(3).strip()

            year_str = re.sub(r'[^\d]', '', year_str)

            if not year_str:
                return None

            if len(year_str) == 2:

                year = 2000 + int(year_str)
            else:
                year = int(year_str)

            table_date = date(year, month, day)
            return table_date
        except (ValueError, TypeError) as e:
            print(f"[DEBUG] Помилка парсингу дати '{date_str}': {e}")
            return None

    return None

UKR_WEEKDAY_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "нд")


def calendar_week_monday_sunday(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def next_calendar_week_monday_sunday(d: date) -> tuple[date, date]:
    mon, sun = calendar_week_monday_sunday(d)
    return mon + timedelta(days=7), sun + timedelta(days=7)


def format_schedule_date_short(d: date) -> str:
    return f"{d.day:02d}.{d.month:02d}.{d.year % 100:02d}"


def format_week_range_human(mon: date, sun: date) -> str:
    return (
        f"{UKR_WEEKDAY_SHORT[mon.weekday()]} {format_schedule_date_short(mon)} — "
        f"{UKR_WEEKDAY_SHORT[sun.weekday()]} {format_schedule_date_short(sun)}"
    )


def schedule_has_entries(parsed: dict | None) -> bool:
    if not parsed or not isinstance(parsed, dict):
        return False
    for _g, weeks in parsed.items():
        if not isinstance(weeks, dict):
            continue
        for _wk, entries in weeks.items():
            if entries:
                return True
    return False


def _is_synthetic_no_classes_entry(entry: dict) -> bool:
    subj = (entry.get("subject") or "").lower()
    if (entry.get("date") or "").strip():
        return False
    if "інформації немає" in subj:
        return True
    return "немає" in subj and "пар" in subj


def merged_schedule_entries_for_group(state: dict, group_name: str) -> list[dict]:
    g = state.get("parsed_schedule_per_group", {}).get(group_name, {})
    out: list[dict] = []
    seen: set[tuple] = set()
    for wk in g.keys():
        for e in g.get(wk, []):
            if _is_synthetic_no_classes_entry(e):
                continue
            ds = (e.get("date") or "").strip()
            if not ds:
                continue
            key = (ds, e.get("time"), e.get("subject"))
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
    return out


def entry_calendar_date(entry: dict, ref_today: date) -> date | None:
    d = parse_schedule_date_str(entry.get("date") or "")
    if d is not None:
        return d
    return extract_date_from_text(entry.get("date") or "", ref_today)


def filter_entries_for_calendar_week(
    entries: list[dict], week_start: date, week_end_exclusive: date, ref_today: date
) -> list[dict]:
    out: list[dict] = []
    for e in entries:
        pd = entry_calendar_date(e, ref_today)
        if pd is None:
            continue
        if week_start <= pd < week_end_exclusive:
            out.append(e)
    return out
