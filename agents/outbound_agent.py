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
    voice_enabled: bool = True  # Per-campaign voice toggle


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
        
        # LLM personalization config
        self._llm_enabled = getattr(self.config, 'outbound_llm_enabled', True)
        self._llm_provider = getattr(self.config, 'outbound_llm_provider', 'openai')  # openai, anthropic, local
        self._llm_model = getattr(self.config, 'outbound_llm_model', 'gpt-4o-mini')
        self._llm_temperature = getattr(self.config, 'outbound_llm_temperature', 0.7)
        self._llm_max_tokens = getattr(self.config, 'outbound_llm_max_tokens', 500)
        self._llm_timeout = getattr(self.config, 'outbound_llm_timeout', 30.0)
    
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
            - voice_enabled: Optional boolean to enable/disable voice (default True)
        """
        payload = message.payload
        
        campaign = Campaign(
            campaign_id=payload.get('campaign_id', f"camp_{time.time()}"),
            name=payload.get('name', 'Unnamed Campaign'),
            template=payload.get('template', ''),
            voice_model_id=payload.get('voice_model_id'),
            status='active',
            voice_enabled=payload.get('voice_enabled', True)
        )
        
        with self.campaigns_lock:
            self.campaigns[campaign.campaign_id] = campaign
        
        self.log("INFO", f"Campaign started: {campaign.name} (voice_enabled={campaign.voice_enabled}, voice_model={campaign.voice_model_id})")
        
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
        
        # Try LLM-based personalization first if enabled
        if self._llm_enabled:
            try:
                personalized = self._llm_personalize(lead, template)
                if personalized and personalized.strip():
                    self.log("DEBUG", f"LLM personalization successful for {lead.get('name')}")
                    return personalized
            except Exception as e:
                self.log("WARNING", f"LLM personalization failed, falling back to template: {e}")
        
        # Fallback: Simple template substitution
        personalized = template.replace('{name}', lead.get('name', 'there'))
        personalized = personalized.replace('{company}', lead.get('company', 'your company'))
        personalized = personalized.replace('{bio}', lead.get('bio', '')[:100] if lead.get('bio') else '')
        
        return personalized

    def _llm_personalize(self, lead: Dict, template: str) -> str:
        """
        Generate personalized message using LLM.
        
        Tries MessageBus request first (for dedicated LLM agent), 
        then falls back to direct API call.
        """
        # Build prompt with lead data and template
        prompt = self._build_personalization_prompt(lead, template)
        
        # Try MessageBus request to LLM agent
        response = self.request(Topics.LLM_GENERATE, {
            'prompt': prompt,
            'model': self._llm_model,
            'temperature': self._llm_temperature,
            'max_tokens': self._llm_max_tokens,
            'provider': self._llm_provider
        }, timeout=self._llm_timeout)
        
        if response and response.payload.get('success'):
            generated = response.payload.get('text', '').strip()
            if generated:
                return generated
        
        # Fallback to direct LLM API call
        return self._direct_llm_call(prompt)

    def _build_personalization_prompt(self, lead: Dict, template: str) -> str:
        """Build the LLM prompt for personalization"""
        lead_name = lead.get('name', 'there')
        lead_company = lead.get('company', 'your company')
        lead_bio = lead.get('bio', '')[:300] if lead.get('bio') else 'No bio available'
        lead_title = lead.get('title', '')
        lead_location = lead.get('location', '')
        lead_linkedin = lead.get('linkedin_url', '')
        
        prompt = f"""You are an expert B2B sales copywriter. Write a personalized cold outreach email.

LEAD INFORMATION:
- Name: {lead_name}
- Company: {lead_company}
- Title: {lead_title or 'Not specified'}
- Location: {lead_location or 'Not specified'}
- LinkedIn: {lead_linkedin or 'Not provided'}
- Bio/Summary: {lead_bio}

CAMPAIGN TEMPLATE (reference style/tone):
{template}

INSTRUCTIONS:
1. Write a personalized, natural-sounding cold email
2. Reference specific details from the lead's bio/company
3. Keep it concise (under 150 words)
4. Professional but conversational tone
5. Clear, low-friction call-to-action (e.g., "Open to a brief chat?")
6. Sign off as "Scott" from "Hivyr AI Agency"
7. Do NOT include placeholders like {{name}} - use actual values
8. Output ONLY the email body, no explanations

