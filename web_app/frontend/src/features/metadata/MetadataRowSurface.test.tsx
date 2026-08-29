import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MetadataRowEditor } from "./MetadataRowSurface";
import type { MetadataDatasetDescription, MetadataRowSchema } from "./api";

describe("Metadata row editor", () => {
  it("stages a valid multi-character value from a JSON Schema search pattern", async () => {
    const onStage = vi.fn(async () => undefined);
    const user = userEvent.setup();

    render(
      <MetadataRowEditor
        mode="edit"
        descriptor={descriptor}
        rowSchema={rowSchema}
        baseRow={{ object_name: "Customer", object_type_code: "TABLE", is_active: true }}
        isSaving={false}
        onClose={() => undefined}
        onStage={onStage}
      />,
    );

    const dialog = screen.getByRole("dialog", { name: "Edit Source Objects row" });
    const objectType = within(dialog).getByLabelText("Object Type Code");
    await user.clear(objectType);
    await user.type(objectType, "table");
    await user.click(within(dialog).getByRole("button", { name: "Stage complete row" }));

    expect(onStage).toHaveBeenCalledWith({
      object_name: "Customer",
      object_type_code: "table",
      is_active: true,
    }, '["Customer"]');
  });

  it("rejects a blank required enum before staging", async () => {
    const onStage = vi.fn(async () => undefined);
    const user = userEvent.setup();

    render(
      <MetadataRowEditor
        mode="add"
        descriptor={singleFieldDescriptor("mode")}
        rowSchema={{
          type: "object",
          properties: { mode: { type: "string", enum: ["source", "target"] } },
          required: ["mode"],
        }}
        baseRow={{}}
        isSaving={false}
        onClose={() => undefined}
        onStage={onStage}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Stage complete row" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Mode is required.");
    expect(onStage).not.toHaveBeenCalled();
  });

  it("rejects empty and exclusive-bound numbers, then stages a valid integer", async () => {
    const onStage = vi.fn(async () => undefined);
    const user = userEvent.setup();

    render(
      <MetadataRowEditor
        mode="add"
        descriptor={singleFieldDescriptor("priority")}
        rowSchema={{
          type: "object",
          properties: {
            priority: { type: "integer", exclusiveMinimum: 0, exclusiveMaximum: 10 },
          },
          required: ["priority"],
        }}
        baseRow={{}}
        isSaving={false}
        onClose={() => undefined}
        onStage={onStage}
      />,
    );

    const priority = screen.getByLabelText("Priority");
    const submit = screen.getByRole("button", { name: "Stage complete row" });
    await user.click(submit);
    expect(screen.getByRole("alert")).toHaveTextContent("Priority is required.");

    await user.type(priority, "0");
    await user.click(submit);
    expect(screen.getByRole("alert")).toHaveTextContent("Priority must be greater than 0.");

    await user.clear(priority);
    await user.type(priority, "10");
    await user.click(submit);
    expect(screen.getByRole("alert")).toHaveTextContent("Priority must be less than 10.");

    await user.clear(priority);
    await user.type(priority, "5");
    await user.click(submit);
    expect(onStage).toHaveBeenCalledWith({ priority: 5 }, undefined);
  });

  it("locks and submits a dataset fixed value without manual entry", async () => {
    const onStage = vi.fn(async () => undefined);
    const user = userEvent.setup();

    render(
      <MetadataRowEditor
        mode="add"
        descriptor={singleFieldDescriptor("zone_code")}
        rowSchema={{
          type: "object",
          properties: { zone_code: { type: "string", enum: ["source", "bronze"] } },
          required: ["zone_code"],
        }}
        fixedValues={{ zone_code: "source" }}
        baseRow={{}}
        isSaving={false}
        onClose={() => undefined}
        onStage={onStage}
      />,
    );

    expect(screen.getByLabelText("Zone Code")).toBeDisabled();
    expect(screen.getByLabelText("Zone Code")).toHaveValue("source");
    expect(screen.getByText("Fixed value")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Stage complete row" }));
    expect(onStage).toHaveBeenCalledWith({ zone_code: "source" }, undefined);
  });

  it.each([
    {
      field: "initial_load_date",
      format: "date",
      invalidValue: "2026-02-30",
      validValue: "2026-08-29",
      message: "Initial Load Date must be a valid YYYY-MM-DD date.",
    },
    {
      field: "last_run_time",
      format: "date-time",
      invalidValue: "2026-08-29 10:42",
      validValue: "2026-08-29t10:42:00z",
      message: "Last Run Time must be a valid ISO 8601 date-time with a timezone.",
    },
  ])("validates $format values before staging", async ({
    field,
    format,
    invalidValue,
    validValue,
    message,
  }) => {
    const onStage = vi.fn(async () => undefined);
    const user = userEvent.setup();

    render(
      <MetadataRowEditor
        mode="add"
        descriptor={singleFieldDescriptor(field)}
        rowSchema={{
          type: "object",
          properties: { [field]: { type: "string", format } },
          required: [field],
        }}
        baseRow={{}}
        isSaving={false}
        onClose={() => undefined}
        onStage={onStage}
      />,
    );

    const input = screen.getByLabelText(metadataFieldLabelForTest(field));
    const submit = screen.getByRole("button", { name: "Stage complete row" });
    await user.type(input, invalidValue);
    await user.click(submit);
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(onStage).not.toHaveBeenCalled();

    await user.clear(input);
    await user.type(input, validValue);
    await user.click(submit);
    expect(onStage).toHaveBeenCalledWith({ [field]: validValue }, undefined);
  });

  it.each([
    { field: "initial_load_date", format: "date", value: "0000-01-01" },
    { field: "last_run_time", format: "date-time", value: "0000-01-01T00:00:00Z" },
  ])("rejects year zero for $format values", async ({ field, format, value }) => {
    const onStage = vi.fn(async () => undefined);
    const user = userEvent.setup();

    render(
      <MetadataRowEditor
        mode="add"
        descriptor={singleFieldDescriptor(field)}
        rowSchema={{
          type: "object",
          properties: { [field]: { type: "string", format } },
          required: [field],
        }}
        baseRow={{}}
        isSaving={false}
        onClose={() => undefined}
        onStage={onStage}
      />,
    );

    await user.type(screen.getByLabelText(metadataFieldLabelForTest(field)), value);
    await user.click(screen.getByRole("button", { name: "Stage complete row" }));

    expect(screen.getByRole("alert")).not.toBeEmptyDOMElement();
    expect(onStage).not.toHaveBeenCalled();
  });

  it("labels a required nullable field by the choice available to the user", () => {
    render(
      <MetadataRowEditor
        mode="add"
        descriptor={{ ...singleFieldDescriptor("description"), natural_key: [] }}
        rowSchema={{
          type: "object",
          properties: {
            description: {
              anyOf: [{ type: "string" }, { type: "null" }],
            },
          },
          required: ["description"],
        }}
        baseRow={{}}
        isSaving={false}
        onClose={() => undefined}
        onStage={async () => undefined}
      />,
    );

    expect(screen.getByText("Nullable")).toBeVisible();
    expect(screen.queryByText("Required")).not.toBeInTheDocument();
  });
});

function singleFieldDescriptor(field: string): MetadataDatasetDescription {
  return {
    dataset: "source_object",
    label: "Source Objects",
    section: "operational",
    change_set_eligible: true,
    read_only: false,
    columns: [field],
    natural_key: [field],
    filter_fields: [field],
  };
}

function metadataFieldLabelForTest(field: string): string {
  return field.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

const descriptor: MetadataDatasetDescription = {
  dataset: "source_object",
  label: "Source Objects",
  section: "operational",
  change_set_eligible: true,
  read_only: false,
  columns: ["object_name", "object_type_code", "is_active"],
  natural_key: ["object_name"],
  filter_fields: ["object_name"],
};

const rowSchema: MetadataRowSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    object_name: { type: "string", minLength: 1, maxLength: 400 },
    object_type_code: { type: "string", minLength: 1, maxLength: 100, pattern: "\\S" },
    is_active: { type: "boolean" },
  },
  required: ["object_name", "object_type_code", "is_active"],
};
