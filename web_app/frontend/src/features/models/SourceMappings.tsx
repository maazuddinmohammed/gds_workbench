import type { LogicalAttributeSource, LogicalEntitySource } from "../logical/api";
import type { DimensionalAttributeSource, DimensionalObjectSource } from "../dimensional/api";
import { MappingDocumentView } from "../mapping/MappingDocumentView";
import { formatRequiredDateTime } from "../../shared/presentation";

type ModeledSource = LogicalAttributeSource | LogicalEntitySource | DimensionalAttributeSource | DimensionalObjectSource;

/** One reading order for modeled provenance: source, purpose, then supporting detail. */
export function SourceMappings({ sources }: { sources: ModeledSource[] }) {
  return <section className="detail-section modeled-source-mappings" aria-label="Source mappings">
    <header><h2>Source mappings</h2><span>{sources.length}</span></header>
    {!sources.length ? <p className="detail-empty">No source mappings are recorded.</p> : <div className="workflow-table-scroll table-scroll"><table aria-label="Source mappings"><thead><tr><th>Source</th><th>Rationale</th><th>Status</th><th>Details</th></tr></thead><tbody>
      {sources.map((source, index) => {
        const physical = source.support_source_type === "object" ? source.source_object : source.support_source_type === "attribute" ? source.source_attribute : null;
        const assertion = source.support_source_type === "assertion" ? source.assertion_record : null;
        const name = physical ? `${physical.object_schema}.${physical.object_name}${"attribute_name" in physical ? `.${physical.attribute_name}` : ""}` : assertion?.modeling_assertion_record_key;
        const mappingId = "logical_entity_source_mapping_id" in source && source.support_source_type !== "attribute" ? source.logical_entity_source_mapping_id
          : "logical_attribute_source_mapping_id" in source ? source.logical_attribute_source_mapping_id
            : "dimensional_attribute_source_mapping_id" in source ? source.dimensional_attribute_source_mapping_id
              : "dimensional_entity_source_mapping_id" in source ? source.dimensional_entity_source_mapping_id : null;
        return <tr key={index}><td><strong>{name}</strong>{"source_role" in source ? <small className="modeled-source-role">{humanize(source.source_role)}</small> : null}</td><td className="modeled-source-rationale">{source.rationale}</td><td>{humanize(source.status)}{source.is_locked ? <small className="modeled-source-role">Locked</small> : null}</td><td><details className="modeled-source-detail"><summary>Show details</summary>
          <MappingDocumentView title="Source detail" document={{
            ...(physical ? { tenant: physical.tenant_code, system: physical.system_code, connection: physical.connection_code, schema: physical.object_schema, object: physical.object_name,
              ...(source.support_source_type === "attribute" ? { attribute: source.source_attribute.attribute_name } : {}) } : {}),
            ...(assertion ? { document: assertion.modeling_assertion_document_name, assertion_type: humanize(assertion.modeling_assertion_record_type), assertion: assertion.modeling_assertion_text } : {}),
            ...(source.support_source_type === "attribute" ? { entity_mapping_id: "logical_entity_source_mapping_id" in source ? source.logical_entity_source_mapping_id : source.dimensional_entity_source_mapping_id } : {}),
            order: source.source_order, source_mapping_id: mappingId, workflow_run: source.workflow_run_id,
            created: formatRequiredDateTime(source.created_at), updated: formatRequiredDateTime(source.updated_at),
          }} />
        </details></td></tr>;
      })}
    </tbody></table></div>}
  </section>;
}

function humanize(value: string) { return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()); }
