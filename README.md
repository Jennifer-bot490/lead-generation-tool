# LeadScout – Web Scraping Lead Generation Tool

Flask + Requests + BeautifulSoup + Pandas. **No Google API, no API keys, no paid services.**

## Folder structure
```
lead-generation-tool/
├── app.py                      # Flask routes, background jobs, rate limiting
├── requirements.txt  .env  .env.example  .gitignore  README.md
├── scrapers/
│   ├── __init__.py             # registry of sources (add new ones here)
│   ├── base_scraper.py         # robots.txt, timeouts, throttling, block detection
│   ├── directory_scraper.py    # OpenStreetMap source + config-driven HTML directory scraper
│   └── business_scraper.py     # reads a company's own website for public email/phone
├── utils/
│   ├── data_cleaning.py        # phone/email/URL validation, N/A, de-duplication
│   └── export.py               # CSV + Excel via Pandas/OpenPyXL
├── templates/index.html
└── static/css/style.css, static/js/script.js
```

## Which sources are used (and why)
- **OpenStreetMap (enabled)**: open data. Its public Nominatim + Overpass services permit automated queries under their usage policy (identify yourself with a contact email, about 1 request/second, no heavy bulk use). Coverage varies by city: phone/website/email exist only when mappers added them, and there are no ratings.
- **Business websites (enrichment)**: for a business that has a website listed, the tool reads its homepage and contact page for a public `mailto:`/`tel:` link, **only if that site's robots.txt allows it**.
- **Commercial directories (not enabled)**: most (Yellow Pages-style sites, Google, Facebook, LinkedIn, etc.) forbid automated collection in their terms. I did not enable any, because I cannot confirm each site's current terms. Check yourself before adding one.

## How the scraper works
1. Your keyword + city go to `/api/search`, which starts a background thread (so the page never freezes) and returns a job id. The browser polls `/api/jobs/<id>`.
2. The city is geocoded to a bounding box (Nominatim). Overpass finds named businesses matching your keyword by OSM category (restaurant, hospital, estate agent…) and by name.
3. Optionally each business website is checked for a public email/phone.
4. `utils/data_cleaning.py` formats phones, validates emails/URLs, removes duplicates and fills `N/A`.
5. Results show in the table; exports use whatever rows your filter currently shows.
Every request goes through `BaseScraper`: robots.txt check, 8–15 s timeout, per-site delay. If a site returns 401/403/429 or disallows bots, the tool stops and tells you. It never bypasses CAPTCHAs, logins or protection.

## Install (Windows PowerShell, Python 3.11.9)
```powershell
cd lead-generation-tool
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Edit `.env` and set `CONTACT_EMAIL` to your real email.

## Run locally
```powershell
python app.py
```
Open http://127.0.0.1:5000

## Test
- `restaurants` in `Lahore` → rows appear, counters change, history is saved.
- Tick "Has email" or type in the filter → table narrows; export CSV/Excel → only shown rows are downloaded.
- Search `xyzxyz` in `Lahore` → a clear "No businesses found" message.
- Search 6 times in one minute → "Too many searches" message.
- Untick "Also read each business's website" → much faster, fewer emails.

## Add another permitted source
1. Read the site's Terms of Service and open `https://site.com/robots.txt`. Continue only if automated access to search/listing pages is allowed. (The tool re-checks robots.txt on every request anyway.)
2. Open the site's search results page in your browser, right-click a listing → *Inspect*, and note the CSS selectors for the listing card and for each field.
3. In `scrapers/__init__.py` uncomment and edit the `SelectorDirectory(...)` example: set `search_url` (with `{keyword}`, `{location}`, `{page}`), `item_selector` and `fields`. Restart the app; it appears in the Source dropdown.
4. For unusual sites, copy `SelectorDirectory` in `directory_scraper.py`, subclass `BaseScraper` and implement `search()`.

## GitHub
```powershell
git init
git add .
git status        # confirm .env is NOT listed
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/lead-generation-tool.git
git push -u origin main
```

## Deploy on Render
1. render.com → **New + → Web Service** → connect the GitHub repo.
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `gunicorn app:app --workers 1 --threads 4 --timeout 120`
   (one worker is required because background jobs are kept in memory)
4. **Environment variables:** `PYTHON_VERSION=3.11.9`, `CONTACT_EMAIL=your real email`, optional `RATE_LIMIT_PER_MIN`, `REQUEST_DELAY`, `DEFAULT_COUNTRY_CODE`.
5. Deploy and open the `onrender.com` URL. Free instances sleep when idle and restart clears running jobs.

## Responsible use
Only publicly listed business contact details are collected. Follow privacy and anti-spam laws (e.g. PECA in Pakistan, GDPR/CAN-SPAM elsewhere) before contacting anyone, and OpenStreetMap data must be credited "© OpenStreetMap contributors" if you publish it.
