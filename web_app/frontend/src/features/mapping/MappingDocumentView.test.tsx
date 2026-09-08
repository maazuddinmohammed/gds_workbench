import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MappingDocumentView } from "./MappingDocumentView";

describe("Mapping document values", () => {
  it("shows readable values and keeps the exact original document available", async () => {
    const document = {
      "free.Key_<literal>": [null, {}, [], "", false, 0, "0", "false", { "nested_key": ["first", "second"] }],
      "": "SELECT '<script>literal</script>' AS text;\nSELECT 2;",
    };
    const { container } = render(<MappingDocumentView title="Transformation document" document={document} />);
    expect(screen.getByTitle("free.Key_<literal>")).toBeVisible();
    const entries = within(screen.getByRole("list", { name: 'Transformation document["free.Key_<literal>"]' })).getAllByRole("listitem");
    expect(entries.slice(0, 8).map((item) => item.textContent)).toEqual([
      "Not set", "No fields", "No items", '\"\"', "false", "0", "0", "false",
    ]);
    expect(screen.getByText("first").compareDocumentPosition(screen.getByText("second")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByText(/SELECT '<script>literal/)[0]!.textContent).toBe(document[""]);
    await userEvent.setup().click(screen.getByText("Original document"));
    expect(container.querySelector("pre code")?.textContent).toBe(JSON.stringify(document, null, 2));
    expect(container.querySelector("script")).toBeNull();
  });
  it("distinguishes an absent document from an authored empty object", () => {
    const { rerender } = render(<MappingDocumentView title="Transformation document" document={null} />);
    expect(screen.getByText("Not authored")).toBeVisible();
    rerender(<MappingDocumentView title="Transformation document" document={{}} />);
    expect(screen.queryByText("Not authored")).not.toBeInTheDocument();
    expect(screen.getByText("No fields")).toBeVisible();
  });
});
