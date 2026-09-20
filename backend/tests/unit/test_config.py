from app.core.config import Settings


def test_settings_expose_organizer_gpt_placeholders_without_google_fields() -> None:
    fields = Settings.model_fields

    assert {
        "gpt_api_key",
        "gpt_base_url",
        "gpt_model",
        "gpt_embedding_model",
    } <= fields.keys()
    assert "google_api_key" not in fields
    assert "gemini_model" not in fields
    assert "gemini_embedding_model" not in fields


def test_settings_reports_only_missing_embedding_configuration_field_names() -> None:
    settings = Settings(
        gpt_api_key="secret-not-inspected-by-the-test",
        gpt_base_url="https://example.invalid",
        gpt_embedding_model="",
    )

    assert settings.has_any_embedding_configuration is True
    assert settings.has_complete_embedding_configuration is False
    assert settings.missing_embedding_configuration_fields == ("GPT_EMBEDDING_MODEL",)


def test_settings_recognizes_complete_embedding_configuration() -> None:
    settings = Settings(
        gpt_api_key="test-key",
        gpt_base_url="https://example.invalid",
        gpt_embedding_model="test-embedding-model",
    )

    assert settings.has_complete_embedding_configuration is True
    assert settings.missing_embedding_configuration_fields == ()


def test_the_shared_demo_admin_token_is_the_default_when_unset(monkeypatch):
    from app.core.config import Settings

    monkeypatch.delenv("PRIVACY_ADMIN_TOKEN", raising=False)

    assert Settings(_env_file=None).privacy_admin_token == "demo-admin-token"


def test_an_explicit_admin_token_overrides_the_default(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("PRIVACY_ADMIN_TOKEN", "my-own-token")

    assert Settings(_env_file=None).privacy_admin_token == "my-own-token"


def test_an_explicitly_empty_admin_token_still_fails_closed(monkeypatch):
    """The default only applies when the variable is absent: setting it empty is a
    deliberate 'no admin access' and must never fall back to the shared token."""
    from fastapi import HTTPException

    from app.api import deps
    from app.core import config

    monkeypatch.setenv("PRIVACY_ADMIN_TOKEN", "")
    config.get_settings.cache_clear()
    try:
        for header in (None, "Bearer demo-admin-token", "Bearer "):
            try:
                deps.require_admin(header)
            except HTTPException as exc:
                assert exc.status_code == 401
            else:
                raise AssertionError(f"empty token must reject {header!r}")
    finally:
        config.get_settings.cache_clear()
