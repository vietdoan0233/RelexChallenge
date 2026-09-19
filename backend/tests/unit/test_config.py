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
