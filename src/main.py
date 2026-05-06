import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from src.stages.condenser import condense_html
from src.stages.formatter import format_output
from src.stages.ie_extractor import extract_fields
from src.stages.renderer import render_page
from src.stages.sanitizer import sanitize_html
from src.stages.xpath_generator import generate_xpaths
from src.stages.reconciler import reconcile_xpaths
from src.exceptions import ForumXPathError

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)


async def run_pipeline(url: str):
    rendered = await render_page(url)
    sanitized = sanitize_html(rendered["html"])
    ie_output = await extract_fields(sanitized)
    condensed = condense_html(rendered["html"], ie_output)
    xpaths = await generate_xpaths(condensed, ie_output, rendered["html"])
    xpaths = await reconcile_xpaths(xpaths, rendered["html"], url)
    output = format_output(xpaths, url)
    return output


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.main <url>")
        sys.exit(1)

    url = sys.argv[1]

    if "--verbose" in sys.argv or "-v" in sys.argv:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        asyncio.run(run_pipeline(url))
        sys.exit(0)
    except ForumXPathError as exc:
        print(f"\nPipeline error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\nUnexpected error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
