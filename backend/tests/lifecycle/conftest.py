"""Fixtures for the lifecycle tests.

The `approval_calls` fixture (autouse, in tests/conftest.py) records the
post-approval .delay() calls for every test.
"""
import pytest

from app.models.enums import FindingStatus, Severity
from tests import factories
from tests.lifecycle.helpers import XSS_ENDPOINT, XSS_TITLE


@pytest.fixture()
def site(db, dept, vendor_a):
    return factories.make_site(db, dept, vendor=vendor_a, name="Juice Shop", url="http://juice-shop.local:3000")


@pytest.fixture()
def xss_finding(db, site):
    return factories.make_finding(
        db, site, severity=Severity.HIGH, status=FindingStatus.APPROVED, endpoint=XSS_ENDPOINT, title=XSS_TITLE
    )


@pytest.fixture()
def open_ticket(db, xss_finding, vendor_a):
    return factories.make_ticket(db, xss_finding, vendor_a)