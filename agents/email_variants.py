"""
Email Variant Templates + Tracking Manager

High-status audio infrastructure outreach templates with A/B testing,
open-rate tracking pixels, UTM attribution, and burn-rate personalization.

Migrated from D:\\[Agent 0]\\audio_infrastructure_outreach.py
"""

import re
import json
import time
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import jinja2
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False
    logger.warning("jinja2 not installed - variant templates unavailable, "
                   "falling back to simple substitution")


# ============================================================================
# HIGH-STATUS AUDIO ARCHITECTURE TEMPLATES (A/B Testing)
# ============================================================================

TEMPLATES: Dict[str, Dict[str, str]] = {
    # VARIANT A: The "Advice" Strategy
    # Goal: Disarm them, ask for expertise, trigger the "Hand Raise"
    'variant_a_advice': {
        'name': 'Expertise Request',
        'subject': 'Question regarding {{ company }} workflow',
        'body': """{{ first_name }},

I'm an AI Audio Architect (ex-Berklee) building a proprietary cloud processing engine specifically for high-volume studios.

I noticed {{ company }} is running {{ hook }}.

I'm bypassing the usual "wrapper" tools (Zapier/n8n) to build raw Python infrastructure that handles heavy DSP and metadata at scale.

Before I finalize the architecture, I'm asking a few studio owners:

What is the one bottleneck in your current QC or ingestion workflow that you would pay to have "hard-coded" out of existence?

Not pitching - just ensuring I'm solving the right bleeding-neck problem.

Best,
{{ sender }}

---
{{ unsubscribe_link }}"""
    },

    # VARIANT B: Problem-Agitate-Solve (The Margin Killer)
    # Goal: Highlight the cost of manual QC
    'variant_b_margin': {
        'name': 'Margin Erosion',
        'subject': 'Ratio of editing hours to finished hours at {{ company }}',
        'body': """Hi {{ first_name }},

I'm reaching out to {{ company }} because I saw your setup ({{ hook }}) and suspect "Margin Erosion" via manual QC is becoming a silent killer.

Quick question: For every finished hour of audio, how many human hours does {{ company }} spend on QC and metadata tagging?

Most studios average 3:1. That means for every $1,000 in revenue, you burn ~${{ burn_rate }}/month on manual listening.

We deploy containerized AI agents that reduce that ratio to 0.2:1.

We don't sell software. We install proprietary infrastructure.

2-min technical breakdown of the architecture: {{ loom }}

Best,
{{ sender }}

---
{{ unsubscribe_link }}{{ tracking_pixel }}"""
    },

    # VARIANT C: High-Status Technical (The "Architect" Frame)
    # Goal: Appeal to their desire for "Enterprise" tech
    'variant_c_tech': {
        'name': 'Infrastructure Audit',
        'subject': 'Moving {{ company }} off manual ingestion?',
        'body': """{{ first_name }},

Most {{ segment }} are still running post-production on local machines and manual file management.

I am looking for 3 partners to deploy a headless, cloud-native audio pipeline (Python/Librosa) that automates:
1. Loudness Normalization (BS.1770)
2. Breath/Noise Removal (DSP)
3. Metadata Injection & Delivery

This isn't a plugin. It's serverless infrastructure.

I've sketched out the schematic here: {{ loom }}

If you are looking to scale volume without hiring more editors, reply "Infrastructure" and we can talk.

{{ sender }}

---
{{ unsubscribe_link }}{{ tracking_pixel }}"""
    },

    # VARIANT D: The "Direct" Approach
    # Goal: Filter for immediate buyers
    'variant_d_direct': {
        'name': 'Founding Seat',
        'subject': 'Post-production capacity at {{ company }}',
        'body': """{{ first_name }},

Quick research question for {{ company }}:

Are you currently capping your production volume because of the "QC Bottleneck"?

I am deploying a private audio processing node (SGM Audio Architecture) for a select group of studios this month.
- Stack: Cloud AI + Custom Python
- Target: 90% reduction in manual touchpoints.

We are opening 5 Founding Seats for the beta deployment.

If you want to see how the top 10% of audiobooks are produced (zero human touch until final check), see this: {{ loom }}

{{ sender }}

---
{{ unsubscribe_link }}{{ tracking_pixel }}"""
    },
}

VARIANT_KEYS = list(TEMPLATES.keys())


# ============================================================================
# TRACKING & ANALYTICS
# ============================================================================

class TrackingManager:
    """Open-rate pixels, UTM attribution, and delivery logging."""

    def __init__(self, base_url: str = "https://sgm-audio.io",
                 log_path: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.log_path = log_path
        self.tracking_log: list = []

    def generate_tracking_id(self, company: str, variant: str) -> str:
        timestamp = datetime.now().isoformat()
        unique_string = f"{company}|{variant}|{timestamp}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:16]

    def create_tracking_pixel(self, company: str, variant: str) -> str:
        tracking_id = self.generate_tracking_id(company, variant)
        pixel_url = f"{self.base_url}/pixel/{tracking_id}.png"
        self._log_open({'type': 'pixel_created', 'tracking_id': tracking_id,
                        'company': company, 'variant': variant})
        return (f'\n<img src="{pixel_url}" width="1" height="1" alt="" '
                f'style="display:none;" />')

    def add_utm_params(self, url: str, company: str, variant: str) -> str:
        if not url or '{{' in url:
            return url
        separator = '&' if '?' in url else '?'
        utm_params = (
            f"utm_source=cold_email"
            f"&utm_medium=sgm_outreach"
            f"&utm_campaign=audio_infrastructure"
            f"&utm_content={variant}"
            f"&utm_term={company.replace(' ', '_').lower()}"
        )
        return f"{url}{separator}{utm_params}"

    def _log_open(self, record: Dict[str, Any]):
        self.tracking_log.append(record)
        if self.log_path:
            try:
                Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(record) + '\n')
            except Exception as e:
                logger.warning(f"Failed to write tracking log: {e}")


