import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: hits real external APIs")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "integration" in item.keywords:
            missing = [
                var for var in ("COMMAND_API_KEY", "COMMAND_DEVICE_ID")
                if not os.getenv(var)
            ]
            if missing:
                item.add_marker(
                    pytest.mark.skip(reason=f"missing env vars: {', '.join(missing)}")
                )
