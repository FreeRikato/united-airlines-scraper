"""Scraper module for United Airlines Hemispheres travel data."""

import json
import re
from urllib.parse import urljoin
from playwright.sync_api import Page

# Configuration
BASE_URL = "https://www.united.com"
MAIN_URL = "https://www.united.com/en/us/hemispheres/places-to-go/index.html"

# URL patterns for filtering
# Only match actual articles, not index pages
ARTICLE_PATTERN = re.compile(
    r"/hemispheres/places-to-go/[^/]+/[^/]+/[^/]+\.html$"
)
# Exclude index pages
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
    # Exclude index pages (region/country listings)
    if INDEX_PATTERN.search(url):
        return False
    return bool(ARTICLE_PATTERN.search(url))


def extract_region_links(page: Page) -> list[str]:
    """Extract major region links from the main page."""
    urls = set()
    anchors = page.locator("a[href]")

    for i in range(anchors.count()):
        href = anchors.nth(i).get_attribute("href")
        if href and "/hemispheres/places-to-go/" in href:
            # Only get region index pages (e.g., /africa/index.html)
            # Pattern: /en/us/hemispheres/places-to-go/<region>/index.html
            if href.endswith("/index.html") and href.count("/") >= 6:
                full_url = urljoin(BASE_URL, href)
                if full_url != MAIN_URL:
                    urls.add(full_url)

    return sorted(urls)


def extract_article_links(page: Page) -> list[str]:
    """Extract valid article links from a region page."""
    urls = set()
    anchors = page.locator("a[href]")

    for i in range(anchors.count()):
        href = anchors.nth(i).get_attribute("href")
        if href:
            full_url = urljoin(BASE_URL, href)
            if is_valid_article(full_url):
                urls.add(full_url)

    return sorted(urls)


def parse_url_parts(url: str) -> dict[str, str]:
    """Parse region, country, and place from article URL."""
    parts = url.split("/")
    # URL structure: .../places-to-go/<region>/<country>/<place>.html
    region = parts[-4].replace("-", " ").title()
    country = parts[-3].replace("-", " ").title()
    place = parts[-2].replace("-", " ").title()
    return {"region": region, "country": country, "place": place}


def scrape_article(page: Page, url: str) -> dict | None:
    """Scrape structured data from an article page."""
    try:
        page.goto(url, timeout=120000, wait_until="domcontentloaded")
        page.wait_for_selector("h1", timeout=30000)

        # Extract title
        title = page.locator("h1").inner_text().strip()

        # Extract hero image
        hero_image = None
        hero_selectors = [
            "img[fetchpriority='high']",
            "article img",
            ".hero-image img",
            ".featured-image img"
        ]
        for selector in hero_selectors:
            if page.locator(selector).count() > 0:
                src = page.locator(selector).first.get_attribute("src")
                if src:
                    hero_image = src if src.startswith("http") else urljoin(BASE_URL, src)
                    break

        # Extract description/snippet (first meaningful paragraph)
        description = None
        desc_selectors = [
            "p.intro",
            ".deck",
            ".article-intro p",
            "article p",
            "main p"
        ]
        for selector in desc_selectors:
            if page.locator(selector).count() > 0:
                text = page.locator(selector).first.inner_text().strip()
                if len(text) > 50:  # Ensure it's meaningful content
                    description = text
                    break

        # Parse URL parts
        url_parts = parse_url_parts(url)

        return {
            "place_name": url_parts["place"],
            "article_title": title,
            "article_url": url,
            "hero_image": hero_image,
            "description": description or ""
        }

    except Exception as e:
        print(f"  [!] Error scraping {url}: {e}")
        return None


def load_checkpoint(checkpoint_file: str) -> dict:
    """Load checkpoint data if it exists."""
    try:
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"processed_urls": [], "countries_data": []}


def save_checkpoint(checkpoint_file: str, data: dict):
    """Save current progress to checkpoint file."""
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def aggregate_by_country(article_data: dict, countries_data: list) -> None:
    """Add article data to the appropriate country in the countries list."""
    url_parts = parse_url_parts(article_data["article_url"])

    # Find existing country entry
    country_entry = next(
        (c for c in countries_data
         if c["region"] == url_parts["region"] and c["country"] == url_parts["country"]),
        None
    )

    if country_entry:
        # Add destination to existing country
        country_entry["destinations"].append({
            "place_name": article_data["place_name"],
            "article_title": article_data["article_title"],
            "article_url": article_data["article_url"],
            "hero_image": article_data["hero_image"],
            "description": article_data["description"]
        })
    else:
        # Create new country entry
        countries_data.append({
            "region": url_parts["region"],
            "country": url_parts["country"],
            "destinations": [{
                "place_name": article_data["place_name"],
                "article_title": article_data["article_title"],
                "article_url": article_data["article_url"],
                "hero_image": article_data["hero_image"],
                "description": article_data["description"]
            }]
        })


def click_see_more(page: Page) -> bool:
    """Click 'See more' button if present to load more articles."""
    try:
        see_more = page.locator("button:has-text('See more'), a:has-text('See more'), button:has-text('Load more')")
        if see_more.count() > 0 and see_more.is_visible():
            see_more.first.click()
            page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    return False
