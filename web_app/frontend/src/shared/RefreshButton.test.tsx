import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { RefreshButton } from "./ui";

it("shows only the arrows icon but keeps a spoken name and tooltip", async () => {
  const refresh = vi.fn();
  const { rerender } = render(<RefreshButton refreshing={false} onClick={refresh} />);
  const button = screen.getByRole("button", { name: "Refresh" });
  expect(button).toHaveAttribute("title", "Refresh");
  expect(button).toHaveTextContent("");
  expect(button.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  await userEvent.setup().click(button);
  expect(refresh).toHaveBeenCalledOnce();

  rerender(<RefreshButton refreshing onClick={refresh} />);
  const busy = screen.getByRole("button", { name: "Refreshing…" });
  expect(busy).toBeDisabled();
  expect(busy).toHaveAttribute("aria-busy", "true");
});
