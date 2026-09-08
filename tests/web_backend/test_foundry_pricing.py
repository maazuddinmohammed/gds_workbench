"""Configured pricing is exact, optional, bounded, and never guessed from model names."""

import json
from decimal import Decimal

import pytest
from gds_etl_workbench.configuration import ConfigurationError
from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.features.workflows.usage.contracts import FoundryModelPricing
from gds_workbench_api.integrations.agents.configuration import AgentRuntimeConfiguration
from pydantic import ValidationError


def _pricing() -> dict[str, object]:
    return {
        "basis": "Synthetic fixture rates",
        "input_usd_per_million": "2.12345678",
        "cached_input_usd_per_million": "0.2",
        "cache_write_input_usd_per_million": "2.5",
        "output_usd_per_million": "10",
        "valid_from": "2026-09-01T00:00:00Z",
        "valid_until": "2026-10-01T00:00:00Z",
        "max_input_tokens": 100000,
    }


def _remote(pricing: str | None = None) -> AgentRuntimeConfiguration:
    values = {
        "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
        "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": "https://fixture.openai.azure.com/openai/v1/",
        "GDS_WEB_FOUNDRY_API_KEY": "synthetic-fixture-key",
    }
    if pricing is not None:
        values["GDS_WEB_FOUNDRY_PRICING_JSON"] = pricing
    return AgentRuntimeConfiguration.from_environment(values, production=False)


def test_pricing_is_optional_and_binds_only_the_configured_registered_model() -> None:
    assert all(connection.pricing is None for connection in _remote().connections)
    configured = _remote(json.dumps({"foundry-primary": _pricing()}))
    primary = next(item for item in configured.connections if item.model_code == "foundry-primary")
    assert primary.pricing is not None
    assert primary.pricing.input_usd_per_million == Decimal("2.12345678")
    assert primary.pricing.model_dump(mode="json")["input_usd_per_million"] == "2.12345678"
    assert all(
        item.pricing is None
        for item in configured.connections
        if item.model_code != "foundry-primary"
    )


def test_app_settings_accept_and_forward_pricing_without_exposing_it_in_repr() -> None:
    # Parse configuration only; never connect to this deliberately unusable address.
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": "https://fixture.openai.azure.com/openai/v1/",
            "GDS_WEB_FOUNDRY_API_KEY": "synthetic-fixture-key",
            "GDS_WEB_FOUNDRY_PRICING_JSON": json.dumps({"foundry-primary": _pricing()}),
        }
    )
    pricing = next(
        item.pricing
        for item in settings.agent_runtime.connections
        if item.model_code == "foundry-primary"
    )
    assert pricing is not None and pricing.input_usd_per_million == Decimal("2.12345678")
    assert pricing.basis not in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_usd_per_million", "-1"),
        ("input_usd_per_million", "1000001"),
        ("input_usd_per_million", "0.000000001"),
        ("input_usd_per_million", "NaN"),
        ("input_usd_per_million", "Infinity"),
        ("input_usd_per_million", True),
        ("input_usd_per_million", None),
        ("cached_input_usd_per_million", "-1"),
        ("cache_write_input_usd_per_million", "-1"),
        ("output_usd_per_million", "-1"),
        ("valid_from", "2026-09-01T00:00:00"),
        ("valid_until", "2026-09-01T00:00:00Z"),
        ("valid_until", "2026-08-01T00:00:00Z"),
        ("max_input_tokens", 0),
        ("max_input_tokens", 1000000000001),
        ("max_input_tokens", True),
        ("max_input_tokens", "1000"),
        ("basis", ""),
        ("basis", "x" * 81),
        ("basis", "Private\nValue"),
        ("basis", "<script>Private</script>"),
        ("unknown_field", "Private"),
    ],
)
def test_pricing_rejects_invalid_configuration_without_echo(field: str, value: object) -> None:
    pricing = {**_pricing(), field: value}
    with pytest.raises(ValidationError):
        FoundryModelPricing.model_validate_json(json.dumps(pricing), strict=True)
    with pytest.raises(ConfigurationError) as caught:
        _remote(json.dumps({"foundry-primary": pricing}))
    assert "Private" not in str(caught.value)
    assert "synthetic-fixture-key" not in str(caught.value)


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "{",
        '{"foundry-primary":null}',
        '{"foundry-primary":{},"foundry-primary":{}}',
        json.dumps({"unregistered-private-model": _pricing()}),
        json.dumps({"foundry-primary": {**_pricing(), "basis": "x" * 65536}}),
    ],
)
def test_pricing_rejects_malformed_unregistered_duplicate_and_oversized_maps(raw: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        _remote(raw)
    assert "private-model" not in str(caught.value)


def test_pricing_requires_explicit_cache_rates_and_allows_zero_and_unrestricted_windows() -> None:
    pricing = {
        **_pricing(),
        "input_usd_per_million": "0",
        "valid_from": None,
        "valid_until": None,
        "max_input_tokens": None,
    }
    parsed = FoundryModelPricing.model_validate_json(json.dumps(pricing), strict=True)
    assert parsed.input_usd_per_million == Decimal(0)
    assert parsed.valid_from is None and parsed.valid_until is None
    del pricing["cache_write_input_usd_per_million"]
    with pytest.raises(ValidationError):
        FoundryModelPricing.model_validate_json(json.dumps(pricing), strict=True)


def test_fake_runtime_cannot_accept_real_pricing_settings() -> None:
    with pytest.raises(ConfigurationError, match="does not accept provider settings"):
        AgentRuntimeConfiguration.from_environment(
            {"GDS_WEB_FOUNDRY_PRICING_JSON": json.dumps({"foundry-primary": _pricing()})},
            production=False,
        )
