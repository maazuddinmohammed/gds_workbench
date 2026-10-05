"""Start, observe, and cancel deterministic profiling. No caller SQL or metrics."""
# pyright: reportUnusedFunction=false

from typing import Annotated, Literal, NoReturn
from uuid import UUID

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.profiling.service import ProfilingService, ProfilingStatus
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError


def safe_error(error: Exception) -> NoReturn:
    if isinstance(error, WorkbenchError):
        raise ValueError(f"{error.code}: {error.message}") from None
    message = str(getattr(getattr(error, "diag", None), "message_primary", ""))
    errors = {
        "model_locked": "Model is locked. Only a human can unlock it.",
        "stale_model_revision": "Refresh the Model Snapshot and reassess before retrying.",
        "profiling_batch_ids_required": "Provide batch IDs for all selected batched Objects.",
        "profiling_protected_scope": "Selected scope has protected or uncertain masking lineage.",
        "profiling_request_conflict": "Request ID was already used for different inputs.",
        "profiling_environment_unavailable": "The selected environment is unavailable.",
        "profiling_run_not_found": "Profiling run is unavailable.",
        "tenant_workflow_conflict": "Another workflow is running for this Tenant.",
        "profiling_scope_changed": "Input metadata changed. Refresh the Snapshot before a new run.",
        "invalid_profiling_request": "Profiling inputs are invalid.",
    }
    for code, explanation in errors.items():
        if message == code or message.startswith(code + ":"):
            raise ValueError(f"{code}: {explanation}") from None
    raise ValueError(
        "profiling_request_failed: Check Model scope, revision, access, and Tenant Lock."
    ) from None


def register_profiling_tools(
    server: MCPServer[None],
    *,
    service: ProfilingService,
    identity_provider: IdentityProvider,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Start deterministic profiling for selected active applied Model Input Scope Objects. "
            "The backend builds SQL, executes through GDS Connection values, and saves profiles. "
            "Batch IDs are mandatory when any selected Object declares a batch Attribute. "
            "Reuse request_id for an identical retry; use the current Snapshot revision. "
            "Poll status, then refresh the Model Snapshot after completion. No SQL fallback."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
        ),
        meta={"gds/toolPolicy": ToolPolicy.TENANT_MODEL_WRITE.value},
        structured_output=True,
    )
    async def start_profiling_run(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        selected_object_ids: Annotated[
            list[Annotated[int, Field(gt=0)]], Field(min_length=1, max_length=500)
        ],
        expected_model_revision: Annotated[int, Field(gt=0)],
        request_id: UUID,
        batch_ids: Annotated[
            list[Annotated[str, Field(min_length=1, max_length=4000)]] | None,
            Field(min_length=1, max_length=2000),
        ] = None,
        environment_code: Annotated[str, Field(min_length=1, max_length=100)] = "dev",
        schema_version: Literal["1.0"] = "1.0",
    ) -> ProfilingStatus:
        del schema_version
        try:
            return await service.start(
                identity_provider.request_principal(ctx.request_context.request),
                model_id=model_id,
                selected_object_ids=selected_object_ids,
                expected_model_revision=expected_model_revision,
                request_id=request_id,
                batch_ids=batch_ids,
                environment_code=environment_code,
            )
        except Exception as error:
            safe_error(error)

    @server.tool(
        description=(
            "Read profiling state and progress. Completed means profiles have been saved; "
            "refresh the Model Snapshot."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        meta={"gds/toolPolicy": ToolPolicy.TENANT_READ.value},
        structured_output=True,
    )
    async def get_profiling_run_status(
        ctx: Context[None],
        run_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ProfilingStatus:
        del schema_version
        try:
            return await service.status(
                identity_provider.request_principal(ctx.request_context.request), run_id
            )
        except Exception as error:
            safe_error(error)

    @server.tool(
        description=(
            "Cancel your profiling run while holding its Tenant Lock. Revokes saving "
            "immediately and requests statement cancellation; prior saved profiles remain."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": ToolPolicy.TENANT_MODEL_WRITE.value},
        structured_output=True,
    )
    async def cancel_profiling_run(
        ctx: Context[None],
        run_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ProfilingStatus:
        del schema_version
        try:
            return await service.cancel(
                identity_provider.request_principal(ctx.request_context.request), run_id
            )
        except Exception as error:
            safe_error(error)

    for name, policy in (
        ("start_profiling_run", ToolPolicy.TENANT_MODEL_WRITE),
        ("get_profiling_run_status", ToolPolicy.TENANT_READ),
        ("cancel_profiling_run", ToolPolicy.TENANT_MODEL_WRITE),
    ):
        audit.register_tool(
            name,
            policy=policy,
            summarize_input=lambda _: {},
            retain_arguments=("model_id", "run_id", "schema_version"),
        )
