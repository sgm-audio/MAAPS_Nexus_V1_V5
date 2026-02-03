"""
Scraper Agent

Web scraping agent using Selenium for dynamic content.
Handles lead generation for V2: Ghost Outbound Engine.
"""

import time
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

from core import BaseAgent, Message, Topics, Priority

logger = logging.getLogger(__name__)


@dataclass
class Lead:
    """Scraped lead data"""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    bio: Optional[str] = None
    source: str = ""
    source_url: str = ""


class ScraperAgent(BaseAgent):
    """
    Web Scraping Agent using Selenium.
    
    V2 Features:
    - Realtor.ca lead scraping
    - Dynamic JS page rendering
    - Lead extraction and parsing
    - Rate limiting and anti-detection
    """
    
    def __init__(self):
        super().__init__(
            agent_id="scraper_agent",
            agent_name="Selenium Scraper Agent"
        )
        
        # Selenium driver
        self._driver = None
        self._driver_lock = threading.Lock()
        
        # Rate limiting
        self._last_request = 0.0
        self._min_delay = 2.0  # seconds between requests
    
    def setup(self):
        """Initialize scraper agent"""
        self.subscribe(Topics.SCRAPER_JOB_START)
        
        # Initialize Selenium connection
        self._init_driver()
        
        self.log("INFO", "Scraper Agent initialized")
    
    def teardown(self):
        """Cleanup scraper agent"""
        self._close_driver()
        self.log("INFO", "Scraper Agent shutdown complete")
    
    def handle_message(self, message: Message):
        """Process scraper messages"""
        try:
            if message.topic == Topics.SCRAPER_JOB_START:
                self._handle_scrape_job(message)
            else:
                self.log("DEBUG", f"Unhandled topic: {message.topic}")
        except Exception as e:
            self.log("ERROR", f"Error handling message: {e}")
    
    def _init_driver(self):
        """Initialize Selenium WebDriver"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            
            # User agent rotation
            options.add_argument(
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
            
            # Connect to Selenium Grid
            selenium_url = self.config.selenium_url
            
            with self._driver_lock:
                self._driver = webdriver.Remote(
                    command_executor=selenium_url,
                    options=options
                )
            
            self.log("INFO", f"Connected to Selenium at {selenium_url}")
        
        except Exception as e:
            self.log("WARNING", f"Could not connect to Selenium: {e}")
            self._driver = None
    
    def _close_driver(self):
        """Close Selenium WebDriver"""
        with self._driver_lock:
            if self._driver:
                try:
                    self._driver.quit()
                except:
                    pass
                self._driver = None
    
    def _handle_scrape_job(self, message: Message):
        """
        Handle scraping job request.
        
        Expected payload:
            - target: Target type ('realtor', 'custom')
            - url: URL to scrape
            - selectors: CSS selectors for data extraction
        """
        payload = message.payload
        target = payload.get('target', 'custom')
        url = payload.get('url', '')
        
        if not url:
            self.respond(message, {
                'success': False,
                'error': 'No URL provided'
            })
            return
        
        self.log("INFO", f"Starting scrape: {target} - {url}")
        
        # Rate limiting
        self._wait_for_rate_limit()
        
        try:
            if target == 'realtor':
                leads = self._scrape_realtor(url)
            else:
                leads = self._scrape_custom(url, payload.get('selectors', {}))
            
            # Publish results
            self.publish(Topics.SCRAPER_LEADS_FOUND, {
                'source': target,
                'url': url,
                'leads': [self._lead_to_dict(l) for l in leads],
                'count': len(leads)
            })
            
            self.publish(Topics.SCRAPER_JOB_COMPLETE, {
                'url': url,
                'leads_found': len(leads)
            })
            
            self.respond(message, {
                'success': True,
                'leads_found': len(leads)
            })
            
            self.log("INFO", f"Scrape complete: {len(leads)} leads found")
        
        except Exception as e:
            self.publish(Topics.SCRAPER_JOB_FAILED, {
                'url': url,
                'error': str(e)
            })
            
            self.respond(message, {
                'success': False,
                'error': str(e)
            })
            
            self.log("ERROR", f"Scrape failed: {e}")
    
    def _wait_for_rate_limit(self):
        """Wait to respect rate limiting"""
        elapsed = time.time() - self._last_request
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request = time.time()
    
    def _scrape_realtor(self, url: str) -> List[Lead]:
        """Scrape Realtor.ca for agent leads"""
        leads = []
        
        with self._driver_lock:
            if not self._driver:
                raise Exception("Selenium not available")
            
            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                self._driver.get(url)
                
                # Wait for page to load
                time.sleep(5)  # Allow JS to render
                
                # Find agent cards (selector may need adjustment)
                cards = self._driver.find_elements(By.CSS_SELECTOR, 
                    "div[class*='agent'], div[class*='realtor'], .member-card")
                
                for card in cards[:20]:  # Limit to first 20
                    try:
                        name = self._safe_find_text(card, ".name, h3, h4")
                        phone = self._safe_find_text(card, ".phone, [href^='tel:']")
                        email = self._safe_find_text(card, ".email, [href^='mailto:']")
                        company = self._safe_find_text(card, ".brokerage, .company")
                        
                        if name:
                            leads.append(Lead(
                                name=name,
                                phone=phone,
                                email=email,
                                company=company,
                                source='realtor.ca',
                                source_url=url
                            ))
                    except:
                        continue
            
            except Exception as e:
                self.log("ERROR", f"Realtor scrape error: {e}")
        
        return leads
    
    def _scrape_custom(self, url: str, selectors: Dict) -> List[Lead]:
        """Scrape custom URL with provided selectors"""
        leads = []
        
        with self._driver_lock:
            if not self._driver:
                raise Exception("Selenium not available")
            
            try:
                self._driver.get(url)
                time.sleep(3)
                
                # Get page content
                page_source = self._driver.page_source
                
                # Basic extraction - can be enhanced
                leads.append(Lead(
                    name="Custom Scrape",
                    source='custom',
                    source_url=url,
                    bio=f"Page loaded: {len(page_source)} chars"
                ))
            
            except Exception as e:
                self.log("ERROR", f"Custom scrape error: {e}")
        
        return leads
    
    def _safe_find_text(self, element, selectors: str) -> Optional[str]:
        """Safely find text by multiple selectors"""
        from selenium.webdriver.common.by import By
        
        for selector in selectors.split(','):
            selector = selector.strip()
            try:
                el = element.find_element(By.CSS_SELECTOR, selector)
                text = el.text.strip()
                if text:
                    return text
            except:
                continue
        return None
    
    def _lead_to_dict(self, lead: Lead) -> Dict:
        """Convert Lead to dictionary"""
        return {
            'name': lead.name,
            'email': lead.email,
            'phone': lead.phone,
            'company': lead.company,
            'bio': lead.bio,
            'source': lead.source,
            'source_url': lead.source_url
        }
