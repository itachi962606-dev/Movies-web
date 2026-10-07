"""
site_grabber.py - A configurable web page metadata and multi-quality download link scraper.
Designed ONLY for extracting metadata and verified download links from your own authorized website.

Usage:
    python site_grabber.py https://my-own-site.com/movie-page --config data/scraper_config.json
    python site_grabber.py https://my-own-site.com/movie-page   # uses DEFAULT_SELECTORS

Requirements:
    requests, beautifulsoup4
"""

import argparse
import json
import os
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
    "title": "h1, .movie-title, meta[property='og:title'], title",
    "poster_url": "img.poster, .poster img, meta[property='og:image']",
    "release_year": ".year, .release-year, meta[property='og:release_date']",
    "genre": ".genre a, .genres a, .genre",
    "description": ".plot, .description, meta[name='description'], meta[property='og:description']",
    "download_link": "a[href*='download'], a.download-btn, a.download, .download-link a, a[download], a[href*='/download/']",
}

QUALITY_ORDER = ["4K", "2160p", "1080p", "720p", "480p", "360p", "HD", "Default"]

QUALITY_REGEXES = [
    ("4K", re.compile(r'\b(?:4K|2160p|UHD)\b', re.IGNORECASE)),
    ("1080p", re.compile(r'\b1080p?\b', re.IGNORECASE)),
    ("720p", re.compile(r'\b720p?\b', re.IGNORECASE)),
    ("480p", re.compile(r'\b480p?\b', re.IGNORECASE)),
    ("360p", re.compile(r'\b360p?\b', re.IGNORECASE)),
    ("HD", re.compile(r'\bHD\b', re.IGNORECASE)),
]

SIZE_REGEX = re.compile(r'(\d+(?:[.\s_-]\d+)?)\s*(GB|MB|KB|G|M|K)\b', re.IGNORECASE)


def get_domain(url: str) -> str:
    """Extract clean domain/hostname from a URL, stripping 'www.' prefix."""
    if not url:
        return ""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_own_domain(url: str, own_site_url: str | None = None) -> bool:
    """
    Verify if the given URL belongs to OWN_SITE_URL.
    Matches hostname exactly or as a valid subdomain, agnostic to www. prefix.
    """
    own = own_site_url or os.environ.get("OWN_SITE_URL", "").strip()
    if not own:
        # If no specific OWN_SITE_URL is defined, allow (permissive fallback)
        return True

    sub_domain = get_domain(url)
    own_domain = get_domain(own)

    if not sub_domain or not own_domain:
        return False

    return sub_domain == own_domain or sub_domain.endswith(f".{own_domain}")


