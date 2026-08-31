from housing_backend.infrastructure.http import safe_error


def test_safe_error_redacts_secrets() -> None:
    message = safe_error(
        RuntimeError(
            "https://api.odcloud.kr/test?serviceKey=very-secret&x=1 "
            'Authorization: "bearer-secret" X-Admin-Token=admin-secret'
        )
    )
    assert "very-secret" not in message
    assert "bearer-secret" not in message
    assert "admin-secret" not in message
    assert message.count("<redacted>") == 3
