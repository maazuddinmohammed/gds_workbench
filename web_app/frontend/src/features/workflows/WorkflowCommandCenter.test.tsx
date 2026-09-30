import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { WorkflowActivityPanel, WorkflowCommandCenter, WorkflowCommandTools, WorkflowFilters, WorkflowMenu } from "./WorkflowCommandCenter";

function CommandPage({ enabled = true }: { enabled?: boolean }) {
  const [open, setOpen] = useState(false);
  return <WorkflowCommandCenter className="test-page" enabled={enabled}>
    <header><WorkflowCommandTools /><WorkflowMenu><button type="button">Export</button></WorkflowMenu></header>
    <WorkflowFilters><label>Object name<input /></label></WorkflowFilters>
    <a href="/detail">Customer detail</a>
    <WorkflowActivityPanel label="Logical" open={open} onOpenChange={setOpen}>
      <p>Selected run details</p>
    </WorkflowActivityPanel>
  </WorkflowCommandCenter>;
}

describe("Command center interactions", () => {
  it("retains filter input when collapsed and leaves detail links available", async () => {
    const user = userEvent.setup();
    render(<CommandPage />);
    expect(screen.queryByRole("textbox", { name: "Object name" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.type(screen.getByRole("textbox", { name: "Object name" }), "Customer");
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByRole("textbox", { name: "Object name" })).toHaveValue("Customer");
    expect(screen.getByRole("link", { name: "Customer detail" })).toHaveAttribute("href", "/detail");
  });

  it("opens, expands and closes activity with keyboard focus restored", async () => {
    const user = userEvent.setup();
    render(<CommandPage />);
    const trigger = screen.getByRole("button", { name: "Show Logical run activity" });
    await user.click(trigger);
    expect(screen.getByRole("button", { name: "Close activity" })).toHaveFocus();
    expect(screen.getByRole("link", { name: "Customer detail" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Expand activity panel" }));
    expect(screen.getByRole("complementary", { name: "Logical activity" })).toHaveClass("is-wide");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("keeps filters directly visible outside list mode", () => {
    render(<CommandPage enabled={false} />);
    expect(screen.getByRole("textbox", { name: "Object name" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Filters" })).not.toBeInTheDocument();
  });
});
