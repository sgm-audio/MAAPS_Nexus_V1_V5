"""
Configuration Manager

Loads environment variables and provides centralized config access.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """MAAPS Nexus configuration"""
    
    # Database
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "maaps_admin"
    postgres_password: str = ""
    postgres_db: str = "maaps"
    
    # Qdrant (Vector DB)
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    
    # Selenium (Scraper)
    selenium_host: str = "selenium"
    selenium_port: int = 4444
    
    # GPU Audio Worker
    gpu_worker_host: str = "audio_worker"
    gpu_worker_port: int = 8000
    
    # CI/CD (V1)
    github_webhook_secret: str = ""
    
    # HeartMuLa (V2/V3)
    heartmula_api_key: str = ""
    heartmula_api_url: str = ""
    
    # ElevenLabs (V2)
    elevenlabs_api_key: str = ""
    
    # Email (V2)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    
    # Audio Export (V3)
    sgm_studios_path: str = "/mnt/sgm_studios"
    
    # Timezone
    timezone: str = "America/Regina"
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables"""
        return cls(
            postgres_host=os.getenv("POSTGRES_HOST", "postgres"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_user=os.getenv("POSTGRES_USER", "maaps_admin"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
            postgres_db=os.getenv("POSTGRES_DB", "maaps"),
            qdrant_host=os.getenv("QDRANT_HOST", "qdrant"),
            qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
            selenium_host=os.getenv("SELENIUM_HOST", "selenium"),
            selenium_port=int(os.getenv("SELENIUM_PORT", "4444")),
            gpu_worker_host=os.getenv("GPU_WORKER_HOST", "audio_worker"),
            gpu_worker_port=int(os.getenv("GPU_WORKER_PORT", "8000")),
            github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
            heartmula_api_key=os.getenv("HEARTMULA_API_KEY", ""),
            heartmula_api_url=os.getenv("HEARTMULA_API_URL", ""),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            sgm_studios_path=os.getenv("SGM_STUDIOS_PATH", "/mnt/sgm_studios"),
            timezone=os.getenv("TZ", "America/Regina")
        )
    
    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def qdrant_url(self) -> str:
        """Get Qdrant connection URL"""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
    
    @property
    def selenium_url(self) -> str:
        """Get Selenium WebDriver URL"""
        return f"http://{self.selenium_host}:{self.selenium_port}/wd/hub"
    
    @property
    def gpu_worker_url(self) -> str:
        """Get GPU Worker API URL"""
        return f"http://{self.gpu_worker_host}:{self.gpu_worker_port}"
