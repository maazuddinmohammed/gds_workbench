"""Description edits share physical Metadata locks, revision fencing and audit."""

# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_metadata_review_governance import (
    _review,
    _selection,
    _setup,
)


@pytest.mark.parametrize("record_type", ["object", "attribute"])
async def test_description_edit_preserves_metadata_and_rejects_stale_locked_retries(
    web_postgres_database: DisposablePostgres, record_type: str
) -> None:
    context, attributes, runtime = _setup(web_postgres_database)
    ids = (
        context.selected_object_ids[0] if record_type == "object" else attributes[0],
    )
    selected = _selection(web_postgres_database, record_type, ids)
    body = [
        {**selected[0], "description": "Customer identifier.\nUsed to match Orders."}
    ]
    key = uuid4()
    await runtime.open()
    try:
        result = await _review(runtime, context, record_type, "describe", body, key=key)
        assert result["denial_code"] is None and result["action_count"] == 1
        assert (
            await _review(runtime, context, record_type, "describe", body, key=key)
            == result
        )
        changed = [{**body[0], "description": "A different description."}]
        assert (
            await _review(runtime, context, record_type, "describe", changed, key=key)
        )["denial_code"] == "metadata_review_conflict"
        assert (await _review(runtime, context, record_type, "describe", body))[
            "denial_code"
        ] == "metadata_revision_conflict"
        fresh = _selection(web_postgres_database, record_type, ids)
        assert (await _review(runtime, context, record_type, "lock", fresh))[
            "denial_code"
        ] is None
        locked = [
            {
                **_selection(web_postgres_database, record_type, ids)[0],
                "description": None,
            }
        ]
        assert (await _review(runtime, context, record_type, "describe", locked))[
            "denial_code"
        ] == f"{record_type}_locked"
    finally:
        await runtime.close()
    with web_postgres_database.connect_owner() as connection:
        if record_type == "object":
            row = connection.execute(
                "SELECT object_description AS description, is_active, is_locked "
                "FROM core.object WHERE object_id=%s",
                ids,
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT attribute_description AS description, is_active, is_locked "
                "FROM core.attribute WHERE attribute_id=%s",
                ids,
            ).fetchone()
        assert row == {
            "description": body[0]["description"],
            "is_active": True,
            "is_locked": True,
        }
        events = connection.execute(
            "SELECT before_records, records FROM application.metadata_review_event "
            "WHERE tenant_id=%s AND action='describe'",
            (context.tenant_id,),
        ).fetchall()
        assert len(events) == 1
        assert "description" not in events[0]["before_records"][0]
        assert "description_digest" in events[0]["before_records"][0]


@pytest.mark.parametrize("description", ["x" * 2001, "é" * 1001, "bad\u0001text"])
async def test_description_write_is_bounded_at_the_sql_boundary(
    web_postgres_database: DisposablePostgres, description: str
) -> None:
    context, _, runtime = _setup(web_postgres_database)
    body = [
        {
            **_selection(web_postgres_database, "object", context.selected_object_ids)[
                0
            ],
            "description": description,
        }
    ]
    await runtime.open()
    try:
        assert (await _review(runtime, context, "object", "describe", body))[
            "denial_code"
        ] == "invalid_request"
    finally:
        await runtime.close()
