"""文件上傳預約的權限、原子寫入及冪等行為。"""

from io import BytesIO
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db import engine
from src.document_uploads import (
    IdempotencyConflict, UploadForbidden, reserve_document_upload,
)
from src.object_storage import PreparedPdf, prepare_pdf

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1", reason="需明確啟用 PostgreSQL 整合測試",
)


def test_reservation_rechecks_membership_and_is_idempotent():
    tenant_a, tenant_b, staff_id, viewer_id, key = (uuid4() for _ in range(5))
    prepared = prepare_pdf(BytesIO(b"%PDF-1.4\nsynthetic reservation\n%%EOF\n"))
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            for tenant_id in (tenant_a, tenant_b):
                connection.execute(text("""
                    INSERT INTO tenants (id, name) VALUES (:id, '合成上傳租戶')
                """), {"id": str(tenant_id)})
            for user_id, role in ((staff_id, "staff"), (viewer_id, "viewer")):
                connection.execute(text("""
                    INSERT INTO users (id, email, password_hash)
                    VALUES (:id, :email, 'synthetic-hash')
                """), {"id": str(user_id), "email": f"{uuid4().hex}@example.invalid"})
                connection.execute(text("""
                    INSERT INTO memberships (tenant_id, user_id, role)
                    VALUES (:tenant_id, :user_id, :role)
                """), {"tenant_id": str(tenant_a), "user_id": str(user_id),
                       "role": role})
            connection.execute(text("""
                INSERT INTO memberships (tenant_id, user_id, role)
                VALUES (:tenant_id, :user_id, 'staff')
            """), {"tenant_id": str(tenant_b), "user_id": str(staff_id)})

            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                reserved = reserve_document_upload(db, tenant_a, staff_id,
                                                   " 合成文件 ", key, prepared)
                assert not reserved.was_existing
                assert reserved.storage_status == "pending_upload"
                again = reserve_document_upload(db, tenant_a, staff_id,
                                                "合成文件", key, prepared)
                assert again.was_existing
                assert (again.document_id, again.version_id, again.storage_key) == (
                    reserved.document_id, reserved.version_id, reserved.storage_key,
                )
                with pytest.raises(IdempotencyConflict):
                    reserve_document_upload(db, tenant_a, staff_id,
                                            "另一個標題", key, prepared)
                with pytest.raises(UploadForbidden):
                    reserve_document_upload(db, tenant_a, viewer_id,
                                            "合成文件", uuid4(), prepared)
                with pytest.raises(ValueError):
                    reserve_document_upload(db, tenant_a, staff_id,
                                            "合成文件", uuid4(),
                                            PreparedPdf(prepared.data, "0" * 64,
                                                        prepared.size))
                other_tenant = reserve_document_upload(db, tenant_b, staff_id,
                                                       "合成文件", key, prepared)
                assert other_tenant.document_id != reserved.document_id

            count = connection.execute(text("""
                SELECT count(*) FROM document_versions
                WHERE tenant_id = :tenant_id AND idempotency_key = :key
            """), {"tenant_id": str(tenant_a), "key": str(key)}).scalar_one()
            assert count == 1
            acl_count = connection.execute(text("""
                SELECT count(*) FROM document_user_acl
                WHERE tenant_id = :tenant_id AND document_id = :document_id
                  AND user_id = :user_id
            """), {"tenant_id": str(tenant_a), "document_id": str(reserved.document_id),
                   "user_id": str(staff_id)}).scalar_one()
            assert acl_count == 1
            role_acl_count = connection.execute(text("""
                SELECT count(*) FROM document_acl
                WHERE tenant_id = :tenant_id AND document_id = :document_id
            """), {"tenant_id": str(tenant_a),
                   "document_id": str(reserved.document_id)}).scalar_one()
            assert role_acl_count == 0
        finally:
            outer.rollback()
