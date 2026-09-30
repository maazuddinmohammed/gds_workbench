import type { LogicalAttributeSource, LogicalEntitySource } from "../logical/api";
import type { DimensionalAttributeSource, DimensionalObjectSource } from "../dimensional/api";
import { MappingDocumentView } from "../mapping/MappingDocumentView";

type ModeledSource = LogicalAttributeSource | LogicalEntitySource | DimensionalAttributeSource | DimensionalObjectSource;

/** Keep source identifiers comparable, with provenance available on demand. */
export function SourceMappings({ sources }: { sources: ModeledSource[] }) {
  const hasAttributes = sources.some((source) => source.support_source_type === "attribute" || source.support_source_type === "logical_attribute");
  const hasRoles = sources.some((source) => "source_role" in source);
  return <section className="detail-section modeled-source-mappings" aria-label="Source mappings">
    <header><h2>Source mappings</h2><span>{sources.length}</span></header>
    {!sources.length ? <p className="detail-empty">No source mappings are recorded.</p> : <div className="workflow-table-scroll table-scroll"><table aria-label="Source mappings"><thead><tr><th className="modeled-source-order">Order</th><th>Schema</th><th>Object / entity</th>{hasAttributes ? <th>Attribute</th> : null}<th>Rationale</th>{hasRoles ? <th>Role</th> : null}<th>Status</th><th>Details</th></tr></thead><tbody>
      {sources.map((source, index) => {
        const physical = source.support_source_type === "object" ? source.source_object : source.support_source_type === "attribute" ? source.source_attribute : null;
        const logical = source.support_source_type === "logical_entity" ? source.source_logical_entity : source.support_source_type === "logical_attribute" ? source.source_logical_attribute : null;
        const assertion = source.support_source_type === "assertion" ? source.assertion_record : null;
        const schema = physical?.object_schema ?? logical?.logical_entity_schema_name;
        const name = physical?.object_name ?? logical?.logical_entity_name ?? assertion?.modeling_assertion_record_key;
        const attribute = source.support_source_type === "attribute" ? source.source_attribute.attribute_name
          : source.support_source_type === "logical_attribute" ? source.source_logical_attribute.logical_attribute_name : null;
        return <tr key={index}>
          <td className="modeled-source-order">{source.source_order ?? "—"}</td>
          <td>{schema ?? "—"}</td>
          <td><strong>{name}</strong>{assertion ? <small className="modeled-source-role">Modeling Assertion</small> : null}</td>
          {hasAttributes ? <td>{attribute ?? "—"}</td> : null}
          <td className="modeled-source-rationale">{source.rationale}</td>
          {hasRoles ? <td>{"source_role" in source ? humanize(source.source_role) : "—"}</td> : null}
          <td>{humanize(source.status)}{source.is_locked ? <small className="modeled-source-role">Locked</small> : null}</td>
          <td><details className="modeled-source-detail"><summary>Show details</summary>
          <MappingDocumentView title="Source detail" document={{
            ...(physical ? { tenant: physical.tenant_code, system: physical.system_code, connection: physical.connection_code, schema: physical.object_schema, object: physical.object_name,
              ...(source.support_source_type === "attribute" ? { attribute: source.source_attribute.attribute_name } : {}) } : {}),
            ...(logical ? { schema: logical.logical_entity_schema_name, entity: logical.logical_entity_name, ...(source.support_source_type === "logical_attribute" ? { attribute: source.source_logical_attribute.logical_attribute_name } : {}) } : {}),
            ...(assertion ? { document: assertion.modeling_assertion_document_name, assertion_type: humanize(assertion.modeling_assertion_record_type), assertion: assertion.modeling_assertion_text } : {}),
          }} />
        </details></td></tr>;
      })}
    </tbody></table></div>}
  </section>;
}

function humanize(value: string) { return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()); }
