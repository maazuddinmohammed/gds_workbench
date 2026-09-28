import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { MultiSelectField } from "./MultiSelectField";

it("keeps selections while searching and closes to the trigger without submitting the form", async () => {
  const submitted = vi.fn();
  function Picker() {
    const [value, setValue] = useState<string[]>([]);
    return <form onSubmit={(event) => { event.preventDefault(); submitted(); }}>
      <MultiSelectField label="Systems" emptyLabel="All Systems" value={value} onChange={setValue}
        options={[["crm", "CRM"], ["erp", "ERP"]]} />
      <button type="submit">Apply</button>
    </form>;
  }
  const user = userEvent.setup();
  render(<Picker />);
  const trigger = screen.getByText("All Systems").closest("summary")!;
  await user.click(trigger);
  const search = screen.getByRole("searchbox", { name: "Find Systems" });
  await user.click(search);
  await user.click(screen.getByText("CRM", { selector: "label span" }));
  expect(trigger.closest("details")).toHaveAttribute("open");
  expect(screen.getByRole("checkbox", { name: "CRM" })).toHaveFocus();
  await user.type(search, "ERP{Enter}");
  expect(submitted).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Select all shown" }));
  await user.clear(search);
  expect(screen.getByRole("checkbox", { name: "CRM" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "ERP" })).toBeChecked();
  await user.keyboard("{Escape}");
  expect(trigger.closest("details")).not.toHaveAttribute("open");
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveTextContent("2 selected");
  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: "Apply" }));
  expect(trigger.closest("details")).not.toHaveAttribute("open");
  expect(screen.getByRole("button", { name: "Apply" })).toHaveFocus();
});
