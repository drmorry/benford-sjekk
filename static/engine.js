// Everything that used to need a server, now in the browser:
// PDF text via pdf.js, website crawling via fetch (through a CORS proxy),
// and number classification via Python in Pyodide (py-worker.js).

const PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/";
const PROXY_KEY = "benford.proxy";
const MAX_BYTES = 25 * 1024 * 1024;
const SKIP_EXT = /\.(?:jpe?g|png|gif|webp|svg|ico|bmp|tiff?|mp[34]|m4a|wav|ogg|webm|avi|mov|zip|gz|tgz|rar|7z|exe|msi|dmg|iso|css|js|json|xml|rss|woff2?|ttf|eot|docx?|xlsx?|pptx?|odt|ods|csv)$/i;

// ------------------------------------------------------------ Python worker

const worker = new Worker(new URL("py-worker.js", import.meta.url));
const pending = new Map();
let nextId = 0;
worker.onmessage = (e) => {
  const { id, result, error } = e.data;
  const p = pending.get(id);
  pending.delete(id);
  error ? p.reject(new Error(error)) : p.resolve(result);
};
function call(fn, ...args) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, fn, args });
  });
}

let ready = null;
export function loadEngine() {
  if (!ready) ready = call("init", new URL(".", location.href).href);
  return ready;
}

export async function analyse(docs, opts) {
  await loadEngine();
  return call("analyse", JSON.stringify(docs), JSON.stringify(opts));
}

// ------------------------------------------------------------ PDF

let pdfjs = null;
async function loadPdfjs() {
  if (!pdfjs) {
    pdfjs = await import(PDFJS + "pdf.min.mjs");
    pdfjs.GlobalWorkerOptions.workerSrc = PDFJS + "pdf.worker.min.mjs";
  }
  return pdfjs;
}

// Rebuild lines from pdf.js text items, so the line-based heuristics
// (page numbers, numbering) work as they did with pypdf.
export async function pdfPages(data) {
  const lib = await loadPdfjs();
  const doc = await lib.getDocument({ data, isEvalSupported: false }).promise;
  const pages = [];
  for (let i = 1; i <= doc.numPages; i++) {
    try {
      const page = await doc.getPage(i);
      const tc = await page.getTextContent();
      let out = "", lastY = null, lastEnd = null;
      for (const it of tc.items) {
        if (!("str" in it)) continue;
        const [, , , , x, y] = it.transform;
        const h = Math.abs(it.transform[3]) || 10;
        if (lastY !== null && Math.abs(y - lastY) > h * 0.5) {
          if (!out.endsWith("\n")) out += "\n";
        } else if (lastEnd !== null && x - lastEnd > h * 0.15 && !/\s$/.test(out) && !/^\s/.test(it.str)) {
          out += " ";
        }
        out += it.str;
        if (it.hasEOL) out += "\n";
        lastY = y;
        lastEnd = x + (it.width || 0);
      }
      pages.push(out);
      page.cleanup();
    } catch {
      pages.push(""); // a broken page shouldn't stop the rest
    }
  }
  await doc.destroy();
  return pages;
}

// ------------------------------------------------------------ fetching

const isLocal = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);

export function getProxy() {
  try {
    const saved = localStorage.getItem(PROXY_KEY);
    if (saved !== null) return saved;
  } catch { /* storage unavailable */ }
  return isLocal ? "proxy?url={url}" : "";
}
export function setProxy(v) {
  try { localStorage.setItem(PROXY_KEY, v); } catch { /* ignore */ }
}

