import pytest
from gds_etl_workbench.configuration import ConfigurationError

from gds_workbench_api.features.workflows.execution.configuration import (
    WorkflowExecutionConfiguration,
)


def test_workflow_execution_configuration_uses_packaged_defaults() -> None:
    configuration = WorkflowExecutionConfiguration.from_environment({})

    assert configuration.lease_duration_seconds == 30
    assert configuration.heartbeat_interval_seconds == 10
    assert configuration.idle_poll_interval_seconds == 1
    assert configuration.error_poll_interval_seconds == 5


def test_workflow_execution_configuration_accepts_bounded_environment_overrides() -> None:
    configuration = WorkflowExecutionConfiguration.from_environment(
        {
            "GDS_WEB_WORKFLOW_LEASE_SECONDS": "60",
            "GDS_WEB_WORKFLOW_HEARTBEAT_SECONDS": "15.5",
            "GDS_WEB_WORKFLOW_IDLE_POLL_SECONDS": "0.25",
            "GDS_WEB_WORKFLOW_ERROR_POLL_SECONDS": "2.5",
        }
    )

    assert configuration.lease_duration_seconds == 60
    assert configuration.heartbeat_interval_seconds == 15.5
    assert configuration.idle_poll_interval_seconds == 0.25
    assert configuration.error_poll_interval_seconds == 2.5


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"GDS_WEB_WORKFLOW_LEASE_SECONDS": "301"},
            "Workflow execution configuration is invalid",
        ),
        (
            {"GDS_WEB_WORKFLOW_IDLE_POLL_SECONDS": "not-a-number"},
            "GDS_WEB_WORKFLOW_IDLE_POLL_SECONDS must be a number",
        ),
        (
            {
                "GDS_WEB_WORKFLOW_LEASE_SECONDS": "10",
                "GDS_WEB_WORKFLOW_HEARTBEAT_SECONDS": "10",
            },
            "Workflow execution configuration is invalid",
        ),
    ],
)
def test_workflow_execution_configuration_rejects_unsafe_values(
    overrides: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ConfigurationError) as captured:
        WorkflowExecutionConfiguration.from_environment(overrides)

    assert str(captured.value) == message
