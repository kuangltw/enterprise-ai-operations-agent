"""密碼雜湊的行為與不可信儲存值防護。"""

from src.passwords import hash_password, verify_password


def test_hash_uses_unique_salts_and_never_contains_plaintext():
    password = "測試用安全密碼-12345"
    first = hash_password(password)
    second = hash_password(password)

    assert first != second
    assert password not in first
    assert verify_password(password, first)
    assert verify_password(password, second)


def test_wrong_password_and_malformed_hash_are_rejected():
    encoded = hash_password("synthetic-password-123")

    assert not verify_password("incorrect-password", encoded)
    assert not verify_password("synthetic-password-123", "malformed")
    assert not verify_password("synthetic-password-123", encoded.replace("32768", "999999999"))


def test_password_input_is_bounded():
    try:
        hash_password("x" * 1025)
    except ValueError:
        pass
    else:
        raise AssertionError("過長密碼必須拒絕")
