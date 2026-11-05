"""Tests for OutboundAgent with LLM personalization and campaign voice settings"""

import pytest
import time
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core import BaseAgent, Message, MessageBus, Topics, Priority
from agents.outbound_agent import OutboundAgent, Campaign, OutboundMessage


class MockConfig:
    """Mock configuration for testing"""
    def __init__(self):
        self.smtp_host = "smtp.test.com"
        self.smtp_port = 587
        self.smtp_user = "test@test.com"
        self.smtp_password = "testpass"
        self.outbound_llm_enabled = False  # Disabled for tests
        self.outbound_llm_provider = "openai"
        self.outbound_llm_model = "gpt-4o-mini"
        self.outbound_llm_temperature = 0.7
        self.outbound_llm_max_tokens = 500
        self.outbound_llm_timeout = 30.0
        self.openai_api_key = "test-key"
        self.anthropic_api_key = "test-key"
        self.local_llm_model = "microsoft/Phi-3-mini-4k-instruct"


@pytest.fixture
def mock_config():
    return MockConfig()


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
def outbound_agent(message_bus, mock_config):
    """Create OutboundAgent with mocked dependencies"""
    with patch('core.config.Config.from_env', return_value=mock_config):
        with patch('core.message_bus.get_bus', return_value=message_bus):
            agent = OutboundAgent()
            agent.start()
            yield agent
            agent.stop()


class TestOutboundAgentPersonalization:
    """Tests for _personalize_message method"""
    
    def test_personalize_with_llm_disabled(self, outbound_agent, mock_config):
        """Test template fallback when LLM is disabled"""
        mock_config.outbound_llm_enabled = False
        outbound_agent._llm_enabled = False
        
        lead = {
            'name': 'John Doe',
            'company': 'Acme Corp',
            'bio': 'CEO at Acme'
        }
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Hi {name}, welcome to {company}!'
        )
        
        result = outbound_agent._personalize_message(lead, campaign)
        
        assert 'John Doe' in result
        assert 'Acme Corp' in result
        assert 'Hi John Doe' in result
    
    def test_personalize_with_no_campaign(self, outbound_agent):
        """Test personalization with no campaign (uses default template)"""
        lead = {
            'name': 'Jane Smith',
            'company': 'Tech Inc',
            'bio': 'CTO at Tech'
        }
        
        result = outbound_agent._personalize_message(lead, None)
        
        assert 'Jane Smith' in result
        assert 'Tech Inc' in result
        assert 'Hivyr AI Agency' in result
    
    @patch('agents.outbound_agent.OutboundAgent._llm_personalize')
    def test_personalize_llm_success(self, mock_llm, outbound_agent):
        """Test successful LLM personalization"""
        # Enable LLM for this test
        outbound_agent._llm_enabled = True
        mock_llm.return_value = "Hi John, I saw Acme Corp is doing great things..."
        
        lead = {
            'name': 'John Doe',
            'company': 'Acme Corp',
            'bio': 'CEO at Acme'
        }
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Hi {name}, welcome to {company}!'
        )
        
        result = outbound_agent._personalize_message(lead, campaign)
        
        assert result == "Hi John, I saw Acme Corp is doing great things..."
        mock_llm.assert_called_once()
    
    def test_personalize_variant_rendering(self, outbound_agent):
        """Campaign with explicit variant uses Agent 0 email system"""
        outbound_agent._llm_enabled = False
        campaign = Campaign(
            campaign_id='test_camp',
            name='Variant Campaign',
            template='Hi {name}, welcome to {company}!',  # ignored when variant set
            variant='variant_b_margin',
        )
        lead = {'name': 'John Doe', 'company': 'Acme Corp', 'volume': 100}

        result = outbound_agent._personalize_message(lead, campaign)

        # Variant B renders first name + company + burn rate
        assert 'Hi John,' in result
        assert 'Acme Corp' in result
        assert 'Margin Erosion' in result
        assert '$15,000/month' in result
        # Tracking pixel embedded
        assert '<img src=' in result

    def test_personalize_legacy_template_when_no_variant(self, outbound_agent):
        """Campaign without variant uses legacy {name} substitution"""
        outbound_agent._llm_enabled = False
        campaign = Campaign(
            campaign_id='test_camp',
            name='Legacy Campaign',
            template='Hi {name}, welcome to {company}!',
            variant=None,  # No variant -> legacy path
        )
        lead = {'name': 'John Doe', 'company': 'Acme Corp'}

        result = outbound_agent._personalize_message(lead, campaign)

        assert 'Hi John Doe, welcome to Acme Corp!' == result

    def test_render_subject_legacy(self, outbound_agent):
        """No variant -> legacy subject format"""
        lead = {'name': 'John Doe'}
        subject, variant_name = outbound_agent._render_subject(lead, None)
        assert subject == 'Quick question for John Doe'
        assert variant_name == ''

    def test_render_subject_variant(self, outbound_agent):
        """With variant -> rendered subject from template"""
        campaign = Campaign(
            campaign_id='test_camp',
            name='V',
            template='',
            variant='variant_b_margin',
        )
        lead = {'name': 'John Doe', 'company': 'Acme Corp'}
        subject, variant_name = outbound_agent._render_subject(lead, campaign)
        assert subject == 'Ratio of editing hours to finished hours at Acme Corp'
        assert variant_name == 'Margin Erosion'

    @patch('agents.outbound_agent.OutboundAgent._llm_personalize')
    def test_personalize_llm_failure_fallback(self, mock_llm, outbound_agent):
        """Test fallback to template when LLM fails"""
        outbound_agent._llm_enabled = True
        mock_llm.side_effect = Exception("LLM API error")
        
        lead = {
            'name': 'John Doe',
            'company': 'Acme Corp',
            'bio': 'CEO at Acme'
        }
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Hi {name}, welcome to {company}!'
        )
        
        result = outbound_agent._personalize_message(lead, campaign)
        
        assert 'John Doe' in result
        assert 'Acme Corp' in result
        assert 'Hi John Doe' in result
    
    @patch('agents.outbound_agent.OutboundAgent._llm_personalize')
    def test_personalize_llm_empty_result_fallback(self, mock_llm, outbound_agent):
        """Test fallback when LLM returns empty string"""
        outbound_agent._llm_enabled = True
        mock_llm.return_value = ""
        
        lead = {
            'name': 'John Doe',
            'company': 'Acme Corp',
            'bio': 'CEO at Acme'
        }
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Hi {name}, welcome to {company}!'
        )
        
        result = outbound_agent._personalize_message(lead, campaign)
        
        assert 'John Doe' in result
        assert 'Acme Corp' in result


