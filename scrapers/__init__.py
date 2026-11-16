from .base_scraper import BaseScraper, ScraperError
from .business_scraper import BusinessSiteScraper
from .directory_scraper import OpenStreetMapDirectory, SelectorDirectory


def build_sources(contact_email="", delay=1.5):
    """Registry of search sources shown in the dropdown. {key: scraper}"""
    sources = [OpenStreetMapDirectory(contact_email, delay)]

    # ---- ADD MORE PERMITTED SOURCES HERE (see README "Add another source") ----
    # Only after you confirmed the site's Terms of Service AND robots.txt allow it:
    # sources.append(SelectorDirectory(
    #     name="mydir", label="My Directory",
    #     search_url="https://example-directory.com/search?q={keyword}&city={location}&page={page}",
    #     item_selector="div.listing",
    #     fields={"name": ("h2", None), "phone": ("span.tel", None),
    #             "website": ("a.website", "href"), "address": ("p.address", None)},
    #     contact_email=contact_email))
    return {s.name: s for s in sources}
