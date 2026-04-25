"""Shared pytest configuration for the backend package.

asyncio_mode = "auto" is set in the root pytest.ini so every async test
function runs under asyncio without needing @pytest.mark.asyncio.
"""