class TestOutboundAgentCampaignVoice:
    """Tests for _should_generate_voice method"""
    
    def test_should_generate_voice_all_conditions_met(self, outbound_agent):
        """Test voice generation when all conditions are met"""
        # Setup campaign with voice enabled
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Test',
            voice_model_id='elevenlabs_model_1',
            status='active',
            voice_enabled=True
        )
        outbound_agent.campaigns['test_camp'] = campaign
        
        # Mock audio worker as available
        with patch.object(outbound_agent, '_is_audio_worker_available', return_value=True):
            message = OutboundMessage(
                message_id='msg_1',
                campaign_id='test_camp',
                lead_id='lead_1',
                lead_name='John',
                lead_email='john@test.com',
                personalized_text='Test message'
            )
            
            result = outbound_agent._should_generate_voice(message)
            
            assert result is True
    
    def test_should_generate_voice_no_campaign(self, outbound_agent):
        """Test voice generation when campaign doesn't exist"""
        message = OutboundMessage(
            message_id='msg_1',
            campaign_id='nonexistent',
            lead_id='lead_1',
            lead_name='John',
            lead_email='john@test.com',
            personalized_text='Test message'
        )
        
        result = outbound_agent._should_generate_voice(message)
        
        assert result is False
    
    def test_should_generate_voice_campaign_not_active(self, outbound_agent):
        """Test voice generation when campaign is not active"""
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Test',
            voice_model_id='model_1',
            status='draft',  # Not active
            voice_enabled=True
        )
        outbound_agent.campaigns['test_camp'] = campaign
        
        message = OutboundMessage(
            message_id='msg_1',
            campaign_id='test_camp',
            lead_id='lead_1',
            lead_name='John',
            lead_email='john@test.com',
            personalized_text='Test message'
        )
        
        result = outbound_agent._should_generate_voice(message)
        
        assert result is False
    
    def test_should_generate_voice_voice_disabled(self, outbound_agent):
        """Test voice generation when voice is disabled for campaign"""
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Test',
            voice_model_id='model_1',
            status='active',
            voice_enabled=False  # Disabled
        )
        outbound_agent.campaigns['test_camp'] = campaign
        
        message = OutboundMessage(
            message_id='msg_1',
            campaign_id='test_camp',
            lead_id='lead_1',
            lead_name='John',
            lead_email='john@test.com',
            personalized_text='Test message'
        )
        
        result = outbound_agent._should_generate_voice(message)
        
        assert result is False
    
    def test_should_generate_voice_no_voice_model(self, outbound_agent):
        """Test voice generation when no voice model configured"""
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Test',
            voice_model_id=None,  # No model
            status='active',
            voice_enabled=True
        )
        outbound_agent.campaigns['test_camp'] = campaign
        
        message = OutboundMessage(
            message_id='msg_1',
            campaign_id='test_camp',
            lead_id='lead_1',
            lead_name='John',
            lead_email='john@test.com',
            personalized_text='Test message'
        )
        
        result = outbound_agent._should_generate_voice(message)
        
        assert result is False
    
    def test_should_generate_voice_audio_worker_unavailable(self, outbound_agent):
        """Test voice generation when audio worker is unavailable"""
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Test',
            voice_model_id='model_1',
            status='active',
            voice_enabled=True
        )
        outbound_agent.campaigns['test_camp'] = campaign
        
        with patch.object(outbound_agent, '_is_audio_worker_available', return_value=False):
            message = OutboundMessage(
                message_id='msg_1',
                campaign_id='test_camp',
                lead_id='lead_1',
                lead_name='John',
                lead_email='john@test.com',
                personalized_text='Test message'
            )
            
            result = outbound_agent._should_generate_voice(message)
            
            assert result is False


