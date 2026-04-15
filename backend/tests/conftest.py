import sys
import os

# Ensure backend/ is on sys.path so services/config can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
