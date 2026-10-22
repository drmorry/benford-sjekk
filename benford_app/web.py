"""HTML text extraction and robots.txt checks for the crawler (which runs in
the browser; this module is loaded into Pyodide)."""

from __future__ import annotations

import re
import urllib.robotparser
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup

USER_AGENT = "BenfordSjekk/1.0"


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


def robots_allows(robots_txt: str, url: str) -> bool:
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return rp.can_fetch(USER_AGENT, url)
