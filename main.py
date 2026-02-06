"""United Airlines Hemispheres travel data scraper."""

import json
import sys
import time
from playwright.sync_api import sync_playwright

from scraper import (
    BASE_URL,
    MAIN_URL,
    extract_region_links,
    extract_article_links,
    scrape_article,
    load_checkpoint,
    save_checkpoint,
    aggregate_by_country,
    click_see_more
)


def handle_cookie_banner(page):
    """Try to dismiss cookie consent banners."""
    try:
        # Try common cookie banner selectors
        cookie_selectors = [
            'button:has-text("Accept")',
            'button:has-text("Accept cookies")',
            'button:has-text("Accept all")',
            '.cookie-banner button',
            '#onetrust-accept-btn-handler',
            '.accept-cookies'
        ]
        for selector in cookie_selectors:
            if page.locator(selector).count() > 0:
                try:
                    page.locator(selector).first.click(timeout=5000)
                    print(f"  Clicked cookie banner: {selector}", flush=True)
                    time.sleep(1)
                    return
                except:
                    pass
    except:
        pass

CHECKPOINT_FILE = "checkpoint.json"
OUTPUT_FILE = "places_to_go.json"


def main():
    """Main scraper entry point."""
    # Load existing checkpoint
    checkpoint = load_checkpoint(CHECKPOINT_FILE)
    processed_urls = set(checkpoint.get("processed_urls", []))
    countries_data = checkpoint.get("countries_data", [])

    print(f"Starting scraper...", flush=True)
    print(f"  Previously processed: {len(processed_urls)} articles", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Try non-headless to avoid bot detection
            args=[
                '--disable-blink-features=AutomationControlled',
            ]
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()

        # Navigate to main page
        print(f"\nVisiting main page: {MAIN_URL}", flush=True)
        page.goto(MAIN_URL, timeout=120000, wait_until="domcontentloaded")
        page.wait_for_load_state("domcontentloaded", timeout=120000)
        print(f"  Waiting for dynamic content to load...", flush=True)
        time.sleep(10)  # Wait longer for dynamic content to load

        # Handle cookie banner if present
        handle_cookie_banner(page)

        # Extract region links
        region_links = extract_region_links(page)
        print(f"Found {len(region_links)} regions", flush=True)

        for i, region_url in enumerate(region_links):
            # Add significant delay between regions to avoid rate limiting
            if i > 0:
                delay = 30 + ((i * 10) % 30)  # Varying delays: 30-60 seconds
                print(f"  Waiting {delay}s before next region to avoid rate limiting...", flush=True)
                time.sleep(delay)
            region_name = region_url.split("/")[-2].replace("-", " ").title()
            print(f"\n{'='*60}", flush=True)
            print(f"Processing region: {region_name}", flush=True)
            print(f"  URL: {region_url}", flush=True)

            try:
                # Navigate to region page with longer timeout
                print(f"  Loading page (may take up to 2 minutes)...", flush=True)
                page.goto(region_url, timeout=120000, wait_until="domcontentloaded")
                page.wait_for_load_state("domcontentloaded", timeout=120000)
                time.sleep(3)  # Additional wait for dynamic content

                # Handle cookie banner if present
                handle_cookie_banner(page)

                # Click "See more" to load all articles
                click_count = 0
                while click_see_more(page):
                    click_count += 1
                    print(f"  Clicked 'See more' ({click_count})", flush=True)
                    time.sleep(1)

                # Extract article links
                article_links = extract_article_links(page)
                print(f"  Found {len(article_links)} articles", flush=True)
                time.sleep(1)

                # Filter out already processed
                new_articles = [url for url in article_links if url not in processed_urls]
                print(f"  New articles to scrape: {len(new_articles)}", flush=True)

                for j, article_url in enumerate(new_articles):
                    # Add delay between articles
                    if j > 0:
                        art_delay = 5 + (j % 5)  # 5-10 seconds between articles
                        print(f"    Waiting {art_delay}s...", flush=True)
                        time.sleep(art_delay)

                    print(f"    Scraping: {article_url}", flush=True)

                    article_data = scrape_article(page, article_url)

                    if article_data:
                        aggregate_by_country(article_data, countries_data)
                        processed_urls.add(article_url)

                        # Save checkpoint after each successful scrape
                        save_checkpoint(CHECKPOINT_FILE, {
                            "processed_urls": list(processed_urls),
                            "countries_data": countries_data
                        })
                    else:
                        print(f"    [!] Failed to scrape, skipping", flush=True)
            except Exception as e:
                print(f"  [!] Error processing region {region_name}: {e}", flush=True)
                continue

        browser.close()

    # Save final output
    print(f"\n{'='*60}", flush=True)
    print(f"Scraping complete!", flush=True)
    print(f"  Total articles processed: {len(processed_urls)}", flush=True)
    print(f"  Total countries: {len(countries_data)}", flush=True)

    # Save final JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(countries_data, f, indent=2, ensure_ascii=False)

    print(f"  Saved to: {OUTPUT_FILE}", flush=True)

    # Print summary by region
    print(f"\nSummary:", flush=True)
    for region in set(c["region"] for c in countries_data):
        region_countries = [c for c in countries_data if c["region"] == region]
        total_destinations = sum(len(c["destinations"]) for c in region_countries)
        print(f"  {region}: {len(region_countries)} countries, {total_destinations} destinations", flush=True)


if __name__ == "__main__":
    main()
