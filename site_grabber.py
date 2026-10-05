"""
site_grabber.py - A configurable web page metadata and download link scraper.
Designed ONLY for extracting metadata and verified download links from your own website.

Usage:
    python site_grabber.py https://my-own-site.com/movie-page --config data/scraper_config.json
    python site_grabber.py https://my-own-site.com/movie-page   # uses DEFAULT_SELECTORS

Requirements:
    requests, beautifulsoup4
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = "SiteGrabber/1.0 (personal project; MoviesHub own site importer)"
TIMEOUT = 15

# Default CSS selectors - can be overridden via config JSON
DEFAULT_SELECTORS = {
    "title": "h1, .movie-title, meta[property='og:title']",
    "poster_url": "img.poster, .poster img, meta[property='og:image']",
    "release_year": ".year, .release-year, meta[property='og:release_date']",
    "genre": ".genre a, .genres a, .genre",
    "description": ".plot, .description, meta[name='description'], meta[property='og:description']",
    "download_link": "a[href*='download'], a.download-btn, a.download, .download-link a, a[download], a[href*='/download/']",
}


def allowed_by_robots(url: str) -> bool:
    """Return True if robots.txt allows fetching this URL."""
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        # If robots.txt can't be reached or read, default to allowing own site
        return True


def fetch_html(url: str, retries: int = 3) -> str | None:
    """Download a page with retries and HTTP error handling."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.HTTPError as e:
            print(f"[HTTP error] {e}", file=sys.stderr)
            if resp.status_code in (403, 404):
                return None
        except requests.exceptions.RequestException as e:
            print(f"[Request error] attempt {attempt}: {e}", file=sys.stderr)
        time.sleep(1.5 * attempt)
    return None


def extract_one(soup: BeautifulSoup, selector: str, base_url: str, attr: str | None = None):
    """Return text or attribute of the first element matching selector."""
    if not selector:
        return None
    el = soup.select_one(selector)
    if el is None:
        return None
    if el.name == "meta":
        return el.get("content")
    if el.name == "img":
        src = el.get("src") or el.get("data-src") or el.get("data-original")
        return urljoin(base_url, src) if src else None
    if attr:
        val = el.get(attr)
        return urljoin(base_url, val) if val and attr == "href" else val
    return el.get_text(strip=True) or None


def extract_many(soup: BeautifulSoup, selector: str) -> list[str]:
    """Return list of text elements matching selector."""
    if not selector:
        return []
    items = []
    for e in soup.select(selector):
        txt = e.get_text(strip=True)
        if txt and txt not in items:
            items.append(txt)
    return items


def extract_download_url(soup: BeautifulSoup, base_url: str, selector: str | None = None) -> str | None:
    """
    Carefully inspect page structure to detect genuine movie download link.
    Does NOT guess randomly. Only returns if verified by selector, class, or href pattern.
    """
    # 1. Configured CSS selector
    if selector:
        candidate = soup.select_one(selector)
        if candidate and candidate.get("href"):
            href = candidate.get("href", "").strip()
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                return urljoin(base_url, href)

    # 2. Inspect anchor tags by text and href patterns
    patterns = [
        re.compile(r"download", re.IGNORECASE),
        re.compile(r"get\s+movie", re.IGNORECASE),
        re.compile(r"direct\s+link", re.IGNORECASE),
        re.compile(r"1080p|720p|hevc|mkv|mp4", re.IGNORECASE),
    ]

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        classes = " ".join(a.get("class", []))

        # Ignore anchor jumps and scripts
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue

        # Check classes or attributes
        if "download" in classes.lower() or a.has_attr("download"):
            return urljoin(base_url, href)

        # Check href pattern
        if "/download/" in href.lower() or href.lower().endswith((".mp4", ".mkv", ".zip")):
            return urljoin(base_url, href)

        # Check anchor text
        for p in patterns:
            if p.search(text) and ("watch" not in text.lower() and "trailer" not in text.lower()):
                return urljoin(base_url, href)

    return None


def scrape(url: str, selectors: dict) -> dict:
    """Scrape one page and return a structured dictionary."""
    if not allowed_by_robots(url):
        raise PermissionError("robots.txt disallows scraping this URL.")

    html = fetch_html(url)
    if html is None:
        raise RuntimeError("Could not download the page.")

    soup = BeautifulSoup(html, "html.parser")

    title = extract_one(soup, selectors.get("title", ""), url)
    poster_url = extract_one(soup, selectors.get("poster_url", ""), url)
    release_year = extract_one(soup, selectors.get("release_year", ""), url)
    genre = extract_many(soup, selectors.get("genre", ""))
    description = extract_one(soup, selectors.get("description", ""), url)
    download_url = extract_download_url(soup, url, selectors.get("download_link"))

    # Cleanup year if it contains extra text like 'Release: 2026'
    if release_year:
        m = re.search(r"\b(19\d\d|20\d\d)\b", release_year)
        if m:
            release_year = m.group(1)

    return {
        "source_url": url,
        "title": title,
        "poster_url": poster_url,
        "release_year": release_year,
        "genre": genre,
        "description": description,
        "download_url": download_url,
    }


def main():
    parser = argparse.ArgumentParser(description="Configurable page metadata and download scraper")
    parser.add_argument("url", help="Page URL on your own website to scrape")
    parser.add_argument("--config", help="JSON file with CSS selectors")
    parser.add_argument("--out", default="output.json", help="Output JSON file")
    args = parser.parse_args()

    selectors = dict(DEFAULT_SELECTORS)
    if args.config:
        try:
            with open(args.config, encoding="utf-8") as f:
                selectors.update(json.load(f))
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"Config error: {e}")

    try:
        data = scrape(args.url, selectors)
    except (PermissionError, RuntimeError) as e:
        sys.exit(f"Error: {e}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
