"""Directory sources: places that LIST businesses.

1. OpenStreetMapDirectory - works out of the box. OpenStreetMap is open data and its
   public Nominatim/Overpass services allow automated queries under their usage
   policy (identify yourself, ~1 request/second, no bulk abuse).
2. SelectorDirectory - a config-driven HTML scraper for ANY other directory you have
   personally verified allows automated access (terms of service + robots.txt).
"""
import re
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScraperError

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# keyword fragment -> OpenStreetMap tags
CATEGORY_TAGS = {
    "restaurant": [("amenity", "restaurant")], "cafe": [("amenity", "cafe")],
    "fast food": [("amenity", "fast_food")], "hospital": [("amenity", "hospital")],
    "clinic": [("amenity", "clinic")], "pharmacy": [("amenity", "pharmacy")],
    "school": [("amenity", "school")], "college": [("amenity", "college")],
    "universit": [("amenity", "university")], "bank": [("amenity", "bank")],
    "hotel": [("tourism", "hotel")], "guest house": [("tourism", "guest_house")],
    "real estate": [("office", "estate_agent")], "estate agen": [("office", "estate_agent")],
    "software": [("office", "it")], "it company": [("office", "it")],
    "marketing": [("office", "advertising_agency")], "advertising": [("office", "advertising_agency")],
    "lawyer": [("office", "lawyer")], "law firm": [("office", "lawyer")],
    "insurance": [("office", "insurance")], "gym": [("leisure", "fitness_centre")],
    "supermarket": [("shop", "supermarket")], "salon": [("shop", "hairdresser")],
    "dentist": [("amenity", "dentist")], "bakery": [("shop", "bakery")],
}
CATEGORY_KEYS = ("amenity", "shop", "office", "tourism", "craft", "healthcare", "leisure")


def _ere(text):
    """Escape text for an Overpass regex string literal."""
    text = re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", text)
    return text.replace("\\", "\\\\").replace('"', '\\"')


class OpenStreetMapDirectory(BaseScraper):
    name = "osm"
    label = "OpenStreetMap"

    def _geocode(self, location):
        self._throttle("nominatim")
        try:
            r = self.session.get(NOMINATIM_URL, params={"q": location, "format": "json", "limit": 1},
                                 timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            raise ScraperError("Could not look up that location (OpenStreetMap geocoder unavailable).")
        if not data:
            raise ScraperError(f"Location '{location}' was not found. Try a bigger city name.")
        s, n, w, e = data[0]["boundingbox"]
        return f"{s},{w},{n},{e}"

    def _build_query(self, keyword, bbox, limit):
        kw = keyword.lower().strip()
        wanted = {(k, v) for frag, tags in CATEGORY_TAGS.items() if frag in kw for k, v in tags}
        parts = [f'nwr["{k}"="{v}"]["name"]({bbox});' for k, v in sorted(wanted)]
        phrase = re.sub(r"ies$", "y", kw)          # "agencies" -> "agency"
        phrase = re.sub(r"(?<!s)s$", "", phrase)   # "restaurants" -> "restaurant"
        parts.append(f'nwr["name"~"{_ere(phrase)}",i]({bbox});')
        return f'[out:json][timeout:50];({"".join(parts)});out tags center {limit};'

    def search(self, keyword, location, limit):
        bbox = self._geocode(location)
        self._throttle("overpass")
        try:
            r = self.session.post(OVERPASS_URL, data={"data": self._build_query(keyword, bbox, limit)},
                                  timeout=70)
        except requests.Timeout:
            raise ScraperError("OpenStreetMap took too long. Try a smaller area or fewer results.")
        except requests.RequestException:
            raise ScraperError("Could not reach OpenStreetMap servers.")
        if r.status_code == 429:
            raise ScraperError("OpenStreetMap is rate-limiting requests. Wait a minute and retry.")
        if r.status_code != 200:
            raise ScraperError(f"OpenStreetMap returned HTTP {r.status_code}. Try a smaller area.")
        try:
            elements = r.json().get("elements", [])
        except ValueError:
            raise ScraperError("OpenStreetMap returned an unreadable answer (area may be too large).")
        leads = [l for l in (self._to_lead(el, location) for el in elements) if l["name"]]
        if not leads:
            raise ScraperError("No businesses found in OpenStreetMap for this keyword and location. "
                               "Try a broader keyword; OSM coverage varies by area.")
        return leads

    def _to_lead(self, el, location):
        t = el.get("tags", {})
        pick = lambda *keys: next((t[k] for k in keys if t.get(k)), "")
        street = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
        address = t.get("addr:full") or ", ".join(
            x for x in (street, t.get("addr:suburb") or t.get("addr:neighbourhood"), t.get("addr:city")) if x)
        cat = next((t[k] for k in CATEGORY_KEYS if t.get(k)), "")
        return {
            "name": t.get("name", ""), "phone": pick("phone", "contact:phone", "mobile", "contact:mobile"),
            "email": pick("email", "contact:email"), "website": pick("website", "contact:website", "url"),
            "address": address, "city": t.get("addr:city") or location,
            "category": cat.replace("_", " ").title(), "source": self.label,
        }


class SelectorDirectory(BaseScraper):
    """Config-driven scraper for a directory whose terms + robots.txt allow it.

    search_url : URL with {keyword}, {location}, {page} placeholders
    item_selector : CSS selector matching ONE listing card
    fields : {"name": ("h2 a", None), "website": ("a.site", "href"), ...}
             (css selector inside the card, attribute to read or None for text)
    """

    def __init__(self, name, label, search_url, item_selector, fields, max_pages=3,
                 contact_email="", delay=2.0):
        super().__init__(contact_email, delay)
        self.name, self.label = name, label
        self.search_url, self.item_selector = search_url, item_selector
        self.fields, self.max_pages = fields, max_pages

    def search(self, keyword, location, limit):
        leads = []
        for page in range(1, self.max_pages + 1):
            url = self.search_url.format(keyword=quote_plus(keyword), location=quote_plus(location), page=page)
            soup = BeautifulSoup(self.get(url).text, "html.parser")
            items = soup.select(self.item_selector)
            if not items:
                break
            for item in items:
                row = {"source": self.label, "city": location}
                for field, (css, attr) in self.fields.items():
                    el = item.select_one(css)
                    value = (el.get(attr, "") if attr else el.get_text(" ", strip=True)) if el else ""
                    row[field] = urljoin(url, value) if attr == "href" else value
                leads.append(row)
            if len(leads) >= limit:
                break
        if not leads:
            raise ScraperError(f"{self.label} returned no listings (page layout may have changed).")
        return leads[:limit]
