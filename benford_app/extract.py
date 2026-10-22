"""Find numbers in free text and classify them as "natural" or "artificial".

Natural numbers are measurements, amounts, counts etc. – the kind of quantities
Benford's law is about. Artificial numbers are identifiers and labels whose
digits are assigned rather than measured: dates, times, years, phone numbers,
page/section numbers, codes, versions, citations and so on.

Every number found is returned with a category so the caller can decide which
categories to include (and so the user can audit the decisions).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Categories. The ones in DEFAULT_INCLUDED are counted in the Benford analysis
# by default; the rest are shown as excluded but can be toggled in the UI.
CATEGORIES = {
    "natural": "Naturlige tall",
    "percent": "Prosenter",
    "small": "Heltall 1–9 uten enhet",
    "year": "Årstall",
    "date": "Datoer og perioder",
    "time": "Klokkeslett",
    "phone": "Telefonnumre",
    "id": "ID-er og lange sifferrekker",
    "code": "Koder (bokstav+tall, f.eks. A4, COVID-19)",
    "label": "Referanser (side, figur, kapittel, nr. …)",
    "enum": "Nummerering og overskrifter",
    "version": "Versjoner, IP-adresser, seksjonsnr.",
    "citation": "Kildehenvisninger [12]",
    "page": "Sidetall",
    "ordinal": "Ordenstall (1st, 2nd …)",
    "isbn": "ISBN/ISSN/DOI",
    "url": "Tall i URL-er og e-postadresser",
    "zero": "Null (har ikke ledende siffer)",
}
DEFAULT_INCLUDED = {"natural", "percent", "small"}


@dataclass
class Found:
    raw: str
    digit: int  # first significant digit, 0 if the number is zero
    category: str
    context: str


# ---------------------------------------------------------------------------
# Patterns

_SP = r"[    ]"  # space, nbsp, narrow nbsp, thin space
_DASH = r"[-–—]"

_MONTHS = (
    r"jan(?:uar|uary)?|feb(?:ruar|ruary)?|mar(?:s|ch)?|apr(?:il)?|mai|may|"
    r"jun(?:i|e)?|jul(?:i|y)?|aug(?:ust)?|sep(?:t|tember)?|okt(?:ober)?|"
    r"oct(?:ober)?|nov(?:ember)?|des(?:ember)?|dec(?:ember)?"
)

_LABEL_WORDS = (
    r"side|sidene|s|sidetall|page|pages|p|pp|nr|no|nos|nummer|number|num|"
    r"kapittel|kap|chapter|ch|figur|fig|figure|figs|tabell|tab|table|vedlegg|"
    r"appendix|app|bilag|artikkel|art|article|section|sec|seksjon|avsnitt|del|"
    r"part|punkt|pkt|ledd|ref|id|versjon|version|ver|v|uke|week|postboks|pb|"
    r"boks|box|rom|room|sak|case|linje|line|kolonne|column|rad|row|vers|"
    r"step|steg|trinn|level|nivå|eksempel|example|ex|oppgave|exercise|"
    r"utgave|edition|vol|volume|bind|issue|serie|series|lov|forskrift|"
    r"rule|regel|note|fotnote|footnote|klasse|class|gruppe|group|"
    r"kvartal|quarter|tertial|halvår|termin|semester|runde|round|"
    r"etasje|floor|plass|seat|gate|gt|vei|veg|veien|street|st|road|rd|avenue|ave"
)

_CURRENCY_PREFIX = {"kr", "nok", "usd", "eur", "sek", "dkk", "gbp", "chf", "jpy", "us", "rs", "r"}

# Spans whose numbers are artificial as a whole. Order matters: earlier
# patterns claim their spans first.
_SPAN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("url", re.compile(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I)),
    ("isbn", re.compile(
        r"\bISBN(?:-1[03])?[\s:]*[\dXx][\d\s\-Xx]{8,16}[\dXx]"
        r"|\bISSN[\s:]*\d{4}-?\d{3}[\dXx]"
        r"|\b(?:doi:\s*)?10\.\d{4,9}/\S+", re.I)),
    ("citation", re.compile(r"\[\s*\d+(?:\s*[,–\-]\s*\d+)*\s*\]")),
    # Date/time combos and dates
    ("date", re.compile(r"(?<![\d.,])\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)?(?![\d])")),
    ("date", re.compile(r"(?<![\d.,])\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2})(?![\d]|[.,]\d)")),
    ("date", re.compile(
        rf"(?<![\d.,])\d{{1,2}}(?:\.|st|nd|rd|th)?{_SP}*(?:{_DASH}{_SP}*\d{{1,2}}\.?{_SP}*)?(?:{_MONTHS})\b\.?"
        rf"(?:,?{_SP}*\d{{4}}\b)?", re.I)),
    ("date", re.compile(
        rf"\b(?:{_MONTHS})\.?{_SP}+\d{{1,2}}(?:st|nd|rd|th)?(?:{_SP}*{_DASH}{_SP}*\d{{1,2}})?(?:,?{_SP}*\d{{4}})?\b(?![.,]\d)", re.I)),
    ("date", re.compile(rf"\b(?:{_MONTHS})\.?,?{_SP}*\d{{4}}\b", re.I)),
    ("date", re.compile(rf"(?<![\d.,])\d\.?{_SP}*(?:kvartal|halvår|halvåret|tertial|quarter|half)\b", re.I)),
    ("date", re.compile(rf"\b[QK][1-4]{_SP}*(?:\d{{4}}|'?\d{{2}})?\b")),
    # Year ranges like 2019–2023, 2023/24, 1990-tallet
    ("year", re.compile(rf"(?<![\d.,])(?:1[89]|20)\d{{2}}{_SP}*[/–\-]{_SP}*(?:(?:1[89]|20)\d{{2}}|\d{{2}})(?![\d]|[.,]\d)")),
    ("year", re.compile(r"(?<![\d.,])(?:1[89]|20)\d{2}-tallet", re.I)),
    # Times
    ("time", re.compile(r"(?<![\d.,])\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:[ap]\.?m\.?))?(?![\d])", re.I)),
    ("time", re.compile(
        rf"\b(?:kl|klokka|klokken)\.?{_SP}*\d{{1,2}}(?:[.:]\d{{2}})?(?:{_SP}*{_DASH}{_SP}*\d{{1,2}}(?:[.:]\d{{2}})?)?", re.I)),
    ("time", re.compile(r"(?<![\d.,])\d{1,2}(?:[.:]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)(?!\w)", re.I)),
    ("ordinal", re.compile(r"(?<![\d.,])\d+(?:st|nd|rd|th)\b", re.I)),
]

# Phone-like digit group runs; checked by _is_phone().
_PHONE_RE = re.compile(
    r"(?<![\w.,])(\+\d{1,3}[\s.\-]?)?(\(\d{1,4}\)[\s.\-]?)?\d{2,4}(?:[  .\-]\d{2,4}){1,5}(?![\w]|[.,]\d)"
)
_PHONE_CONTEXT = re.compile(r"(?:tlf|telefon|telephone|phone|tel|mob|mobil|mobile|fax|faks|ring|call)\W{0,4}$", re.I)
_PHONE_SHAPES = {(2, 2, 2, 2), (3, 2, 3), (3, 3, 4), (3, 4), (4, 4), (2, 3, 3, 3)}

# Dotted digit groups (versions, IP addresses, section numbers 1.2.3)
_DOTTED_RE = re.compile(r"(?<![\w.,])\d+(?:\.\d+){2,}(?![\w]|\.\d)")

# Line-start numbering ("1.", "2)", "3.4 Overskrift", "1.2.3")
_ENUM_RE = re.compile(
    r"^[ \t•·\-–*]*(?:(\d{1,2}(?:\.\d{1,2})+)\.?(?=[ \t]+\S)|(\d{1,2})[.)](?=[ \t]+\S))",
    re.M,
)

# Page number lines (applied to the first/last lines of a PDF page)
_PAGE_LINE_RE = re.compile(
    r"^\s*(?:[-–]\s*)?(?:(?:side|page|s\.|p\.|pg\.?)\s*)?\d{1,4}(?:\s*(?:/|av|of)\s*\d{1,4})?(?:\s*[-–])?\s*$",
    re.I,
)

_EDGE_NUMBER_RE = re.compile(r"^\s*(\d{1,4})(?=\s|[A-ZÆØÅ])|(?<=\s)(\d{1,4})\s*$")
_HHMM_RE = re.compile(r"(?<![\d.,])(?:[01]?\d|2[0-4])[.:][0-5]\d(?![\d]|[.,:]\d)")

# Label word directly before a number: "side 12", "fig. 3", "§ 4", "nr. 17"
_LABEL_BEFORE = re.compile(rf"(?:\b(?:{_LABEL_WORDS})\.?|§§?|#|№){_SP}*$", re.I)

_NUMBER_RE = re.compile(
    rf"""
    (?<![\d])(?<![\d][.,])           # not inside another number
    (?:
        \d{{1,3}}(?:{_SP}\d{{3}})+(?![\d])(?:,\d+)?   # 1 234 567,89
      | \d{{1,3}}(?:,\d{{3}})+(?![\d])(?:\.\d+)?      # 1,234,567.89
      | \d{{1,3}}(?:\.\d{{3}})+(?![\d])(?:,\d+)?      # 1.234.567,89
      | \d+(?:[.,]\d+)?                              # 1234 / 12,5 / 0.034
      | [.,]\d+                                      # .5
    )
    """,
    re.X,
)

_PERCENT_AFTER = re.compile(rf"^{_SP}*(?:%|‰|prosent|percent|pct\b|per cent|prosentpoeng|pp\b)", re.I)


def _first_digit(raw: str) -> int:
    for ch in raw:
        if ch in "123456789":
            return int(ch)
    return 0


def _context(text: str, start: int, end: int, width: int = 45) -> str:
    a = max(0, start - width)
    b = min(len(text), end + width)
    s = text[a:start] + "⟦" + text[start:end] + "⟧" + text[end:b]
    s = re.sub(r"\s+", " ", s).strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def _is_phone(text: str, m: re.Match) -> bool:
    s = m.group(0)
    groups = [len(g) for g in re.findall(r"\d+", s)]
    total = sum(groups)
    if total < 7 or total > 15:
        return False
    if m.group(1) or m.group(2):  # +47 / (555)
        return True
    if _PHONE_CONTEXT.search(text[max(0, m.start() - 20):m.start()]):
        return True
    seps = set(re.findall(r"[^\d]", s))
    if "-" in seps and len(groups) >= 3:
        return True
    if tuple(groups) in _PHONE_SHAPES:
        # But a valid thousands grouping (1 234 567 / 1.234.567) is a number.
        if groups[0] <= 3 and all(g == 3 for g in groups[1:]) and len(seps) == 1:
            return False
        return True
    return False


def _is_thousands_grouping(s: str) -> bool:
    parts = s.split(".")
    return 1 <= len(parts[0]) <= 3 and all(len(p) == 3 for p in parts[1:])


def classify_text(
    text: str, *, page_mode: bool = False, page_no: int | None = None, space_thousands: bool = True
) -> list[Found]:
    """Find all numbers in `text` and classify each.

    page_mode: the text is a single PDF page; standalone numbers on the first
    or last two lines are treated as page numbers. With page_no (1-based page
    index) a number at the start/end of those lines close to page_no counts
    as a page number too ("Torsdag 16. juni 2022 37").
    """
    results: list[Found] = []
    taken = bytearray(len(text))  # 1 where a span has already been claimed

    def claim(start: int, end: int, category: str) -> None:
        span = text[start:end]
        for nm in re.finditer(r"\d+(?:[.,]\d+)*", span):
            s, e = start + nm.start(), start + nm.end()
            if any(taken[s:e]):
                continue
            results.append(Found(nm.group(0), _first_digit(nm.group(0)), category, _context(text, s, e)))
        for i in range(start, end):
            taken[i] = 1

    def free(start: int, end: int) -> bool:
        return not any(taken[start:end])

    # 1. Page numbers on the first/last lines of a page.
    if page_mode:
        lines = list(re.finditer(r"[^\n]*", text))
        lines = [l for l in lines if l.group(0).strip()]
        for l in lines[:2] + lines[-2:]:
            if _PAGE_LINE_RE.match(l.group(0)) and free(l.start(), l.end()):
                claim(l.start(), l.end(), "page")
            elif page_no is not None:
                for m in _EDGE_NUMBER_RE.finditer(l.group(0)):
                    g = 1 if m.group(1) else 2
                    if abs(int(m.group(g)) - page_no) <= 20:
                        s, e = l.start() + m.start(g), l.start() + m.end(g)
                        if free(s, e):
                            claim(s, e, "page")

    # 2. Span patterns (URLs, dates, times …)
    for cat, pat in _SPAN_PATTERNS:
        for m in pat.finditer(text):
            if free(m.start(), m.end()):
                claim(m.start(), m.end(), cat)

    # 2b. Clock times written HH.MM ("21.30") – only when another such time
    # is nearby (TV listings, timetables), since "12.50" is often a decimal.
    cands = [m for m in _HHMM_RE.finditer(text) if free(m.start(), m.end())]
    for i, m in enumerate(cands):
        near = (i > 0 and m.start() - cands[i - 1].end() <= 60) or (
            i + 1 < len(cands) and cands[i + 1].start() - m.end() <= 60
        )
        if near:
            claim(m.start(), m.end(), "time")

    # 3. Line-start numbering / section headings
    for m in _ENUM_RE.finditer(text):
        g = 1 if m.group(1) else 2
        s, e = m.start(g), m.end(g)
        if not free(s, e):
            continue
        if m.group(1):
            # "3.5 Resultater" is a heading, "3.5 millioner" is a decimal.
            rest = text[m.end():m.end() + 3].lstrip()
            if m.group(1).count(".") == 1 and not (rest[:1].isupper()):
                continue
        claim(s, e, "enum")

    # 4. Phone numbers
    for m in _PHONE_RE.finditer(text):
        if free(m.start(), m.end()) and _is_phone(text, m):
            claim(m.start(), m.end(), "phone")

    # 5. Dotted groups: versions / IPs / section numbers (unless thousands)
    for m in _DOTTED_RE.finditer(text):
        if free(m.start(), m.end()) and not _is_thousands_grouping(m.group(0)):
            claim(m.start(), m.end(), "version")

    # 6. Remaining numbers
    for m in _NUMBER_RE.finditer(text):
        s, e = m.start(), m.end()
        raw = m.group(0)
        if not space_thousands and re.search(_SP, raw):
            # Treat "100 200 300" as separate numbers.
            for sub in re.finditer(r"\d+(?:,\d+)?", raw):
                _classify_one(text, s + sub.start(), s + sub.end(), sub.group(0), taken, results)
            continue
        _classify_one(text, s, e, raw, taken, results)

    return results


def _classify_one(text: str, s: int, e: int, raw: str, taken: bytearray, results: list[Found]) -> None:
    if any(taken[s:e]):
        return
    digit = _first_digit(raw)
    plain_int = raw.isdigit()
    before = text[max(0, s - 30):s]
    after = text[e:e + 20]

    cat = "natural"
    prev = text[s - 1] if s > 0 else ""
    prev2 = text[s - 2] if s > 1 else ""
    nxt = text[e] if e < len(text) else ""

    if digit == 0:
        cat = "zero"
    elif prev and (prev.isalpha() or (prev in "-_/" and prev2.isalpha()) or prev in "#№_"):
        letters = re.search(r"([A-Za-zÆØÅæøå$€£]+)[-_]?$", before)
        if letters and letters.group(1).lower() in _CURRENCY_PREFIX | {"$", "€", "£"}:
            cat = "natural"
        else:
            cat = "code"
    elif nxt.isalpha() and re.match(r"[A-Za-zÆØÅæøå]+\d", after):
        cat = "code"  # 3a4f, 2x3b …
    elif nxt == "_" or (nxt and nxt in "-/" and re.match(r"[-/][A-Za-zÆØÅæøå]", after) and re.match(r"[-/][A-ZÆØÅ]{1,3}\b", after)):
        cat = "code"  # 12-A, 4/B
    elif plain_int and len(raw) == 1 and re.match(r"[A-Z]{1,2}\b", after):
        cat = "code"  # 3D, 5G, 4K
    elif _LABEL_BEFORE.search(before):
        cat = "label"
    elif plain_int and len(raw) > 1 and raw[0] == "0":
        cat = "id"  # 0150, 007 – leading zeros mean a code
    elif plain_int and len(raw) >= 8:
        cat = "id"
    elif plain_int and len(raw) == 4 and 1800 <= int(raw) <= 2100:
        cat = "year"
    elif _PERCENT_AFTER.match(after):
        cat = "percent"
    elif plain_int and len(raw) == 1:
        cat = "small"

    results.append(Found(raw, digit, cat, _context(text, s, e)))
    for i in range(s, e):
        taken[i] = 1


def drop_repeated_lines(texts: list[str], min_len: int = 1) -> list[str]:
    """Remove lines that already appeared in an earlier text (running
    headers/footers, site navigation repeated on every page)."""
    seen: set[str] = set()
    out = []
    for t in texts:
        keep = []
        local: set[str] = set()
        for line in t.split("\n"):
            key = re.sub(r"\s+", " ", line).strip()
            if len(key) < min_len or not re.search(r"\d", key):
                keep.append(line)
                continue
            if key in seen and key not in local:
                continue
            local.add(key)
            keep.append(line)
        seen |= local
        out.append("\n".join(keep))
    return out
