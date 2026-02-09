"""
web_reader.py – Production-grade web scraper with smart extraction & chunking.

Upgrades:
  • Extracts main article content, strips boilerplate (nav, sidebar, ads).
  • Preserves heading hierarchy as context for each chunk.
  • Sentence-aware overlapping chunker (delegates to file_loader.chunk_text).
  • Retry with back-off on transient HTTP errors.
  • Optional recursive link following (same-domain only).
"""

import re
import time
import logging
from urllib.parse import urljoin, urlparse
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .file_loader import chunk_text

logger = logging.getLogger("memloop.web_reader")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Tags that are almost never useful content
_NOISE_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "form", "button", "iframe", "noscript", "svg", "figure",
    "figcaption", "menu", "menuitem",
]

_NOISE_CLASSES = re.compile(
    r"sidebar|widget|breadcrumb|pagination|comment|share|social|"
    r"advertisement|ad-|related|newsletter|popup|modal|cookie|banner",
    re.IGNORECASE,
)


# ── Public API ────────────────────────────────────────────

def crawl_and_extract(
    url: str,
    chunk_size: int = 800,
    overlap: int = 150,
    max_retries: int = 3,
    follow_links: bool = False,
    max_pages: int = 10,
    timeout: int = 20,
) -> list[str]:
    """
    Scrape *url*, extract article content, and return overlapping text chunks.

    When *follow_links* is True, the scraper will also crawl same-domain
    links found on the page (up to *max_pages* total).
    """
    visited: set[str] = set()
    all_chunks: list[str] = []
    queue = [url]

    while queue and len(visited) < max_pages:
        current_url = queue.pop(0)
        normalised = _normalise_url(current_url)
        if normalised in visited:
            continue
        visited.add(normalised)

        html = _fetch_html(current_url, max_retries=max_retries, timeout=timeout)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Discover same-domain links before cleaning the tree
        if follow_links:
            for link in _extract_links(soup, current_url):
                norm_link = _normalise_url(link)
                if norm_link not in visited:
                    queue.append(link)

        text = _extract_content(soup, current_url)
        if not text.strip():
            continue

        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        all_chunks.extend(chunks)

    logger.info(
        "Scraped %d page(s) from %s → %d chunks", len(visited), url, len(all_chunks)
    )
    return all_chunks


# ── Internals ─────────────────────────────────────────────

def _fetch_html(
    url: str,
    max_retries: int = 3,
    timeout: int = 20,
) -> Optional[str]:
    """GET the URL with exponential back-off on transient errors."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = 2 ** attempt
                logger.warning("HTTP %d for %s – retrying in %ds", status, url, wait)
                time.sleep(wait)
                continue
            logger.warning("HTTP error fetching %s: %s", url, e)
            return None
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            logger.warning("Request failed for %s: %s", url, e)
            return None
    return None


def _extract_content(soup: BeautifulSoup, url: str) -> str:
    """
    Extract the main textual content from *soup*.

    Strategy:
      1. Remove noise tags and noisy class/id elements.
      2. Prefer <article> or <main> if present.
      3. Fall back to <body>.
      4. Preserve heading hierarchy as inline markers for context.
    """
    # 1. Strip noise
    for tag_name in _NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Remove elements whose class or id match common noise patterns
    for el in list(soup.find_all(True)):
        try:
            classes = " ".join(el.get("class", []) or [])
            el_id = el.get("id", "") or ""
            if _NOISE_CLASSES.search(classes) or _NOISE_CLASSES.search(el_id):
                el.decompose()
        except (AttributeError, TypeError):
            continue

    # 2. Find the best content container
    main = soup.find("article") or soup.find("main") or soup.find("body")
    if not main:
        return ""

    # 3. Walk the tree and build structured text
    lines: list[str] = []
    for element in main.descendants:
        if isinstance(element, Tag):
            if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                heading_text = element.get_text(strip=True)
                if heading_text:
                    level = element.name  # e.g. "h2"
                    lines.append(f"\n[{level.upper()}] {heading_text}\n")
        elif element.string:
            text = element.string.strip()
            if text and len(text) > 1:
                lines.append(text)

    # Deduplicate consecutive identical lines (common in scraped HTML)
    deduped: list[str] = []
    for line in lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    return "\n".join(deduped)


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Return all same-domain absolute URLs found in the page."""
    base_domain = urlparse(base_url).netloc
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
            # Skip anchors, media, etc.
            if not parsed.path.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".pdf")):
                links.append(absolute)
    return links


def _normalise_url(url: str) -> str:
    """Strip fragment and trailing slash for dedup purposes."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"