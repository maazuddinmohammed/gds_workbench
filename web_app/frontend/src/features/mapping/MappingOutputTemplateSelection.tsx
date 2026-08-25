import type { OutputTemplateSummary } from "./api";

export function MappingOutputTemplateSelection({
  mappingObjects,
  mappingAttributes,
  objectValue,
  attributeValue,
  disabled,
  onObjectChange,
  onAttributeChange,
}: {
  mappingObjects: OutputTemplateSummary[];
  mappingAttributes: OutputTemplateSummary[];
  objectValue: string;
  attributeValue: string;
  disabled: boolean;
  onObjectChange: (value: string) => void;
  onAttributeChange: (value: string) => void;
}) {
  return (
    <section className="agent-run-configuration" aria-labelledby="mapping-output-template-heading">
      <header>
        <strong id="mapping-output-template-heading">Output templates</strong>
        <span>Select each Mapping target type independently, or keep it free-form.</span>
      </header>
      <div className="agent-run-grid">
        <OutputTemplateSelect
          label="Object Mapping Output Template"
          templates={mappingObjects}
          value={objectValue}
          disabled={disabled}
          onChange={onObjectChange}
        />
        <OutputTemplateSelect
          label="Attribute Mapping Output Template"
          templates={mappingAttributes}
          value={attributeValue}
          disabled={disabled}
          onChange={onAttributeChange}
        />
      </div>
    </section>
  );
}

function OutputTemplateSelect({
  label,
  templates,
  value,
  disabled,
  onChange,
}: {
  label: string;
  templates: OutputTemplateSummary[];
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const selected = templates.find((template) => (
    template.output_template_id === Number(value)
  ));
  const descriptionId = `${label.toLowerCase().replaceAll(" ", "-")}-status`;

  return (
    <label>
      <span>{label}</span>
      <select
        aria-label={label}
        aria-describedby={descriptionId}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Free-form · no Output Template</option>
        {templates.map((template) => (
          <option
            key={template.output_template_id}
            value={template.output_template_id}
            disabled={!template.output_template_schema_digest_is_valid}
          >
            {template.output_template_name} · Schema {template.output_template_schema_digest_is_valid
              ? "valid"
              : "invalid"}
          </option>
        ))}
      </select>
      <small id={descriptionId}>
        {selected
          ? `${selected.output_template_name} · Schema ${selected.output_template_schema_digest_is_valid ? "valid" : "invalid"}.`
          : "Free-form selected · no Output Template schema validation."}
      </small>
    </label>
  );
}
