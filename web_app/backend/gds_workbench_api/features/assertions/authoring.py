"""Manual requirements use the same Assertion records and graph validation as imports."""

from typing import Annotated

from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_validation import (
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import read_model_review_snapshot
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ModelingAssertionRecordRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type Nonblank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AssertionDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    notes: Nonblank | None = None


class SaveAssertionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, str_strip_whitespace=True)

    expected_model_revision: int = Field(gt=0)
    record_id: int | None = Field(default=None, gt=0)
    document_name: str = Field(min_length=1, max_length=255, pattern=r"\S")
    document_type: str | None = Field(default=None, min_length=1, max_length=100)
    record_key: str = Field(min_length=1, max_length=100, pattern=r"\S")
    record_type: str = Field(min_length=1, max_length=100, pattern=r"\S")
    text: Nonblank
    details: AssertionDetails = Field(default_factory=AssertionDetails)
    source_system_code: str | None = Field(default=None, min_length=1, max_length=100)
    source_reference: Nonblank | None = None


async def prepare_assertion(
    transaction: ReadTransaction,
    model: ModelReadContext,
    command: SaveAssertionRequest,
) -> ValidatedModelChangeSet:
    review = await read_model_review_snapshot(transaction, model, enforce_row_limits=False)
    snapshot = review.snapshot
    key = normalize_model_key_value(command.record_key)
    row = (
        review.records_by_id.get("modeling_assertion_record", {}).get(command.record_id)
        if command.record_id is not None
        else None
    )
    existing = row if isinstance(row, ModelingAssertionRecordRecord) else None
    if command.record_id is not None:
        if (
            existing is None
            or normalize_model_key_value(existing.modeling_assertion_record_key) != key
        ):
            raise InvalidRequestError("The Assertion is unavailable. Refresh and retry.")
        if existing.modeling_assertion_record_is_locked:
            raise InvalidRequestError("Unlock this Assertion before editing it.")
        if normalize_model_key_value(
            existing.modeling_assertion_document_name
        ) != normalize_model_key_value(command.document_name):
            raise InvalidRequestError("An Assertion must stay in its original Document.")
    elif any(
        normalize_model_key_value(r.modeling_assertion_record_key) == key
        for r in snapshot.assertion.records
    ):
        raise InvalidRequestError("This Assertion key already exists. Choose a different key.")

    document_name = existing.modeling_assertion_document_name if existing else command.document_name
    document = next(
        (
            d
            for d in snapshot.assertion.documents
            if normalize_model_key_value(d.modeling_assertion_document_name)
            == normalize_model_key_value(document_name)
        ),
        None,
    )
    if existing is not None and not (
        (existing.modeling_assertion_source_location or {}).get("entry_method") == "manual"
        or document is not None
        and document.modeling_assertion_document_metadata.get("origin") == "manual"
    ):
        raise InvalidRequestError("Only manually entered Assertions can be edited here.")

    # Systems are registered globally. Tenant scope always comes from the authorized Model.
    tenant = await transaction.fetch_one(
        "SELECT tenant_code FROM core.tenant WHERE tenant_id = %s AND is_active",
        (model.tenant_id,),
    )
    if tenant is None:
        raise InvalidRequestError("The Model Tenant is unavailable.")
    if document is not None and not document.is_active:
        raise InvalidRequestError("This Document is inactive. Choose an active Document.")
    if document is not None and (
        document.system_code != command.source_system_code
        or document.modeling_assertion_document_type != command.document_type
    ):
        raise InvalidRequestError(
            "Existing Document type and scope cannot change here. Refresh and retry."
        )
    staged: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
        "modeling_assertion_document": []
        if document
        else [
            {
                "modeling_assertion_document_name": document_name,
                "tenant_code": tenant["tenant_code"] if command.source_system_code else None,
                "system_code": command.source_system_code,
                "modeling_assertion_file_pattern": None,
                "modeling_assertion_document_type": command.document_type,
                "modeling_assertion_document_description": None,
                "modeling_assertion_document_metadata": {"origin": "manual"},
                "is_active": True,
            }
        ],
        "modeling_assertion_record": [
            {
                "modeling_assertion_document_name": document_name,
                "modeling_assertion_record_key": command.record_key,
                "modeling_assertion_record_type": command.record_type,
                "modeling_assertion_text": command.text,
                "modeling_assertion_details": {
                    **(
                        {
                            name: value
                            for name, value in existing.modeling_assertion_details.items()
                            if name not in AssertionDetails.model_fields
                        }
                        if existing
                        else {}
                    ),
                    **command.details.model_dump(exclude_none=True),
                },
                "modeling_assertion_source_location": {
                    "entry_method": "manual",
                    **({"reference": command.source_reference} if command.source_reference else {}),
                },
                "modeling_assertion_applicable_layers": [
                    "analysis",
                    "conceptual",
                    "logical",
                    "dimensional",
                    "mapping",
                ],
                "modeling_assertion_confidence": existing.modeling_assertion_confidence
                if existing
                else None,
                "modeling_assertion_record_status": (
                    existing.modeling_assertion_record_status if existing else "active"
                ),
                "modeling_assertion_record_is_locked": False,
            }
        ],
    }
    validation = validate_future_graph(
        snapshot=snapshot,
        staged_documents=staged,
        physical_scope=await load_model_physical_scope(transaction, model),
    )
    if not validation.valid or validation.candidate_digest is None:
        raise InvalidRequestError(
            "The Assertion could not be saved. Check its Document, System, "
            "and existing model references."
        )
    return validation
