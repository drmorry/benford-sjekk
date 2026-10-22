import pytest

from benford_app.extract import classify_text, drop_repeated_lines


def cats(text, **kw):
    return [(f.raw, f.category) for f in classify_text(text, **kw)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Omsetningen var 4 512 300 kroner", [("4 512 300", "natural")]),
        ("Revenue of $1,234,567.89 in total", [("1,234,567.89", "natural")]),
        ("Snitt 0,0345 mm", [("0,0345", "natural")]),
        ("Vi målte 12,5 kg og 1.234.567,8 liter", [("12,5", "natural"), ("1.234.567,8", "natural")]),
        ("Det kostet kr 450 eller NOK450", [("450", "natural"), ("450", "natural")]),
        ("Vekst på 23 % fra i fjor", [("23", "percent")]),
        ("Han hadde 3 barn", [("3", "small")]),
        ("Rapport fra 2023", [("2023", "year")]),
        ("I perioden 2019–2023 økte det", [("2019", "year"), ("2023", "year")]),
        ("Møtet 22.10.2024 kl. 14.30", [("22.10.2024", "date"), ("14.30", "time")]),
        ("Den 3. mars 2021 skjedde det", [("3", "date"), ("2021", "date")]),
        ("On October 22, 2024 at 10:15 am", [("22", "date"), ("2024", "date"), ("10", "time"), ("15", "time")]),
        ("Dato: 2024-10-22T08:30:00Z", [("2024", "date"), ("10", "date"), ("22", "date"), ("08", "date"), ("30", "date"), ("00", "date")]),
        ("Ring tlf 22 33 44 55", [("22", "phone"), ("33", "phone"), ("44", "phone"), ("55", "phone")]),
        ("Mobil: +47 412 34 567", [("47", "phone"), ("412", "phone"), ("34", "phone"), ("567", "phone")]),
        ("Call 555-123-4567 now", [("555", "phone"), ("123", "phone"), ("4567", "phone")]),
        ("Se side 12 og figur 3", [("12", "label"), ("3", "label")]),
        ("Jf. § 14 i loven", [("14", "label")]),
        ("Versjon 2.4.1 og IP 192.168.0.1", [("2.4.1", "version"), ("192.168.0.1", "version")]),
        ("Covid-19 og A4-papir og 5G", [("19", "code"), ("4", "code"), ("5", "code")]),
        ("Org.nr. 987654321", [("987654321", "label")]),
        ("Konto 12345678901", [("12345678901", "id")]),
        ("Kode 0150 og 98765432", [("0150", "id"), ("98765432", "id")]),
        ("Som vist [12] og [3, 4]", [("12", "citation"), ("3", "citation"), ("4", "citation")]),
        ("Se https://example.com/a/123 eller post@firma123.no", [("123", "url"), ("123", "url")]),
        ("ISBN 978-82-02-12345-6 er boka", [("978", "isbn"), ("82", "isbn"), ("02", "isbn"), ("12345", "isbn"), ("6", "isbn")]),
        ("Vi kom på 2nd place", [("2", "ordinal")]),
        ("Verdien er 0", [("0", "zero")]),
        ("Det tok 15 km og 10kg", [("15", "natural"), ("10", "natural")]),
        ("I 3. kvartal falt salget", [("3", "date")]),
    ],
)
def test_classification(text, expected):
    assert cats(text) == expected


def test_enumeration_and_headings():
    text = "1. Innledning\n2) Metode\n3.4 Resultater\n3.5 millioner brukere\n1.2.3 Del"
    assert cats(text) == [
        ("1", "enum"),
        ("2", "enum"),
        ("3.4", "enum"),
        ("1.2.3", "enum"),
        ("3.5", "natural"),
    ]


def test_page_numbers_only_in_page_mode():
    text = "Overskrift\nDet var 345 deltakere.\nSide 7 av 20"
    assert ("7", "page") in cats(text, page_mode=True)
    assert ("7", "label") in cats(text)


def test_space_thousands_off():
    assert cats("100 200 300", space_thousands=False) == [
        ("100", "natural"),
        ("200", "natural"),
        ("300", "natural"),
    ]


def test_drop_repeated_lines():
    pages = ["Firma AS 2024 rapport\nInnhold 15", "Firma AS 2024 rapport\nInnhold 27"]
    assert drop_repeated_lines(pages) == ["Firma AS 2024 rapport\nInnhold 15", "Innhold 27"]


def test_hhmm_times_need_a_neighbour():
    assert cats("17.30 Nyheter 18.00 Sport") == [("17.30", "time"), ("18.00", "time")]
    assert cats("Prisen var 12.50 i fjor") == [("12.50", "natural")]


def test_page_number_in_running_header():
    text = "Torsdag 16. juni 2022 37\nDet kom 450 personer."
    assert ("37", "page") in cats(text, page_mode=True, page_no=36)
