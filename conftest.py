"""Pytest configuration file."""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "earth_engine: marks tests that require Earth Engine authentication"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")


@pytest.fixture(scope="session")
def ee_initialized():
    """Initialize Earth Engine once per test session.

    This fixture attempts to initialize Earth Engine and skips all
    tests requiring EE if initialization fails.
    """
    import ee

    try:
        ee.Initialize()
        return True
    except Exception as e:
        pytest.skip(f"Earth Engine not authenticated or Initialize failed: {e}")
        return False


@pytest.fixture(scope="session")
def ee_available():
    """Check if Earth Engine is available without initializing.

    This is a faster check that only imports ee and checks for credentials.
    """
    try:
        # Try to get credentials without full initialization
        try:
            from ee.data import get_persistent_credentials

            get_persistent_credentials()
            return True
        except Exception:
            return False
    except ImportError:
        return False
