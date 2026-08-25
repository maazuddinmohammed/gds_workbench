import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import type {
  LogicalAttributeDetail,
  LogicalAttributeSource,
  LogicalEntityDetail,
  LogicalEntitySource,
  LogicalRelationshipDetail,
  LogicalSubmodelDetail,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { logicalQueryKeys, type LogicalApi } from "./api";

export function LogicalEntityDetailPage({
  api,
  tenantId,
  modelId,
  entityId,
}: {
  api: LogicalApi;
  tenantId: number;
  modelId: number;
  entityId: number;
}) {
  const query = useQuery({
    queryKey: logicalQueryKeys.entity(tenantId, modelId, entityId),
    queryFn: () => api.readLogicalEntity(tenantId, modelId, entityId),
  });
  if (query.isPending) return <DetailState label="Loading Logical Entity…" />;
  if (query.isError) return <DetailState label="Logical Entity details could not be loaded." error />;
  return <LogicalEntityView tenantId={tenantId} modelId={modelId} entity={query.data} />;
}

export function LogicalAttributeDetailPage({
  api,
  tenantId,
  modelId,
  attributeId,
}: {
  api: LogicalApi;
  tenantId: number;
  modelId: number;
  attributeId: number;
}) {
  const query = useQuery({
    queryKey: logicalQueryKeys.attribute(tenantId, modelId, attributeId),
    queryFn: () => api.readLogicalAttribute(tenantId, modelId, attributeId),
  });
  if (query.isPending) return <DetailState label="Loading Logical Attribute…" />;
  if (query.isError) return <DetailState label="Logical Attribute details could not be loaded." error />;
  return <LogicalAttributeView tenantId={tenantId} modelId={modelId} attribute={query.data} />;
}

export function LogicalRelationshipDetailPage({
  api,
  tenantId,
  modelId,
  relationshipId,
}: {
  api: LogicalApi;
  tenantId: number;
  modelId: number;
  relationshipId: number;
}) {
  const query = useQuery({
    queryKey: logicalQueryKeys.relationship(tenantId, modelId, relationshipId),
    queryFn: () => api.readLogicalRelationship(tenantId, modelId, relationshipId),
  });
  if (query.isPending) return <DetailState label="Loading Logical Relationship…" />;
  if (query.isError) {
    return <DetailState label="Logical Relationship details could not be loaded." error />;
  }
  return (
    <LogicalRelationshipView
      tenantId={tenantId}
      modelId={modelId}
      relationship={query.data}
    />
  );
}

export function LogicalSubmodelDetailPage({
  api,
  tenantId,
  modelId,
  submodelId,
}: {
  api: LogicalApi;
  tenantId: number;
  modelId: number;
  submodelId: number;
}) {
  const query = useQuery({
    queryKey: logicalQueryKeys.submodel(tenantId, modelId, submodelId),
    queryFn: () => api.readLogicalSubmodel(tenantId, modelId, submodelId),
  });
  if (query.isPending) return <DetailState label="Loading Logical Submodel…" />;
  if (query.isError) return <DetailState label="Logical Submodel details could not be loaded." error />;
  return <LogicalSubmodelView tenantId={tenantId} modelId={modelId} submodel={query.data} />;
}

function LogicalEntityView({
  tenantId,
  modelId,
  entity,
}: {
  tenantId: number;
  modelId: number;
  entity: LogicalEntityDetail;
}) {
  return (
    <article className="workflow-detail-page logical-detail-page page-enter">
      <header className="workflow-detail-header">
        <div>
          <Link
            className="text-action"
            aria-label="Back to Logical"
            to="/tenants/$tenantId/models/$modelId/logical"
            params={{ tenantId: String(tenantId), modelId: String(modelId) }}
          >
            ← Back to Logical
          </Link>
          <p className="eyebrow">Logical Entity {entity.logical_entity_id}</p>
          <h1>{entity.logical_entity_name}</h1>
        </div>
        <div className="detail-badge-stack">
          <span className={`status-badge ${statusTone(entity.logical_entity_status)}`}>
            {humanize(entity.logical_entity_status)}
          </span>
          <span className="status-badge is-neutral">
            {entity.logical_entity_is_locked ? "Locked" : "Open"}
          </span>
        </div>
      </header>

      <section className="detail-section" aria-labelledby="logical-entity-overview">
        <header><h2 id="logical-entity-overview">Entity definition</h2></header>
        <p className="detail-prose is-prominent">{entity.logical_entity_definition}</p>
        <dl className="detail-fact-grid">
          <Fact label="Type" value={humanize(entity.logical_entity_type)} />
          <Fact label="Type detail" value={entity.logical_entity_type_detail ?? "Not specified"} />
          <Fact label="Grain" value={entity.logical_entity_grain} />
          <Fact label="Dependency order" value={String(entity.logical_entity_dependency_order)} />
          <Fact label="Confidence" value={humanize(entity.logical_entity_confidence)} />
          <Fact label="Updated" value={formatDateTime(entity.updated_at)} />
        </dl>
      </section>

      <section className="detail-section" aria-labelledby="logical-submodel-membership">
        <header>
          <h2 id="logical-submodel-membership">Submodel membership</h2>
          <span>{entity.submodels.length} records</span>
        </header>
        {entity.submodels.length === 0 ? (
          <p className="detail-empty">No Submodel membership is recorded.</p>
        ) : (
          <div className="normalized-membership-ledger">
            {entity.submodels.map((membership) => (
              <article key={membership.logical_entity_submodel_id}>
                <strong>{membership.logical_submodel_name}</strong>
                <dl className="support-facts">
                  <Fact label="Submodel ID" value={String(membership.logical_submodel_id)} />
                  <Fact label="Status" value={humanize(membership.membership_status)} />
                  <Fact label="Lock" value={membership.membership_is_locked ? "Locked" : "Open"} />
                  <Fact
                    label="Workflow"
                    value={membership.workflow_run_id === null
                      ? "No workflow provenance"
                      : `Workflow run ${membership.workflow_run_id}`}
                  />
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>

      <SourceMappings sources={entity.sources} />

      <section className="detail-section" aria-labelledby="logical-provenance">
        <header><h2 id="logical-provenance">Provenance</h2></header>
        <dl className="detail-fact-grid">
          <Fact
            label="Workflow"
            value={entity.workflow_run_id === null
              ? "No workflow provenance"
              : `Workflow run ${entity.workflow_run_id}`}
          />
          <Fact label="Created" value={formatDateTime(entity.created_at)} />
        </dl>
      </section>
    </article>
  );
}

function SourceMappings({ sources }: { sources: LogicalEntitySource[] }) {
  return (
    <section className="detail-section" aria-labelledby="logical-source-mappings">
      <header>
        <h2 id="logical-source-mappings">Source mappings</h2>
        <span>{sources.length} records</span>
      </header>
      {sources.length === 0 ? (
        <p className="detail-empty">No source mappings are recorded.</p>
      ) : (
        <div className="support-ledger">
          {sources.map((source, index) => (
            <article key={source.logical_entity_source_mapping_id} className="support-record">
              <header>
                <span className="support-index">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <small>{source.support_source_type === "object" ? "Physical Object" : "Modeling Assertion"}</small>
                  <strong>
                    {source.support_source_type === "object"
                      ? `${source.source_object.object_schema}.${source.source_object.object_name}`
                      : source.assertion_record.modeling_assertion_record_key}
                  </strong>
                </div>
                <span className={`status-badge ${statusTone(source.status)}`}>
                  {humanize(source.status)}
                </span>
              </header>
              <p>{source.rationale}</p>
              {source.support_source_type === "object" ? (
                <dl className="support-facts">
                  <Fact
                    label="Source"
                    value={`${source.source_object.tenant_code} · ${source.source_object.system_code} · ${source.source_object.connection_code}`}
                  />
                  <Fact
                    label="Object"
                    value={`${source.source_object.object_schema}.${source.source_object.object_name}`}
                  />
                  <Fact label="Order" value={source.source_order === null ? "Not assigned" : String(source.source_order)} />
                  <Fact label="Lock" value={source.is_locked ? "Locked" : "Open"} />
                </dl>
              ) : (
                <div className="assertion-support-detail">
                  <p>{source.assertion_record.modeling_assertion_text}</p>
                  <dl className="support-facts">
                    <Fact label="Document" value={source.assertion_record.modeling_assertion_document_name} />
                    <Fact label="Type" value={humanize(source.assertion_record.modeling_assertion_record_type)} />
                    <Fact label="Order" value={source.source_order === null ? "Not assigned" : String(source.source_order)} />
                    <Fact label="Lock" value={source.is_locked ? "Locked" : "Open"} />
                  </dl>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function LogicalAttributeView({
  tenantId,
  modelId,
  attribute,
}: {
  tenantId: number;
  modelId: number;
  attribute: LogicalAttributeDetail;
}) {
  return (
    <article className="workflow-detail-page logical-detail-page page-enter">
      <LogicalDetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Logical Attribute ${attribute.logical_attribute_id}`}
        title={attribute.logical_attribute_name}
        status={attribute.logical_attribute_status}
        locked={attribute.logical_attribute_is_locked}
      />
      <section className="detail-section" aria-labelledby="logical-attribute-overview">
        <header><h2 id="logical-attribute-overview">Attribute definition</h2></header>
        <p className="detail-prose is-prominent">{attribute.logical_attribute_definition}</p>
        <dl className="detail-fact-grid">
          <Fact label="Entity" value={attribute.logical_entity_name} />
          <Fact label="Data type" value={attribute.logical_attribute_data_type} />
          <Fact label="Ordinal" value={String(attribute.logical_attribute_ordinal_position)} />
          <Fact label="Nullable" value={attribute.logical_attribute_is_nullable ? "Yes" : "No"} />
          <Fact label="Primary key" value={attribute.logical_attribute_is_primary_key ? "Yes" : "No"} />
          <Fact label="Natural key" value={attribute.logical_attribute_is_natural_key ? "Yes" : "No"} />
          <Fact label="Surrogate key" value={attribute.logical_attribute_is_surrogate_key ? "Yes" : "No"} />
          <Fact label="Audit column" value={attribute.logical_attribute_is_audit_column ? "Yes" : "No"} />
        </dl>
      </section>
      <AttributeSourceMappings sources={attribute.sources} />
      <LogicalProvenance workflowRunId={attribute.workflow_run_id} createdAt={attribute.created_at} />
    </article>
  );
}

function LogicalRelationshipView({
  tenantId,
  modelId,
  relationship,
}: {
  tenantId: number;
  modelId: number;
  relationship: LogicalRelationshipDetail;
}) {
  return (
    <article className="workflow-detail-page logical-detail-page page-enter">
      <LogicalDetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Logical Relationship ${relationship.logical_relationship_id}`}
        title={relationship.logical_relationship_name}
        status={relationship.logical_relationship_status}
        locked={relationship.logical_relationship_is_locked}
      />
      <section className="detail-section" aria-labelledby="logical-relationship-overview">
        <header><h2 id="logical-relationship-overview">Relationship definition</h2></header>
        <p className="detail-prose is-prominent">{relationship.logical_relationship_definition}</p>
        <div className="conceptual-endpoints" aria-label="Relationship endpoints">
          <section>
            <small>From</small>
            <strong>
              {relationship.from_logical_entity_name}.{relationship.from_logical_attribute_name}
            </strong>
          </section>
          <span aria-hidden="true">→</span>
          <section>
            <small>To</small>
            <strong>
              {relationship.to_logical_entity_name}.{relationship.to_logical_attribute_name}
            </strong>
          </section>
        </div>
        <dl className="detail-fact-grid">
          <Fact label="Cardinality" value={humanize(relationship.logical_relationship_cardinality)} />
          <Fact label="Confidence" value={humanize(relationship.logical_relationship_confidence)} />
          <Fact label="Updated" value={formatDateTime(relationship.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="logical-relationship-reasoning">
        <header><h2 id="logical-relationship-reasoning">Reasoning</h2></header>
        <dl className="conceptual-reasoning">
          <Fact label="Relationship basis" value={relationship.logical_relationship_basis} />
          <Fact label="Cardinality basis" value={relationship.logical_relationship_cardinality_basis} />
        </dl>
      </section>
      <LogicalProvenance workflowRunId={relationship.workflow_run_id} createdAt={relationship.created_at} />
    </article>
  );
}

function LogicalSubmodelView({
  tenantId,
  modelId,
  submodel,
}: {
  tenantId: number;
  modelId: number;
  submodel: LogicalSubmodelDetail;
}) {
  return (
    <article className="workflow-detail-page logical-detail-page page-enter">
      <LogicalDetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Logical Submodel ${submodel.logical_submodel_id}`}
        title={submodel.logical_submodel_name}
        status={submodel.logical_submodel_status}
        locked={submodel.logical_submodel_is_locked}
      />
      <section className="detail-section" aria-labelledby="logical-submodel-overview">
        <header><h2 id="logical-submodel-overview">Submodel definition</h2></header>
        <p className="detail-prose is-prominent">{submodel.logical_submodel_definition}</p>
        <dl className="detail-fact-grid">
          <Fact label="Entities" value={String(submodel.entity_count)} />
          <Fact label="Updated" value={formatDateTime(submodel.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="logical-submodel-entities">
        <header>
          <h2 id="logical-submodel-entities">Member entities</h2>
          <span>{submodel.entities.length} records</span>
        </header>
        {submodel.entities.length === 0 ? (
          <p className="detail-empty">No member entities are recorded.</p>
        ) : (
          <div className="normalized-membership-ledger">
            {submodel.entities.map((membership) => (
              <article key={membership.logical_entity_submodel_id}>
                <strong>{membership.logical_entity_name}</strong>
                <dl className="support-facts">
                  <Fact label="Entity ID" value={String(membership.logical_entity_id)} />
                  <Fact label="Type" value={humanize(membership.logical_entity_type)} />
                  <Fact label="Entity status" value={humanize(membership.logical_entity_status)} />
                  <Fact label="Membership status" value={humanize(membership.membership_status)} />
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
      <LogicalProvenance workflowRunId={submodel.workflow_run_id} createdAt={submodel.created_at} />
    </article>
  );
}

function AttributeSourceMappings({ sources }: { sources: LogicalAttributeSource[] }) {
  return (
    <section className="detail-section" aria-labelledby="logical-attribute-sources">
      <header>
        <h2 id="logical-attribute-sources">Source mappings</h2>
        <span>{sources.length} records</span>
      </header>
      {sources.length === 0 ? (
        <p className="detail-empty">No source mappings are recorded.</p>
      ) : (
        <div className="support-ledger">
          {sources.map((source, index) => (
            <article key={source.logical_attribute_source_mapping_id} className="support-record">
              <header>
                <span className="support-index">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <small>{source.support_source_type === "attribute" ? "Physical Attribute" : "Modeling Assertion"}</small>
                  <strong>
                    {source.support_source_type === "attribute"
                      ? `${source.source_attribute.object_schema}.${source.source_attribute.object_name}.${source.source_attribute.attribute_name}`
                      : source.assertion_record.modeling_assertion_record_key}
                  </strong>
                </div>
                <span className={`status-badge ${statusTone(source.status)}`}>
                  {humanize(source.status)}
                </span>
              </header>
              <p>{source.rationale}</p>
              {source.support_source_type === "attribute" ? (
                <dl className="support-facts">
                  <Fact
                    label="Source"
                    value={`${source.source_attribute.tenant_code} · ${source.source_attribute.system_code} · ${source.source_attribute.connection_code}`}
                  />
                  <Fact
                    label="Attribute"
                    value={`${source.source_attribute.object_schema}.${source.source_attribute.object_name}.${source.source_attribute.attribute_name}`}
                  />
                  <Fact label="Entity mapping" value={String(source.logical_entity_source_mapping_id)} />
                  <Fact label="Lock" value={source.is_locked ? "Locked" : "Open"} />
                </dl>
              ) : (
                <div className="assertion-support-detail">
                  <p>{source.assertion_record.modeling_assertion_text}</p>
                  <dl className="support-facts">
                    <Fact label="Document" value={source.assertion_record.modeling_assertion_document_name} />
                    <Fact label="Type" value={humanize(source.assertion_record.modeling_assertion_record_type)} />
                    <Fact label="Order" value={source.source_order === null ? "Not assigned" : String(source.source_order)} />
                    <Fact label="Lock" value={source.is_locked ? "Locked" : "Open"} />
                  </dl>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function LogicalDetailHeader({
  tenantId,
  modelId,
  eyebrow,
  title,
  status,
  locked,
}: {
  tenantId: number;
  modelId: number;
  eyebrow: string;
  title: string;
  status: string;
  locked: boolean;
}) {
  return (
    <header className="workflow-detail-header">
      <div>
        <Link
          className="text-action"
          aria-label="Back to Logical"
          to="/tenants/$tenantId/models/$modelId/logical"
          params={{ tenantId: String(tenantId), modelId: String(modelId) }}
        >
          ← Back to Logical
        </Link>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      <div className="detail-badge-stack">
        <span className={`status-badge ${statusTone(status)}`}>{humanize(status)}</span>
        <span className="status-badge is-neutral">{locked ? "Locked" : "Open"}</span>
      </div>
    </header>
  );
}

function LogicalProvenance({
  workflowRunId,
  createdAt,
}: {
  workflowRunId: number | null;
  createdAt: string;
}) {
  return (
    <section className="detail-section" aria-labelledby="logical-record-provenance">
      <header><h2 id="logical-record-provenance">Provenance</h2></header>
      <dl className="detail-fact-grid">
        <Fact
          label="Workflow"
          value={workflowRunId === null ? "No workflow provenance" : `Workflow run ${workflowRunId}`}
        />
        <Fact label="Created" value={formatDateTime(createdAt)} />
      </dl>
    </section>
  );
}

function DetailState({ label, error = false }: { label: string; error?: boolean }) {
  return (
    <div
      className={`surface-state detail-state${error ? " is-error" : ""}`}
      {...(error ? { role: "alert" } : { "aria-busy": true })}
    >
      {label}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

function statusTone(status: string): string {
  if (status === "active") return "is-success";
  if (status === "needs_review") return "is-warning";
  return "is-neutral";
}
