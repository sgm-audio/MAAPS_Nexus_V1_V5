"""Tests for ScraperAgent v2 (Hunter-Killer: Playwright + Groq)"""

import pytest
import time
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core import MessageBus, Message, Topics, Priority
from agents.scraper_agent import ScraperAgent, StudioQualifier, Lead, clean_html_content


class MockConfig:
    """Mock configuration for testing"""
    def __init__(self):
        self.groq_api_key = ""  # No AI by default -> heuristic mode


@pytest.fixture
def message_bus():
    """Create a fresh MessageBus for each test"""
    if MessageBus._instance:
        MessageBus._instance.stop()
        MessageBus._instance = None
    bus = MessageBus()
    bus.start()
    yield bus
    bus.stop()
    MessageBus._instance = None


@pytest.fixture
def mock_config():
    return MockConfig()


@pytest.fixture
def mock_playwright():
    """Insert a fake playwright module since it may not be installed locally"""
    import sys
    import types
    fake_playwright = types.ModuleType('playwright')
    fake_sync_api = types.ModuleType('playwright.sync_api')
    fake_sync_api.sync_playwright = MagicMock()
    fake_playwright.sync_api = fake_sync_api
    created = []
    if 'playwright' not in sys.modules:
        sys.modules['playwright'] = fake_playwright
        created.append('playwright')
    if 'playwright.sync_api' not in sys.modules:
        sys.modules['playwright.sync_api'] = fake_sync_api
        created.append('playwright.sync_api')
    yield fake_sync_api
    for name in created:
        del sys.modules[name]


@pytest.fixture
def scraper_agent(message_bus, mock_config, mock_playwright):
    """Create ScraperAgent without starting Playwright"""
    with patch('core.config.Config.from_env', return_value=mock_config):
        with patch('core.message_bus.get_bus', return_value=message_bus):
            agent = ScraperAgent()
            agent.setup()
            yield agent
            agent.teardown()


class TestCleanHtmlContent:
    """Tests for HTML cleaning utility"""

    def test_strips_script_and_style(self):
        html = "<html><head><style>.x{}</style></head><body><p>Hello</p><script>bad()</script></body></html>"
        result = clean_html_content(html)
        assert "Hello" in result
        assert "bad()" not in result
        assert ".x{}" not in result

    def test_truncates_to_limit(self):
        html = "<p>" + ("word " * 5000) + "</p>"
        result = clean_html_content(html, max_chars=100)
        assert len(result) <= 100

    def test_fallback_without_bs4(self):
        """Regex fallback when bs4 unavailable"""
        with patch.dict('sys.modules', {'bs4': None}):
            html = "<html><body><p>Test Content</p></body></html>"
            result = clean_html_content(html)
            assert "Test Content" in result


class TestStudioQualifier:
    """Tests for AI qualification node"""

    def test_heuristic_rejects_non_audio(self):
        """Heuristic mode rejects non-audio businesses"""
        qualifier = StudioQualifier()  # No GROQ key -> heuristic
        result = qualifier.analyze("Premier Dental Clinic", "We do teeth cleanings")
        assert result['status'] == 'SKIP'
        assert 'dental' in result['reason'].lower()

    def test_heuristic_qualifies_audio(self):
        qualifier = StudioQualifier()
        text = "Post-production studio with Dolby Atmos mixing. Contact info@studio.com"
        result = qualifier.analyze("Acme Post", text)
        assert result['status'] == 'QUALIFIED'
        assert result['segment'] == 'Post-Production'
        assert 'atmos' in result['hook'].lower()
        assert result['email'] == 'info@studio.com'

    def test_heuristic_email_extraction(self):
        qualifier = StudioQualifier()
        result = qualifier.analyze("Studio X", "Email us at booking@studiox.ca today")
        assert result['email'] == 'booking@studiox.ca'

    def test_heuristic_segment_audiobook(self):
        qualifier = StudioQualifier()
        result = qualifier.analyze("Books Audio", "We produce audiobooks for publishers")
        assert result['segment'] == 'Audiobook'

    def test_heuristic_segment_dubbing(self):
        qualifier = StudioQualifier()
        result = qualifier.analyze("Dub House", "Dubbing and localization services")
        assert result['segment'] == 'Dubbing'

    @patch('agents.scraper_agent.StudioQualifier._init_groq')
    def test_groq_success(self, mock_init):
        """AI mode returns parsed JSON with confidence"""
        qualifier = StudioQualifier()
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = (
            '{"status": "QUALIFIED", "reason": "Real studio", '
            '"segment": "Music", "hook": "Neve Console", "email": "a@b.com"}'
        )
        mock_client.chat.completions.create.return_value = mock_completion
        qualifier.client = mock_client

        result = qualifier.analyze("Acme Music", "some site text")
        assert result['status'] == 'QUALIFIED'
        assert result['segment'] == 'Music'
        assert result['hook'] == 'Neve Console'
        assert result['confidence'] == 0.9

    @patch('agents.scraper_agent.StudioQualifier._init_groq')
    def test_groq_error_falls_back_to_heuristic(self, mock_init):
        """AI failure falls back to heuristic with note in reason"""
        qualifier = StudioQualifier()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API down")
        qualifier.client = mock_client

        text = "Post-production with Dolby Atmos. info@x.com"
        result = qualifier.analyze("Acme", text)
        assert result['status'] == 'QUALIFIED'  # heuristic qualifies
        assert 'heuristic' in result['reason'].lower()

    def test_available_property(self):
        qualifier = StudioQualifier()
        assert qualifier.available == (qualifier.client is not None)


