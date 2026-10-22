"""Get text out of PDFs and websites."""

from __future__ import annotations

import io
import re
import urllib.robotparser
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

USER_AGENT = "BenfordSjekk/1.0 (+lokal analyseapp)"
MAX_BYTES = 25 * 1024 * 1024
TIMEOUT = 15

_SKIP_EXT = re.compile(
    r"\.(?:jpe?g|png|gif|webp|svg|ico|bmp|tiff?|mp[34]|m4a|wav|ogg|webm|avi|mov|"
    r"zip|gz|tgz|rar|7z|exe|msi|dmg|iso|css|js|json|xml|rss|woff2?|ttf|eot|"
    r"docx?|xlsx?|pptx?|odt|ods|csv)(?:$|\?)",
    re.I,
)


@dataclass
class Document:
    name: str  # file name or URL
    pages: list[str]  # text per page (a web page is a single "page")
    kind: str  # "pdf" | "html"
    depth: int = 0
    error: str | None = None
    links: list[str] = field(default_factory=list)


def pdf_pages(data: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise ValueError("PDF-en er kryptert") from exc
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 – a broken page shouldn't stop the rest
            pages.append("")
    return pages


def html_text_and_links(html: str, base_url: str, strip_boilerplate: bool) -> tuple[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    base = soup.find("base", href=True)
    if base:
        base_url = urljoin(base_url, base["href"])
    # Links in the main content first, then navigation/footer links, so a
    # small page budget is spent on content pages rather than menus.
    content_links, nav_links = [], []
    for a in soup.find_all("a", href=True):
        href = urldefrag(urljoin(base_url, a["href"].strip()))[0]
        if href.startswith(("http://", "https://")):
            in_nav = a.find_parent(["nav", "header", "footer", "aside"]) is not None
            (nav_links if in_nav else content_links).append(href)
    links = list(dict.fromkeys(content_links + nav_links))
    drop = ["script", "style", "noscript", "template", "svg", "head", "iframe", "code", "pre"]
    if strip_boilerplate:
        drop += ["nav", "header", "footer", "aside", "form"]
    for tag in soup(drop):
        tag.decompose()
    # Block elements become line breaks so line-based heuristics work.
    text = soup.get_text("\n")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip(), links


def _host(url: str) -> str:
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


class Crawler:
    def __init__(
        self,
        start_url: str,
        max_depth: int = 1,
        max_pages: int = 20,
        same_site: bool = True,
        include_pdfs: bool = True,
        respect_robots: bool = True,
        strip_boilerplate: bool = True,
    ):
        if not re.match(r"https?://", start_url, re.I):
            start_url = "https://" + start_url
        self.start_url = urldefrag(start_url)[0]
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.same_site = same_site
        self.include_pdfs = include_pdfs
        self.respect_robots = respect_robots
        self.strip_boilerplate = strip_boilerplate
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session.get(root + "/robots.txt", timeout=TIMEOUT)
                if r.status_code >= 400:
                    rp = None
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp = None
            self._robots[root] = rp
        rp = self._robots[root]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    def _fetch(self, url: str, depth: int) -> Document:
        if not self._allowed(url):
            return Document(url, [], "html", depth, "Blokkert av robots.txt")
        try:
            r = self.session.get(url, timeout=TIMEOUT, stream=True)
            r.raise_for_status()
            data = b""
            for chunk in r.iter_content(64 * 1024):
                data += chunk
                if len(data) > MAX_BYTES:
                    return Document(url, [], "html", depth, "For stor (> 25 MB)")
            ctype = r.headers.get("Content-Type", "").lower()
            final_url = r.url
        except requests.RequestException as exc:
            return Document(url, [], "html", depth, f"Feil ved henting: {exc.__class__.__name__}")

        if "pdf" in ctype or data[:5] == b"%PDF-":
            if not self.include_pdfs and depth > 0:
                return Document(url, [], "pdf", depth, "PDF hoppet over")
            try:
                return Document(url, pdf_pages(data), "pdf", depth)
            except Exception as exc:  # noqa: BLE001
                return Document(url, [], "pdf", depth, f"Kunne ikke lese PDF: {exc}")
        if "html" not in ctype and "xml" not in ctype and ctype:
            return Document(url, [], "html", depth, f"Ikke HTML ({ctype.split(';')[0]})")
        html = data.decode(r.encoding or r.apparent_encoding or "utf-8", errors="replace")
        text, links = html_text_and_links(html, final_url, self.strip_boilerplate)
        return Document(url, [text], "html", depth, links=links)

    def crawl(self) -> list[Document]:
        start_host = _host(self.start_url)
        seen = {self.start_url}
        frontier = deque([self.start_url])
        docs: list[Document] = []
        depth = 0
        with ThreadPoolExecutor(max_workers=6) as pool:
            while frontier and len(docs) < self.max_pages and depth <= self.max_depth:
                batch = [frontier.popleft() for _ in range(min(len(frontier), self.max_pages - len(docs)))]
                frontier.clear()
                results = list(pool.map(lambda u: self._fetch(u, depth), batch))
                docs.extend(results)
                if depth == self.max_depth:
                    break
                for doc in results:
                    for link in doc.links:
                        if link in seen or _SKIP_EXT.search(urlparse(link).path):
                            continue
                        if self.same_site and _host(link) != start_host:
                            continue
                        if not self.include_pdfs and link.lower().endswith(".pdf"):
                            continue
                        seen.add(link)
                        frontier.append(link)
                depth += 1
        return docs
