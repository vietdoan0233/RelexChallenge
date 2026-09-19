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
