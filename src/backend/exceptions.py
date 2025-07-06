"""
Custom exceptions for the backend application.
"""

class WikiArenaException(Exception):
    """Base exception for the application."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class PageNotFoundException(WikiArenaException):
    """Raised when a specific Wikipedia page cannot be found."""
    pass

class InvalidModelNameException(WikiArenaException):
    """Raised when a requested model name is not available."""
    pass

class WikiServiceUnavailableException(WikiArenaException):
    """Raised when the Wikipedia API is unreachable or returns an error."""
    pass 