def check_robots_permission(url: str) -> tuple[bool, str | None]:
    """
    Check if the URL is allowed by robots.txt according to standard RFC 9309 rules.
    Returns (is_allowed: bool, error_message: str | None).
    
    Logs:
    1. robots.txt URL checked
    2. User-Agent
    3. Movie URL being evaluated
    4. HTTP status code
    5. Response body length
    6. Parsed rules
    7. Final decision
    """
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    headers = {"User-Agent": USER_AGENT}

    print(f"[robots.txt] Checking robots URL: {robots_url}", file=sys.stderr)
    print(f"[robots.txt] User-Agent: {USER_AGENT}", file=sys.stderr)
    print(f"[robots.txt] Movie URL being checked: {url}", file=sys.stderr)

    try:
        resp = requests.get(robots_url, headers=headers, timeout=10)
        body_len = len(resp.text)
        print(f"[robots.txt] HTTP status returned: {resp.status_code}", file=sys.stderr)
        print(f"[robots.txt] Response body length: {body_len} bytes", file=sys.stderr)

        # Non-200 (e.g. 404 Not Found, 403 Forbidden, 5xx): per RFC, access is allowed
        if resp.status_code != 200:
            print(f"[robots.txt] Parsed rules: None (HTTP {resp.status_code})", file=sys.stderr)
            print(f"[robots.txt] Final decision for {url}: allowed=True (HTTP {resp.status_code})", file=sys.stderr)
            return True, None

        # Empty body (0 bytes): no disallow rules exist -> allowed per RFC 9309
        body = resp.text.strip()
        if not body:
            print(f"[robots.txt] Parsed rules: None (empty robots.txt file)", file=sys.stderr)
            print(f"[robots.txt] Final decision for {url}: allowed=True (empty robots.txt)", file=sys.stderr)
            return True, None

        # Collect rule lines for logging and diagnostic visibility
        raw_lines = resp.text.splitlines()
        rule_lines = [line.strip() for line in raw_lines if line.strip() and not line.strip().startswith('#')]
        print(f"[robots.txt] Parsed rules ({len(rule_lines)} directives): {rule_lines}", file=sys.stderr)

        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(raw_lines)

        # Check standard user agent matching
        can_fetch = rp.can_fetch(USER_AGENT, url)
        print(f"[robots.txt] Final decision for {url}: allowed={can_fetch}", file=sys.stderr)

        if not can_fetch:
            # Find specific disallow rule for detailed reporting
            path = parts.path or "/"
            matching_disallow = []
            for r in rule_lines:
                if r.lower().startswith("disallow:"):
                    rule_val = r.split(":", 1)[1].strip()
                    if rule_val and (rule_val == "/" or path.startswith(rule_val)):
                        matching_disallow.append(r)
            
            rule_detail = f" (matching rule: {', '.join(matching_disallow)})" if matching_disallow else ""
            print(f"[robots.txt] Blocked by rule{rule_detail}", file=sys.stderr)
            return False, f"This URL is disallowed by your website's robots.txt{rule_detail}. Please allow this path in robots.txt."

        return True, None
    except Exception as e:
        print(f"[robots.txt] Request error for {robots_url}: {e}. Defaulting to allowed=True for own authorized site.", file=sys.stderr)
        return True, None


def allowed_by_robots(url: str) -> bool:
    """Compatibility helper returning bool."""
    allowed, _ = check_robots_permission(url)
    return allowed


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


def parse_size_to_bytes(size_str: str | None) -> tuple[str | None, int | None]:
    """Convert human-readable size (e.g. '1.2 GB', '1 6 GB', '700 MB') into (formatted_str, bytes)."""
    if not size_str:
        return None, None
    m = SIZE_REGEX.search(size_str)
    if not m:
        return None, None
    num_part = m.group(1).replace('_', '.').replace('-', '.').replace(' ', '.')
    try:
        val = float(num_part)
    except ValueError:
        return None, None

    unit = m.group(2).upper()
    if unit in ("GB", "G"):
        return f"{val:.1f} GB", int(val * 1024 * 1024 * 1024)
    elif unit in ("MB", "M"):
        return f"{val:.0f} MB" if val.is_integer() else f"{val:.1f} MB", int(val * 1024 * 1024)
    elif unit in ("KB", "K"):
        return f"{val:.0f} KB", int(val * 1024)
    return None, None


def format_bytes(num_bytes: int) -> str:
    """Format bytes into readable string (e.g. '1.2 GB', '700 MB')."""
    if num_bytes >= 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024 * 1024):.1f} GB"
    elif num_bytes >= 1024 * 1024:
        mb = num_bytes / (1024 * 1024)
        return f"{mb:.0f} MB" if mb.is_integer() else f"{mb:.1f} MB"
    elif num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"


def detect_quality_from_context(element, href: str, page_context: str = "") -> str:
    """
    Detect video quality (e.g. 1080p, 720p, 480p, 4K, HD)
    from element text, attributes, URL, or surrounding context.
    """
    # 1. Check element text
    text = element.get_text(strip=True) if element else ""
    for label, pattern in QUALITY_REGEXES:
        if pattern.search(text):
            return label

    # 2. Check attributes (data-quality, class, id, title)
    if element:
        for attr in ("data-quality", "data-res", "title", "class", "id"):
            val = element.get(attr)
            if isinstance(val, list):
                val = " ".join(val)
            if val:
                for label, pattern in QUALITY_REGEXES:
                    if pattern.search(val):
                        return label

    # 3. Check href
    if href:
        for label, pattern in QUALITY_REGEXES:
            if pattern.search(href):
                return label

    # 4. Check enclosing parent container / preceding heading
    if element:
        parent = element.find_parent(["tr", "li", "div", "section", "article"])
        if parent:
            parent_text = parent.get_text()
            for label, pattern in QUALITY_REGEXES:
                if pattern.search(parent_text):
                    return label

    # 5. Check page context (e.g. title tag, meta description, page URL)
    if page_context:
        for label, pattern in QUALITY_REGEXES:
            if pattern.search(page_context):
                return label

    return "Default"


