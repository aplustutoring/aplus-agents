import os
import sys

# Tests must NEVER write to live systems: force DRY_RUN before src.config is imported
# (short-circuits every HubSpot/Slack/Gmail write). Tests that need write-path logic
# monkeypatch the client functions or module-level DRY_RUN explicitly.
os.environ["DRY_RUN"] = "true"

sys.path.insert(0, os.path.dirname(__file__))
