import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PromptStageVariable } from "./api";
import { PromptVariables } from "./PromptVariables";

const input: PromptStageVariable = {
  name: "description_requests",
  resolver_key: "workflow.metadata_enrichment.one_shot.candidate_authoring.inputs.description_requests",
  data_type: "json",
  is_required: false,
  description: "Metadata evidence for the assigned descriptions.",
  example: [{ target_ref: "attribute:201", source_description: "<script> is literal metadata" }],
  order: 110,
  source: "Selected metadata and backend type evidence; no samples.",
  availability: "Current batch only, containing 1–25 requests.",
  delivery: "structured_context",
  context_path: "context.original_context.description_requests",
  value_schema: { type: "array", minItems: 1, maxItems: 25, items: { type: "object" } },
};

describe("Prompt input reference", () => {
  it("explains delivery and exposes the complete synthetic example and schema on demand", async () => {
    const user = userEvent.setup();
    const { container } = render(<PromptVariables variables={[input]} />);
    const table = screen.getByRole("table", { name: "Allowed Prompt variables" });
    expect(within(table).getByText("{{description_requests}}")).toBeVisible();
    expect(within(table).getByText(input.source!)).toBeVisible();
    expect(within(table).getByText(input.availability!)).toBeVisible();
    expect(screen.queryByText(input.context_path!)).not.toBeInTheDocument();
    expect(screen.getByText(/Only referenced variables/)).toBeVisible();
    const disclosure = screen.getByText("Shape and example for description_requests");
    expect(screen.getByRole("heading", { name: "Value schema", hidden: true })).not.toBeVisible();
    await user.click(disclosure);
    expect(screen.getByRole("heading", { name: "Value schema" })).toBeVisible();
    expect(container.querySelectorAll("pre")[0]?.textContent).toBe(JSON.stringify(input.example, null, 2));
    expect(container.querySelectorAll("pre")[1]?.textContent).toBe(JSON.stringify(input.value_schema, null, 2));
    expect(container.querySelector("script")).toBeNull();
  });

  it("preserves legacy help without inventing a schema or data source", async () => {
    const user = userEvent.setup();
    render(<PromptVariables variables={[{
      name: "entity_name", resolver_key: "logical.entity.name", data_type: "text",
      is_required: true, description: "Canonical Entity name", example: "Customer", order: 10,
    }]} />);
    expect(screen.getByText("Canonical Entity name")).toBeVisible();
    expect(screen.queryByText("Source")).not.toBeInTheDocument();
    await user.click(screen.getByText("Shape and example for entity_name"));
    expect(screen.getByText("No value schema registered.")).toBeVisible();
    expect(screen.getByText('"Customer"')).toBeVisible();
  });

  it("filters workflow groups and inserts only an explicitly chosen variable using the keyboard", async () => {
    const user = userEvent.setup();
    const insert = vi.fn();
    render(<PromptVariables variables={[input, { ...input, name: "logical_entities", description: "Saved Logical Entities", group: "Logical results" }]} onInsert={insert} />);
    await user.selectOptions(screen.getByLabelText("Variable group"), "Logical results");
    expect(screen.queryByText("{{description_requests}}")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Search variables"), "saved");
    const button = screen.getByRole("button", { name: "Insert logical_entities" });
    button.focus();
    await user.keyboard("{Enter}");
    expect(insert).toHaveBeenCalledExactlyOnceWith("logical_entities");
    await user.type(screen.getByLabelText("Search variables"), " absent");
    expect(screen.getByText("No variables match. Change the search or group.")).toBeVisible();
  });
});