class TestOutboundAgentCampaignCreation:
    """Tests for campaign creation with voice settings"""
    
    def test_campaign_creation_with_voice_enabled(self, outbound_agent, message_bus):
        """Test campaign creation with voice_enabled parameter"""
        # Create a mock response handler
        responses = []
        def capture_response(msg):
            if msg.topic == Topics.OUTBOUND_CAMPAIGN_START + '.response':
                responses.append(msg.payload)
        
        message_bus.subscribe(Topics.OUTBOUND_CAMPAIGN_START + '.response', capture_response)
        
        # Send campaign start message
        test_message = Message(
            topic=Topics.OUTBOUND_CAMPAIGN_START,
            payload={
                'campaign_id': 'test_camp_1',
                'name': 'Voice Campaign',
                'template': 'Test template',
                'voice_model_id': 'model_1',
                'voice_enabled': True
            },
            sender='test_sender'
        )
        
        outbound_agent.handle_message(test_message)
        
        # Wait for async processing
        time.sleep(0.1)
        
        # Check campaign was created with voice_enabled=True
        assert 'test_camp_1' in outbound_agent.campaigns
        campaign = outbound_agent.campaigns['test_camp_1']
        assert campaign.voice_enabled is True
        assert campaign.voice_model_id == 'model_1'
        assert campaign.status == 'active'
    
    def test_campaign_creation_with_voice_disabled(self, outbound_agent, message_bus):
        """Test campaign creation with voice_enabled=False"""
        responses = []
        def capture_response(msg):
            if msg.topic == Topics.OUTBOUND_CAMPAIGN_START + '.response':
                responses.append(msg.payload)
        
        message_bus.subscribe(Topics.OUTBOUND_CAMPAIGN_START + '.response', capture_response)
        
        test_message = Message(
            topic=Topics.OUTBOUND_CAMPAIGN_START,
            payload={
                'campaign_id': 'test_camp_2',
                'name': 'No Voice Campaign',
                'template': 'Test template',
                'voice_model_id': 'model_1',
                'voice_enabled': False  # Explicitly disabled
            },
            sender='test_sender'
        )
        
        outbound_agent.handle_message(test_message)
        time.sleep(0.1)
        
        assert 'test_camp_2' in outbound_agent.campaigns
        campaign = outbound_agent.campaigns['test_camp_2']
        assert campaign.voice_enabled is False
    
    def test_campaign_creation_default_voice_enabled(self, outbound_agent, message_bus):
        """Test campaign creation defaults voice_enabled to True"""
        responses = []
        def capture_response(msg):
            if msg.topic == Topics.OUTBOUND_CAMPAIGN_START + '.response':
                responses.append(msg.payload)
        
        message_bus.subscribe(Topics.OUTBOUND_CAMPAIGN_START + '.response', capture_response)
        
        test_message = Message(
            topic=Topics.OUTBOUND_CAMPAIGN_START,
            payload={
                'campaign_id': 'test_camp_3',
                'name': 'Default Campaign',
                'template': 'Test template',
                'voice_model_id': 'model_1'
                # voice_enabled not specified - should default to True
            },
            sender='test_sender'
        )
        
        outbound_agent.handle_message(test_message)
        time.sleep(0.1)
        
        assert 'test_camp_3' in outbound_agent.campaigns
        campaign = outbound_agent.campaigns['test_camp_3']
        assert campaign.voice_enabled is True  # Default


