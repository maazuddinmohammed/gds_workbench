import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PromptTools } from "./PromptTools";

function ToolChoices() {
  const [selected, setSelected] = useState<string[]>([]);
  return <PromptTools selected={selected} onChange={setSelected} disabled={false} tools={[{
    name: "get_objects", description: "Get scoped Objects for a Source Connection.",
    default_behavior: "Omit source_connection_key to return all scoped Objects, paged.",
    input_schema: { type: "object", properties: { source_connection_key: { type: "object" } } },
    result_schema: { type: "object", properties: { items: { type: "array" } } },
    example: { items: [{ object_name: "<script> literal" }], next_cursor: null, is_complete: true },
  }, { name: "get_object_details", description: "Read scoped Attribute details and profiling.", input_schema: { type: "object" } }]} />;
}

describe("Prompt tool choices", () => {
  it("supports optional keyboard selection, filtering, no-input guidance and complete inert schemas", async () => {
    const user = userEvent.setup();
    const { container } = render(<ToolChoices />);
    expect(screen.getByText("0 of 2 enabled")).toBeVisible();
    const checkbox = screen.getByRole("checkbox", { name: /get_objects/ });
    checkbox.focus();
    await user.keyboard(" ");
    expect(checkbox).toBeChecked();
    await user.click(screen.getByText("Inputs and result for get_objects"));
    expect(screen.getByText("Omit source_connection_key to return all scoped Objects, paged.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Result schema" })).toBeVisible();
    expect(container.querySelector("script")).toBeNull();
    await user.type(screen.getByLabelText("Search tools"), "profiling");
    expect(screen.queryByRole("checkbox", { name: /get_objects/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enable all" }));
    expect(screen.getByText("2 of 2 enabled")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Clear tools" }));
    expect(screen.getByText("0 of 2 enabled")).toBeVisible();
  });
});
