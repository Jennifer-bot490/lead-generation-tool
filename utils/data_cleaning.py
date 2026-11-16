"""Clean + validate leads. Missing values become 'N/A' (never invented)."""
import re
from urllib.parse import urlparse

NA = "N/A"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


def clean_phone(raw, cc="92"):
    """'0300-1234567' -> '+92 300 1234567'. Returns '' if it doesn't look like a phone."""
    first = (raw or "").split(";")[0].split(",")[0].strip()
    digits = re.sub(r"\D", "", first)
    if first.startswith("+"):
        digits = digits
    elif digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and cc:
        digits = cc + digits[1:]
    if not 8 <= len(digits) <= 15:
        return ""
    if cc and digits.startswith(cc):
        rest = digits[len(cc):]
        return f"+{cc} {rest[:3]} {rest[3:]}" if len(rest) >= 8 else f"+{cc} {rest}"
    return "+" + digits


def clean_email(raw):
    e = (raw or "").split(";")[0].strip().lower()
    return e if EMAIL_RE.match(e) else ""


def clean_website(raw):
    u = (raw or "").split(";")[0].strip()
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "http://" + u
    p = urlparse(u)
    return u if "." in p.netloc and " " not in u else ""


def domain(url):
    return urlparse(url).netloc.lower().replace("www.", "") if url else ""


def clean_lead(raw, cc="92"):
    name = " ".join((raw.get("name") or "").split())
    if not name:
        return None
    lead = {
        "name": name, "phone": clean_phone(raw.get("phone"), cc), "email": clean_email(raw.get("email")),
        "website": clean_website(raw.get("website")), "address": " ".join((raw.get("address") or "").split()),
        "city": (raw.get("city") or "").strip(), "category": (raw.get("category") or "").strip(),
        "source": (raw.get("source") or "").strip(),
    }
    return lead


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def deduplicate(leads):
    """Same name + same address, same name + same phone, or (no address) same name + same website."""
    kept, index = [], {}
    for lead in leads:
        n = _norm(lead["name"])
        keys = []
        if lead["address"]:
            keys.append((n, _norm(lead["address"])))
        if lead["phone"]:
            keys.append((n, lead["phone"]))
        if lead["website"] and not lead["address"]:
            keys.append((n, domain(lead["website"])))
        keys = keys or [(n,)]
        hit = next((index[k] for k in keys if k in index), None)
        if hit is not None:                       # duplicate -> merge any missing fields
            for f, v in lead.items():
                if v and not kept[hit][f]:
                    kept[hit][f] = v
            continue
        kept.append(lead)
        for k in keys:
            index[k] = len(kept) - 1
    return kept


def finalize(leads):
    """Replace empty values with N/A for display/export."""
    return [{k: (v or NA) for k, v in l.items()} for l in leads]
