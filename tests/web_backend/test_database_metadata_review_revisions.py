"""Physical catalog revisions and inactive visibility on disposable PostgreSQL."""

# pyright: reportPrivateUsage=false
import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata import (
    DatabaseMetadataService,
    MetadataObjectNotFoundError,
    ObjectCatalogFilters,
    PostgresMetadataRepository,
)
from gds_workbench_api.features.model_input_scope import (
    DatabaseModelInputScopeService,
    ModelInputScopeObjectNotFoundError,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_model_change_sets import _seed_profile_model


async def test_catalog_revisions_hash_full_hidden_content_and_ignore_session_timezone(
    web_postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id, attribute_id, entra_tenant_id, entra_object_id, _ = _seed_profile_model(
        web_postgres_database
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    with web_postgres_database.connect_owner() as connection:
        object_id = require_row(
            connection.execute(
                (
                    "UPDATE core.attribute SET attribute_description=%s, "
                    "attribute_custom_code='original' WHERE attribute_id=%s RETURNING "
                    "object_id"
                ),
                ("x" * 2000 + "original", attribute_id),
            ).fetchone()
        )["object_id"]
        connection.execute(
            "UPDATE core.object SET object_description=%s WHERE object_id=%s",
            ("y" * 2000 + "original", object_id),
        )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    catalog = DatabaseMetadataService(
        database=database,
        repository=PostgresMetadataRepository(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"fixture-catalog-review-key-32-bytes",
    )
    scope = DatabaseModelInputScopeService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"fixture-scope-review-key-32-bytes",
    )
    await database.open()
    try:
        baseline = await catalog.get_object(principal, tenant_id=tenant_id, object_id=object_id)
        summary = await catalog.list_objects(
            principal,
            tenant_id=tenant_id,
            filters=ObjectCatalogFilters(active_state="all"),
            page_size=200,
            cursor=None,
        )
        listed = next(item for item in summary.items if item.object_id == object_id)
        assert listed.review_revision == baseline.review_revision
        assert listed.is_locked is baseline.is_locked is False
        scoped = await scope.read_input_scope_object(
            principal, tenant_id=tenant_id, model_id=model_id, object_id=object_id
        )
        assert scoped.attributes[0].review_revision == baseline.attributes[0].review_revision
        assert scoped.review_revision == baseline.review_revision
        assert scoped.object_description == baseline.object_description
        assert scoped.description_truncated is True
        assert baseline.object_description == "y" * 2000
        assert baseline.attributes[0].attribute_description == "x" * 2000
        timezone_revisions: list[object] = []
        async with database.read_transaction() as transaction:
            for timezone in ("UTC", "Pacific/Honolulu", "Asia/Kolkata"):
                await transaction.fetch_one("SELECT set_config('TimeZone', %s, TRUE)", (timezone,))
                timezone_revisions.append(
                    await transaction.fetch_one(
                        (
                            "SELECT application.metadata_object_review_revision(object) AS "
                            "object_revision, "
                            "application.metadata_attribute_review_revision(attribute, "
                            "object) AS attribute_revision FROM core.object AS object JOIN "
                            "core.attribute AS attribute ON "
                            "attribute.object_id=object.object_id WHERE "
                            "attribute.attribute_id=%s"
                        ),
                        (attribute_id,),
                    )
                )
        assert (
            timezone_revisions
            == [
                {
                    "object_revision": baseline.review_revision,
                    "attribute_revision": baseline.attributes[0].review_revision,
                }
            ]
            * 3
        )
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.attribute SET attribute_description=%s WHERE attribute_id=%s",
                ("x" * 2000 + "changed", attribute_id),
            )
        changed_description = await catalog.get_object(
            principal, tenant_id=tenant_id, object_id=object_id
        )
        assert (
            changed_description.attributes[0].attribute_description
            == baseline.attributes[0].attribute_description
        )
        assert (
            changed_description.attributes[0].review_revision
            != baseline.attributes[0].review_revision
        )
        assert changed_description.review_revision == baseline.review_revision
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.attribute SET attribute_custom_code='changed' WHERE attribute_id=%s",
                (attribute_id,),
            )
        changed_hidden = await catalog.get_object(
            principal, tenant_id=tenant_id, object_id=object_id
        )
        assert changed_hidden.attributes[0].model_dump(
            exclude={"review_revision"}
        ) == changed_description.attributes[0].model_dump(exclude={"review_revision"})
        assert (
            changed_hidden.attributes[0].review_revision
            != changed_description.attributes[0].review_revision
        )
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.object SET object_description=%s WHERE object_id=%s",
                ("y" * 2000 + "changed", object_id),
            )
        changed_object = await catalog.get_object(
            principal, tenant_id=tenant_id, object_id=object_id
        )
        assert changed_object.object_description == baseline.object_description
        assert changed_object.review_revision != baseline.review_revision
        # Child revisions witness the parent's identity, ownership and lifecycle,
        # while unrelated parent content does not invalidate a child action.
        assert (
            changed_object.attributes[0].review_revision
            == changed_hidden.attributes[0].review_revision
        )
    finally:
        await database.close()


