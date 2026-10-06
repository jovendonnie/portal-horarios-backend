from src.core.security import (
    generate_session_token,
    generate_temporary_password,
    hash_password,
    verify_password,
)


def test_hash_password_produces_different_hashes_for_same_password() -> None:
    password = "correcthorsebatterystaple"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash


def test_verify_password_accepts_correct_password_for_both_hashes() -> None:
    password = "correcthorsebatterystaple"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert verify_password(password, first_hash) is True
    assert verify_password(password, second_hash) is True


def test_verify_password_rejects_incorrect_password() -> None:
    password_hash = hash_password("correcthorsebatterystaple")

    assert verify_password("wrong-password", password_hash) is False


def test_generate_session_token_produces_different_tokens() -> None:
    first_token = generate_session_token()
    second_token = generate_session_token()

    assert first_token != second_token


def test_generate_temporary_password_produces_different_passwords() -> None:
    first_password = generate_temporary_password()
    second_password = generate_temporary_password()

    assert first_password != second_password
