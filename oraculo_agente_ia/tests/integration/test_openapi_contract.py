from __future__ import annotations

import pytest
import schemathesis


@pytest.mark.integration
def test_openapi_health_live_contract(client_factory, fake_oraculo_api_client):
    with client_factory(fake_client=fake_oraculo_api_client) as (client, _settings):
        schema = schemathesis.openapi.from_dict(client.get("/openapi.json").json())
        case = schema["/api/v1/health/live"]["GET"].Case()
        response = client.get("/api/v1/health/live")
        case.validate_response(response)

    assert response.status_code == 200