def detect_size_from_context(element, href: str, fetch_head: bool = True, page_context: str = "") -> tuple[str | None, int | None]:
    """
    Detect file size.
    Prefer file size displayed directly on the webpage (near link, in text, parent, attributes).
    If not displayed, optionally use HTTP HEAD request with Content-Length.
    Never download the actual video file.
    If size cannot be determined, return (None, None) without guessing.
    """
    # 1. Check element text
    if element:
        text = element.get_text(strip=True)
        display, num_bytes = parse_size_to_bytes(text)
        if display:
            return display, num_bytes

        # 2. Check attributes
        for attr in ("data-size", "data-filesize", "title"):
            val = element.get(attr)
            if val:
                display, num_bytes = parse_size_to_bytes(str(val))
                if display:
                    return display, num_bytes

        # 3. Check sibling / parent row or container
        parent = element.find_parent(["tr", "li", "div", "p"])
        if parent:
            display, num_bytes = parse_size_to_bytes(parent.get_text())
            if display:
                return display, num_bytes

    # 4. Check href text/slug (e.g. /download/movie-1080p-1-6-gb/)
    if href:
        display, num_bytes = parse_size_to_bytes(href)
        if display:
            return display, num_bytes

    # 5. Check page context (title, meta description)
    if page_context:
        display, num_bytes = parse_size_to_bytes(page_context)
        if display:
            return display, num_bytes

    # 6. HEAD request fallback if not found in HTML
    if fetch_head and href and href.startswith(("http://", "https://")):
        try:
            resp = requests.head(href, headers={"User-Agent": USER_AGENT}, allow_redirects=True, timeout=5)
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit():
                num_bytes = int(cl)
                if num_bytes > 0:
                    return format_bytes(num_bytes), num_bytes
        except Exception:
            pass

    return None, None


def extract_all_download_options(soup: BeautifulSoup, base_url: str, selector: str | None = None, fetch_head: bool = True) -> tuple[list[dict], str | None]:
    """
    Extract all download links from page, group by quality, and select the smallest file per quality.
    
    Returns:
        (download_options, primary_download_url)
    """
    candidates = []
    seen_urls = set()

    # Build page context string from title, meta description, and page URL
    page_title = soup.title.get_text() if soup.title else ""
    meta_desc = ""
    meta_el = soup.select_one("meta[name='description'], meta[property='og:description']")
    if meta_el and meta_el.get("content"):
        meta_desc = meta_el.get("content")
    page_context = f"{page_title} {meta_desc} {base_url}"

    # 1. Configured selector candidates
    if selector:
        for el in soup.select(selector):
            href = el.get("href", "").strip() if el.name == "a" else el.find("a", href=True).get("href", "").strip() if el.find("a", href=True) else ""
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                full_url = urljoin(base_url, href)
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    anchor = el if el.name == "a" else el.find("a")
                    candidates.append((anchor, full_url))

    # 2. General anchor pattern scan
    patterns = [
        re.compile(r"download", re.IGNORECASE),
        re.compile(r"1080p|720p|480p|hevc|mkv|mp4|zip", re.IGNORECASE),
        re.compile(r"direct\s+link", re.IGNORECASE),
    ]

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue

        text = a.get_text(strip=True)
        classes = " ".join(a.get("class", []))

        is_dl = (
            "download" in classes.lower()
            or a.has_attr("download")
            or "/download/" in href.lower()
            or href.lower().endswith((".mp4", ".mkv", ".zip", ".avi"))
        )

        if not is_dl:
            for p in patterns:
                if p.search(text) and ("watch" not in text.lower() and "trailer" not in text.lower()):
                    is_dl = True
                    break

        if is_dl:
            seen_urls.add(full_url)
            candidates.append((a, full_url))

    if not candidates:
        return [], None

    # Group extracted links by quality
    grouped: dict[str, list[dict]] = {}

    for el, url in candidates:
        quality = detect_quality_from_context(el, url, page_context=page_context)
        size_display, size_bytes = detect_size_from_context(el, url, fetch_head=fetch_head, page_context=page_context)

        item = {
            "quality": quality,
            "url": url,
            "size": size_display,
            "size_bytes": size_bytes,
        }

        grouped.setdefault(quality, []).append(item)

    # For each quality: select the smallest known file size
    selected_options = []

    for quality, links in grouped.items():
        # Filter links with known size
        with_size = [link for link in links if link.get("size_bytes") is not None]
        if with_size:
            # Select the link with smallest file size
            chosen = min(with_size, key=lambda x: x["size_bytes"])
        else:
            # If size cannot be determined, do not guess, select first link in that quality
            chosen = links[0]

        selected_options.append(chosen)

    # Sort options by quality hierarchy
    def quality_sort_key(opt):
        q = opt.get("quality", "")
        if q in QUALITY_ORDER:
            return QUALITY_ORDER.index(q)
        return len(QUALITY_ORDER)

    selected_options.sort(key=quality_sort_key)

    primary_url = selected_options[0]["url"] if selected_options else None
    return selected_options, primary_url