class TestOutboundAgentLLMIntegration:
    """Tests for LLM integration methods"""
    
    def test_build_personalization_prompt(self, outbound_agent):
        """Test prompt building includes all lead data"""
        lead = {
            'name': 'John Doe',
            'company': 'Acme Corp',
            'title': 'CEO',
            'location': 'San Francisco',
            'linkedin_url': 'https://linkedin.com/in/johndoe',
            'bio': 'Experienced CEO with 20 years in tech'
        }
        template = 'Hi {name}, welcome to {company}!'
        
        prompt = outbound_agent._build_personalization_prompt(lead, template)
        
        assert 'John Doe' in prompt
        assert 'Acme Corp' in prompt
        assert 'CEO' in prompt
        assert 'San Francisco' in prompt
        assert 'linkedin.com' in prompt
        assert 'Experienced CEO' in prompt
        assert 'Hi {name}, welcome to {company}!' in prompt
        assert 'PERSONALIZED EMAIL:' in prompt
    
    @patch('agents.outbound_agent.OutboundAgent.request')
    def test_llm_personalize_messagebus_success(self, mock_request, outbound_agent):
        """Test LLM personalization via MessageBus"""
        mock_response = MagicMock()
        mock_response.payload = {
            'success': True,
            'text': 'Personalized email from LLM'
        }
        mock_request.return_value = mock_response
        
        lead = {'name': 'John', 'company': 'Acme', 'bio': 'CEO'}
        template = 'Test template'
        
        result = outbound_agent._llm_personalize(lead, template)
        
        assert result == 'Personalized email from LLM'
        mock_request.assert_called_once()
        # Check the request payload
        call_args = mock_request.call_args[0]
        assert call_args[0] == Topics.LLM_GENERATE
        assert 'prompt' in call_args[1]
    
    @patch('agents.outbound_agent.OutboundAgent.request')
    @patch('agents.outbound_agent.OutboundAgent._direct_llm_call')
    def test_llm_personalize_fallback_to_direct(self, mock_direct, mock_request, outbound_agent):
        """Test fallback to direct LLM call when MessageBus fails"""
        # MessageBus returns None (no LLM agent)
        mock_request.return_value = None
        mock_direct.return_value = 'Direct LLM result'
        
        lead = {'name': 'John', 'company': 'Acme', 'bio': 'CEO'}
        template = 'Test template'
        
        result = outbound_agent._llm_personalize(lead, template)
        
        assert result == 'Direct LLM result'
        mock_direct.assert_called_once()
    
    @patch('agents.outbound_agent.OutboundAgent.request')
    @patch('agents.outbound_agent.OutboundAgent._direct_llm_call')
    def test_llm_personalize_messagebus_failure(self, mock_direct, mock_request, outbound_agent):
        """Test fallback when MessageBus returns failed response"""
        mock_response = MagicMock()
        mock_response.payload = {'success': False, 'error': 'Model not found'}
        mock_request.return_value = mock_response
        mock_direct.return_value = 'Direct LLM result'
        
        lead = {'name': 'John', 'company': 'Acme', 'bio': 'CEO'}
        template = 'Test template'
        
        result = outbound_agent._llm_personalize(lead, template)
        
        assert result == 'Direct LLM result'
        mock_direct.assert_called_once()


