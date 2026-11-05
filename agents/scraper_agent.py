"""
Scraper Agent (v2 - Hunter-Killer)

Playwright-based Google Maps scraping with AI qualification via Groq (Llama 3).
Handles lead generation for V2: Ghost Outbound Engine.

Migrated from D:\\[Agent 0]\\studio_acquisition_engine.py

Features:
- Playwright headless Chromium (10x faster and more reliable than Selenium)
- Groq API (free Llama 3 70B) for one-pass qualification
- Deep scan: follows contact pages to extract emails
- Hunter-Killer logic: qualify/reject with segment, hook, email, confidence
"""

import re
import time
import threading
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from core import BaseAgent, Message, Topics, Priority

logger = logging.getLogger(__name__)


@dataclass
class Lead:
    """Qualified lead data"""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    bio: Optional[str] = None
    segment: str = "Unknown"          # Audiobook / Post-Production / Music / Dubbing
    hook: str = ""                    # High-status equipment/credit found by AI
    website: str = ""
    source: str = ""
    source_url: str = ""
    status: str = "QUALIFIED"         # QUALIFIED | SKIP
    reason: str = ""                  # Why qualified or skipped
    confidence: float = 0.0


# ============================================================================
# HTML -> high-density text (for LLM context)
# ============================================================================

def clean_html_content(html_content: str, max_chars: int = 6000) -> str:
    """Strip tags and useless whitespace to give LLM high-density context."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # crude fallback: strip tags with regex
        text = re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>', '', html_content)
        text = re.sub(r'<[^>]+>', ' ', text)
        return re.sub(r'\s+', ' ', text)[:max_chars]

    soup = BeautifulSoup(html_content, 'html.parser')
    for junk in soup(["script", "style", "nav", "footer", "header"]):
        junk.extract()

    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)

    return text[:max_chars]


class StudioQualifier:
    """
    AI Qualification Node (Hunter-Killer).

    Uses Groq (free Llama 3 70B) to classify + extract + hook in ONE call.
    Falls back to a heuristic qualifier if Groq is unavailable.
    """

    MODEL = "llama-3.3-70b-versatile"

    QUALIFY_PROMPT = """You are an Elite Audio Industry Scout. Analyze this website text for '{company_name}'.

TASK:
1. STATUS: Is this a legitimate Audio Post-Production studio, Music Studio, or Game Audio house?
   - REJECT if: Real Estate, Dental, Marketing Agency, Wedding DJ, Home Studio.
2. SEGMENT: Classify as 'Audiobook', 'Post-Production', 'Music', 'Dubbing'.
3. HOOK: Find one specific piece of high-status equipment or credit (e.g. "Dolby Atmos 7.1.4", "Neve Console", "Netflix Credit").
4. CONTACT: Extract the primary email address from the text (e.g. info@..., booking@...). If none, return "".

WEBSITE TEXT:
{website_text}

