"""Tests for email variant templates + tracking (Agent 0 migration)"""

import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.email_variants import (
    TEMPLATES,
    VARIANT_KEYS,
    TrackingManager,
    calculate_burn_rate,
    determine_segment,
    extract_first_name,
    render_email,
    select_variant,
    simple_substitute,
    HAS_JINJA2,
)

requires_jinja2 = pytest.mark.skipif(not HAS_JINJA2, reason="jinja2 not installed")


class TestTemplates:
    """Template registry integrity"""

    def test_four_variants_exist(self):
        assert len(TEMPLATES) == 4

    def test_all_variants_have_subject_and_body(self):
        for key, variant in TEMPLATES.items():
            assert 'name' in variant, f"{key} missing name"
            assert 'subject' in variant, f"{key} missing subject"
            assert 'body' in variant, f"{key} missing body"

    def test_variant_keys_match(self):
        assert VARIANT_KEYS == list(TEMPLATES.keys())


class TestTrackingManager:
    """Tracking pixel + UTM tests"""

    def test_generate_tracking_id_deterministic_per_call_time(self):
        tracker = TrackingManager()
        id1 = tracker.generate_tracking_id("Acme", "variant_a")
        id2 = tracker.generate_tracking_id("Acme", "variant_a")
        # 16-char hex
        assert len(id1) == 16
        assert all(c in '0123456789abcdef' for c in id1)

    def test_create_tracking_pixel_format(self):
        tracker = TrackingManager(base_url="https://example.io")
        pixel = tracker.create_tracking_pixel("Acme", "variant_b")
        assert '<img src="https://example.io/pixel/' in pixel
        assert 'width="1" height="1"' in pixel
        assert 'display:none' in pixel

    def test_add_utm_params(self):
        tracker = TrackingManager()
        url = tracker.add_utm_params("https://loom.com/share/x", "Acme Post", "variant_c")
        assert 'utm_source=cold_email' in url
        assert 'utm_content=variant_c' in url
        assert 'utm_term=acme_post' in url
        assert '?utm_' in url

    def test_add_utm_params_appends_with_ampersand_when_query_exists(self):
        tracker = TrackingManager()
        url = tracker.add_utm_params("https://loom.com/share/x?h=1", "Acme", "variant_a")
        assert '&utm_' in url

    def test_add_utm_params_skips_unrendered_jinja(self):
        tracker = TrackingManager()
        url = tracker.add_utm_params("{{ loom }}", "Acme", "variant_a")
        assert url == "{{ loom }}"

    def test_tracking_log_records_pixels(self):
        tracker = TrackingManager()
        tracker.create_tracking_pixel("Acme", "variant_d")
        assert len(tracker.tracking_log) == 1
        assert tracker.tracking_log[0]['company'] == 'Acme'

    def test_tracking_log_written_to_file(self, tmp_path):
        log_file = tmp_path / "tracking" / "log.jsonl"
        tracker = TrackingManager(log_path=str(log_file))
        tracker.create_tracking_pixel("Acme", "variant_d")
        assert log_file.exists()
        content = log_file.read_text()
        assert 'Acme' in content


class TestEnrichment:
    """Burn rate + segment + name extraction"""

    def test_calculate_burn_rate_volume_100(self):
        assert calculate_burn_rate({'volume': 100}) == "15,000"  # 100*3*50

    def test_calculate_burn_rate_legacy_capitalized_key(self):
        assert calculate_burn_rate({'Volume': 50}) == "7,500"

    def test_calculate_burn_rate_invalid_defaults(self):
        assert calculate_burn_rate({'volume': 'abc'}) == "12,500"
        assert calculate_burn_rate({'volume': None}) == "12,500"
        # Missing keys default to volume=50 -> 7,500
        assert calculate_burn_rate({}) == "7,500"

    def test_determine_segment_audiobook(self):
        assert determine_segment({'segment': 'Audiobook'}) == "Audiobook Publishers"

    def test_determine_segment_post(self):
        assert determine_segment({'segment': 'Post-Production'}) == "Post-Production Houses"

    def test_determine_segment_dubbing(self):
        assert determine_segment({'segment': 'Dubbing'}) == "Localization Studios"

    def test_determine_segment_unknown(self):
        assert determine_segment({'segment': ''}) == "High-Volume Studios"

    def test_extract_first_name(self):
        assert extract_first_name({'name': 'John Doe'}) == 'John'

    def test_extract_first_name_head_of_post_fallback(self):
        assert extract_first_name({'name': 'Head of Post'}) == 'there'

    def test_extract_first_name_empty(self):
        assert extract_first_name({}) == 'there'


