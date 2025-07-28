"""
Elastic Beanstalk WSGI entry point for Wiki Arena FastAPI application.

This file is the bridge between Elastic Beanstalk's WSGI server and your FastAPI app.
EB looks for a variable named 'application' in this file to run your app.
"""

import os
import sys
import logging

# Add the src directory to Python path so we can import our modules
# This matches the PYTHONPATH we set in the EB configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import your FastAPI app
from backend.main import app

# Elastic Beanstalk expects a variable named 'application'
# This is what the WSGI server will actually run
application = app

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # This won't run in EB (since EB uses WSGI), but useful for local testing
    import uvicorn
    logger.info("Running FastAPI app locally...")
    uvicorn.run(application, host="0.0.0.0", port=8000)