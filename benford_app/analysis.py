"""Run the number classifier over a set of documents and package the result
for the UI. Runs in the browser via Pyodide."""

from __future__ import annotations

import json

from .extract import CATEGORIES, DEFAULT_INCLUDED, classify_text, drop_repeated_lines

MAX_NUMBERS = 300_000
CAT_KEYS = list(CATEGORIES)


def analyse(docs: list[dict], opts: dict) -> dict:
    """docs: [{name, kind ("pdf"|"html"), depth, pages: [str], error}]"""
    # Flatten all pages so repeated lines are detected across pages and documents.
    flat = [(di, pi, page) for di, d in enumerate(docs) for pi, page in enumerate(d["pages"])]
    texts = [p for _, _, p in flat]
    if opts.get("drop_repeated", True):
        texts = drop_repeated_lines(texts)

    numbers: list[list] = []
    counts = [0] * len(docs)
    truncated = False
    for (di, pi, _), text in zip(flat, texts):
        is_pdf = docs[di]["kind"] == "pdf"
        for f in classify_text(
            text,
            page_mode=is_pdf,
            page_no=pi + 1 if is_pdf else None,
            space_thousands=opts.get("space_thousands", True),
        ):
            counts[di] += 1
            if len(numbers) < MAX_NUMBERS:
                numbers.append([f.digit, CAT_KEYS.index(f.category), di, f.raw, f.context])
            else:
                truncated = True

    return {
        "categories": [{"key": k, "label": v, "included": k in DEFAULT_INCLUDED} for k, v in CATEGORIES.items()],
        "sources": [
            {
                "name": d["name"],
                "kind": d["kind"],
                "depth": d.get("depth", 0),
                "pages": len(d["pages"]),
                "error": d.get("error"),
                "numbers": counts[i],
            }
            for i, d in enumerate(docs)
        ],
        "numbers": numbers,
        "truncated": truncated,
    }


def analyse_json(docs_json: str, opts_json: str) -> str:
    return json.dumps(analyse(json.loads(docs_json), json.loads(opts_json)), ensure_ascii=False)
