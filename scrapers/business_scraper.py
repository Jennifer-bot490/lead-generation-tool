"""Business-website scraper: reads a company's OWN public website to find a
contact email / phone that the directory did not list. Fills gaps only - never overwrites."""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScraperError

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
JUNK = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", "sentry", "wixpress", "example.", "domain.com")


class BusinessSiteScraper(BaseScraper):
    name = "business-site"
    label = "Business website"

    def __init__(self, contact_email="", delay=1.5, timeout=8):
        super().__init__(contact_email, delay, timeout)

    def _scan(self, url):
        soup = BeautifulSoup(self.get(url).text, "html.parser")
        emails = [a["href"][7:].split("?")[0] for a in soup.select('a[href^="mailto:"]')]
        emails += EMAIL_RE.findall(soup.get_text(" "))
        phones = [a["href"][4:] for a in soup.select('a[href^="tel:"]')]
        contact = next((urljoin(url, a["href"]) for a in soup.select("a[href]")
                        if "contact" in a["href"].lower() or "contact" in a.get_text().lower()), None)
        return emails, phones, contact

    def _best_email(self, emails, site):
        emails = [e.strip().lower() for e in emails if e and not any(j in e.lower() for j in JUNK)]
        domain = urlparse(site).netloc.replace("www.", "")
        return next((e for e in emails if e.endswith(domain)), emails[0] if emails else "")

    def enrich_one(self, lead):
        site = lead.get("website", "")
        if not site or (lead.get("email") and lead.get("phone")):
            return lead
        if not site.startswith("http"):
            site = "http://" + site
        try:
            emails, phones, contact = self._scan(site)
            if not emails and contact and urlparse(contact).netloc == urlparse(site).netloc:
                e2, p2, _ = self._scan(contact)
                emails, phones = emails + e2, phones + p2
        except (ScraperError, Exception):  # unreachable/blocked site -> keep lead as is
            return lead
        if not lead.get("email"):
            lead["email"] = self._best_email(emails, site)
        if not lead.get("phone") and phones:
            lead["phone"] = phones[0]
        return lead

    def enrich_many(self, leads, max_sites=40, progress=None):
        targets = [l for l in leads if l.get("website")][:max_sites]
        done = 0
        with ThreadPoolExecutor(max_workers=5) as pool:
            for _ in pool.map(self.enrich_one, targets):
                done += 1
                if progress:
                    progress(done, len(targets))
        return leads
