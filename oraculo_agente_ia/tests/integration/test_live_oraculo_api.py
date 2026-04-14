from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from tests.helpers import sqlite_url


ROOT = Path(__file__).resolve().parents[3]
ORACULO_API_ROOT = ROOT / "oraculo_api"
ORACULO_API_PYTHON = ORACULO_API_ROOT / ".venv" / "Scripts" / "python.exe"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _run_live_oraculo_api(*, port: int, database_url: str, jwt_secret: str, admin_email: str, admin_password: str) -> Iterator[str]:
    env = os.environ.copy()
    env.update(
        {
            "ORACULO_ENVIRONMENT": "test",
            "ORACULO_DATABASE_URL": database_url,
            "ORACULO_JWT_SECRET_KEY": jwt_secret,
            "ORACULO_ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
            "ORACULO_RATE_LIMIT_ENABLED": "false",
            "ORACULO_AUTO_SEED_ADMIN": "true",
            "ORACULO_SEED_ADMIN_EMAIL": admin_email,
            "ORACULO_SEED_ADMIN_PASSWORD": admin_password,
            "ORACULO_DOCS_ENABLED": "false",
        }
    )
    log_file = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False)
    process = subprocess.Popen(
        [
            str(ORACULO_API_PYTHON),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ORACULO_API_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=5.0) as client:
            deadline = time.time() + 180
            while time.time() < deadline:
                if process.poll() is not None:
                    log_file.flush()
                    log_file.seek(0)
                    logs = log_file.read()
                    raise RuntimeError(f"oraculo_api process exited before becoming ready.\n{logs}")
                try:
                    response = client.get(f"{base_url}/api/v1/health/ready")
                    if response.status_code == 200:
                        payload = response.json()
                        if payload.get("database_connected") and payload.get("model_loaded"):
                            yield base_url
                            return
                except httpx.HTTPError:
                    pass
                time.sleep(1)
        log_file.flush()
        log_file.seek(0)
        logs = log_file.read()
        raise RuntimeError(f"oraculo_api did not become ready in time.\n{logs}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
        log_file.close()


@pytest.mark.integration
@pytest.mark.live
def test_agent_invokes_real_oraculo_api_for_prediction(client_factory, tmp_path):
    if not ORACULO_API_ROOT.exists():
        pytest.skip("Sibling oraculo_api project is not available.")
    if not ORACULO_API_PYTHON.exists():
        pytest.skip("Sibling oraculo_api virtual environment is not available.")

    port = _pick_free_port()
    jwt_secret = "live-integration-secret-that-is-long-enough-32"
    admin_email = "service.integration@example.com"
    admin_password = "StrongPass!12345"
    database_url = sqlite_url(tmp_path / "live_integration.db")

    with _run_live_oraculo_api(
        port=port,
        database_url=database_url,
        jwt_secret=jwt_secret,
        admin_email=admin_email,
        admin_password=admin_password,
    ) as base_url:
        with httpx.Client(base_url=base_url, timeout=20.0) as upstream_client:
            login_response = upstream_client.post(
                "/api/v1/auth/login",
                json={"email": admin_email, "password": admin_password},
            )
            assert login_response.status_code == 200
            user_token = login_response.json()["access_token"]

        message = (
            "Haz una prediccion con este JSON: "
            '{"age": 39, "workclass": "Private", "fnlwgt": 77516, '
            '"education": "Bachelors", "education.num": 13, '
            '"marital.status": "Never-married", "occupation": "Adm-clerical", '
            '"relationship": "Not-in-family", "race": "White", "sex": "Male", '
            '"capital.gain": 2174, "capital.loss": 0, "hours.per.week": 40, '
            '"native.country": "United-States"}'
        )

        with client_factory(
            oraculo_api_base_url=base_url,
            oraculo_api_verify_remote_user=True,
            oraculo_api_jwt_secret_key=jwt_secret,
            oraculo_api_service_email="broken.service@example.com",
            oraculo_api_service_password="BrokenPassword!123",
        ) as (client, _settings):
            response = client.post(
                "/api/v1/chat/invoke",
                json={"message": message},
                headers={"Authorization": f"Bearer {user_token}"},
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "prediction"
    assert payload["prediction_result"] is not None
    assert payload["prediction_result"]["label"] in {">50K", "<=50K"}
