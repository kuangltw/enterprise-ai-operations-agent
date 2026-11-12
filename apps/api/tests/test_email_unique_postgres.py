"""Email 大小寫唯一索引的 PostgreSQL 整合測試。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.db import engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用本機 PostgreSQL 整合測試",
)


def test_email_case_difference_is_rejected():
    prefix = uuid4().hex
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.execute(text("""
                INSERT INTO users (id, email, password_hash)
                VALUES (:id, :email, 'synthetic-hash')
            """), {"id": str(uuid4()), "email": f"{prefix}@example.invalid"})
            savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(text("""
                    INSERT INTO users (id, email, password_hash)
                    VALUES (:id, :email, 'synthetic-hash')
                """), {"id": str(uuid4()), "email": f"{prefix.upper()}@example.invalid"})
            savepoint.rollback()
        finally:
            outer.rollback()
