"""Scraper using webReader MCP tool as fallback.

This module uses the webReader tool which runs on a different server
that isn't blocked by united.com's bot detection.
"""

import json
import re
import time
from urllib.parse import urljoin, urlparse

# Note: This would need to be adapted to use the actual webReader tool
# via the MCP interface. For now, this is a placeholder showing the structure.

BASE_URL = "https://www.united.com"
MAIN_URL = "https://www.united.com/en/us/hemispheres/places-to-go/index.html"

# URL patterns for filtering
ARTICLE_PATTERN = re.compile(
    r"/hemispheres/places-to-go/[^/]+/[^/]+/[^/]+\.html$"
)
INDEX_PATTERN = re.compile(r"/index\.html$")

BLOCKLIST = [
    "/nyt/",
    "/things-to-do/",
    "/stays/",
    "/food/",
    "/culture/"
]


def is_valid_article(url: str) -> bool:
    """Check if URL is a valid places-to-go article."""
    if any(bad in url for bad in BLOCKLIST):
        return False
    if INDEX_PATTERN.search(url):
        return False
    return bool(ARTICLE_PATTERN.search(url))


def parse_url_parts(url: str) -> dict[str, str]:
    """Parse region, country, and place from article URL."""
    parts = url.split("/")
    # URL structure: .../places-to-go/<region>/<country>/<place>.html
    region = parts[-4].replace("-", " ").title()
    country = parts[-3].replace("-", " ").title()
    place = parts[-2].replace("-", " ").title()
    return {"region": region, "country": country, "place": place}


def extract_links_from_html(html: str, base_url: str) -> list[str]:
    """Extract all href links from HTML content."""
    # Simple regex-based link extraction
    # In production, use BeautifulSoup
    pattern = r'href="(/[^"]*)"'
    links = re.findall(pattern, html)
    return [urljoin(base_url, link) for link in links]


def extract_region_links(html: str) -> list[str]:
    """Extract region links from main page HTML."""
    urls = set()
    pattern = r'href="(/en/us/hemispheres/places-to-go/[^/]+/index\.html)"'
    matches = re.findall(pattern, html)

    for match in matches:
        full_url = urljoin(BASE_URL, match)
        if full_url != MAIN_URL:
            urls.add(full_url)

    return sorted(urls)


def extract_article_links(html: str) -> list[str]:
    """Extract article links from region page HTML."""
    urls = set()
    pattern = r'href="(/en/us/hemispheres/places-to-go/[^"]+\.html)"'
    matches = re.findall(pattern, html)

    for match in matches:
        full_url = urljoin(BASE_URL, match)
        if is_valid_article(full_url):
            urls.add(full_url)

    return sorted(urls)


def scrape_article_from_html(html: str, url: str) -> dict | None:
    """Scrape article data from HTML content."""
    try:
        # Extract title (usually in h1 tag)
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Clean HTML entities and tags from title
        title = re.sub(r'<[^>]+>', '', title)
        title = title.replace('&nbsp;', ' ').replace('&amp;', '&').strip()

        # Extract hero image
        hero_image = None
        img_patterns = [
            r'<img[^>]*src="([^"]*)"[^>]*fetchpriority="high"',
            r'<img[^>]*src="([^"]*)"[^>]*class="[^"]*hero',
        ]
        for pattern in img_patterns:
            match = re.search(pattern, html)
            if match:
                hero_image = match.group(1)
                if not hero_image.startswith("http"):
                    hero_image = urljoin(BASE_URL, hero_image)
                break

        # Extract description (first paragraph with substantial content)
        desc_match = re.search(r'<p[^>]*class="[^"]*intro[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL)
        if not desc_match:
            desc_match = re.search(r'<p[^>]*>(.{100,500})</p>', html, re.DOTALL)

        description = ""
        if desc_match:
            description = desc_match.group(1).strip()
            description = re.sub(r'<[^>]+>', '', description)
            description = description.replace('&nbsp;', ' ').replace('&amp;', '&')
            description = ' '.join(description.split())  # Normalize whitespace

        # Parse URL parts
        url_parts = parse_url_parts(url)

        return {
            "place_name": url_parts["place"],
            "article_title": title,
            "article_url": url,
            "hero_image": hero_image,
            "description": description[:500] if description else ""  # Limit length
        }

    except Exception as e:
        print(f"  [!] Error parsing article {url}: {e}")
        return None