class TestOutboundAgentEndToEnd:
    """End-to-end tests for lead processing flow"""
    
    def test_lead_process_queues_message(self, outbound_agent):
        """Test lead processing queues message for worker"""
        # Setup campaign
        campaign = Campaign(
            campaign_id='test_camp',
            name='Test Campaign',
            template='Hi {name}!',
            voice_model_id='model_1',
            status='active',
            voice_enabled=True
        )
        outbound_agent.campaigns['test_camp'] = campaign
        
        # Send lead process message
        test_message = Message(
            topic=Topics.OUTBOUND_LEAD_PROCESS,
            payload={
                'lead': {
                    'id': 'lead_1',
                    'name': 'John Doe',
                    'email': 'john@test.com',
                    'company': 'Acme Corp',
                    'bio': 'CEO at Acme'
                },
                'campaign_id': 'test_camp'
            },
            sender='test_sender'
        )
        
        outbound_agent.handle_message(test_message)
        time.sleep(0.1)
        
        # Verify message was queued
        with outbound_agent.messages_lock:
            assert len(outbound_agent.pending_messages) == 1
            msg = outbound_agent.pending_messages[0]
            assert msg.lead_name == 'John Doe'
            assert msg.lead_email == 'john@test.com'
            assert msg.campaign_id == 'test_camp'
        
        # Check OUTBOUND_COMPLETE was published
        # (We can't easily capture it without subscribing, but we verified the mocks)
    
    def test_lead_without_email_skipped(self, outbound_agent, message_bus):
        """Test lead without email is skipped"""
        test_message = Message(
            topic=Topics.OUTBOUND_LEAD_PROCESS,
            payload={
                'lead': {
                    'id': 'lead_1',
                    'name': 'John Doe',
                    'email': '',  # No email
                    'company': 'Acme Corp'
                },
                'campaign_id': 'test_camp'
            },
            sender='test_sender'
        )
        
        # Should not crash and should not queue message
        outbound_agent.handle_message(test_message)
        time.sleep(0.1)
        
        # No pending messages should be queued
        with outbound_agent.messages_lock:
            assert len(outbound_agent.pending_messages) == 0


class TestOutboundAgentAudioWorkerHealth:
    """Tests for audio worker health checking"""
    
    @patch('agents.outbound_agent.OutboundAgent.request')
    def test_is_audio_worker_available_success(self, mock_request, outbound_agent):
        """Test audio worker health check success"""
        mock_response = MagicMock()
        mock_response.payload = {
            'success': True,
            'gpu_available': True,
            'model_loaded': True,
            'model_ready': True
        }
        mock_request.return_value = mock_response
        
        result = outbound_agent._is_audio_worker_available('model_1')
        
        assert result is True
        mock_request.assert_called_once()
        call_args = mock_request.call_args[0]
        assert call_args[0] == Topics.AUDIO_WORKER_HEALTH
        assert call_args[1]['check_model'] == 'model_1'
    
    @patch('agents.outbound_agent.OutboundAgent.request')
    def test_is_audio_worker_available_no_response(self, mock_request, outbound_agent):
        """Test audio worker health check with no response"""
        mock_request.return_value = None
        
        result = outbound_agent._is_audio_worker_available('model_1')
        
        assert result is False
    
    @patch('agents.outbound_agent.OutboundAgent.request')
    def test_is_audio_worker_available_gpu_unavailable(self, mock_request, outbound_agent):
        """Test audio worker health check with GPU unavailable"""
        mock_response = MagicMock()
        mock_response.payload = {
            'success': True,
            'gpu_available': False,  # GPU not available
            'model_loaded': True,
            'model_ready': True
        }
        mock_request.return_value = mock_response
        
        result = outbound_agent._is_audio_worker_available('model_1')
        
        assert result is False
    
    @patch('agents.outbound_agent.OutboundAgent.request')
    def test_is_audio_worker_available_exception(self, mock_request, outbound_agent):
        """Test audio worker health check with exception"""
        mock_request.side_effect = Exception("Connection failed")
        
        result = outbound_agent._is_audio_worker_available('model_1')
        
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])