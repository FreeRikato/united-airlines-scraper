"""
Listing Crawler for United Hemispheres magazine.

A Playwright-based crawler for discovering article URLs from listing pages.
"""

from pathlib import Path
from urllib.parse import urlparse, urljoin

from playwright.sync_api import sync_playwright, Page, BrowserType


class ListingCrawler:
    """Crawler for listing pages to discover article URLs."""

    def __init__(self, headless: bool = False, output_dir: Path = None):
        """Initialize with headless mode and optional output directory."""
        self.headless = headless
        self.output_dir = output_dir or Path("output")
        self.state = {
            "listing_url": "",
            "total_found": 0,
            "valid_urls": [],
            "skipped_urls": [],
            "processed": {},
            "remaining": [],
        }

    def get_article_urls(self, listing_url: str, place_slug: str | None = None) -> list[str]:
        """
        Main entry point to get all article URLs from a listing page.

        Args:
            listing_url: URL of the listing page
            place_slug: Optional place slug to filter articles (e.g., "africa", "asia")

        Returns:
            List of valid article URLs
        """
        with sync_playwright() as p:
            browser = p.firefox.launch(
                headless=self.headless,
                firefox_user_prefs={
                    'network.http.http2.enabled': False,
                    'network.http.http3.enabled': False,
                }
            )
            try:
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Accept-Encoding": "gzip, deflate, br",
                        "DNT": "1",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Cache-Control": "max-age=0",
                    }
                )

                # Inject stealth script to avoid detection
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    window.chrome = { runtime: {} };
                """)

                page = context.new_page()
                state = self.crawl_listing(page, listing_url, place_slug)
                context.close()
                return state["valid_urls"]
            finally:
                browser.close()

    def crawl_listing(self, page: Page, listing_url: str, place_slug: str | None = None) -> dict:
        """
        Crawl a listing page and return state dict with all discovered URLs.

        Args:
            page: Playwright page instance
            listing_url: URL of the listing page
            place_slug: Optional place slug to filter articles

        Returns:
            State dictionary with discovered URLs
        """
        self.state["listing_url"] = listing_url

        print(f"Navigating to listing page: {listing_url}...")
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)

        # Wait for initial content to load
        print("Waiting for page to load...")
        page.wait_for_timeout(3000)

        # Load all articles by clicking "See more" until no more content
        all_urls = self._load_all_articles(page, place_slug)

        # Categorize URLs
        valid_urls = []
        skipped_urls = []
        for url in all_urls:
            if self._is_valid_article_url(url, place_slug):
                valid_urls.append(url)
            else:
                skipped_urls.append(url)

        # Update state
        self.state["total_found"] = len(all_urls)
        self.state["valid_urls"] = valid_urls
        self.state["skipped_urls"] = skipped_urls
        self.state["remaining"] = valid_urls.copy()

        # Initialize processed dict with pending status
        for url in valid_urls:
            self.state["processed"][url] = "pending"

        print(f"\nCrawling complete:")
        print(f"  Total URLs found: {len(all_urls)}")
        if place_slug:
            print(f"  Valid URLs (/places-to-go/{place_slug}/): {len(valid_urls)}")
        else:
            print(f"  Valid URLs (/places-to-go/): {len(valid_urls)}")
        print(f"  Skipped URLs (/things-to-do/): {len(skipped_urls)}")

        return self.state

    def _load_all_articles(self, page: Page, place_slug: str | None = None) -> list[str]:
        """Clicks 'See more' button until no more content loads."""
        all_urls = set()
        max_attempts = 50  # Safety limit
        attempts = 0

        while attempts < max_attempts:
            # Extract current URLs
            current_urls = self._extract_article_links(page, place_slug)
            previous_count = len(all_urls)
            all_urls.update(current_urls)

            print(f"  Found {len(current_urls)} article links on page "
                  f"(total unique: {len(all_urls)})")

            # Try to click "See more" button
            clicked = self._click_see_more(page)

            if not clicked:
                print("  No more 'See more' button found, stopping.")
                break

            # Wait for new content to load
            page.wait_for_timeout(2000)

            # Check if new content was actually loaded
            new_urls = self._extract_article_links(page, place_slug)
            if len(new_urls) <= previous_count:
                print("  No new content loaded after click, stopping.")
                break

            attempts += 1

        if attempts >= max_attempts:
            print(f"  Reached maximum attempts ({max_attempts}), stopping.")

        return list(all_urls)

    def _extract_article_links(self, page: Page, place_slug: str | None = None) -> list[str]:
        """Extracts all article links from current page state."""
        links = []

        # Get the current page URL for resolving relative URLs
        base_url = page.url

        # Build selector based on place_slug
        # Only look for places-to-go links - things-to-do will be filtered out by _is_valid_article_url
        if place_slug:
            selector = f'a[href*="/places-to-go/{place_slug}/"]'
        else:
            selector = 'a[href*="/places-to-go/"]'

        # Find all links with places-to-go/{place} or things-to-do patterns
        # Using JavaScript evaluation for more reliable extraction
        hrefs = page.evaluate(f"""
            () => {{
                const links = [];
                const anchors = document.querySelectorAll('{selector}');
                anchors.forEach(a => {{
                    if (a.href) {{
                        links.push(a.href);
                    }}
                }});
                return links;
            }}
        """)

        # Convert to absolute URLs and deduplicate
        seen = set()
        for href in hrefs:
            # Resolve relative URLs
            absolute_url = urljoin(base_url, href)

            # Normalize URL (remove fragments)
            parsed = urlparse(absolute_url)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            if normalized not in seen:
                seen.add(normalized)
                links.append(normalized)

        return links

    def _is_valid_article_url(self, url: str, place_slug: str | None = None) -> bool:
        """
        Returns True if URL is a valid article.

        Args:
            url: URL to validate
            place_slug: Optional place slug to filter (e.g., "africa", "asia")
        """
        parsed = urlparse(url)
        path = parsed.path.lower()

        # Must contain /places-to-go/
        if "/places-to-go/" not in path:
            return False

        # Must NOT contain /things-to-do/
        if "/things-to-do/" in path:
            return False

        # If place_slug specified, must contain /{place_slug}/ in the path
        if place_slug:
            if f"/{place_slug.lower()}/" not in path:
                return False

        # Must NOT be an index.html page (these are listing pages, not articles)
        if path.endswith("/index.html") or path.endswith("/index"):
            return False

        # Must be an actual article page (ends with .html but not index.html)
        if not path.endswith(".html"):
            return False

        return True

    def get_place_urls(self, index_url: str) -> list[str]:
        """
        Extract all place category URLs from the main index page.

        Args:
            index_url: URL of the main places-to-go index page

        Returns:
            List of full URLs for place category pages
        """
        with sync_playwright() as p:
            browser = p.firefox.launch(
                headless=self.headless,
                firefox_user_prefs={
                    'network.http.http2.enabled': False,
                    'network.http.http3.enabled': False,
                }
            )
            try:
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Accept-Encoding": "gzip, deflate, br",
                        "DNT": "1",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Cache-Control": "max-age=0",
                    }
                )

                # Inject stealth script to avoid detection
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    window.chrome = { runtime: {} };
                """)

                page = context.new_page()
                place_urls = self._extract_place_urls(page, index_url)
                context.close()
                return place_urls
            finally:
                browser.close()

    def _extract_place_urls(self, page: Page, index_url: str) -> list[str]:
        """
        Navigate to index page and extract place category URLs.

        Args:
            page: Playwright page instance
            index_url: URL of the main index page

        Returns:
            List of full URLs for place category pages
        """
        print(f"Navigating to index page: {index_url}...")
        page.goto(index_url, wait_until="domcontentloaded", timeout=60000)

        print("Waiting for page to load...")
        page.wait_for_timeout(3000)

        # Extract place URLs using JavaScript
        hrefs = page.evaluate("""
            () => {
                const links = [];
                // Look for anchor tags linking to /places-to-go/{place}/index.html
                const anchors = document.querySelectorAll('a[href*="/places-to-go/"]');
                anchors.forEach(a => {
                    const href = a.getAttribute('href');
                    if (href && href.includes('/places-to-go/') && href.includes('/index.html')) {
                        links.push(href);
                    }
                });
                return links;
            }
        """)

        # Convert to absolute URLs and deduplicate
        base_url = page.url
        seen = set()
        place_urls = []

        for href in hrefs:
            # Resolve relative URLs to absolute
            absolute_url = urljoin(base_url, href)

            # Normalize URL (remove fragments)
            parsed = urlparse(absolute_url)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            if normalized not in seen:
                seen.add(normalized)
                place_urls.append(normalized)

        print(f"Found {len(place_urls)} place category URLs:")
        for url in place_urls:
            print(f"  - {url}")

        return place_urls

    def _click_see_more(self, page: Page) -> bool:
        """Attempts to click 'See more' button, returns True if successful/new content loaded."""
        try:
            # Try multiple selectors for the "See more" button
            selectors = [
                'button:has-text("See more")',
                'button:has-text("see more")',
                'button[class*="see-more"]',
                '[class*="see-more"]',
                'button:has-text("Load more")',
                'button:has-text("Show more")',
                'a:has-text("See more")',
            ]

            for selector in selectors:
                try:
                    # Check if button exists and is visible
                    button = page.locator(selector).first
                    if button.count() > 0 and button.is_visible():
                        print(f"  Clicking 'See more' button...")

                        # Scroll to button to ensure it's in viewport
                        button.scroll_into_view_if_needed()
                        page.wait_for_timeout(500)

                        # Click the button
                        button.click()
                        return True
                except Exception:
                    continue

            # Try JavaScript approach as fallback
            clicked = page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const seeMoreBtn = buttons.find(b =>
                        b.textContent.toLowerCase().includes('see more') ||
                        b.textContent.toLowerCase().includes('load more') ||
                        b.textContent.toLowerCase().includes('show more')
                    );
                    if (seeMoreBtn && seeMoreBtn.offsetParent !== null) {
                        seeMoreBtn.click();
                        return true;
                    }
                    return false;
                }
            """)

            if clicked:
                print("  Clicking 'See more' button (via JavaScript)...")
                return True

            return False

        except Exception as e:
            print(f"  Error clicking 'See more': {e}")
            return False
