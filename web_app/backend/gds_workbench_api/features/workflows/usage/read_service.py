"""Bounded numeric usage totals from durable, Model-owned request receipts."""

from typing import Annotated, Literal, LiteralString

from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import BaseModel, ConfigDict, Field

type UnpricedReason = Literal[
    "pricing_not_configured",
    "outside_pricing_window",
    "context_limit_exceeded",
    "missing_usage",
    "unsupported_token_types",
]
_UNPRICED_REASONS: tuple[UnpricedReason, ...] = (
    "pricing_not_configured",
    "outside_pricing_window",
    "context_limit_exceeded",
    "missing_usage",
    "unsupported_token_types",
)


class WorkflowCostEstimate(BaseModel):
    """Observed model token cost under immutable administrator-supplied rates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["unavailable", "unpriced", "partial", "estimated"] = "unavailable"
    currency: Literal["USD"] = "USD"
    amount: str | None = Field(default=None, pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")
    priced_request_count: int = Field(default=0, ge=0)
    unpriced_request_count: int = Field(default=0, ge=0)
    pricing_bases: tuple[str, ...] = ()
    unpriced_reasons: dict[UnpricedReason, Annotated[int, Field(ge=0)]] = Field(
        default_factory=lambda: dict.fromkeys(_UNPRICED_REASONS, 0)
    )


class WorkflowTokenUsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["unavailable", "recording", "complete", "partial"] = "unavailable"
    request_count: int = Field(default=0, ge=0)
    reported_request_count: int = Field(default=0, ge=0)
    pending_request_count: int = Field(default=0, ge=0)
    missing_usage_request_count: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    cache_write_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_output_tokens: int | None = Field(default=None, ge=0)
    history_incomplete: bool = False
    cost_estimate: WorkflowCostEstimate = Field(default_factory=WorkflowCostEstimate)


_TOKEN_USAGE_SQL: LiteralString = """
SELECT run.workflow_run_state,
       run.usage_tracking_version,
       (run.usage_history_incomplete OR (
           run.usage_tracking_version IS NOT NULL
           AND run.usage_tracked_recovery_count IS DISTINCT FROM run.workflow_run_recovery_count
       )) AS history_incomplete,
       usage.*
  FROM application.workflow_run AS run
  JOIN model.model AS model
    ON model.model_id = run.model_id
   AND model.tenant_id = %s
 CROSS JOIN LATERAL (
       SELECT count(*) AS request_count,
              count(*) FILTER (WHERE completed_time IS NULL) AS pending_request_count,
              count(*) FILTER (
                  WHERE completed_time IS NOT NULL
                    AND input_tokens IS NOT NULL
                    AND output_tokens IS NOT NULL
                    AND total_tokens IS NOT NULL
              ) AS reported_request_count,
              count(*) FILTER (
                  WHERE completed_time IS NOT NULL
                    AND (input_tokens IS NULL OR output_tokens IS NULL OR total_tokens IS NULL)
              ) AS missing_usage_request_count,
              sum(input_tokens) AS input_tokens,
              sum(output_tokens) AS output_tokens,
              sum(total_tokens) AS total_tokens,
              CASE WHEN count(*) = count(cached_input_tokens)
                   THEN coalesce(sum(cached_input_tokens), 0) END AS cached_input_tokens,
              CASE WHEN count(*) = count(cache_write_input_tokens)
                   THEN coalesce(sum(cache_write_input_tokens), 0) END AS cache_write_input_tokens,
              CASE WHEN count(*) = count(reasoning_output_tokens)
                   THEN coalesce(sum(reasoning_output_tokens), 0) END AS reasoning_output_tokens,
              count(*) FILTER (WHERE eligibility.reason IS NULL) AS priced_request_count,
              count(*) FILTER (WHERE eligibility.reason IS NOT NULL) AS unpriced_request_count,
              count(*) FILTER (
                  WHERE eligibility.reason = 'pricing_not_configured'
              ) AS pricing_not_configured_count,
              count(*) FILTER (
                  WHERE eligibility.reason = 'outside_pricing_window'
              ) AS outside_pricing_window_count,
              count(*) FILTER (
                  WHERE eligibility.reason = 'context_limit_exceeded'
              ) AS context_limit_exceeded_count,
              count(*) FILTER (
                  WHERE eligibility.reason = 'missing_usage'
              ) AS missing_usage_count,
              count(*) FILTER (
                  WHERE eligibility.reason = 'unsupported_token_types'
              ) AS unsupported_token_types_count,
              array_agg(DISTINCT pricing_basis ORDER BY pricing_basis) FILTER (
                  WHERE eligibility.reason IS NULL
              ) AS pricing_bases,
              sum(CASE WHEN eligibility.reason IS NULL THEN (
                  input_tokens::NUMERIC * pricing_input_usd_per_million
                  + coalesce(cached_input_tokens, 0)::NUMERIC
                      * (pricing_cached_input_usd_per_million - pricing_input_usd_per_million)
                  + coalesce(cache_write_input_tokens, 0)::NUMERIC
                      * (pricing_cache_write_input_usd_per_million - pricing_input_usd_per_million)
                  + output_tokens::NUMERIC * pricing_output_usd_per_million
              ) * 0.000001::NUMERIC END) AS cost_amount
         FROM application.workflow_run_model_request AS request
        CROSS JOIN LATERAL (
              SELECT CASE
                  WHEN pricing_basis IS NULL THEN 'pricing_not_configured'
                  WHEN completed_time IS NULL OR input_tokens IS NULL
                      OR output_tokens IS NULL OR total_tokens IS NULL THEN 'missing_usage'
                  WHEN other_token_types THEN 'unsupported_token_types'
                  WHEN started_time < pricing_valid_from
                      OR started_time >= pricing_valid_until THEN 'outside_pricing_window'
                  WHEN input_tokens > pricing_max_input_tokens THEN 'context_limit_exceeded'
                  WHEN input_tokens > 0 AND (
                      (cached_input_tokens IS NULL
                          AND pricing_cached_input_usd_per_million <> pricing_input_usd_per_million)
                      OR (cache_write_input_tokens IS NULL
                          AND pricing_cache_write_input_usd_per_million
                              <> pricing_input_usd_per_million)
                  ) THEN 'missing_usage'
              END AS reason
        ) AS eligibility
        WHERE request.workflow_run_id = run.workflow_run_id
 ) AS usage
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
"""


async def read_run_token_usage(
    transaction: ReadTransaction,
    *,
    tenant_id: int,
    model_id: int,
    workflow_run_id: int,
) -> WorkflowTokenUsageSummary | None:
    """Read inside the caller's authorized Run transaction, retaining ownership checks."""
    row = await transaction.fetch_one(_TOKEN_USAGE_SQL, (tenant_id, model_id, workflow_run_id))
    if row is None:
        return None
    if row["usage_tracking_version"] is None:
        return WorkflowTokenUsageSummary(history_incomplete=row["history_incomplete"])

    counts = {
        key: int(row[key])
        for key in (
            "request_count",
            "reported_request_count",
            "pending_request_count",
            "missing_usage_request_count",
        )
    }
    if row["workflow_run_state"] in {"queued", "running"}:
        status = "recording"
    elif (
        row["history_incomplete"]
        or counts["pending_request_count"]
        or counts["missing_usage_request_count"]
    ):
        status = "partial"
    else:
        status = "complete"
    # Known core counts remain useful on partial runs. Optional detail is shown
    # only when every receipt includes it; omitted detail never means zero.
    tokens = {
        key: (
            (None if row["history_incomplete"] else 0)
            if counts["request_count"] == 0
            else int(row[key])
            if row[key] is not None
            else None
        )
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "cache_write_input_tokens",
            "reasoning_output_tokens",
        )
    }
    cost = WorkflowCostEstimate()
    if counts["request_count"] == 0:
        if not row["history_incomplete"]:
            cost = WorkflowCostEstimate(status="estimated", amount="0")
    else:
        priced_count = int(row["priced_request_count"])
        unpriced_count = int(row["unpriced_request_count"])
        cost = WorkflowCostEstimate(
            status=(
                "unpriced"
                if priced_count == 0
                else "partial"
                if unpriced_count or row["history_incomplete"]
                else "estimated"
            ),
            amount=format(row["cost_amount"], "f") if priced_count else None,
            priced_request_count=priced_count,
            unpriced_request_count=unpriced_count,
            pricing_bases=tuple(row["pricing_bases"] or ()),
            unpriced_reasons={reason: int(row[f"{reason}_count"]) for reason in _UNPRICED_REASONS},
        )
    return WorkflowTokenUsageSummary.model_validate(
        {
            "status": status,
            **counts,
            **tokens,
            "history_incomplete": row["history_incomplete"],
            "cost_estimate": cost,
        }
    )