@pytest.mark.parametrize(
    "change", ["parent_lock", "parent_inactive", "child_inactive", "source_tenant"]
)
async def test_catalog_retains_inactive_records_but_scope_keeps_current_eligibility(
    web_postgres_database: DisposablePostgres,
    change: str,
) -> None:
    model_id, tenant_id, attribute_id, entra_tenant_id, entra_object_id, _ = _seed_profile_model(
        web_postgres_database
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    with web_postgres_database.connect_owner() as connection:
        object_id = require_row(
            connection.execute(
                "SELECT object_id FROM core.attribute WHERE attribute_id=%s",
                (attribute_id,),
            ).fetchone()
        )["object_id"]
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    catalog = DatabaseMetadataService(
        database=database,
        repository=PostgresMetadataRepository(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"fixture-catalog-review-key-32-bytes",
    )
    scope = DatabaseModelInputScopeService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"fixture-scope-review-key-32-bytes",
    )
    await database.open()
    try:
        baseline = await catalog.get_object(principal, tenant_id=tenant_id, object_id=object_id)
        if change == "source_tenant":
            _, foreign_tenant, *_ = _seed_profile_model(web_postgres_database)
            with web_postgres_database.connect_owner() as connection:
                connection.execute(
                    "UPDATE core.object SET source_tenant_id=%s WHERE object_id=%s",
                    (foreign_tenant, object_id),
                )
                revision = require_row(
                    connection.execute(
                        (
                            "SELECT "
                            "application.metadata_attribute_review_revision(attribute, "
                            "object) AS revision FROM core.attribute AS attribute JOIN "
                            "core.object AS object ON object.object_id=attribute.object_id "
                            "WHERE attribute.attribute_id=%s"
                        ),
                        (attribute_id,),
                    ).fetchone()
                )["revision"]
            assert revision != baseline.attributes[0].review_revision
            with pytest.raises(MetadataObjectNotFoundError):
                await catalog.get_object(principal, tenant_id=tenant_id, object_id=object_id)
        else:
            with web_postgres_database.connect_owner() as connection:
                if change == "parent_lock":
                    connection.execute(
                        "UPDATE core.object SET is_locked=TRUE WHERE object_id=%s",
                        (object_id,),
                    )
                elif change == "parent_inactive":
                    connection.execute(
                        "UPDATE core.object SET is_active=FALSE WHERE object_id=%s",
                        (object_id,),
                    )
                else:
                    connection.execute(
                        "UPDATE core.attribute SET is_active=FALSE WHERE attribute_id=%s",
                        (attribute_id,),
                    )
            changed = await catalog.get_object(principal, tenant_id=tenant_id, object_id=object_id)
            assert changed.attribute_count == 1
            assert changed.attributes[0].review_revision != baseline.attributes[0].review_revision
            assert changed.attributes[0].is_locked is False
            assert changed.attributes[0].is_active is (change != "child_inactive")
            assert changed.is_active is (change != "parent_inactive")
            assert changed.is_locked is (change == "parent_lock")
            all_rows = await catalog.list_objects(
                principal,
                tenant_id=tenant_id,
                filters=ObjectCatalogFilters(active_state="all"),
                page_size=200,
                cursor=None,
            )
            assert (
                next(item for item in all_rows.items if item.object_id == object_id).review_revision
                == changed.review_revision
            )
            inactive = await catalog.list_objects(
                principal,
                tenant_id=tenant_id,
                filters=ObjectCatalogFilters(active_state="inactive"),
                page_size=200,
                cursor=None,
            )
            assert (object_id in {item.object_id for item in inactive.items}) is (
                change == "parent_inactive"
            )
        if change in {"parent_inactive", "source_tenant"}:
            expected_error = (
                InvalidRequestError
                if change == "source_tenant"
                else ModelInputScopeObjectNotFoundError
            )
            with pytest.raises(expected_error):
                await scope.read_input_scope_object(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    object_id=object_id,
                )
        else:
            scoped = await scope.read_input_scope_object(
                principal, tenant_id=tenant_id, model_id=model_id, object_id=object_id
            )
            assert scoped.attribute_count == (0 if change == "child_inactive" else 1)
            if change == "parent_lock":
                assert (
                    scoped.attributes[0].review_revision != baseline.attributes[0].review_revision
                )
    finally:
        await database.close()