OUTPUT JSON ONLY:
{{
    "status": "QUALIFIED | SKIP",
    "reason": "Why you qualified or skipped them",
    "segment": "...",
    "hook": "...",
    "email": ""
}}"""

    def __init__(self, agent_log=None):
        self.client = None
        self._log = agent_log or (lambda level, msg: logger.log(
            getattr(logging, level, logging.INFO), msg))
        self._init_groq()

    def _init_groq(self):
        """Initialize Groq client if API key is available."""
        try:
            from groq import Groq
            import os
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key or "REPLACE" in api_key:
                self._log("WARNING", "No GROQ_API_KEY found. AI qualification bypassed "
                                     "(heuristic mode).")
                self.client = None
            else:
                self.client = Groq(api_key=api_key)
                self._log("INFO", f"Groq AI qualification online (model: {self.MODEL})")
        except ImportError:
            self._log("WARNING", "groq package not installed. AI qualification bypassed "
                                 "(heuristic mode).")
            self.client = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def analyze(self, company_name: str, website_text: str) -> Dict[str, Any]:
        """
        One-pass Hunter-Killer analysis.

        Returns dict with: status, reason, segment, hook, email, confidence
        """
        if not self.client:
            return self._heuristic_analyze(company_name, website_text)

        prompt = self.QUALIFY_PROMPT.format(
            company_name=company_name,
            website_text=website_text[:4000],
        )

        try:
            completion = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            import json
            result = json.loads(completion.choices[0].message.content)
            result.setdefault('status', 'QUALIFIED')
            result.setdefault('reason', '')
            result.setdefault('segment', 'Unknown')
            result.setdefault('hook', '')
            result.setdefault('email', '')
            result['confidence'] = 0.9
            return result
        except Exception as e:
            self._log("ERROR", f"Groq analysis failed: {e}")
            heuristic = self._heuristic_analyze(company_name, website_text)
            heuristic['reason'] = f"AI error -> heuristic: {heuristic['reason']}"
            return heuristic

    def _heuristic_analyze(self, company_name: str, website_text: str) -> Dict[str, Any]:
        """Fallback qualifier when no AI available - keyword based."""
        text = (website_text or "").lower()
        name_lower = company_name.lower()

        # Reject patterns
        reject_terms = ['real estate', 'realtor', 'dental', 'dentist', 'marketing agency',
                        'wedding dj', 'roofing', 'plumbing']
        for term in reject_terms:
            if term in name_lower or term in text[:500]:
                return {'status': 'SKIP', 'reason': f'Reject pattern: {term}',
                        'segment': 'Unknown', 'hook': '', 'email': '',
                        'confidence': 0.4}

        # Segment detection
        if 'audiobook' in text:
            segment = 'Audiobook'
        elif 'dubbing' in text or 'localization' in text:
            segment = 'Dubbing'
        elif 'post-production' in text or 'post production' in text:
            segment = 'Post-Production'
        else:
            segment = 'Music'

        # Hook detection (high-status gear/credits)
        hooks = ['dolby atmos', 'neve', 'pro tools', 'ssl', 'avid', 'netflix',
                 'hbo', 'amazon', 'disney', 'uaudio', 'uad']
        hook = ''
        for h in hooks:
            if h in text:
                hook = h.title()
                break

        # Email extraction
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', website_text or '')
        email = email_match.group(0) if email_match else ''

        return {'status': 'QUALIFIED', 'reason': 'Heuristic match',
                'segment': segment, 'hook': hook, 'email': email,
                'confidence': 0.5}


class ScraperAgent(BaseAgent):
    """
    Hunter-Killer Scraping Agent using Playwright + Groq.

    V2 Features:
    - Google Maps lead harvesting by query (city + niche)
    - AI qualification in one pass (Groq/Llama 3, heuristic fallback)
    - Deep scan for contact pages and email extraction
    - Rate limiting between page visits
    """

    SEARCH_QUERY_DEFAULT = "Audio Post Production Studio"
    MAX_RESULTS_PER_QUERY = 8      # Quality over quantity
    MAX_DEEP_SCANS = 20            # Per job; deep scans are slow
    FEED_SCROLLS = 3               # Google Maps feed scroll rounds
    LISTING_SELECTOR = 'div[class*="Nv2PK"]'

    def __init__(self):
        super().__init__(
            agent_id="scraper_agent",
            agent_name="Hunter-Killer Scraper Agent"
        )

        # Playwright browser (lazy-initialized, one per job batch)
        self._playwright = None
        self._browser = None
        self._browser_lock = threading.Lock()

        # Rate limiting
        self._last_request = 0.0
        self._min_delay = 2.0  # seconds between page visits

        # AI qualifier (created lazily in setup)
        self._qualifier: Optional[StudioQualifier] = None

        # Job counter for deep scan limits
        self._deep_scans_used = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self):
        """Initialize scraper agent"""
        self.subscribe(Topics.SCRAPER_JOB_START)

        # Lazy: qualifier init is cheap (no network on init)
        self._qualifier = StudioQualifier(agent_log=self.log)

        self.log("INFO", "Hunter-Killer Scraper Agent initialized "
                         f"(AI qualifier available: {self._qualifier.available})")

    def teardown(self):
        """Cleanup scraper agent"""
        self._close_browser()
        self.log("INFO", "Scraper Agent shutdown complete")

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def handle_message(self, message: Message):
        """Process scraper messages"""
        try:
            if message.topic == Topics.SCRAPER_JOB_START:
                self._handle_scrape_job(message)
            else:
                self.log("DEBUG", f"Unhandled topic: {message.topic}")
        except Exception as e:
            self.log("ERROR", f"Error handling message: {e}")

    def _handle_scrape_job(self, message: Message):
        """
        Handle scraping job request.

        Expected payload:
            - query: Search query, e.g. "Audio Post Production Studio in Los Angeles"
              (optional; defaults to SEARCH_QUERY_DEFAULT + 'city' or TARGET_CITIES)
            - city: Optional city to append to default query
            - max_results: Max qualified leads per query (default: 8)
            - headless: Run browser headless (default: True)
        """
        payload = message.payload
        query = payload.get('query', '')
        city = payload.get('city', '')
        max_results = int(payload.get('max_results', self.MAX_RESULTS_PER_QUERY))
        headless = payload.get('headless', True)

        # Build query from parts if not given directly
        if not query:
            base = payload.get('search_query', self.SEARCH_QUERY_DEFAULT)
            query = f"{base} in {city}" if city else base

        # Validate Playwright availability before launching a browser job
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            self.respond(message, {
                'success': False,
                'error': "playwright not installed. Run: pip install playwright "
                         "&& playwright install chromium",
            })
            return

        self.log("INFO", f"Starting Hunter-Killer scrape: {query}")

        self._deep_scans_used = 0
        started = time.time()

        try:
            leads = self._harvest(query, max_results, headless)
            elapsed = time.time() - started

            # Publish results for outbound agent
            self.publish(Topics.SCRAPER_LEADS_FOUND, {
                'source': 'google_maps',
                'query': query,
                'leads': [self._lead_to_dict(l) for l in leads],
                'count': len(leads),
                'elapsed': elapsed,
            })

            self.publish(Topics.SCRAPER_JOB_COMPLETE, {
                'query': query,
                'leads_found': len(leads),
                'elapsed': elapsed,
            })

            self.respond(message, {
                'success': True,
                'leads_found': len(leads),
                'elapsed': elapsed,
            })

            self.log("INFO", f"Scrape complete: {len(leads)} qualified leads "
                             f"in {elapsed:.1f}s")

        except Exception as e:
            self.publish(Topics.SCRAPER_JOB_FAILED, {
                'query': query,
                'error': str(e),
            })
            self.respond(message, {'success': False, 'error': str(e)})
            self.log("ERROR", f"Scrape failed: {e}")

        finally:
            # Close browser after each job to avoid stale contexts
            self._close_browser()

    # ------------------------------------------------------------------
    # Harvesting
    # ------------------------------------------------------------------

    def _harvest(self, query: str, max_results: int, headless: bool) -> List[Lead]:
        """Run the full harvest: Maps scrape -> deep scan -> AI qualify."""
        from playwright.sync_api import sync_playwright

        leads: List[Lead] = []
        seen_names = set()

        with sync_playwright() as p:
            with self._browser_lock:
                self._playwright = p
                self._browser = p.chromium.launch(headless=headless)

            context = self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            maps_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
            try:
                page.goto(maps_url, timeout=60_000)
                page.wait_for_timeout(3_000)
            except Exception:
                self.log("WARNING", "Maps timeout - grabbing whatever is visible")

            # Scroll the feed to load more listings
            try:
                feed = page.locator('div[role="feed"]')
                feed.wait_for(timeout=5_000)
                for _ in range(self.FEED_SCROLLS):
                    feed.evaluate("node => node.scrollTop += 2000")
                    page.wait_for_timeout(1_000)
            except Exception:
                self.log("WARNING", "Feed scroll issue - grabbing visible listings")

            listings = page.locator(self.LISTING_SELECTOR).all()
            self.log("INFO", f"Detected {len(listings)} signals. "
                             "Engaging Hunter-Killer logic...")

            count = 0
            for listing in listings:
                if count >= max_results:
                    break
                if self._deep_scans_used >= self.MAX_DEEP_SCANS:
                    self.log("WARNING", "Deep scan budget exhausted - stopping")
                    break

                try:
                    lead = self._process_listing(page, listing, query, seen_names)
                    if lead and lead.status == 'QUALIFIED':
                        leads.append(lead)
                        count += 1
                        self.log("INFO", f"QUALIFIED: {lead.company} "
                                         f"[{lead.segment}] hook={lead.hook!r} "
                                         f"email={lead.email!r}")
                    elif lead:
                        self.log("DEBUG", f"KILL: {lead.company} - {lead.reason}")
                except Exception as e:
                    self.log("DEBUG", f"Listing processing error: {e}")
                    continue

            context.close()

        return leads

    def _process_listing(self, page, listing, query: str,
                         seen_names: set) -> Optional[Lead]:
        """Extract + qualify a single Maps listing."""
        text_lines = listing.inner_text().split('\n')
        company_name = text_lines[0].strip() if text_lines else ''
        if not company_name or company_name in seen_names:
            return None
        seen_names.add(company_name)

        # Extract website from card links
        website = ""
        try:
            for link in listing.locator('a').all():
                href = link.get_attribute('href') or ''
                if href and 'google' not in href and href.startswith('http'):
                    website = href
                    break
        except Exception:
            pass

        # Hunter-Killer sequence: deep scan homepage (+ contact page)
        site_text = ""
        if website:
            self._wait_for_rate_limit()
            self.log("INFO", f"Inspecting: {company_name} ({website})")
            try:
                site_page = page.context.new_page()
                try:
                    site_page.goto(website, timeout=10_000)
                    site_text = clean_html_content(site_page.content())

                    # Deep scan: find contact page
                    contact_url = self._find_contact_url(site_page, website)
                    if contact_url:
                        self.log("INFO", f"Deep scan: visiting {contact_url}")
                        self._deep_scans_used += 1
                        try:
                            site_page.goto(contact_url, timeout=8_000)
                            site_text += "\n" + clean_html_content(site_page.content())
                        except Exception:
                            self.log("DEBUG", "Deep scan failed (timeout) - using homepage")
                finally:
                    site_page.close()
            except Exception as e:
                self.log("WARNING", f"Site scan failed: {e}")
        else:
            self.log("DEBUG", f"No website for {company_name} - presuming target")

        # AI qualification
        analysis = self._qualifier.analyze(company_name, site_text)

        return Lead(
            name="Head of Post",
            company=company_name,
            email=analysis.get('email') or None,
            segment=analysis.get('segment', 'Unknown'),
            hook=analysis.get('hook', ''),
            website=website,
            source='google_maps',
            source_url=query,
            status=analysis.get('status', 'QUALIFIED'),
            reason=analysis.get('reason', ''),
            confidence=analysis.get('confidence', 0.0),
        )

    def _find_contact_url(self, site_page, website: str) -> Optional[str]:
        """Find a contact/about link on the page and resolve it to an absolute URL."""
        try:
            link = site_page.get_by_text(re.compile("contact", re.IGNORECASE)).first
            if link.count() == 0:
                return None
            href = link.get_attribute('href')
            if not href:
                return None
            if href.startswith('/'):
                return website.rstrip('/') + href
            if href.startswith('http'):
                return href
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Browser + rate limit helpers
    # ------------------------------------------------------------------

    def _close_browser(self):
        """Close Playwright browser if open."""
        with self._browser_lock:
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None
            self._playwright = None

    def _wait_for_rate_limit(self):
        """Wait to respect rate limiting between page visits."""
        elapsed = time.time() - self._last_request
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request = time.time()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _lead_to_dict(self, lead: Lead) -> Dict:
        """Convert Lead to dictionary (message-bus payload)."""
        return {
            'name': lead.name,
            'email': lead.email,
            'phone': lead.phone,
            'company': lead.company,
            'bio': lead.bio,
            'segment': lead.segment,
            'hook': lead.hook,
            'website': lead.website,
            'source': lead.source,
            'source_url': lead.source_url,
            'status': lead.status,
            'reason': lead.reason,
            'confidence': lead.confidence,
        }
