import os
from typing import Dict, Any
from pydantic import BaseModel

class BackendConfig(BaseModel):
    """Configuration for the FastAPI backend."""
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # CORS settings
    cors_origins: list = ["http://localhost:3000", "http://localhost:5173"]  # React dev servers
    
    # Game settings
    default_max_steps: int = 30
    max_concurrent_games: int = 10
    
    # MCP server settings - reuse from existing config
    mcp_server_name: str = "stdio_mcp_server"
    
    @classmethod
    def from_env(cls) -> "BackendConfig":
        """Create config from environment variables."""
        return cls(
            host=os.getenv("BACKEND_HOST", "0.0.0.0"),
            port=int(os.getenv("BACKEND_PORT", "8000")),
            debug=os.getenv("BACKEND_DEBUG", "false").lower() == "true",
            cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(","),
            default_max_steps=int(os.getenv("DEFAULT_MAX_STEPS", "30")),
            max_concurrent_games=int(os.getenv("MAX_CONCURRENT_GAMES", "10"))
        )

# Global config instance
config = BackendConfig.from_env()
