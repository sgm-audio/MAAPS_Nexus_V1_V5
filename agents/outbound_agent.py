"""
Outbound Agent

Handles V2: Ghost Outbound Engine.
Orchestrates lead processing, voice generation, and email automation.
"""

import time
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

from core import BaseAgent, Message, Topics, Priority

logger = logging.getLogger(__name__)


@dataclass
class Campaign:
    """Outbound campaign"""
    campaign_id: str
    name: str
    template: str
    voice_model_id: Optional[str] = None
    status: str = "draft"


@dataclass
class OutboundMessage:
    """Outbound message to a lead"""
    message_id: str
    campaign_id: str
    lead_id: str
    lead_name: str
    lead_email: str
    personalized_text: str
    audio_path: Optional[str] = None
    email_sent: bool = False


class OutboundAgent(BaseAgent):
    """
    Ghost Outbound Engine Agent.
    
    V2 Features:
    - Lead processing from scraped data
    - LLM-generated personalized pitches
    - HeartMuLa/ElevenLabs voice generation
    - Automated email delivery with audio attachments
    """
    
    def __init__(self):
        super().__init__(
            agent_id="outbound_agent",
            agent_name="Ghost Outbound Engine Agent"
        )
        
        # Campaign tracking
        self.campaigns: Dict[str, Campaign] = {}
        self.campaigns_lock = threading.Lock()
        
        # Message queue
        self.pending_messages: List[OutboundMessage] = []
        self.messages_lock = threading.Lock()
        
        # Worker thread
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_active = False
        
        # SMTP Session
        self._smtp_session = None
        self._last_smtp_activity = 0.0
        self._smtp_timeout = 300.0  # 5 minutes
        
        # Templates
        self._default_email_template = ""
    
    def setup(self):
        """Initialize outbound agent"""
        # Load templates
        self._load_templates()
        
        # Subscribe to outbound topics
        self.subscribe(Topics.OUTBOUND_CAMPAIGN_START)
        self.subscribe(Topics.OUTBOUND_LEAD_PROCESS)
        self.subscribe(Topics.SCRAPER_LEADS_FOUND)  # Listen for new leads
        
        # Start worker thread
        self._start_worker()
        
        self.log("INFO", "Outbound Agent initialized")
    
    def teardown(self):
        """Cleanup outbound agent"""
        self._stop_worker()
        self._close_smtp()
        self.log("INFO", "Outbound Agent shutdown complete")
    
    def _load_templates(self):
        """Load email templates from file"""
        try:
            import os
            template_path = os.path.join(os.path.dirname(__file__), 'templates', 'default_email.txt')
            if os.path.exists(template_path):
                with open(template_path, 'r') as f:
                    self._default_email_template = f.read()
                self.log("INFO", "Loaded default email template")
            else:
                self.log("WARNING", f"Template not found: {template_path}")
        except Exception as e:
            self.log("ERROR", f"Error loading templates: {e}")

    def _get_smtp_connection(self):
        """Get or create SMTP connection with keepalive"""
        # Check if session exists and is fresh enough
        if self._smtp_session:
            try:
                # Noop check
                status = self._smtp_session.noop()[0]
                if status == 250:
                    self._last_smtp_activity = time.time()
                    return self._smtp_session
            except:
                self.log("INFO", "SMTP session stale, reconnecting")
                self._close_smtp()
        
        # Create new connection
        try:
            smtp_host = self.config.smtp_host
            smtp_port = self.config.smtp_port
            smtp_user = self.config.smtp_user
            smtp_pass = self.config.smtp_password
            
            if not all([smtp_host, smtp_user, smtp_pass]):
                return None
            
            self._smtp_session = smtplib.SMTP(smtp_host, smtp_port)
            self._smtp_session.starttls()
            self._smtp_session.login(smtp_user, smtp_pass)
            
            self._last_smtp_activity = time.time()
            self.log("INFO", "SMTP connected")
            return self._smtp_session
            
        except Exception as e:
            self.log("ERROR", f"SMTP connection failed: {e}")
            return None

    def _close_smtp(self):
        """Close SMTP session"""
        if self._smtp_session:
            try:
                self._smtp_session.quit()
            except:
                pass
            self._smtp_session = None
    
    def handle_message(self, message: Message):
        """Process outbound messages"""
        try:
            if message.topic == Topics.OUTBOUND_CAMPAIGN_START:
                self._handle_campaign_start(message)
            
            elif message.topic == Topics.OUTBOUND_LEAD_PROCESS:
                self._handle_lead_process(message)
            
            elif message.topic == Topics.SCRAPER_LEADS_FOUND:
                self._handle_new_leads(message)
            
            else:
                self.log("DEBUG", f"Unhandled topic: {message.topic}")
        
        except Exception as e:
            self.log("ERROR", f"Error handling message: {e}")
    
    def _handle_campaign_start(self, message: Message):
        """
        Start an outbound campaign.
        
        Expected payload:
            - campaign_id: Unique campaign ID
            - name: Campaign name
            - template: Email/voice template
            - voice_model_id: Optional voice model for audio
        """
        payload = message.payload
        
        campaign = Campaign(
            campaign_id=payload.get('campaign_id', f"camp_{time.time()}"),
            name=payload.get('name', 'Unnamed Campaign'),
            template=payload.get('template', ''),
            voice_model_id=payload.get('voice_model_id'),
            status='active'
        )
        
        with self.campaigns_lock:
            self.campaigns[campaign.campaign_id] = campaign
        
        self.log("INFO", f"Campaign started: {campaign.name}")
        
        self.respond(message, {
            'success': True,
            'campaign_id': campaign.campaign_id
        })
    
    def _handle_new_leads(self, message: Message):
        """Handle leads from scraper"""
        payload = message.payload
        leads = payload.get('leads', [])
        
        self.log("INFO", f"Received {len(leads)} new leads from scraper")
        
        # Queue leads for processing
        for lead in leads:
            self.publish(Topics.OUTBOUND_LEAD_PROCESS, {
                'lead': lead,
                'campaign_id': 'default'  # Use default campaign
            }, priority=Priority.LOW)
    
    def _handle_lead_process(self, message: Message):
        """
        Process a single lead.
        
        Expected payload:
            - lead: Lead data (name, email, bio, etc.)
            - campaign_id: Campaign to use
        """
        payload = message.payload
        lead = payload.get('lead', {})
        campaign_id = payload.get('campaign_id', 'default')
        
        if not lead.get('email'):
            self.log("DEBUG", f"Skipping lead without email: {lead.get('name')}")
            return
        
        self.log("INFO", f"Processing lead: {lead.get('name')}")
        
        # Get campaign
        with self.campaigns_lock:
            campaign = self.campaigns.get(campaign_id)
        
        # Generate personalized message
        personalized = self._personalize_message(lead, campaign)
        
        # Create outbound message
        outbound = OutboundMessage(
            message_id=f"msg_{time.time()}",
            campaign_id=campaign_id,
            lead_id=lead.get('id', ''),
            lead_name=lead.get('name', ''),
            lead_email=lead.get('email', ''),
            personalized_text=personalized
        )
        
        # Queue for processing
        with self.messages_lock:
            self.pending_messages.append(outbound)
        
        self.log("INFO", f"Lead queued: {outbound.lead_name}")
    
    def _personalize_message(self, lead: Dict, campaign: Optional[Campaign]) -> str:
        """Generate personalized message for lead"""
        template = campaign.template if campaign else self._default_template()
        
        # Simple template substitution
        personalized = template.replace('{name}', lead.get('name', 'there'))
        personalized = personalized.replace('{company}', lead.get('company', 'your company'))
        personalized = personalized.replace('{bio}', lead.get('bio', '')[:100] if lead.get('bio') else '')
        
        # TODO: Use LLM for more sophisticated personalization
        
        return personalized
    
    def _default_template(self) -> str:
        """Default outbound template"""
        if self._default_email_template:
            return self._default_email_template
            
        return """Hi {name},

I noticed you're with {company} and wanted to reach out. 

We specialize in AI-powered audio production and automation systems that could help streamline your workflow.

Would you be open to a quick 10-minute call to see if we could help?

Best,
Scott
Hivyr AI Agency"""
    
    def _start_worker(self):
        """Start message processing worker"""
        self._worker_active = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="Outbound_Worker",
            daemon=True
        )
        self._worker_thread.start()
    
    def _stop_worker(self):
        """Stop message processing worker"""
        self._worker_active = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
    
    def _worker_loop(self):
        """Process pending outbound messages"""
        while self._worker_active:
            try:
                # Get next pending message
                message = None
                with self.messages_lock:
                    if self.pending_messages:
                        message = self.pending_messages.pop(0)
                
                if message:
                    self._process_outbound(message)
                else:
                    time.sleep(1.0)
            
            except Exception as e:
                self.log("ERROR", f"Worker error: {e}")
                time.sleep(1.0)
    
    def _process_outbound(self, message: OutboundMessage):
        """Process a single outbound message"""
        try:
            # Step 1: Generate voice (optional)
            if self._should_generate_voice(message):
                audio_path = self._generate_voice(message)
                message.audio_path = audio_path
            
            # Step 2: Send email
            success = self._send_email(message)
            message.email_sent = success
            
            if success:
                self.publish(Topics.OUTBOUND_COMPLETE, {
                    'message_id': message.message_id,
                    'lead_email': message.lead_email,
                    'has_audio': message.audio_path is not None
                })
                
                self.log("INFO", f"Outbound sent: {message.lead_email}")
            else:
                self.log("WARNING", f"Failed to send: {message.lead_email}")
        
        except Exception as e:
            self.log("ERROR", f"Outbound processing error: {e}")
    
    def _should_generate_voice(self, message: OutboundMessage) -> bool:
        """Check if we should generate voice for this message"""
        # TODO: Check campaign settings
        return False  # Disabled by default
    
    def _generate_voice(self, message: OutboundMessage) -> Optional[str]:
        """Generate voice audio using HeartMuLa or ElevenLabs"""
        # Request voice generation from audio worker
        response = self.request(Topics.OUTBOUND_VOICE_GENERATE, {
            'text': message.personalized_text,
            'voice_model': None  # Use default
        }, timeout=60.0)
        
        if response and response.payload.get('success'):
            return response.payload.get('audio_path')
        
        return None
    
    def _send_email(self, message: OutboundMessage) -> bool:
        """Send email to lead"""
        try:
            server = self._get_smtp_connection()
            if not server:
                self.log("WARNING", "No SMTP connection available")
                return False
            
            smtp_user = self.config.smtp_user
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = message.lead_email
            msg['Subject'] = f"Quick question for {message.lead_name}"
            
            # Add text body
            msg.attach(MIMEText(message.personalized_text, 'plain'))
            
            # Add audio attachment if present
            if message.audio_path:
                with open(message.audio_path, 'rb') as f:
                    audio_part = MIMEBase('audio', 'mpeg')
                    audio_part.set_payload(f.read())
                    encoders.encode_base64(audio_part)
                    audio_part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="voice_message.mp3"'
                    )
                    msg.attach(audio_part)
            
            # Send (using reused connection)
            server.send_message(msg)
            
            return True
        
        except Exception as e:
            self.log("ERROR", f"Email send error: {e}")
            # Force reconnect next time
            self._close_smtp()
            return False
