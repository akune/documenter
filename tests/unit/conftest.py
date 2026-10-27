import os
import sys

# The application modules import each other by plain name (PYTHONPATH=/app/src in the image)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
