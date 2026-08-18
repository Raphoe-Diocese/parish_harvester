"""
liturgical.py — Catholic liturgical calendar lookup for Greenlough URL prediction.
"""
import re
from datetime import date, timedelta
from functools import lru_cache
from urllib.parse import unquote


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _ordinary_time_name(week: int) -> str:
    if week == 6:
        return "Sixth_Sunday_in_Ordinary_Time"
    return f"{_ordinal(week)}_Sunday_in_Ordinary_Time"


def _easter_sunday(year: int) -> date:
    """
    Return Gregorian Easter Sunday for *year* (Anonymous Gregorian computus).
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _sunday_on_or_after(d: date) -> date:
    return d + timedelta(days=(6 - d.weekday()) % 7)


@lru_cache(maxsize=None)
def get_liturgical_sundays(year: int) -> dict[date, str]:
    """
    Build liturgical Sunday names for *year* in the Greenlough filename format.
    """
    names: dict[date, str] = {}

    easter = _easter_sunday(year)
    epiphany = _sunday_on_or_after(date(year, 1, 2))
    baptism = epiphany + timedelta(days=7)
    lent_1 = easter - timedelta(days=42)
    palm = easter - timedelta(days=7)
    pentecost = easter + timedelta(days=49)
    trinity = easter + timedelta(days=56)
    corpus = easter + timedelta(days=63)
    first_advent = _sunday_on_or_after(date(year, 11, 27))
    christ_king = first_advent - timedelta(days=7)
    all_saints = date(year, 11, 1)
    christmas = date(year, 12, 25)

    names[epiphany] = "Epiphany_of_the_Lord"
    names[baptism] = "Baptism_of_the_Lord"

    # Ordinary Time before Lent starts.
    cur = baptism + timedelta(days=7)
    week = 2
    while cur < lent_1:
        names[cur] = _ordinary_time_name(week)
        cur += timedelta(days=7)
        week += 1

    names[lent_1] = "1st_Sunday_of_Lent"
    names[lent_1 + timedelta(days=7)] = "2nd_Sunday_of_Lent"
    names[lent_1 + timedelta(days=14)] = "3rd_Sunday_of_Lent"
    names[lent_1 + timedelta(days=21)] = "4th_Sunday_of_Lent"
    names[lent_1 + timedelta(days=28)] = "5th_Sunday_of_Lent"
    names[palm] = "Palm_Sunday"
    names[easter] = f"Easter_Sunday_{year}"
    names[easter + timedelta(days=7)] = "2nd_Sunday_of_Easter_-_Divine_Mercy_Sunday"
    names[easter + timedelta(days=14)] = "3rd_Sunday_of_Easter"
    names[easter + timedelta(days=21)] = "4th_Sunday_of_Easter"
    names[easter + timedelta(days=28)] = "5th_Sunday_of_Easter"
    names[easter + timedelta(days=35)] = "6th_Sunday_of_Easter"
    names[easter + timedelta(days=42)] = "7th_Sunday_of_Easter"
    names[pentecost] = "Pentecost_Sunday"
    names[trinity] = "Trinity_Sunday"
    names[corpus] = "The_Most_Holy_Body_and_Blood_of_Christ"

    # Ordinary Time after Corpus Christi to Christ the King.
    ordinary_slots_after_corpus: list[date] = []
    cur = corpus + timedelta(days=7)
    while cur < christ_king:
        ordinary_slots_after_corpus.append(cur)
        cur += timedelta(days=7)

    starting_week = 33 - (len(ordinary_slots_after_corpus) - 1)
    for i, sunday in enumerate(ordinary_slots_after_corpus):
        if sunday not in names and sunday != all_saints:
            names[sunday] = _ordinary_time_name(starting_week + i)

    if all_saints.weekday() == 6:
        names[all_saints] = "All_Saints_Day"

    names[christ_king] = "Our_Lord_Jesus_Christ_King_of_the_Universe"
    names[first_advent] = "1st_Sunday_of_Advent"
    names[first_advent + timedelta(days=7)] = "2nd_Sunday_of_Advent"
    names[first_advent + timedelta(days=14)] = "3rd_Sunday_of_Advent"
    names[first_advent + timedelta(days=21)] = "4th_Sunday_of_Advent"
    names[christmas] = "Christmas_Day"

    # Sunday in the octave of Christmas; if absent, celebrated on Dec 30.
    holy_family = _sunday_on_or_after(christmas + timedelta(days=1))
    if holy_family.year != year:
        holy_family = date(year, 12, 30)
    names[holy_family] = "The_Holy_Family"
    return names


def get_liturgical_name(target: date) -> str | None:
    """Return the liturgical Sunday name for the given date, or None if not found."""
    return get_liturgical_sundays(target.year).get(target)


# Word ordinals used in filenames (Holy Family "Twentieth-Sunday-in-Ordinary-Time.pdf",
# Glenariffe "Sixteenth-Sunday-of-Ordinary-Time.pdf") instead of 20th / 16th.
_WORD_ORDINALS: dict[str, int] = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
    "twenty-first": 21,
    "twenty first": 21,
    "twenty-second": 22,
    "twenty second": 22,
    "twenty-third": 23,
    "twenty third": 23,
    "twenty-fourth": 24,
    "twenty fourth": 24,
    "twenty-fifth": 25,
    "twenty fifth": 25,
    "twenty-sixth": 26,
    "twenty sixth": 26,
    "twenty-seventh": 27,
    "twenty seventh": 27,
    "twenty-eighth": 28,
    "twenty eighth": 28,
    "twenty-ninth": 29,
    "twenty ninth": 29,
    "thirtieth": 30,
    "thirty-first": 31,
    "thirty first": 31,
    "thirty-second": 32,
    "thirty second": 32,
    "thirty-third": 33,
    "thirty third": 33,
}

# Filename is specific enough to match a calendar name as a substring
# ("20th sunday" → 20th Sunday in Ordinary Time) without matching every
# "ordinary time" file against every Ordinary Time Sunday.
_SPECIFIC_LITURGICAL_RE = re.compile(
    r"\b(?:\d{1,2}(?:st|nd|rd|th)\s+sunday|"
    r"pentecost|trinity|palm sunday|easter sunday|epiphany|"
    r"baptism of the lord|body and blood|corpus christi|"
    r"christ the king|all saints|holy family|"
    r"\d{1,2}(?:st|nd|rd|th)\s+sunday of advent|"
    r"\d{1,2}(?:st|nd|rd|th)\s+sunday of lent)\b",
    re.IGNORECASE,
)


def normalize_liturgical_phrase(text: str) -> str:
    """Lowercase, fix Suday typo, turn Twentieth into 20th, of→in Ordinary Time."""
    phrase = unquote(text or "").lower().replace("suday", "sunday")
    phrase = phrase.replace("&amp;", " ")
    phrase = re.sub(r"[_\-/]+", " ", phrase)
    phrase = re.sub(r"[^a-z0-9 ]+", " ", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip()
    phrase = phrase.replace(" of ordinary time", " in ordinary time")
    for word, number in sorted(_WORD_ORDINALS.items(), key=lambda item: len(item[0]), reverse=True):
        phrase = re.sub(rf"\b{re.escape(word)}\b", _ordinal(number), phrase)
    phrase = re.sub(r"\b(\d{1,2})\s+(st|nd|rd|th)\b", r"\1\2", phrase)
    return phrase


def year_hint_from_upload_url(text: str, fallback: int) -> int:
    """Prefer /uploads/YYYY/ (or /app/uploads/YYYY/) over the harvest year.

    Scoring a 2024 'Twentieth-Sunday' archive file with the 2026 harvest
    year would treat it as this week's bulletin (found 2026-08-18,
    glenariffeparish.org/whats-on).
    """
    match = re.search(r"/uploads/(20\d{2})/", unquote(text or ""), re.IGNORECASE)
    if match:
        return int(match.group(1))
    return fallback


def liturgical_date_from_text(text: str, year: int) -> date | None:
    """Map a filename/slug like 'Twentieth-Sunday-in-Ordinary-Time' onto *year*.

    Used when the parish names the file after the liturgical Sunday and the
    WordPress /uploads/YYYY/MM/ folder would otherwise default the day to the
    1st (Holy Family / Loughshore / Derriaghy, found 2026-08-18).
    """
    raw = unquote(text or "")
    basename = raw.rsplit("/", 1)[-1]
    needle = normalize_liturgical_phrase(basename)
    if len(needle) < 8:
        return None

    def _best_in_year(lookup_year: int) -> date | None:
        best_date: date | None = None
        best_len = 0
        for sunday, name in get_liturgical_sundays(lookup_year).items():
            hay = normalize_liturgical_phrase(name)
            if len(hay) < 8:
                continue
            matched = hay in needle
            if not matched and _SPECIFIC_LITURGICAL_RE.search(needle) and needle in hay:
                matched = True
            if matched and len(hay) > best_len:
                best_date = sunday
                best_len = len(hay)
        return best_date

    found = _best_in_year(year)
    if found:
        return found
    # Early January / late December filenames may belong to the adjacent year.
    for other in (year - 1, year + 1):
        if other < 2000:
            continue
        found = _best_in_year(other)
        if found:
            return found
    return None


_CYCLE_LETTER_FOR_YEAR_MOD3 = {0: "C", 1: "A", 2: "B"}


def first_advent_sunday(year: int) -> date:
    """Return the First Sunday of Advent for *year* (always Nov 27 - Dec 3)."""
    return _sunday_on_or_after(date(year, 11, 27))


def liturgical_cycle_letter(target: date) -> str:
    """Return the Sunday Mass reading cycle letter ('A'/'B'/'C') for *target*.

    The cycle rotates on a 3-year schedule keyed off the calendar year, EXCEPT
    that the liturgical year itself starts on the First Sunday of Advent (late
    Nov/early Dec), not Jan 1 — so any date on/after that Sunday already uses
    next calendar year's letter. Confirmed against naomhfionan.com's own
    filenames (2022-2026): e.g. "...-SunB-03122023.pdf" for the 3 Dec 2023
    First Sunday of Advent, immediately after "...-SunA-26112023.pdf" the week
    before, while 2024 (whose letter B carries the whole liturgical year
    starting that Advent Sunday) otherwise maps from year%3 as C/A/B.
    """
    year = target.year
    if target >= first_advent_sunday(year):
        year += 1
    return _CYCLE_LETTER_FOR_YEAR_MOD3[year % 3]
