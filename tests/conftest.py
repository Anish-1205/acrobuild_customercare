"""Shared test isolation.

services/request_security_service.py rate-limits /api/support/assist to 30
requests per 60s per client IP, and every TestClient request arrives from the
same identity ("testclient"). The HTTP-level tests in this suite together
exceed that inside one 60s window, so whichever tests happened to run last
got a 429 and failed with a confusing KeyError on the missing response body.
That made the suite order-dependent and flaky (a second consecutive run of
the same files would fail where the first passed).

The limiter is a production safeguard, not behaviour any test here is
asserting, so clear its bucket table before each test. The one test that does
assert on it (test_upgrade_security.test_rate_limit_is_durable) issues its own
requests after this reset and is unaffected.
"""
from contextlib import closing

import pytest


@pytest.fixture(autouse=True)
def _reset_request_rate_limits():
    from services.database_service import open_database_connection
    try:
        with closing(open_database_connection()) as conn, conn:
            conn.execute("DELETE FROM request_limits")
    except Exception:
        # The table only exists once initialize_database() has run; a test
        # module that never touches the DB does not need the reset.
        pass
    yield
