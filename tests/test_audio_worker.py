import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure we can import from audio_worker
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'audio_worker')))

from audio_worker.server import app

client = TestClient(app)

def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "gpu_available" in data

def test_process_invalid_job_type():
    """Test invalid job type"""
    response = client.post("/process", json={
        "job_type": "invalid_type",
        "input_path": "test.wav"
    })
    assert response.status_code == 400

@patch("demucs.separate.main")
def test_demucs_process(mock_demucs):
    """Test demucs processing endpoint"""
    # Mock successful execution
    mock_demucs.return_value = None
    
    response = client.post("/process", json={
        "job_type": "demucs_split",
        "input_path": "/files/test.wav",
        "output_path": "/files/out"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["job_type"] == "demucs_split"

@patch("audio_worker.server.get_heartmula_model")
@patch("soundfile.write")
def test_heartmula_process(mock_sf_write, mock_get_model):
    """Test HeartMuLa generation endpoint"""
    # Mock model and processor
    mock_processor = MagicMock()
    mock_model = MagicMock()
    mock_model.config.audio_encoder.sampling_rate = 32000
    
    # Mock generate return value (tensor)
    mock_tensor = MagicMock()
    mock_tensor.cpu().numpy.return_value = [0.1, 0.2] # Fake audio data
    # Accessing [0, 0]
    mock_model.generate.return_value = MagicMock()
    mock_model.generate.return_value.__getitem__.return_value.__getitem__.return_value = mock_tensor
    
    mock_get_model.return_value = (mock_processor, mock_model)
    
    response = client.post("/process", json={
        "job_type": "heartmula_generate",
        "params": {
            "prompt": "test song",
            "duration": 5
        }
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["job_type"] == "heartmula_generate"

@patch("pedalboard.Pedalboard")
@patch("soundfile.read")
@patch("soundfile.write")
def test_rvc_process(mock_sf_write, mock_sf_read, mock_pedalboard):
    """Test RVC (simulated) endpoint"""
    # Mock soundfile read
    mock_sf_read.return_value = ([0.1, 0.2], 44100)
    
    # Mock pedalboard instance call
    mock_board_instance = MagicMock()
    mock_board_instance.return_value = [0.1, 0.2] # Processed data
    mock_pedalboard.return_value = mock_board_instance
    
    response = client.post("/process", json={
        "job_type": "rvc_clone",
        "input_path": "/files/voice.wav"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert "Pedalboard" in data["message"]

@patch("audio_worker.server.get_rag_components")
def test_query_docs(mock_get_rag):
    """Test RAG query endpoint"""
    mock_client = MagicMock()
    mock_model = MagicMock()
    
    # Mock embedding
    mock_model.encode.return_value.tolist.return_value = [0.1, 0.2, 0.3]
    
    # Mock search result
    mock_result = MagicMock()
    mock_result.payload = {"content": "test content", "metadata": {"source": "doc1"}}
    mock_client.search.return_value = [mock_result]
    
    mock_get_rag.return_value = (mock_client, mock_model)
    
    response = client.post("/query_docs", json={
        "query": "test query",
        "top_k": 1
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "test content" in data["context"]
