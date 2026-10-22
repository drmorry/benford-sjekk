"""Local server for Benford-sjekk.

The app itself runs entirely in the browser (Pyodide + pdf.js), exactly as on
GitHub Pages. This server only serves the files and adds a CORS-free fetch
proxy at /proxy so website scanning works locally without a public proxy.

Run:  .venv\\Scripts\\python app.py   then open http://127.0.0.1:5000
"""

from __future__ import annotations

from pathlib import Path

import requests
from flask import Flask, Response, abort, request, send_from_directory

ROOT = Path(__file__).parent
MAX_BYTES = 25 * 1024 * 1024

app = Flask(__name__, static_folder="static", static_url_path="")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/py/<path:name>")
def python_source(name: str):
    # Same layout as the GitHub Pages build: /py/benford_app/*.py
    return send_from_directory(ROOT, name, mimetype="text/plain")


@app.get("/proxy")
def proxy():
    url = request.args.get("url", "")
    if not url.startswith(("http://", "https://")):
        abort(400)
    try:
        r = requests.get(url, timeout=15, stream=True, headers={"User-Agent": "BenfordSjekk/1.0"})
        data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    except requests.RequestException as exc:
        return Response(f"Feil ved henting: {exc.__class__.__name__}", status=502)
    if len(data) > MAX_BYTES:
        return Response("For stor (> 25 MB)", status=413)
    resp = Response(data, status=r.status_code, content_type=r.headers.get("Content-Type", "application/octet-stream"))
    resp.headers["X-Final-URL"] = r.url
    resp.headers["Access-Control-Expose-Headers"] = "X-Final-URL"
    return resp


if __name__ == "__main__":
    app.run(debug=False, port=5000)
