"""
Configuration and environment variables for AI4Test LangGraph.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Application configuration."""
    
    # LLM Configuration
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_api_compatible")
    llm_model: str = os.getenv("LLM_MODEL", "privacy_Qwen3-Coder-480B-A35B-ReAct")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://localhost:8000/v1")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0"))
    
    # Alternative models for different tasks
    model_chat: str = os.getenv("MODEL_CHAT", "privacy_Qwen3-Coder-480B-A35B-ReAct")
    model_mindmap: str = os.getenv("MODEL_MINDMAP", "privacy_DeepSeek-v3.1-w8a8-Instruct-Long")
    model_testcase: str = os.getenv("MODEL_TESTCASE", "privacy_DeepSeek-v3.1-w8a8-Instruct-Long")
    model_sql: str = os.getenv("MODEL_SQL", "GPT-4.1-only-for-qrb")
    model_intent: str = os.getenv("MODEL_INTENT", "privacy_Qwen3-Coder-480B-A35B-Instruct")
    model_ts_extract: str = os.getenv("MODEL_TS_EXTRACT", "privacy_Qwen3-Coder-480B-A35B-Instruct")
    
    # Knowledge Base Configuration
    knowledge_base_id: str = os.getenv(
        "KNOWLEDGE_BASE_ID", 
        "3YNXhWifKwSrIIBisBx1nokIGbDbm7vzkKZ0s00t6y6EaakRGJggH0Dh9RYuIwv3"
    )
    rerank_model: str = os.getenv("RERANK_MODEL", "gte-rerank")
    rerank_provider: str = os.getenv("RERANK_PROVIDER", "tongyi")
    top_k: int = int(os.getenv("KNOWLEDGE_TOP_K", "3"))
    score_threshold: Optional[float] = (
        float(os.getenv("KNOWLEDGE_SCORE_THRESHOLD")) 
        if os.getenv("KNOWLEDGE_SCORE_THRESHOLD") 
        else None
    )
    
    # Database Configuration
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "gaussdb")
    db_user: str = os.getenv("DB_USER", "admin")
    db_password: str = os.getenv("DB_PASSWORD", "")
    
    # Database Advanced Configuration
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    db_statement_timeout: int = int(os.getenv("DB_STATEMENT_TIMEOUT", "30"))
    db_max_rows: int = int(os.getenv("DB_MAX_ROWS", "1000"))
    
    # Excel Generation API
    excel_api_url: str = os.getenv("EXCEL_API_URL", "http://10.31.169.36:9002/generate_excel")
    excel_api_timeout: int = int(os.getenv("EXCEL_API_TIMEOUT", "300"))
    
    # Notification Configuration
    notification_enabled: bool = os.getenv("NOTIFICATION_ENABLED", "true").lower() == "true"
    
    # Graph Configuration
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "10"))
    max_sql_iterations: int = int(os.getenv("MAX_SQL_ITERATIONS", "3"))
    parallel_iterations: int = int(os.getenv("PARALLEL_ITERATIONS", "3"))
    
    # Retry Configuration
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    retry_interval: int = int(os.getenv("RETRY_INTERVAL", "1000"))
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls()
    
    def validate(self) -> bool:
        """Validate required configuration."""
        required = ["llm_api_key"]
        for field in required:
            if not getattr(self, field):
                raise ValueError(f"Required configuration '{field}' is not set")
        return True


# Global configuration instance
config = Config.from_env()
