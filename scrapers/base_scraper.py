"""Base class: polite HTTP client that obeys robots.txt, timeouts and rate limits.

It NEVER tries to bypass CAPTCHAs, logins or anti-bot protection. If a site says no
(robots.txt, 403, 429, ...) we stop and report it.
"""
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests


class ScraperError(Exception):
    """A problem we can explain to the user in plain language."""


class BaseScraper:
    name = "base"
    label = "Base"
    BOT_NAME = "LeadScoutBot"

    def __init__(self, contact_email="", delay=1.5, timeout=15):
        self.delay, self.timeout = delay, timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"{self.BOT_NAME}/1.0 (contact: {contact_email or 'not-set'})",
            "Accept-Language": "en",
        })
        self._robots, self._last_hit = {}, {}

    # ---- politeness helpers
    def _throttle(self, host):
        """Wait so we hit the same host at most once every `delay` seconds."""
        wait = self.delay - (time.time() - self._last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.time()

    def allowed(self, url):
        """True only if the site's robots.txt lets our bot fetch this URL."""
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        rp = self._robots.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._throttle(p.netloc)
                r = self.session.get(base + "/robots.txt", timeout=self.timeout)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                elif r.status_code < 400 or 404 <= r.status_code < 500 and r.status_code not in (401, 403):
                    rp.allow_all = True       # no robots.txt => allowed
                else:
                    rp.disallow_all = True    # 401/403/5xx => be conservative
            except requests.RequestException:
                rp.disallow_all = True        # can't read the rules => don't scrape
            self._robots[base] = rp
        return rp.can_fetch(self.BOT_NAME, url)

    def get(self, url, **kwargs):
        """robots.txt-checked, throttled GET. Raises ScraperError with a clear reason."""
        host = urlparse(url).netloc
        if not self.allowed(url):
            raise ScraperError(f"{host} does not allow automated access (robots.txt). Source skipped.")
        self._throttle(host)
        try:
            r = self.session.get(url, timeout=self.timeout, **kwargs)
        except requests.Timeout:
            raise ScraperError(f"{host} took too long to respond.")
        except requests.RequestException:
            raise ScraperError(f"{host} could not be reached.")
        if r.status_code in (401, 403, 429):
            raise ScraperError(f"{host} blocked automated access (HTTP {r.status_code}). "
                               "We do not bypass blocks - use another source.")
        if r.status_code >= 400:
            raise ScraperError(f"{host} returned HTTP {r.status_code}.")
        return r

    def search(self, keyword, location, limit):
        """Return a list of dicts: name, phone, email, website, address, city, category, source."""
        raise NotImplementedError
