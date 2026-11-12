"""空白資料庫首次建帳的輸入檢查。"""

import pytest

from src.bootstrap_identity import create_initial_admin


@pytest.mark.parametrize("email,password,name", [
    ("invalid", "synthetic-password-123", "測試租戶"),
    ("admin@example.invalid", "short", "測試租戶"),
    ("admin@example.invalid", "synthetic-password-123", ""),
])
def test_invalid_bootstrap_input_fails_before_database_access(email, password, name):
    class NoDatabaseAccess:
        def execute(self, *_):
            raise AssertionError("無效輸入不應觸及資料庫")

    with pytest.raises(ValueError):
        create_initial_admin(NoDatabaseAccess(), email, password, name)
