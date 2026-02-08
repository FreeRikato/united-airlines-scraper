#!/usr/bin/env python3
"""
United Airlines Hemispheres Article Scraper

Main entry point for scraping United Airlines Hemispheres magazine articles.
"""

import argparse
import sys
from pathlib import Path

from scraper import HemispheresScraper


DEFAULT_URL = "https://www.united.com/en/us/hemispheres/places-to-go/africa/morocco/marrakesh-solo-travel.html"
DEFAULT_LISTING_URL = "https://www.united.com/en/us/hemispheres/places-to-go/africa/index.html"


def print_batch_summary(results, output_dir):
    """Print a formatted summary of batch scraping results."""
    total = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total - successful

    print()
    print("=" * 80)
    print("BATCH SCRAPING SUMMARY")
    print("=" * 80)
    print(f"Total articles found:     {total}")
    print(f"Successfully scraped:     {successful}")
    print(f"Failed:                   {failed}")
    print(f"Output directory:         {output_dir}")
    print()
    print("-" * 80)
    print(f"{'URL':<50} {'Status':<12} {'Output Files'}")
    print("-" * 80)

    for result in results:
        url = result["url"][:47] + "..." if len(result["url"]) > 50 else result["url"]
        status = "SUCCESS" if result["success"] else "FAILED"
        files = ", ".join(result.get("files", [])) if result["success"] else result.get("error", "Unknown error")
        if len(files) > 30:
            files = files[:27] + "..."
        print(f"{url:<50} {status:<12} {files}")

    print("-" * 80)
    print()

    if successful > 0:
        print("Output files created:")
        for result in results:
            if result["success"] and "file_paths" in result:
                for format_name, path in result["file_paths"].items():
                    print(f"  - {path}")
        print()

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape United Airlines Hemispheres magazine articles",
        epilog="""Examples:
  # Scrape single article
  python main.py --url https://.../marrakesh-solo-travel.html

  # Scrape all articles from Africa listing
  python main.py --listing-url https://.../africa/index.html --batch

  # Scrape first 5 articles only
  python main.py --listing-url https://.../africa/index.html --batch --max-articles 5
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url",
        type=str,
        help="URL to scrape for single article mode"
    )
    parser.add_argument(
        "--listing-url",
        type=str,
        help="Listing page URL to scrape all articles from (e.g., https://.../africa/index.html)"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Enable batch mode - scrape all articles from listing page"
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        help="Limit number of articles to scrape (for testing)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="Output directory for scraped files (default: output)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no visible window)"
    )

    args = parser.parse_args()

    # Determine mode: batch or single article
    is_batch_mode = args.batch or args.listing_url is not None

    if not is_batch_mode and args.url is None:
        # No URL provided, show help with examples
        parser.print_help()
        return 0

    print("=" * 60)
    print("United Airlines Hemispheres Article Scraper")
    print("=" * 60)

    try:
        scraper = HemispheresScraper(
            headless=args.headless,
            output_dir=args.output
        )

        if is_batch_mode:
            # Batch mode: scrape all articles from listing page
            listing_url = args.listing_url or DEFAULT_LISTING_URL
            print(f"Mode: BATCH")
            print(f"Listing URL: {listing_url}")
            if args.max_articles:
                print(f"Max articles: {args.max_articles}")
            print(f"Output directory: {args.output}")
            print(f"Browser mode: {'headless' if args.headless else 'headed (visible)'}")
            print("=" * 60)
            print()

            results = scraper.scrape_batch(
                listing_url,
                max_articles=args.max_articles,
                progress_callback=lambda current, total, url: print(
                    f"Processing article {current} of {total}..."
                )
            )

            print_batch_summary(results, args.output)

            # Return appropriate exit code
            failed_count = sum(1 for r in results if not r["success"])
            if failed_count == len(results) and len(results) > 0:
                return 1  # All failed
            elif failed_count > 0:
                return 2  # Partial success
            return 0

        else:
            # Single article mode
            print(f"Mode: SINGLE ARTICLE")
            print(f"Target URL: {args.url}")
            print(f"Output directory: {args.output}")
            print(f"Browser mode: {'headless' if args.headless else 'headed (visible)'}")
            print("=" * 60)
            print()

            result = scraper.scrape_and_save(args.url)
            article = result["article"]

            print()
            print("=" * 60)
            print("Scraping Complete!")
            print("=" * 60)
            print(f"Title: {article.title}")
            if article.subtitle:
                print(f"Subtitle: {article.subtitle}")
            if article.date:
                print(f"Date: {article.date}")
            if article.author:
                print(f"Author: {article.author}")
            print(f"Sections: {len(article.sections)}")
            print(f"Total images: {sum(len(s.images) for s in article.sections)}")
            print()
            print("Output files:")
            for format_name, path in result["files"].items():
                print(f"  - {format_name}: {path}")
            print("=" * 60)

            return 0

    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user.")
        return 130
    except Exception as e:
        print(f"\n\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
