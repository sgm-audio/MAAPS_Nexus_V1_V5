"""Tests for WebSocket telemetry (Agent 0 Visual Feedback Layer migration)"""

import sys
import os
import asyncio
import time

import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'audio_worker')))

from fastapi.testclient import TestClient
from audio_worker.server import (
    app,
    collect_metrics,
    record_job_submitted,
    record_job_finished,
    JOB_METRICS,
    JOB_LATENCY_MS,
    _gpu_metrics,
    _system_metrics,
    _latency_stats,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_job_metrics():
    """Clean metrics between tests"""
    JOB_METRICS['counts'] = {'submitted': 0, 'complete': 0, 'error': 0}
    JOB_METRICS['by_type'] = {}
    JOB_METRICS['recent'].clear()
    JOB_LATENCY_MS.clear()
    yield


class TestCollectMetrics:
    """Telemetry snapshot structure"""

    def test_snapshot_has_all_sections(self):
        m = collect_metrics()
        assert 'timestamp' in m
        assert 'system' in m
        assert 'gpu' in m
        assert 'jobs' in m

    def test_system_metrics_shape(self):
        sys_m = _system_metrics()
        # psutil may or may not be installed; keys always present
        assert 'cpu_load' in sys_m
        assert 'mem_used_pct' in sys_m
        assert 'mem_used_mb' in sys_m

    def test_gpu_metrics_shape(self):
        gpu = _gpu_metrics()
        assert 'gpu_available' in gpu
        assert 'gpu_name' in gpu
        assert 'vram_used_mb' in gpu
        assert 'vram_total_mb' in gpu
        assert 'util_pct' in gpu

    def test_latency_stats_empty(self):
        stats = _latency_stats()
        assert stats == {'avg_ms': None, 'p95_ms': None, 'last_ms': None}

    def test_job_metrics_shape(self):
        m = collect_metrics()
        jobs = m['jobs']
        assert set(jobs['counts'].keys()) == {'submitted', 'complete', 'error'}
        assert 'by_type' in jobs
        assert 'latency' in jobs
        assert 'recent' in jobs


class TestJobRecording:
    """Job metric recording"""

    def test_record_submitted(self):
        record_job_submitted('demucs_split')
        assert JOB_METRICS['counts']['submitted'] == 1
        assert JOB_METRICS['by_type']['demucs_split'] == 1
        assert len(JOB_METRICS['recent']) == 1
        assert JOB_METRICS['recent'][-1]['status'] == 'submitted'

    def test_record_finished_success_updates_latency(self):
        record_job_submitted('lufs_normalize')
        import time
        record_job_finished('lufs_normalize', time.time() - 0.05, success=True)
        assert JOB_METRICS['counts']['complete'] == 1
        assert JOB_METRICS['counts']['error'] == 0
        assert len(JOB_LATENCY_MS) == 1
        # ~50ms, allow scheduler slop
        assert JOB_LATENCY_MS[-1] > 30

    def test_record_finished_error(self):
        record_job_submitted('rvc_clone')
        import time
        record_job_finished('rvc_clone', time.time(), success=False)
        assert JOB_METRICS['counts']['error'] == 1
        assert JOB_METRICS['counts']['complete'] == 0

    def test_by_type_counter_accumulates(self):
        record_job_submitted('demucs_split')
        record_job_submitted('demucs_split')
        record_job_submitted('lufs_normalize')
        assert JOB_METRICS['by_type'] == {'demucs_split': 2, 'lufs_normalize': 1}

    def test_recent_window_capped(self):
        for _ in range(150):
            record_job_submitted('demucs_split')
        assert len(JOB_METRICS['recent']) <= 100


class TestStatusEndpoint:
    """/status polling fallback"""

    def test_status_200(self):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert 'timestamp' in data
        assert 'system' in data
        assert 'gpu' in data
        assert 'jobs' in data


class TestWebSocketMonitor:
    """/ws/monitor real-time stream"""

    def test_websocket_streams_metrics(self):
        with client.websocket_connect("/ws/monitor") as ws:
            data = ws.receive_json()
            assert 'timestamp' in data
            assert 'system' in data
            assert 'gpu' in data
            assert 'jobs' in data

    def test_websocket_set_interval(self):
        with client.websocket_connect("/ws/monitor") as ws:
            # First frame arrives at 60Hz default
            data1 = ws.receive_json()
            assert 'timestamp' in data1
            # Slow to 1Hz
            ws.send_json({"action": "set_interval", "interval": 1.0})
            data2 = ws.receive_json()
            assert data2['timestamp'] >= data1['timestamp']

    def test_websocket_pause_resume(self):
        with client.websocket_connect("/ws/monitor") as ws:
            data1 = ws.receive_json()
            ws.send_json({"action": "pause"})
            ws.send_json({"action": "resume"})
            data2 = ws.receive_json()
            assert data2['timestamp'] >= data1['timestamp']


class TestProcessJobTracking:
    """/process records telemetry"""

    def test_invalid_job_type_recorded_as_error(self):
        before = JOB_METRICS['counts']['error']
        response = client.post("/process", json={
            "job_type": "invalid_type",
            "input_path": "test.wav"
        })
        assert response.status_code == 400
        assert JOB_METRICS['counts']['error'] == before + 1
        assert JOB_METRICS['by_type'].get('invalid_type') == 1

    def test_successful_demucs_recorded(self):
        from unittest.mock import patch
        with patch("demucs.separate.main"):
            before = JOB_METRICS['counts']['complete']
            response = client.post("/process", json={
                "job_type": "demucs_split",
                "input_path": "/files/test.wav",
                "output_path": "/files/out"
            })
            assert response.status_code == 200
            assert JOB_METRICS['counts']['complete'] == before + 1
            assert JOB_METRICS['by_type']['demucs_split'] >= 1

    def test_error_status_payload_counted_as_error(self):
        """Handlers returning {"status": "error"} count as errors"""
        from unittest.mock import patch
        with patch("demucs.separate.main", side_effect=ImportError):
            before_err = JOB_METRICS['counts']['error']
            response = client.post("/process", json={
                "job_type": "demucs_split",
                "input_path": "/files/test.wav",
            })
            # Handler returns status=error dict with 200
            assert response.status_code == 200
            assert response.json()['status'] == 'error'
            assert JOB_METRICS['counts']['error'] == before_err + 1


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
