"""
Centralized logging configuration for wiki_arena project.
Provides consistent, development-friendly logging across all components.
"""

import logging
import sys
from rich.logging import RichHandler
from rich.console import Console
from typing import Optional

def setup_logging(
    level: str = "INFO",
    use_rich: bool = True,
) -> None:
    """
    Set up consistent logging across the entire wiki_arena project.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        use_rich: Whether to use Rich's colored output (recommended for development)
        show_file_line: Whether to show file:line info (very helpful for debugging)
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Get root logger and clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    if use_rich:
        # Rich handler for beautiful terminal output
        console = Console(file=sys.stderr)  # Log to stderr by convention
        
        handler = RichHandler(
            console=console,
            level=numeric_level,
            show_time=True,
            show_level=True,
            show_path=True,
            enable_link_path=True,  # Makes file paths clickable in some terminals
            rich_tracebacks=True,
            markup=False,  # Disable rich markup in log messages
            log_time_format="[%H:%M:%S]"
        )
        
        # Simple format - Rich handles the formatting
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        
    else:
        # Plain text handler for production or when Rich isn't available
        handler = logging.StreamHandler(sys.stderr)
        
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        )
        
        handler.setFormatter(formatter)
    
    handler.setLevel(numeric_level)
    root_logger.addHandler(handler)
    
    # Set specific logger levels for noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    # Log the setup
    logger = logging.getLogger(__name__)
    logger.debug(f"Logging configured: level={level}, rich={use_rich}")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.
    This is just a convenience wrapper around logging.getLogger.
    """
    return logging.getLogger(name)

# Convenience function for common development setup
def setup_dev_logging(level: str = "DEBUG") -> None:
    """Quick setup for development with all debugging features enabled."""
    setup_logging(level=level, use_rich=True)

# Convenience function for production setup
def setup_prod_logging(level: str = "INFO") -> None:
    """Setup for production with clean, structured output."""
    setup_logging(level=level, use_rich=False) 