#!/usr/bin/env python3
"""
United Airlines Hemispheres Article Scraper

Main entry point for scraping United Airlines Hemispheres magazine articles.
"""

import argparse
import sys
from pathlib import Path

from scraper import HemispheresScraper
from listing_crawler import ListingCrawler


DEFAULT_URL = "https://www.united.com/en/us/hemispheres/places-to-go/africa/morocco/marrakesh-solo-travel.html"
DEFAULT_LISTING_URL = "https://www.united.com/en/us/hemispheres/places-to-go/africa/index.html"
DEFAULT_INDEX_URL = "https://www.united.com/en/us/hemispheres/places-to-go/index.html"


def print_batch_summary(results, output_dir, place_name: str = None):
    """Print a formatted summary of batch scraping results."""
    total = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total - successful

    print()
    print("=" * 80)
    if place_name:
        print(f"BATCH SCRAPING SUMMARY - {place_name.upper()}")
    else:
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


def print_multi_place_summary(all_results: dict, output_dir: str):
    """Print a formatted summary for multi-place scraping results."""
    print()
    print("=" * 80)
    print("MULTI-PLACE SCRAPING SUMMARY")
    print("=" * 80)

    total_places = len(all_results)
    total_articles = sum(len(results) for results in all_results.values())
    total_successful = sum(
        sum(1 for r in results if r["success"])
        for results in all_results.values()
    )
    total_failed = total_articles - total_successful

    print(f"Total places scraped:     {total_places}")
    print(f"Total articles found:     {total_articles}")
    print(f"Successfully scraped:     {total_successful}")
    print(f"Failed:                   {total_failed}")
    print(f"Output directory:         {output_dir}")
    print()

    for place_name, results in all_results.items():
        successful = sum(1 for r in results if r["success"])
        failed = len(results) - successful
        print(f"  {place_name:<15} {len(results):>3} articles  ({successful} success, {failed} failed)")

    print()
    print("=" * 80)


def scrape_single_place(scraper, listing_url: str, max_articles: int | None, place_name: str) -> list:
    """Scrape articles from a single place listing."""
    print(f"\n{'=' * 80}")
    print(f"SCRAPING PLACE: {place_name.upper()}")
    print(f"Listing URL: {listing_url}")
    print(f"{'=' * 80}")

    results = scraper.scrape_batch(
        listing_url,
        max_articles=max_articles,
        progress_callback=lambda current, total, url: print(
            f"Processing article {current} of {total}..."
        ),
        place_slug=place_name
    )

    print_batch_summary(results, scraper.output_dir, place_name)
    return results


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

  # Scrape all places from main index
  python main.py --all-places

  # Scrape specific places
  python main.py --places africa,asia,europe

  # Scrape all places with article limit
  python main.py --all-places --max-articles 5
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
    parser.add_argument(
        "--all-places",
        action="store_true",
        help="Scrape all places from the main index page"
    )
    parser.add_argument(
        "--places",
        type=str,
        help="Comma-separated list of specific places to scrape (e.g., 'africa,asia,europe')"
    )

    args = parser.parse_args()

    # Determine mode
    is_single_article = args.url is not None
    is_batch_listing = args.batch or args.listing_url is not None
    is_all_places = args.all_places
    is_specific_places = args.places is not None

    # Default to --all-places if no specific mode given
    if not is_single_article and not is_batch_listing and not is_all_places and not is_specific_places:
        is_all_places = True

    print("=" * 60)
    print("United Airlines Hemispheres Article Scraper")
    print("=" * 60)

    try:
        scraper = HemispheresScraper(
            headless=args.headless,
            output_dir=args.output
        )

        if is_single_article:
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

        elif is_batch_listing:
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

        elif is_all_places:
            # Scrape all places from main index
            print(f"Mode: ALL PLACES")
            print(f"Index URL: {DEFAULT_INDEX_URL}")
            if args.max_articles:
                print(f"Max articles per place: {args.max_articles}")
            print(f"Output directory: {args.output}")
            print(f"Browser mode: {'headless' if args.headless else 'headed (visible)'}")
            print("=" * 60)
            print()

            # Get all place URLs from index
            crawler = ListingCrawler(headless=args.headless)
            place_urls = crawler.get_place_urls(DEFAULT_INDEX_URL)

            if not place_urls:
                print("No places found on index page.")
                return 1

            # Scrape each place
            all_results = {}
            for place_url in place_urls:
                # Extract place name from URL
                # URL format: https://.../places-to-go/{place}/index.html
                place_name = place_url.split('/places-to-go/')[-1].split('/')[0]

                results = scrape_single_place(scraper, place_url, args.max_articles, place_name)
                all_results[place_name] = results

            # Print overall summary
            print_multi_place_summary(all_results, args.output)

            # Return appropriate exit code
            total_failed = sum(
                sum(1 for r in results if not r["success"])
                for results in all_results.values()
            )
            total_articles = sum(len(results) for results in all_results.values())

            if total_failed == total_articles and total_articles > 0:
                return 1  # All failed
            elif total_failed > 0:
                return 2  # Partial success
            return 0

        elif is_specific_places:
            # Scrape specific places
            place_names = [p.strip().lower() for p in args.places.split(',')]
            print(f"Mode: SPECIFIC PLACES")
            print(f"Places: {', '.join(place_names)}")
            if args.max_articles:
                print(f"Max articles per place: {args.max_articles}")
            print(f"Output directory: {args.output}")
            print(f"Browser mode: {'headless' if args.headless else 'headed (visible)'}")
            print("=" * 60)
            print()

            # Get all place URLs from index
            crawler = ListingCrawler(headless=args.headless)
            place_urls = crawler.get_place_urls(DEFAULT_INDEX_URL)

            # Filter to requested places
            filtered_place_urls = []
            for place_url in place_urls:
                place_name = place_url.split('/places-to-go/')[-1].split('/')[0].lower()
                if place_name in place_names:
                    filtered_place_urls.append((place_name, place_url))

            if not filtered_place_urls:
                print(f"No matching places found for: {', '.join(place_names)}")
                print("Available places:")
                for place_url in place_urls:
                    place_name = place_url.split('/places-to-go/')[-1].split('/')[0]
                    print(f"  - {place_name}")
                return 1

            # Scrape each requested place
            all_results = {}
            for place_name, place_url in filtered_place_urls:
                results = scrape_single_place(scraper, place_url, args.max_articles, place_name)
                all_results[place_name] = results

            # Print overall summary
            print_multi_place_summary(all_results, args.output)

            # Return appropriate exit code
            total_failed = sum(
                sum(1 for r in results if not r["success"])
                for results in all_results.values()
            )
            total_articles = sum(len(results) for results in all_results.values())

            if total_failed == total_articles and total_articles > 0:
                return 1  # All failed
            elif total_failed > 0:
                return 2  # Partial success
            return 0

    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user.")
        return 130
    except Exception as e:
        print(f"\n\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