async function get(url) {
  const tmpl = getProxy().trim();
  const target = tmpl
    ? (tmpl.includes("{url}") ? tmpl.replace("{url}", encodeURIComponent(url)) : tmpl + url)
    : url;
  let res;
  try {
    res = await fetch(new URL(target, location.href), { signal: AbortSignal.timeout(20000) });
  } catch (err) {
    if (err.name === "TimeoutError") throw new Error("Tidsavbrudd");
    throw new Error(tmpl ? "Proxyen svarte ikke" : "Blokkert av nettleseren (CORS) – sett opp en proxy");
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  if (buf.byteLength > MAX_BYTES) throw new Error("For stor (> 25 MB)");
  return {
    buf,
    ctype: (res.headers.get("Content-Type") || "").toLowerCase(),
    finalUrl: res.headers.get("X-Final-URL") || url,
  };
}

function decode(buf, ctype) {
  const head = new TextDecoder("latin1").decode(buf.slice(0, 2048));
  const cs = (ctype.match(/charset=([\w-]+)/) || head.match(/<meta[^>]+charset=["']?([\w-]+)/i) || [])[1];
  try { return new TextDecoder(cs || "utf-8").decode(buf); } catch { return new TextDecoder("utf-8").decode(buf); }
}

const host = (u) => new URL(u).hostname.toLowerCase().replace(/^www\./, "");

// ------------------------------------------------------------ crawler

export async function crawl(startUrl, o, onProgress) {
  await loadEngine();
  if (!/^https?:\/\//i.test(startUrl)) startUrl = "https://" + startUrl;
  startUrl = startUrl.split("#")[0];
  const startHost = host(startUrl);
  const robotsCache = new Map();

  async function allowed(url) {
    if (!o.respectRobots) return true;
    const origin = new URL(url).origin;
    if (!robotsCache.has(origin)) {
      robotsCache.set(origin, get(origin + "/robots.txt").then((r) => decode(r.buf, r.ctype)).catch(() => null));
    }
    const txt = await robotsCache.get(origin);
    return txt === null || /<html/i.test(txt) ? true : call("robots", txt, url);
  }

  async function fetchDoc(url, depth) {
    const doc = { name: url, kind: "html", depth, pages: [], error: null, links: [] };
    try {
      if (!(await allowed(url))) throw new Error("Blokkert av robots.txt");
      const r = await get(url);
      const magic = new TextDecoder("latin1").decode(r.buf.slice(0, 5));
      if (r.ctype.includes("pdf") || magic === "%PDF-") {
        doc.kind = "pdf";
        if (!o.includePdfs && depth > 0) throw new Error("PDF hoppet over");
        doc.pages = await pdfPages(new Uint8Array(r.buf));
      } else if (r.ctype && !/html|xml/.test(r.ctype)) {
        throw new Error(`Ikke HTML (${r.ctype.split(";")[0]})`);
      } else {
        const [text, links] = await call("html", decode(r.buf, r.ctype), r.finalUrl, o.stripBoilerplate);
        doc.pages = [text];
        doc.links = links;
      }
    } catch (err) {
      doc.error = err.message;
    }
    return doc;
  }

  const docs = [];
  const seen = new Set([startUrl]);
  let frontier = [startUrl];
  for (let depth = 0; depth <= o.maxDepth && frontier.length && docs.length < o.maxPages; depth++) {
    const batch = frontier.slice(0, o.maxPages - docs.length);
    const results = new Array(batch.length);
    let next = 0;
    const runOne = async () => {
      while (next < batch.length) {
        const i = next++;
        results[i] = await fetchDoc(batch[i], depth);
        onProgress?.(docs.length + results.filter(Boolean).length, depth);
      }
    };
    await Promise.all(Array.from({ length: Math.min(6, batch.length) }, runOne));
    docs.push(...results);
    frontier = [];
    if (depth === o.maxDepth) break;
    for (const d of results) {
      for (const link of d.links) {
        if (seen.has(link)) continue;
        let u;
        try { u = new URL(link); } catch { continue; }
        if (SKIP_EXT.test(u.pathname)) continue;
        if (o.sameSite && host(link) !== startHost) continue;
        if (!o.includePdfs && /\.pdf$/i.test(u.pathname)) continue;
        seen.add(link);
        frontier.push(link);
      }
    }
  }
  return docs.map(({ links, ...d }) => d);
}