class TestScraperAgentSetup:
    """Tests for agent lifecycle"""

    def test_setup_subscribes_to_job_start(self, scraper_agent):
        assert Topics.SCRAPER_JOB_START in scraper_agent._subscribed_topics

    def test_qualifier_created(self, scraper_agent):
        assert scraper_agent._qualifier is not None

    def test_teardown_closes_browser(self, scraper_agent):
        # Should not raise even if browser never opened
        scraper_agent.teardown()


class TestScraperAgentJobHandling:
    """Tests for scrape job message handling"""

    def test_default_query_applied_when_empty(self, scraper_agent, message_bus):
        """Empty payload uses default search query and completes successfully"""
        responses = []

        def capture(msg):
            if msg.topic.endswith('.response'):
                responses.append(msg.payload)

        message_bus.subscribe(Topics.SCRAPER_JOB_START + '.response', capture)

        with patch.object(scraper_agent, '_harvest', return_value=[]) as mock_harvest:
            msg = Message(
                topic=Topics.SCRAPER_JOB_START,
                payload={},  # No query, no city -> default
                sender='test',
            )
            scraper_agent.handle_message(msg)
            time.sleep(0.1)

            # Default query was used
            called_query = mock_harvest.call_args[0][0]
            assert scraper_agent.SEARCH_QUERY_DEFAULT in called_query

            assert len(responses) == 1
            assert responses[0]['success'] is True
            assert responses[0]['leads_found'] == 0

    @patch('playwright.sync_api.sync_playwright')
    def test_harvest_error_publishes_failure(self, mock_pw, scraper_agent, message_bus):
        """Playwright runtime failure -> SCRAPER_JOB_FAILED + failed response"""
        mock_pw.side_effect = Exception("browser launch failed")

        failures = []
        responses = []
        message_bus.subscribe(Topics.SCRAPER_JOB_FAILED, lambda m: failures.append(m.payload))
        message_bus.subscribe(Topics.SCRAPER_JOB_START + '.response',
                              lambda m: responses.append(m.payload))

        msg = Message(
            topic=Topics.SCRAPER_JOB_START,
            payload={'query': 'Audio Post Production Studio in Los Angeles'},
            sender='test',
        )
        scraper_agent.handle_message(msg)
        time.sleep(0.2)

        assert len(failures) == 1
        assert len(responses) == 1
        assert responses[0]['success'] is False

    def test_query_from_city(self, scraper_agent, message_bus):
        """Query built from city when query not provided"""
        captured = {}

        def capture(msg):
            if msg.topic.endswith('.response'):
                captured['payload'] = msg.payload

        message_bus.subscribe(Topics.SCRAPER_JOB_START + '.response', capture)

        # Patch _harvest to capture the query and return empty
        with patch.object(scraper_agent, '_harvest', return_value=[]) as mock_harvest:
            msg = Message(
                topic=Topics.SCRAPER_JOB_START,
                payload={'city': 'Nashville'},
                sender='test',
            )
            scraper_agent.handle_message(msg)
            time.sleep(0.1)

            # Verify query was built from city
            called_query = mock_harvest.call_args[0][0]
            assert 'Nashville' in called_query
            assert 'Audio Post Production Studio' in called_query


class TestLeadSerialization:
    """Tests for lead serialization"""

    def test_lead_to_dict(self, scraper_agent):
        lead = Lead(
            name="Head of Post",
            company="Acme Post",
            email="info@acme.com",
            segment="Post-Production",
            hook="Dolby Atmos",
            website="https://acme.com",
            source="google_maps",
            source_url="test query",
            status="QUALIFIED",
            reason="Real studio",
            confidence=0.9,
        )
        d = scraper_agent._lead_to_dict(lead)
        assert d['company'] == 'Acme Post'
        assert d['segment'] == 'Post-Production'
        assert d['hook'] == 'Dolby Atmos'
        assert d['confidence'] == 0.9
        assert d['email'] == 'info@acme.com'


class TestRateLimiting:
    """Tests for rate limiting"""

    def test_wait_for_rate_limit(self, scraper_agent):
        start = time.time()
        scraper_agent._last_request = time.time() - 10  # Long ago -> no wait
        scraper_agent._wait_for_rate_limit()
        assert time.time() - start < 0.5  # Should not have waited


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