PERSONALIZED EMAIL:"""
        return prompt

    def _direct_llm_call(self, prompt: str) -> str:
        """
        Direct LLM API call as fallback.
        Supports OpenAI, Anthropic, and local transformers.
        """
        provider = self._llm_provider.lower()
        
        try:
            if provider == 'openai':
                return self._call_openai(prompt)
            elif provider == 'anthropic':
                return self._call_anthropic(prompt)
            elif provider == 'local':
                return self._call_local_llm(prompt)
            else:
                self.log("WARNING", f"Unknown LLM provider: {provider}")
                return ""
        except Exception as e:
            self.log("ERROR", f"Direct LLM call failed: {e}")
            return ""

    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API"""
        try:
            import openai
            api_key = getattr(self.config, 'openai_api_key', None) or getattr(self.config, 'OPENAI_API_KEY', None)
            if not api_key:
                self.log("WARNING", "OpenAI API key not configured")
                return ""
            
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=self._llm_model,
                messages=[
                    {"role": "system", "content": "You are an expert B2B sales copywriter."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self._llm_temperature,
                max_tokens=self._llm_max_tokens
            )
            return response.choices[0].message.content.strip()
        except ImportError:
            self.log("WARNING", "openai package not installed")
            return ""
        except Exception as e:
            self.log("ERROR", f"OpenAI API error: {e}")
            return ""

    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API"""
        try:
            import anthropic
            api_key = getattr(self.config, 'anthropic_api_key', None) or getattr(self.config, 'ANTHROPIC_API_KEY', None)
            if not api_key:
                self.log("WARNING", "Anthropic API key not configured")
                return ""
            
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=self._llm_model,
                max_tokens=self._llm_max_tokens,
                temperature=self._llm_temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except ImportError:
            self.log("WARNING", "anthropic package not installed")
            return ""
        except Exception as e:
            self.log("ERROR", f"Anthropic API error: {e}")
            return ""

    def _call_local_llm(self, prompt: str) -> str:
        """Call local transformers model"""
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch
            
            model_name = getattr(self.config, 'local_llm_model', 'microsoft/Phi-3-mini-4k-instruct')
            
            # Load model (cached)
            if not hasattr(self, '_local_llm_model') or self._local_llm_model is None:
                self.log("INFO", f"Loading local LLM: {model_name}")
                self._local_llm_tokenizer = AutoTokenizer.from_pretrained(model_name)
                self._local_llm_model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    device_map="auto" if torch.cuda.is_available() else None
                )
            
            inputs = self._local_llm_tokenizer(prompt, return_tensors="pt")
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self._local_llm_model.generate(
                    **inputs,
                    max_new_tokens=self._llm_max_tokens,
                    temperature=self._llm_temperature,
                    do_sample=True,
                    pad_token_id=self._local_llm_tokenizer.eos_token_id
                )
            
            generated = self._local_llm_tokenizer.decode(
                outputs[0][inputs['input_ids'].shape[1]:], 
                skip_special_tokens=True
            )
            return generated.strip()
        except ImportError:
            self.log("WARNING", "transformers/torch not installed for local LLM")
            return ""
        except Exception as e:
            self.log("ERROR", f"Local LLM error: {e}")
            return ""
    
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
        """Check if we should generate voice for this message
        
        Checks:
        1. Campaign exists and is active
        2. Campaign has voice_enabled=True
        3. Campaign has a voice_model_id configured
        4. Audio worker is available (GPU, model loaded)
        """
        # Get campaign for this message
        with self.campaigns_lock:
            campaign = self.campaigns.get(message.campaign_id)
        
        if not campaign:
            self.log("DEBUG", f"No campaign found for message {message.message_id}, skipping voice")
            return False
        
        # Check 1: Campaign must be active
        if campaign.status != 'active':
            self.log("DEBUG", f"Campaign {campaign.campaign_id} not active (status={campaign.status}), skipping voice")
            return False
        
        # Check 2: Voice must be enabled for this campaign
        if not campaign.voice_enabled:
            self.log("DEBUG", f"Voice disabled for campaign {campaign.campaign_id}, skipping voice")
            return False
        
        # Check 3: Campaign must have a voice model configured
        if not campaign.voice_model_id:
            self.log("DEBUG", f"No voice_model_id configured for campaign {campaign.campaign_id}, skipping voice")
            return False
        
        # Check 4: Audio worker must be available
        if not self._is_audio_worker_available(campaign.voice_model_id):
            self.log("WARNING", f"Audio worker unavailable for model {campaign.voice_model_id}, skipping voice")
            return False
        
        self.log("INFO", f"Voice generation enabled for message {message.message_id} (campaign={campaign.campaign_id}, model={campaign.voice_model_id})")
        return True
    
    def _is_audio_worker_available(self, voice_model_id: str) -> bool:
        """Check if audio worker is available and has the model loaded
        
        Queries the audio worker via MessageBus to check:
        - GPU availability
        - Model loaded/ready
        - Worker responding to health checks
        """
        try:
            # Send health check request to audio worker
            response = self.request(Topics.AUDIO_WORKER_HEALTH, {
                'check_model': voice_model_id
            }, timeout=5.0)
            
            if not response:
                self.log("DEBUG", "Audio worker health check: no response")
                return False
            
            payload = response.payload
            success = payload.get('success', False)
            gpu_available = payload.get('gpu_available', False)
            model_loaded = payload.get('model_loaded', False)
            model_ready = payload.get('model_ready', False)
            
            self.log("DEBUG", f"Audio worker health: success={success}, gpu={gpu_available}, model_loaded={model_loaded}, model_ready={model_ready}")
            
            return success and gpu_available and model_loaded and model_ready
            
        except Exception as e:
            self.log("WARNING", f"Audio worker health check failed: {e}")
            return False
    
    def _generate_voice(self, message: OutboundMessage) -> Optional[str]:
        """Generate voice audio using HeartMuLa or ElevenLabs"""
        # Get campaign to find the voice model
        with self.campaigns_lock:
            campaign = self.campaigns.get(message.campaign_id)
        
        voice_model = campaign.voice_model_id if campaign else None
        
        # Request voice generation from audio worker
        response = self.request(Topics.OUTBOUND_VOICE_GENERATE, {
            'text': message.personalized_text,
            'voice_model': voice_model
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
