"""
United Airlines Hemispheres Article Scraper

A Playwright-based web scraper for extracting content from United Airlines
Hemispheres magazine articles. Handles React SPAs with proper waiting strategies.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser
from urllib.parse import urlparse, urljoin

from listing_crawler import ListingCrawler


@dataclass
class ImageData:
    """Represents an image in the article."""
    src: str
    alt: str
    caption: Optional[str] = None
    attribution: Optional[str] = None


@dataclass
class ArticleSection:
    """Represents a section of the article."""
    heading: Optional[str] = None
    heading_level: int = 2
    content: str = ""
    images: list[ImageData] = field(default_factory=list)


@dataclass
class Article:
    """Represents a scraped article."""
    url: str
    title: str
    subtitle: Optional[str] = None
    date: Optional[str] = None
    author: Optional[str] = None
    hero_image: Optional[ImageData] = None
    sections: list[ArticleSection] = field(default_factory=list)
    related_articles: list[dict] = field(default_factory=list)
    raw_html: str = ""


class HemispheresScraper:
    """Scraper for United Airlines Hemispheres articles."""

    def __init__(self, headless: bool = False, output_dir: str = "output"):
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def scrape(self, url: str) -> Article:
        """Scrape an article from the given URL."""
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
                article = self._scrape_page(page, url)
                context.close()
                return article
            finally:
                browser.close()

    def _scrape_page(self, page: Page, url: str) -> Article:
        """Scrape the article page."""
        print(f"Navigating to {url}...")
        response = page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Print actual URL (in case of redirect)
        actual_url = page.url
        print(f"Actual URL: {actual_url}")
        if actual_url != url:
            print(f"Note: Redirected from {url} to {actual_url}")

        # Wait for React SPA to fully hydrate
        print("Waiting for page to load...")
        # Skip networkidle - SPAs often have ongoing analytics/tracking that prevent it from firing
        # Instead rely on domcontentloaded + selector wait for reliable content detection

        # Wait longer for React SPA to render content
        print("Waiting for React SPA to render...")
        page.wait_for_timeout(8000)

        # Scroll down progressively to trigger lazy loading
        print("Scrolling to trigger content loading...")
        for i in range(5):
            page.evaluate(f"() => {{ window.scrollTo(0, document.body.scrollHeight * {i} / 5); }}")
            page.wait_for_timeout(1000)

        page.evaluate("() => { window.scrollTo(0, 0); }")
        page.wait_for_timeout(1000)

        # Wait for article content to be visible
        try:
            page.wait_for_selector("h1", timeout=20000)
        except Exception:
            print("Warning: Could not find h1 heading, continuing anyway...")

        print("Extracting content...")

        # Get raw HTML
        raw_html = page.content()

        # Extract article data using JavaScript evaluation
        article_data = page.evaluate(self._get_extraction_script())

        # Build Article object
        article = self._build_article(url, article_data, raw_html)

        print(f"Extracted {len(article.sections)} sections")
        print(f"Found {sum(len(s.images) for s in article.sections)} images")

        return article

    def _get_extraction_script(self) -> str:
        """Returns JavaScript code to extract article content."""
        return """
        () => {
            const data = {
                title: '',
                subtitle: '',
                date: '',
                author: '',
                heroImage: null,
                sections: [],
                relatedArticles: []
            };

            // United Hemispheres specific selectors
            // Title from article intro
            const titleEl = document.querySelector('.hemi-3pd-article-intro__title');
            if (titleEl) {
                data.title = titleEl.textContent.trim();
            } else {
                // Fallback to h1
                const h1 = document.querySelector('h1');
                if (h1) data.title = h1.textContent.trim();
            }

            // Subtitle from hero section
            const subtitleEl = document.querySelector('.heroBasic-subtitle-section');
            if (subtitleEl) {
                data.subtitle = subtitleEl.textContent.trim();
            }

            // Date from article date
            const dateEl = document.querySelector('.hemi-article-date');
            if (dateEl) {
                data.date = dateEl.textContent.trim();
            }

            // Author from article author
            const authorEl = document.querySelector('.hemi-article-author-name');
            if (authorEl) {
                data.author = authorEl.textContent.trim();
            }

            // Hero image
            const heroImg = document.querySelector('.hemi-3pd-article-intro img') ||
                           document.querySelector('[class*="hero"] img');
            if (heroImg && heroImg.src) {
                data.heroImage = {
                    src: heroImg.src,
                    alt: heroImg.alt || '',
                    caption: heroImg.closest('figure')?.querySelector('figcaption')?.textContent?.trim() || ''
                };
            }

            // Extract article sections
            const sections = [];

            // Get intro paragraph
            const introEl = document.querySelector('.hemi-3pd-article-intro__paragraph');
            if (introEl) {
                sections.push({
                    heading: null,
                    headingLevel: 2,
                    content: introEl.textContent.trim(),
                    images: []
                });
            }

            // Get all article sections with class hemi-article-section
            const articleSections = document.querySelectorAll('.hemi-article-section');

            articleSections.forEach((sectionEl, index) => {
                const section = {
                    heading: null,
                    headingLevel: 2,
                    content: '',
                    images: []
                };

                // Find section title
                const titleEl = sectionEl.querySelector('.hemi-article-section-title');
                if (titleEl) {
                    section.heading = titleEl.textContent.trim();
                }

                // Get all paragraphs in this section
                const paragraphs = sectionEl.querySelectorAll('p');
                paragraphs.forEach(p => {
                    const text = p.textContent.trim();
                    if (text && text !== section.heading) {
                        section.content += text + '\\n\\n';
                    }
                });

                // Get images in section
                const images = sectionEl.querySelectorAll('img');
                images.forEach(img => {
                    if (img.src) {
                        section.images.push({
                            src: img.src,
                            alt: img.alt || '',
                            caption: img.closest('figure')?.querySelector('figcaption')?.textContent?.trim() || ''
                        });
                    }
                });

                if (section.content || section.images.length > 0) {
                    sections.push(section);
                }
            });

            // If no sections found with hemi-article-section, try generic approach
            if (sections.length === 0 || (sections.length === 1 && !sections[0].heading)) {
                // Try to find all headings and their content
                const allHeadings = document.querySelectorAll('h2, h3');
                allHeadings.forEach(heading => {
                    const text = heading.textContent.trim();
                    // Filter out navigation/UI headings
                    if (text && text.length > 10 && !text.includes('Menu') && !text.includes('Search')) {
                        const section = {
                            heading: text,
                            headingLevel: parseInt(heading.tagName[1]),
                            content: '',
                            images: []
                        };

                        // Get next siblings until next heading
                        let nextEl = heading.parentElement?.nextElementSibling || heading.nextElementSibling;
                        let safety = 0;
                        while (nextEl && safety < 50) {
                            safety++;
                            if (nextEl.tagName === 'P') {
                                section.content += nextEl.textContent.trim() + '\\n\\n';
                            }
                            if (nextEl.querySelectorAll) {
                                const imgs = nextEl.querySelectorAll('img');
                                imgs.forEach(img => {
                                    if (img.src) {
                                        section.images.push({
                                            src: img.src,
                                            alt: img.alt || '',
                                            caption: ''
                                        });
                                    }
                                });
                            }
                            nextEl = nextEl.nextElementSibling;
                        }

                        if (section.content) {
                            sections.push(section);
                        }
                    }
                });
            }

            data.sections = sections;

            // Find related articles
            const relatedSection = document.querySelector('[class*="DynamicRecommendation"]');
            if (relatedSection) {
                const links = relatedSection.querySelectorAll('a');
                links.forEach(link => {
                    const title = link.textContent.trim();
                    if (title && title.length > 5 && link.href) {
                        data.relatedArticles.push({
                            title: title,
                            url: link.href
                        });
                    }
                });
            }

            return data;
        }
        """

    def _build_article(self, url: str, data: dict, raw_html: str) -> Article:
        """Build Article object from extracted data."""
        # Parse hero image
        hero_image = None
        if data.get("heroImage"):
            hero_image = ImageData(
                src=data["heroImage"]["src"],
                alt=data["heroImage"]["alt"],
                caption=data["heroImage"].get("caption")
            )

        # Parse sections
        sections = []
        for sec_data in data.get("sections", []):
            images = [
                ImageData(
                    src=img["src"],
                    alt=img["alt"],
                    caption=img.get("caption")
                )
                for img in sec_data.get("images", [])
            ]

            section = ArticleSection(
                heading=sec_data.get("heading"),
                heading_level=sec_data.get("headingLevel", 2),
                content=sec_data.get("content", "").strip(),
                images=images
            )
            sections.append(section)

        return Article(
            url=url,
            title=data.get("title", "Untitled"),
            subtitle=data.get("subtitle"),
            date=data.get("date"),
            author=data.get("author"),
            hero_image=hero_image,
            sections=sections,
            related_articles=data.get("relatedArticles", []),
            raw_html=raw_html
        )

    def save_json(self, article: Article) -> Path:
        """Save article as JSON."""
        output_path = self.output_dir / "article.json"

        data = {
            "url": article.url,
            "title": article.title,
            "subtitle": article.subtitle,
            "date": article.date,
            "author": article.author,
            "hero_image": {
                "src": article.hero_image.src,
                "alt": article.hero_image.alt,
                "caption": article.hero_image.caption
            } if article.hero_image else None,
            "sections": [
                {
                    "heading": s.heading,
                    "heading_level": s.heading_level,
                    "content": s.content,
                    "images": [
                        {
                            "src": img.src,
                            "alt": img.alt,
                            "caption": img.caption
                        }
                        for img in s.images
                    ]
                }
                for s in article.sections
            ],
            "related_articles": article.related_articles,
            "scraped_at": datetime.now().isoformat()
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Saved JSON: {output_path}")
        return output_path

    def save_html(self, article: Article) -> Path:
        """Save raw HTML."""
        output_path = self.output_dir / "article.html"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(article.raw_html)

        print(f"Saved HTML: {output_path}")
        return output_path

    def save_markdown(self, article: Article) -> Path:
        """Save article as Markdown."""
        output_path = self.output_dir / "article.md"

        md_content = self._generate_markdown(article)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"Saved Markdown: {output_path}")
        return output_path

    def _generate_markdown(self, article: Article) -> str:
        """Generate Markdown content from article."""
        lines = []

        # Title
        lines.append(f"# {article.title}")
        lines.append("")

        # Subtitle
        if article.subtitle:
            lines.append(f"*{article.subtitle}*")
            lines.append("")

        # Metadata
        if article.date:
            lines.append(f"**Date:** {article.date}")
        if article.author:
            lines.append(f"**Author:** {article.author}")
        if article.date or article.author:
            lines.append("")

        # Hero image
        if article.hero_image:
            lines.append(f"![{article.hero_image.alt}]({article.hero_image.src})")
            if article.hero_image.caption:
                lines.append(f"*{article.hero_image.caption}*")
            lines.append("")

        # Source URL
        lines.append(f"**Source:** [{article.url}]({article.url})")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Sections
        for section in article.sections:
            if section.heading:
                heading_prefix = "#" * section.heading_level
                lines.append(f"{heading_prefix} {section.heading}")
                lines.append("")

            if section.content:
                # Clean up content
                content = section.content.replace("\\n", "\n").strip()
                lines.append(content)
                lines.append("")

            for img in section.images:
                lines.append(f"![{img.alt}]({img.src})")
                if img.caption:
                    lines.append(f"*{img.caption}*")
                lines.append("")

        # Related articles
        if article.related_articles:
            lines.append("---")
            lines.append("")
            lines.append("## Related Articles")
            lines.append("")
            for related in article.related_articles[:5]:  # Limit to 5
                lines.append(f"- [{related['title']}]({related['url']})")
            lines.append("")

        return "\n".join(lines)

    def scrape_and_save(self, url: str) -> dict:
        """Scrape article and save in all formats."""
        article = self.scrape(url)

        json_path = self.save_json(article)
        html_path = self.save_html(article)
        md_path = self.save_markdown(article)

        return {
            "article": article,
            "files": {
                "json": json_path,
                "html": html_path,
                "markdown": md_path
            }
        }

    def scrape_batch(self, listing_url: str, max_articles: Optional[int] = None, progress_callback=None) -> list:
        """
        Main batch processing entry point.

        Scrapes multiple articles from a listing page.

        Args:
            listing_url: URL of the listing page containing article links
            max_articles: Maximum number of articles to scrape (None for all)
            progress_callback: Optional callback function(current, total, url) for progress updates

        Returns:
            List of result dictionaries with keys: url, success, files, error, file_paths
        """
        # Create listing crawler to get all article URLs
        crawler = ListingCrawler(headless=self.headless)
        urls = crawler.get_article_urls(listing_url)

        if max_articles:
            urls = urls[:max_articles]

        valid_urls = [url for url in urls if self._is_valid_article_url(url)]

        print(f"\nFound {len(urls)} total URLs, {len(valid_urls)} valid article URLs")
        print(f"Will scrape up to {len(valid_urls)} articles\n")

        # Initialize results list - one entry per URL
        results = []

        # Reuse browser setup logic from scrape() but keep browser open
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

                # Process each URL
                for index, url in enumerate(valid_urls, 1):
                    print(f"Scraping {index} of {len(valid_urls)}: {url}")

                    if progress_callback:
                        progress_callback(index, len(valid_urls), url)

                    result = self._scrape_single_article_in_batch(page, url)
                    results.append(result)
                    print()

                context.close()
            finally:
                browser.close()

        return results

    def _scrape_single_article_in_batch(self, page: Page, url: str) -> dict:
        """
        Scrapes a single article during batch processing.

        Args:
            page: Playwright page instance
            url: Article URL to scrape

        Returns:
            Result dictionary with keys: url, success, files, error, file_paths
        """
        result = {
            "url": url,
            "success": False,
            "files": [],
            "error": None,
            "file_paths": {}
        }

        try:
            # Navigate to the URL
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Call existing _scrape_page logic
            article = self._scrape_page(page, url)

            # Generate unique filename based on URL
            base_name = self._generate_unique_filename(url)

            # Save article with custom filename
            saved_files = self._save_article_batch(article, base_name)

            result["success"] = True
            result["files"] = ["json", "html", "markdown"]
            result["file_paths"] = saved_files
            print(f"  ✓ Successfully scraped: {article.title}")

        except Exception as e:
            result["error"] = str(e)
            print(f"  ✗ Failed to scrape: {e}")

        return result

    def _generate_unique_filename(self, url: str) -> str:
        """
        Extracts slug from URL path for use as filename.

        Example: URL `/africa/morocco/marrakesh-solo-travel.html`
        → `marrakesh-solo-travel`

        Args:
            url: Article URL

        Returns:
            Base filename without extension
        """
        parsed = urlparse(url)
        path = parsed.path

        # Get the last segment of the path
        filename = path.split('/')[-1]

        # Remove .html extension if present
        if filename.endswith('.html'):
            filename = filename[:-5]

        # Fallback if empty
        if not filename:
            filename = "article"

        return filename

    def _save_article_batch(self, article: Article, base_name: str) -> dict:
        """
        Saves article with custom filename (not just "article.json").

        Creates subdirectory based on region if needed.

        Args:
            article: Article to save
            base_name: Base filename (without extension)

        Returns:
            Dictionary of saved file paths
        """
        # Extract region from URL path for subdirectory
        parsed = urlparse(article.url)
        path_parts = [p for p in parsed.path.split('/') if p]

        # Determine region subdirectory (e.g., 'africa', 'asia', etc.)
        region = None
        if len(path_parts) >= 2:
            # URL pattern: /places-to-go/{region}/{country}/{article}.html
            if path_parts[0] == 'places-to-go' and len(path_parts) >= 2:
                region = path_parts[1]

        # Create subdirectory if region found
        if region:
            output_subdir = self.output_dir / region
            output_subdir.mkdir(exist_ok=True)
        else:
            output_subdir = self.output_dir

        # Save JSON
        json_path = output_subdir / f"{base_name}.json"
        data = {
            "url": article.url,
            "title": article.title,
            "subtitle": article.subtitle,
            "date": article.date,
            "author": article.author,
            "hero_image": {
                "src": article.hero_image.src,
                "alt": article.hero_image.alt,
                "caption": article.hero_image.caption
            } if article.hero_image else None,
            "sections": [
                {
                    "heading": s.heading,
                    "heading_level": s.heading_level,
                    "content": s.content,
                    "images": [
                        {
                            "src": img.src,
                            "alt": img.alt,
                            "caption": img.caption
                        }
                        for img in s.images
                    ]
                }
                for s in article.sections
            ],
            "related_articles": article.related_articles,
            "scraped_at": datetime.now().isoformat()
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  Saved JSON: {json_path}")

        # Save HTML
        html_path = output_subdir / f"{base_name}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(article.raw_html)
        print(f"  Saved HTML: {html_path}")

        # Save Markdown
        md_path = output_subdir / f"{base_name}.md"
        md_content = self._generate_markdown(article)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"  Saved Markdown: {md_path}")

        return {
            "json": str(json_path),
            "md": str(md_path),
            "html": str(html_path)
        }

    def _get_output_files_for_url(self, url: str, base_name: str) -> dict:
        """
        Get the output file paths for a given URL.

        Args:
            url: Article URL
            base_name: Base filename

        Returns:
            Dictionary of file paths
        """
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]

        region = None
        if len(path_parts) >= 2:
            if path_parts[0] == 'places-to-go' and len(path_parts) >= 2:
                region = path_parts[1]

        if region:
            output_subdir = self.output_dir / region
        else:
            output_subdir = self.output_dir

        return {
            "json": str(output_subdir / f"{base_name}.json"),
            "md": str(output_subdir / f"{base_name}.md"),
            "html": str(output_subdir / f"{base_name}.html")
        }

    def _is_valid_article_url(self, url: str) -> bool:
        """
        Check if a URL is a valid article URL (not index page).

        Args:
            url: URL to check

        Returns:
            True if valid article URL
        """
        parsed = urlparse(url)

        # Must be HTTP or HTTPS
        if parsed.scheme not in ('http', 'https'):
            return False

        # Must have a path that looks like an article
        path = parsed.path.lower()
        if not path or path == '/':
            return False

        # Must NOT be an index.html page (these are listing pages, not articles)
        if path.endswith("/index.html") or path.endswith("/index"):
            return False

        # Must be an actual article page (ends with .html)
        if not path.endswith(".html"):
            return False

        return True
