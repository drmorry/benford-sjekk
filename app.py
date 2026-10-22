"""Benford-sjekk: web app that tests the first-digit distribution of the
natural numbers in a PDF or website against Benford's law.

Run:  .venv\\Scripts\\python app.py   then open http://127.0.0.1:5000
"""

from __future__ import annotations

import json

from flask import Flask, jsonify, request, send_from_directory

from benford_app.extract import CATEGORIES, DEFAULT_INCLUDED, classify_text, drop_repeated_lines
from benford_app.sources import Crawler, Document, pdf_pages

MAX_NUMBERS = 300_000
CAT_KEYS = list(CATEGORIES)

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024


def _options() -> dict:
    raw = request.form.get("options") if request.form else None
    opts = json.loads(raw) if raw else (request.get_json(silent=True) or {})
    return {
        "drop_repeated": bool(opts.get("drop_repeated", True)),
        "space_thousands": bool(opts.get("space_thousands", True)),
    }


def analyse(docs: list[Document], opts: dict) -> dict:
    # Flatten all pages so repeated lines are detected across pages and documents.
    flat = [(di, pi, page) for di, d in enumerate(docs) for pi, page in enumerate(d.pages)]
    texts = [p for _, _, p in flat]
    if opts["drop_repeated"]:
        texts = drop_repeated_lines(texts)

    numbers: list[list] = []
    counts = [dict.fromkeys(CAT_KEYS, 0) for _ in docs]
    truncated = False
    for (di, pi, _), text in zip(flat, texts):
        is_pdf = docs[di].kind == "pdf"
        for f in classify_text(
            text,
            page_mode=is_pdf,
            page_no=pi + 1 if is_pdf else None,
            space_thousands=opts["space_thousands"],
        ):
            counts[di][f.category] += 1
            if len(numbers) < MAX_NUMBERS:
                numbers.append([f.digit, CAT_KEYS.index(f.category), di, f.raw, f.context])
            else:
                truncated = True

    return {
        "categories": [{"key": k, "label": v, "included": k in DEFAULT_INCLUDED} for k, v in CATEGORIES.items()],
        "sources": [
            {
                "name": d.name,
                "kind": d.kind,
                "depth": d.depth,
                "pages": len(d.pages),
                "error": d.error,
                "numbers": sum(counts[i].values()),
            }
            for i, d in enumerate(docs)
        ],
        "numbers": numbers,
        "truncated": truncated,
    }


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/pdf")
def api_pdf():
    files = request.files.getlist("file")
    if not files:
        return jsonify(error="Ingen fil mottatt"), 400
    docs = []
    for f in files:
        try:
            docs.append(Document(f.filename or "dokument.pdf", pdf_pages(f.read()), "pdf"))
        except Exception as exc:  # noqa: BLE001
            docs.append(Document(f.filename or "dokument.pdf", [], "pdf", error=f"Kunne ikke lese PDF: {exc}"))
    return jsonify(analyse(docs, _options()))


@app.post("/api/url")
def api_url():
    body = request.get_json(force=True)
    url = (body.get("url") or "").strip()
    if not url:
        return jsonify(error="Mangler URL"), 400
    crawler = Crawler(
        url,
        max_depth=max(0, min(int(body.get("max_depth", 1)), 5)),
        max_pages=max(1, min(int(body.get("max_pages", 20)), 500)),
        same_site=bool(body.get("same_site", True)),
        include_pdfs=bool(body.get("include_pdfs", True)),
        respect_robots=bool(body.get("respect_robots", True)),
        strip_boilerplate=bool(body.get("strip_boilerplate", True)),
    )
    docs = crawler.crawl()
    return jsonify(analyse(docs, _options()))


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="Filen er for stor (maks 200 MB)"), 413


if __name__ == "__main__":
    app.run(debug=False, port=5000)