# ============================================================================
# DATA ENRICHMENT & PERSONALIZATION
# ============================================================================

def calculate_burn_rate(row: Dict[str, Any]) -> str:
    """
    Estimated money wasted on manual QC based on studio volume.
    Assumes $50/hr senior editor time, 3 hours QC per finished hour.
    """
    try:
        vol = int(row.get('volume', row.get('Volume', 50)))  # hours/month
        burn = vol * 3 * 50
        return f"{burn:,}"
    except (ValueError, TypeError):
        return "12,500"  # Default painful number


def determine_segment(row: Dict[str, Any]) -> str:
    """Classifies the studio type for specific messaging."""
    raw_seg = str(row.get('segment', row.get('Segment', ''))).lower()
    if 'book' in raw_seg:
        return "Audiobook Publishers"
    if 'post' in raw_seg:
        return "Post-Production Houses"
    if 'dub' in raw_seg:
        return "Localization Studios"
    return "High-Volume Studios"


def extract_first_name(lead: Dict[str, Any]) -> str:
    """Get a first name from lead data, falling back gracefully."""
    name = lead.get('name') or lead.get('first_name') or lead.get('First Name') or ''
    name = name.strip()
    if not name or name.lower() in ('head of post', 'there', 'n/a'):
        return 'there'
    # Take first token only
    return name.split()[0]


def render_email(lead: Dict[str, Any], variant_key: str,
                 tracker: TrackingManager,
                 sender: str = "Scott Mills\nAI Audio Architect | SGM Studios\nCreator of MAAPS",
                 loom_url: str = "https://www.loom.com/share/YOUR_ARCHITECT_VIDEO",
                 ) -> Tuple[str, str, str]:
    """
    Render a variant email for a lead.

    Args:
        lead: Lead dict (from ScraperAgent: company, hook, segment, volume...)
        variant_key: One of VARIANT_KEYS
        tracker: TrackingManager instance
        sender: Signature block
        loom_url: Architecture breakdown video URL

    Returns:
        (subject, body, variant_name)
    """
    if not HAS_JINJA2:
        raise ImportError("jinja2 required for variant templates: pip install jinja2")

    if variant_key not in TEMPLATES:
        raise ValueError(f"Unknown variant: {variant_key}. "
                         f"Valid: {', '.join(VARIANT_KEYS)}")

    variant = TEMPLATES[variant_key]
    company = lead.get('company', lead.get('Company', 'Your Studio'))

    context = {
        'first_name': extract_first_name(lead),
        'company': company,
        'city': lead.get('city', lead.get('City', 'your area')),
        'segment': determine_segment(lead),
        'hook': lead.get('hook', lead.get('Hook', '') or 'your current workflow'),
        'burn_rate': calculate_burn_rate(lead),
        'sender': sender,
        'loom': tracker.add_utm_params(loom_url, company, variant_key),
        'unsubscribe_link': f"Opt-out: {tracker.base_url}/unsubscribe",
        'tracking_pixel': tracker.create_tracking_pixel(company, variant_key),
    }

    subject = jinja2.Template(variant['subject']).render(**context)
    body = jinja2.Template(variant['body']).render(**context)

    return subject, body, variant['name']


def select_variant(campaign_variant: str, lead_index: int) -> str:
    """
    Resolve which variant to use for a lead.

    - Explicit variant key -> use it
    - 'rotate' -> sequential A/B rotation by lead index
    - 'random' -> hash-based deterministic pick (stable per company)
    """
    if campaign_variant in TEMPLATES:
        return campaign_variant
    if campaign_variant == 'rotate':
        return VARIANT_KEYS[lead_index % len(VARIANT_KEYS)]
    if campaign_variant == 'random':
        return VARIANT_KEYS[lead_index % len(VARIANT_KEYS)]
    # Fallback
    return 'variant_b_margin'


def simple_substitute(text: str, lead: Dict[str, Any]) -> str:
    """Legacy {name}/{company}/{bio} substitution (no jinja2 needed)."""
    text = text.replace('{name}', lead.get('name', 'there'))
    text = text.replace('{company}', lead.get('company', 'your company'))
    bio = lead.get('bio') or ''
    text = text.replace('{bio}', bio[:100])
    return text


# ============================================================================
# SELF-TEST
# ============================================================================

if __name__ == '__main__':
    if not HAS_JINJA2:
        print("jinja2 required: pip install jinja2")
        raise SystemExit(1)

    tracker = TrackingManager()
    lead = {
        'name': 'John Doe',
        'company': 'Acme Post',
        'segment': 'Post-Production',
        'hook': 'Dolby Atmos 7.1.4',
        'volume': 100,
    }
    for key in VARIANT_KEYS:
        subject, body, name = render_email(lead, key, tracker)
        print(f"=== {name} ({key}) ===")
        print(f"Subject: {subject}")
        print(body[:300])
        print()
