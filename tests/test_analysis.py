from benford_app.analysis import analyse
from benford_app.web import html_text_and_links, robots_allows


def test_analyse_counts_per_source():
    docs = [
        {"name": "a.pdf", "kind": "pdf", "pages": ["Det var 450 personer\n3"], "error": None},
        {"name": "https://x.no", "kind": "html", "pages": ["Pris 1 200 kr i 2024"], "error": None},
    ]
    r = analyse(docs, {})
    assert [s["numbers"] for s in r["sources"]] == [2, 2]
    cats = [c["key"] for c in r["categories"]]
    assert [(n[3], cats[n[1]]) for n in r["numbers"]] == [
        ("3", "page"),
        ("450", "natural"),
        ("1 200", "natural"),
        ("2024", "year"),
    ]


def test_html_text_and_links():
    html = '<nav><a href="/meny">Meny 12</a></nav><main><p>Hei 345</p><a href="side#x">s</a></main><script>var a=9</script>'
    text, links = html_text_and_links(html, "https://x.no/a/", strip_boilerplate=True)
    assert "345" in text and "12" not in text and "9" not in text
    assert links == ["https://x.no/a/side", "https://x.no/meny"]


def test_robots():
    assert not robots_allows("User-agent: *\nDisallow: /privat", "https://x.no/privat/a")
    assert robots_allows("User-agent: *\nDisallow: /privat", "https://x.no/offentlig")
