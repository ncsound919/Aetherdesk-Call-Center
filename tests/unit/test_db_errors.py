import pytest
from apps.api.services.db_errors import DatabaseError, NotFoundError, PoolNotAvailableError


class TestDatabaseError:
    def test_basic_error(self):
        err = DatabaseError("something went wrong")
        assert str(err) == "something went wrong"
        assert err.detail == {}

    def test_error_with_detail(self):
        err = DatabaseError("failed", {"code": 500})
        assert err.detail == {"code": 500}

    def test_not_found_error(self):
        err = NotFoundError("User", "USER-001")
        assert "User" in str(err)
        assert "USER-001" in str(err)
        assert err.detail == {"resource": "User", "id": "USER-001"}

    def test_pool_not_available(self):
        err = PoolNotAvailableError()
        assert "pool" in str(err).lower()

    def test_inheritance(self):
        assert issubclass(NotFoundError, DatabaseError)
        assert issubclass(PoolNotAvailableError, DatabaseError)
