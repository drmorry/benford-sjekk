// Web Worker that runs the Python analysis code (benford_app/*.py) in Pyodide,
// so the page stays responsive while large documents are processed.
/* global importScripts, loadPyodide */
"use strict";

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.2/full/";
const PY_FILES = ["__init__.py", "extract.py", "analysis.py", "web.py"];

let pyPromise = null;

function init(baseUrl) {
  if (!pyPromise) {
    pyPromise = (async () => {
      importScripts(PYODIDE_URL + "pyodide.js");
      const py = await loadPyodide({ indexURL: PYODIDE_URL });
      await py.loadPackage(["beautifulsoup4"]);
      py.FS.mkdirTree("/app/benford_app");
      for (const f of PY_FILES) {
        const res = await fetch(new URL(`py/benford_app/${f}`, baseUrl));
        if (!res.ok) throw new Error(`Fant ikke ${f} (${res.status})`);
        py.FS.writeFile(`/app/benford_app/${f}`, await res.text());
      }
      py.runPython(`
import sys, json
sys.path.insert(0, "/app")
from benford_app.analysis import analyse_json
from benford_app.web import html_text_and_links, robots_allows

def html_json(html, url, strip):
    text, links = html_text_and_links(html, url, strip)
    return json.dumps([text, links])
`);
      return {
        analyse: py.globals.get("analyse_json"),
        html: py.globals.get("html_json"),
        robots: py.globals.get("robots_allows"),
      };
    })();
  }
  return pyPromise;
}

self.onmessage = async (e) => {
  const { id, fn, args } = e.data;
  try {
    let result;
    if (fn === "init") {
      await init(args[0]);
      result = true;
    } else {
      const py = await pyPromise;
      if (fn === "analyse") result = JSON.parse(py.analyse(args[0], args[1]));
      else if (fn === "html") result = JSON.parse(py.html(args[0], args[1], args[2]));
      else if (fn === "robots") result = py.robots(args[0], args[1]);
      else throw new Error("Ukjent funksjon " + fn);
    }
    self.postMessage({ id, result });
  } catch (err) {
    self.postMessage({ id, error: String(err && err.message ? err.message : err) });
  }
};