@requires_jinja2
class TestRenderEmail:
    """Full email rendering"""

    LEAD = {
        'name': 'John Doe',
        'company': 'Acme Post',
        'segment': 'Post-Production',
        'hook': 'Dolby Atmos 7.1.4',
        'volume': 100,
    }

    def test_render_variant_a(self):
        tracker = TrackingManager()
        subject, body, name = render_email(self.LEAD, 'variant_a_advice', tracker)
        assert name == 'Expertise Request'
        assert 'Question regarding Acme Post workflow' == subject
        assert 'John,' in body
        assert 'Dolby Atmos 7.1.4' in body
        assert '{{' not in body  # All placeholders rendered

    def test_render_variant_b_burn_rate(self):
        tracker = TrackingManager()
        subject, body, name = render_email(self.LEAD, 'variant_b_margin', tracker)
        assert name == 'Margin Erosion'
        assert '$15,000/month' in body
        assert 'tracking' not in subject.lower()

    def test_render_variant_b_includes_pixel(self):
        tracker = TrackingManager()
        _, body, _ = render_email(self.LEAD, 'variant_b_margin', tracker)
        assert '<img src=' in body  # tracking pixel embedded

    def test_render_variant_c_segment(self):
        tracker = TrackingManager()
        _, body, name = render_email(self.LEAD, 'variant_c_tech', tracker)
        assert name == 'Infrastructure Audit'
        assert 'Most Post-Production Houses' in body

    def test_render_variant_d_founding_seat(self):
        tracker = TrackingManager()
        subject, body, name = render_email(self.LEAD, 'variant_d_direct', tracker)
        assert name == 'Founding Seat'
        assert '5 Founding Seats' in body

    def test_render_unknown_variant_raises(self):
        tracker = TrackingManager()
        with pytest.raises(ValueError, match="Unknown variant"):
            render_email(self.LEAD, 'variant_z_fake', tracker)

    def test_render_missing_lead_fields_fallback(self):
        tracker = TrackingManager()
        subject, body, _ = render_email({}, 'variant_a_advice', tracker)
        assert 'Your Studio' in subject
        assert 'there,' in body


class TestSelectVariant:
    """Variant selection strategies"""

    def test_explicit_key(self):
        assert select_variant('variant_a_advice', 0) == 'variant_a_advice'
        assert select_variant('variant_d_direct', 7) == 'variant_d_direct'

    def test_rotate_sequential(self):
        assert select_variant('rotate', 0) == 'variant_a_advice'
        assert select_variant('rotate', 1) == 'variant_b_margin'
        assert select_variant('rotate', 3) == 'variant_d_direct'
        assert select_variant('rotate', 4) == 'variant_a_advice'  # wraps

    def test_unknown_falls_back_to_margin(self):
        assert select_variant('bogus', 0) == 'variant_b_margin'


class TestSimpleSubstitute:
    """Legacy substitution (jinja2-free fallback)"""

    def test_substitutes_name_company_bio(self):
        template = "Hi {name} at {company}. Bio: {bio}"
        lead = {'name': 'Jane', 'company': 'Tech Inc', 'bio': 'A' * 200}
        result = simple_substitute(template, lead)
        assert 'Jane' in result
        assert 'Tech Inc' in result
        assert len(result) < len(template) + 110  # bio truncated to 100

    def test_missing_fields_defaults(self):
        result = simple_substitute("Hi {name}", {})
        assert 'Hi there' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