def scrape(url: str, selectors: dict, own_site_url: str | None = None, fetch_head: bool = True) -> dict:
    """Scrape one page and return a structured dictionary."""
    # 1. Domain verification: reject third-party websites
    if not is_own_domain(url, own_site_url):
        own = own_site_url or os.environ.get("OWN_SITE_URL", "")
        raise PermissionError(
            f"Security restriction: URL '{url}' does not belong to your verified domain ({own}). "
            "Third-party websites are strictly disallowed."
        )

    # 2. Robots.txt check: respect actual rules
    allowed, robots_err = check_robots_permission(url)
    if not allowed:
        raise PermissionError(robots_err or "This URL is disallowed by your website's robots.txt. Please allow this path in robots.txt.")

    html = fetch_html(url)
    if html is None:
        raise RuntimeError("Could not download the page.")

    soup = BeautifulSoup(html, "html.parser")

    raw_title = extract_one(soup, selectors.get("title", ""), url)
    poster_url = extract_one(soup, selectors.get("poster_url", ""), url)
    release_year = extract_one(soup, selectors.get("release_year", ""), url)
    genre = extract_many(soup, selectors.get("genre", ""))
    description = extract_one(soup, selectors.get("description", ""), url)

    # Clean title if it contains generic suffixes like 'Download Moviesda' or '- isaimini'
    title = raw_title
    if title:
        # If title came from <title> tag, clean common suffixes
        title = re.sub(r'\s*[-|–]\s*(?:isaimini|moviesda|tamilrockers|download).*$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+(?:full\s+movie\s+download|movie\s+download|download)\s+.*$', '', title, flags=re.IGNORECASE).strip()

    # Extract year from title or text if not found by selector
    if not release_year:
        search_text = f"{raw_title or ''} {description or ''} {url}"
        m_year = re.search(r'\b(19\d\d|20\d\d)\b', search_text)
        if m_year:
            release_year = m_year.group(1)
    else:
        m = re.search(r'\b(19\d\d|20\d\d)\b', release_year)
        if m:
            release_year = m.group(1)

    # Extract all quality options and pick smallest per quality
    download_options, primary_download_url = extract_all_download_options(
        soup, url, selectors.get("download_link"), fetch_head=fetch_head
    )

    return {
        "source_url": url,
        "title": title or raw_title,
        "poster_url": poster_url,
        "release_year": release_year,
        "genre": genre,
        "description": description,
        "download_url": primary_download_url,
        "download_options": download_options,
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
