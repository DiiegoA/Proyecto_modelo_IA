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
