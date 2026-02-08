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


def main():
    parser = argparse.ArgumentParser(
        description="Scrape United Airlines Hemispheres magazine articles"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_URL,
        help=f"URL to scrape (default: {DEFAULT_URL})"
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

    print("=" * 60)
    print("United Airlines Hemispheres Article Scraper")
    print("=" * 60)
    print(f"Target URL: {args.url}")
    print(f"Output directory: {args.output}")
    print(f"Browser mode: {'headless' if args.headless else 'headed (visible)'}")
    print("=" * 60)
    print()

    try:
        scraper = HemispheresScraper(
            headless=args.headless,
            output_dir=args.output
        )

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
