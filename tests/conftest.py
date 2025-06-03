import sys
import os

# Add the project root directory to sys.path
# This allows pytest to find the 'backend' module when tests are run.
# os.path.dirname(__file__) is the 'tests' directory
# os.path.join(os.path.dirname(__file__), '..') goes one level up to the project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# We can also define project-wide fixtures here if needed later. 