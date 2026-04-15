from __future__ import annotations

from app.core.config import Settings


def test_settings_normalize_hosts_and_origins(settings_factory):
    settings = settings_factory(
        allowed_hosts="localhost/docs,https://demo.hf.space/docs,127.0.0.1:8000,*.hf.space",
        cors_allow_origins="https://FrontEnd.com/app/,http://LOCALHOST:3000",
    )

    assert settings.allowed_hosts == [
        "localhost",
        "demo.hf.space",
        "127.0.0.1",
        "*.hf.space",
    ]
    assert settings.cors_allow_origins == [
        "https://frontend.com",
        "http://localhost:3000",
    ]


def test_settings_create_runtime_directories(settings_factory):
    settings = settings_factory()

    assert settings.data_dir.exists()
    assert settings.generated_dir.exists()
    assert settings.knowledge_base_dir.exists()
    assert settings.resolved_qdrant_path.exists()
    assert settings.resolved_checkpoints_db_path.parent.exists()


def test_settings_accept_chatgpt_aliases(monkeypatch):
    monkeypatch.setenv("ORACULO_AGENT_CHATGPT_API_KEY", "alias-openai-key")
    monkeypatch.setenv("ORACULO_AGENT_CHATGPT_CHAT_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("ORACULO_AGENT_CHATGPT_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("ORACULO_AGENT_CHATGPT_TEMPERATURE", "0.2")
    settings = Settings()

    try:
        assert settings.can_use_openai_models is True
        assert settings.effective_openai_api_key == "alias-openai-key"
        assert settings.effective_openai_chat_model == "gpt-5.4-mini"
        assert settings.effective_openai_embedding_model == "text-embedding-3-small"
        assert settings.effective_openai_temperature == 0.2
    finally:
        for name in (
            "ORACULO_AGENT_CHATGPT_API_KEY",
            "ORACULO_AGENT_CHATGPT_CHAT_MODEL",
            "ORACULO_AGENT_CHATGPT_EMBEDDING_MODEL",
            "ORACULO_AGENT_CHATGPT_TEMPERATURE",
        ):
            monkeypatch.delenv(name, raising=False)
