import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TenantLockFocus } from "./TenantLockFocus";
import {
  tenantHomeQueryKey,
  type AcquireTenantLockResult,
  type OverrideTenantLockResult,
  type RenewTenantLockResult,
  type TenantLockApi as CompleteTenantLockApi,
  type TenantLockActions,
  type TenantLockState,
} from "./api";

type TenantLockApi = Omit<CompleteTenantLockApi, "listTenantLockHistory">
  & Partial<Pick<CompleteTenantLockApi, "listTenantLockHistory">>;

describe("Tenant Lock acquisition", () => {
  it("acquires only after explicit submission and refetches server-owned state", async () => {
    let lock: TenantLockState = unlockedTenant();
    const readTenantHome = vi.fn(async () => lock);
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(async (_tenantId, command): Promise<AcquireTenantLockResult> => {
        lock = {
          is_locked: true,
          owner_display_name: "Maaz",
          owned_by_current_principal: true,
          purpose: command.purpose,
          acquired_at: "2026-08-24T14:00:00Z",
          expires_at: "2026-08-24T15:30:00Z",
        };
        return {
          tenant_id: 7,
          action: "acquired",
          lock: {
            owner_display_name: "Maaz",
            owned_by_current_principal: true,
            purpose: command.purpose,
            acquired_at: "2026-08-24T14:00:00Z",
            expires_at: "2026-08-24T15:30:00Z",
          },
          previous_lock: null,
        };
      }),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({ api, readTenantHome });

    expect(await screen.findByText("Tenant is unlocked")).toBeVisible();
    expect(api.acquireTenantLock).not.toHaveBeenCalled();

    const duration = screen.getByRole("spinbutton", { name: "Duration (minutes)" });
    await user.clear(duration);
    await user.type(duration, "90");
    await user.type(screen.getByRole("textbox", { name: "Purpose (optional)" }), "Metadata review");
    await user.click(screen.getByRole("button", { name: "Acquire Tenant Lock" }));

    expect(api.acquireTenantLock).toHaveBeenCalledWith(7, {
      duration_minutes: 90,
      purpose: "Metadata review",
    });
    expect(await screen.findByText("Locked by you")).toBeVisible();
    expect(readTenantHome).toHaveBeenCalledTimes(2);
  });

  it("renders a bounded error without exposing raw failure details", async () => {
    const readTenantHome = vi.fn(async () => unlockedTenant());
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(async () => {
        throw new Error("secret database diagnostics");
      }),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({ api, readTenantHome });
    await user.click(await screen.findByRole("button", { name: "Acquire Tenant Lock" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Tenant Lock could not be acquired. Refresh and try again.",
    );
    expect(screen.queryByText(/secret database diagnostics/i)).not.toBeInTheDocument();
  });

  it("maps a stable tenant_locked code to a bounded acquisition reason", async () => {
    const readTenantHome = vi.fn(async () => unlockedTenant());
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(async () => {
        throw {
          code: "tenant_locked",
          message: "sensitive owner and database diagnostics",
        };
      }),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({ api, readTenantHome });
    await user.click(await screen.findByRole("button", { name: "Acquire Tenant Lock" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Another Principal currently owns this Tenant Lock. Refresh for current state.",
    );
    expect(screen.queryByText(/sensitive owner and database diagnostics/i)).not.toBeInTheDocument();
  });

  it("does not infer acquire authority from an unlocked display state", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => unlockedTenant()),
      actions: {
        can_acquire: false,
        can_renew: false,
        can_release: false,
        can_override: false,
      },
    });

    expect(await screen.findByText("Tenant is unlocked")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Acquire Tenant Lock" })).not.toBeInTheDocument();
    expect(api.acquireTenantLock).not.toHaveBeenCalled();
  });
});

describe("Tenant Lock renewal", () => {
  it("renews only after explicit submission and refetches server-owned state", async () => {
    let lock = ownedTenant();
    const readTenantHome = vi.fn(async () => lock);
    const renewTenantLock = vi.fn(async (
      _tenantId: number,
      _command: { duration_minutes: number },
    ): Promise<RenewTenantLockResult> => {
      lock = {
        ...lock,
        acquired_at: "2026-08-24T15:00:00Z",
        expires_at: "2026-08-24T17:00:00Z",
      };
      return {
        tenant_id: 7,
        action: "renewed" as const,
        lock: {
          owner_display_name: "Maaz",
          owned_by_current_principal: true as const,
          purpose: lock.purpose,
          acquired_at: "2026-08-24T15:00:00Z",
          expires_at: "2026-08-24T17:00:00Z",
        },
        previous_lock: null,
      };
    });
    const api = {
      acquireTenantLock: vi.fn(),
      renewTenantLock,
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome,
      actions: {
        can_acquire: false,
        can_renew: true,
        can_release: true,
        can_override: false,
      },
    });

    expect(await screen.findByText("Locked by you")).toBeVisible();
    expect(renewTenantLock).not.toHaveBeenCalled();

    const duration = screen.getByRole("spinbutton", { name: "Extend duration (minutes)" });
    await user.clear(duration);
    await user.type(duration, "120");
    await user.click(screen.getByRole("button", { name: "Extend Tenant Lock" }));

    expect(renewTenantLock).toHaveBeenCalledWith(7, { duration_minutes: 120 });
    expect(readTenantHome).toHaveBeenCalledTimes(2);
  });

  it("maps a stable missing-owned-lock code to a bounded extension reason", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(async () => {
        throw {
          code: "tenant_lock_required",
          message: "sensitive owner and database diagnostics",
        };
      }),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => ownedTenant()),
      actions: renewableActions(),
    });
    await user.click(await screen.findByRole("button", { name: "Extend Tenant Lock" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your active Tenant Lock is no longer available. Refresh for current state.",
    );
    expect(screen.queryByText(/sensitive owner and database diagnostics/i)).not.toBeInTheDocument();
  });

  it("redacts unknown renewal diagnostics", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(async () => {
        throw new Error("secret renewal database diagnostics");
      }),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => ownedTenant()),
      actions: renewableActions(),
    });
    await user.click(await screen.findByRole("button", { name: "Extend Tenant Lock" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Tenant Lock could not be extended. Refresh and try again.",
    );
    expect(screen.queryByText(/secret renewal database diagnostics/i)).not.toBeInTheDocument();
  });

  it("does not infer renew authority from lock ownership", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => ownedTenant()),
      actions: {
        can_acquire: false,
        can_renew: false,
        can_release: true,
        can_override: false,
      },
    });

    expect(await screen.findByText("Locked by you")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Extend Tenant Lock" })).not.toBeInTheDocument();
    expect(api.renewTenantLock).not.toHaveBeenCalled();
  });
});

describe("Tenant Lock release", () => {
  it("releases only after explicit confirmation and refetches server-owned state", async () => {
    let lock = ownedTenant();
    const readTenantHome = vi.fn(async () => lock);
    const releaseTenantLock = vi.fn(async () => {
      lock = unlockedTenant();
      return {
        tenant_id: 7,
        action: "released" as const,
        lock: null,
        previous_lock: null,
      };
    });
    const api = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock,
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({ api, readTenantHome, actions: renewableActions() });

    expect(await screen.findByText("Locked by you")).toBeVisible();
    expect(releaseTenantLock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Release Tenant Lock" }));
    expect(releaseTenantLock).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "Confirm Tenant Lock release" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Confirm release" }));

    expect(releaseTenantLock).toHaveBeenCalledWith(7);
    expect(await screen.findByText("Tenant is unlocked")).toBeVisible();
    expect(readTenantHome).toHaveBeenCalledTimes(2);
  });

  it("maps a stable missing-owned-lock code to a bounded release reason", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(async () => {
        throw {
          code: "tenant_lock_required",
          message: "sensitive release database diagnostics",
        };
      }),
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => ownedTenant()),
      actions: renewableActions(),
    });
    await user.click(await screen.findByRole("button", { name: "Release Tenant Lock" }));
    await user.click(screen.getByRole("button", { name: "Confirm release" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your active Tenant Lock is no longer available. Refresh for current state.",
    );
    expect(screen.queryByText(/sensitive release database diagnostics/i)).not.toBeInTheDocument();
  });

  it("redacts unknown release diagnostics", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(async () => {
        throw new Error("secret release database diagnostics");
      }),
      overrideTenantLock: vi.fn(),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => ownedTenant()),
      actions: renewableActions(),
    });
    await user.click(await screen.findByRole("button", { name: "Release Tenant Lock" }));
    await user.click(screen.getByRole("button", { name: "Confirm release" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Tenant Lock could not be released. Refresh and try again.",
    );
    expect(screen.queryByText(/secret release database diagnostics/i)).not.toBeInTheDocument();
  });

  it("does not infer release authority from lock ownership", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => ownedTenant()),
      actions: {
        can_acquire: false,
        can_renew: true,
        can_release: false,
        can_override: false,
      },
    });

    expect(await screen.findByText("Locked by you")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Release Tenant Lock" })).not.toBeInTheDocument();
    expect(api.releaseTenantLock).not.toHaveBeenCalled();
  });
});

describe("Tenant Lock override", () => {
  it("revokes with an explicit reason, refetches unlocked state, and never acquires", async () => {
    let lock = otherOwnedTenant();
    const readTenantHome = vi.fn(async () => lock);
    const acquireTenantLock = vi.fn();
    const overrideTenantLock = vi.fn(async (
      _tenantId: number,
      _command: { reason: string },
    ): Promise<OverrideTenantLockResult> => {
      lock = unlockedTenant();
      return {
        tenant_id: 7,
        action: "overridden" as const,
        lock: null,
        previous_lock: {
          owner_display_name: "Elena Morris",
          owned_by_current_principal: false as const,
          purpose: "Metadata review",
          acquired_at: "2026-08-24T14:00:00Z",
          expires_at: "2026-08-24T15:00:00Z",
        },
      };
    });
    const api = {
      acquireTenantLock,
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock,
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome,
      actions: (currentLock) => currentLock.is_locked
        ? overrideActions()
        : {
            can_acquire: true,
            can_renew: false,
            can_release: false,
            can_override: false,
          },
    });

    expect(await screen.findByText("Locked by another Principal")).toBeVisible();
    expect(overrideTenantLock).not.toHaveBeenCalled();
    const reason = screen.getByRole("textbox", { name: "Override reason" });
    const revoke = screen.getByRole("button", { name: "Revoke Tenant Lock" });
    expect(reason).toHaveAttribute("maxlength", "2000");
    expect(revoke).toBeDisabled();
    await user.type(reason, "   ");
    expect(revoke).toBeDisabled();
    await user.clear(reason);

    await user.type(
      reason,
      "Incident 4821 access recovery",
    );
    await user.click(revoke);

    expect(overrideTenantLock).toHaveBeenCalledWith(7, {
      reason: "Incident 4821 access recovery",
    });
    expect(await screen.findByText("Tenant is unlocked")).toBeVisible();
    expect(screen.getByRole("button", { name: "Acquire Tenant Lock" })).toBeVisible();
    expect(acquireTenantLock).not.toHaveBeenCalled();
    expect(readTenantHome).toHaveBeenCalledTimes(2);
  });

  it("maps a stable invalid override code to a bounded reason", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(async () => {
        throw {
          code: "invalid_request",
          message: "sensitive override database diagnostics",
        };
      }),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => otherOwnedTenant()),
      actions: overrideActions(),
    });
    await user.type(
      await screen.findByRole("textbox", { name: "Override reason" }),
      "Incident 4821 access recovery",
    );
    await user.click(screen.getByRole("button", { name: "Revoke Tenant Lock" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Tenant Lock state changed or the override reason is invalid. Refresh and try again.",
    );
    expect(screen.queryByText(/sensitive override database diagnostics/i)).not.toBeInTheDocument();
  });

  it("redacts unknown override diagnostics", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(async () => {
        throw new Error("secret override database diagnostics");
      }),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => otherOwnedTenant()),
      actions: overrideActions(),
    });
    await user.type(
      await screen.findByRole("textbox", { name: "Override reason" }),
      "Incident 4821 access recovery",
    );
    await user.click(screen.getByRole("button", { name: "Revoke Tenant Lock" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Tenant Lock could not be revoked. Refresh and try again.",
    );
    expect(screen.queryByText(/secret override database diagnostics/i)).not.toBeInTheDocument();
  });

  it("does not infer override authority from another Principal owning the lock", async () => {
    const api: TenantLockApi = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
    };

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => otherOwnedTenant()),
      actions: {
        can_acquire: false,
        can_renew: false,
        can_release: false,
        can_override: false,
      },
    });

    expect(await screen.findByText("Locked by another Principal")).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Override reason" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke Tenant Lock" })).not.toBeInTheDocument();
    expect(api.overrideTenantLock).not.toHaveBeenCalled();
  });
});

describe("Tenant Lock history", () => {
  it("loads and renders the first bounded page only after the reader opens history", async () => {
    const listTenantLockHistory = vi.fn(async () => ({
      tenant_id: 7,
      items: [
        {
          event_id: 41,
          event_type: "force_unlocked" as const,
          owner_display_name: "Elena Morris",
          actor_display_name: "Maaz",
          reason: "Incident 4821 access recovery",
          acquired_at: "2026-08-24T14:00:00Z",
          expires_at: "2026-08-24T15:00:00Z",
          created_at: "2026-08-24T14:30:00Z",
        },
      ],
      next_cursor: null,
    }));
    const api = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
      listTenantLockHistory,
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => otherOwnedTenant()),
      actions: {
        can_acquire: false,
        can_renew: false,
        can_release: false,
        can_override: false,
      },
    });

    expect(await screen.findByRole("button", { name: "View history" })).toBeVisible();
    expect(listTenantLockHistory).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "Tenant Lock history" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "View history" }));

    const history = await screen.findByRole("region", { name: "Tenant Lock history" });
    expect(listTenantLockHistory).toHaveBeenCalledWith(7, undefined);
    expect(within(history).getByText("Force unlocked")).toBeVisible();
    expect(within(history).getByText("Elena Morris")).toBeVisible();
    expect(within(history).getByText("Maaz")).toBeVisible();
    expect(within(history).getByText("Incident 4821 access recovery")).toBeVisible();
    expect(within(history).getByText("Acquired")).toBeVisible();
    expect(within(history).getByText("Expires")).toBeVisible();
    expect(within(history).getByText("Created")).toBeVisible();
    expect(within(history).getByText(formatExpectedDate("2026-08-24T14:30:00Z"))).toBeVisible();
  });

  it("loads more only on click and stops when the server repeats a cursor", async () => {
    const listTenantLockHistory = vi.fn(async (
      _tenantId: number,
      cursor?: string,
    ) => ({
      tenant_id: 7,
      items: [
        {
          event_id: cursor ? 42 : 41,
          event_type: cursor ? "renewed" as const : "acquired" as const,
          owner_display_name: "Maaz",
          actor_display_name: "Maaz",
          reason: null,
          acquired_at: "2026-08-24T14:00:00Z",
          expires_at: "2026-08-24T15:00:00Z",
          created_at: cursor ? "2026-08-24T14:30:00Z" : "2026-08-24T14:00:00Z",
        },
      ],
      next_cursor: "repeat-cursor",
    }));
    const api = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
      listTenantLockHistory,
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => unlockedTenant()),
    });
    await user.click(await screen.findByRole("button", { name: "View history" }));

    expect((await screen.findAllByText("Acquired"))[0]).toBeVisible();
    expect(listTenantLockHistory).toHaveBeenCalledTimes(1);
    expect(listTenantLockHistory).toHaveBeenLastCalledWith(7, undefined);

    await user.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByText("Renewed")).toBeVisible();
    expect(listTenantLockHistory).toHaveBeenCalledTimes(2);
    expect(listTenantLockHistory).toHaveBeenLastCalledWith(7, "repeat-cursor");
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("renders a generic history error without exposing raw diagnostics", async () => {
    const api = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
      listTenantLockHistory: vi.fn(async () => {
        throw new Error("secret history database diagnostics");
      }),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => unlockedTenant()),
    });
    await user.click(await screen.findByRole("button", { name: "View history" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Tenant Lock history could not be loaded. Close and try again.",
    );
    expect(screen.queryByText(/secret history database diagnostics/i)).not.toBeInTheDocument();
  });

  it("never renders a history reason beyond the server bound", async () => {
    const boundedReason = "x".repeat(2000);
    const api = {
      acquireTenantLock: vi.fn(),
      renewTenantLock: vi.fn(),
      releaseTenantLock: vi.fn(),
      overrideTenantLock: vi.fn(),
      listTenantLockHistory: vi.fn(async () => ({
        tenant_id: 7,
        items: [
          {
            event_id: 52,
            event_type: "released" as const,
            owner_display_name: "Maaz",
            actor_display_name: "Maaz",
            reason: `${boundedReason}UNBOUNDED_TAIL`,
            acquired_at: "2026-08-24T14:00:00Z",
            expires_at: "2026-08-24T15:00:00Z",
            created_at: "2026-08-24T14:30:00Z",
          },
        ],
        next_cursor: null,
      })),
    };
    const user = userEvent.setup();

    renderTenantLock({
      api,
      readTenantHome: vi.fn(async () => unlockedTenant()),
    });
    await user.click(await screen.findByRole("button", { name: "View history" }));

    const history = await screen.findByRole("region", { name: "Tenant Lock history" });
    expect(within(history).getByText(boundedReason)).toBeVisible();
    expect(within(history).queryByText(/UNBOUNDED_TAIL/)).not.toBeInTheDocument();
  });
});

function renderTenantLock({
  api,
  readTenantHome,
  actions,
}: {
  api: TenantLockApi;
  readTenantHome: () => Promise<TenantLockState>;
  actions?: TenantLockActions | ((lock: TenantLockState) => TenantLockActions);
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  function Harness() {
    const homeQuery = useQuery({
      queryKey: tenantHomeQueryKey(7),
      queryFn: readTenantHome,
    });
    if (!homeQuery.data) return <p>Loading…</p>;
    const currentActions = typeof actions === "function" ? actions(homeQuery.data) : actions;
    const completeApi: CompleteTenantLockApi = {
      listTenantLockHistory: async () => ({ tenant_id: 7, items: [], next_cursor: null }),
      ...api,
    };
    return (
      <TenantLockFocus
        actions={{
          ...(currentActions ?? {
            can_acquire: !homeQuery.data.is_locked,
            can_renew: false,
            can_release: false,
            can_override: false,
          }),
        }}
        api={completeApi}
        lock={homeQuery.data}
        tenantId={7}
        tenantName="Northwind Analytics"
      />
    );
  }

  return render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  );
}

function unlockedTenant(): TenantLockState {
  return {
    is_locked: false,
    owner_display_name: null,
    owned_by_current_principal: null,
    purpose: null,
    acquired_at: null,
    expires_at: null,
  };
}

function ownedTenant(): TenantLockState {
  return {
    is_locked: true,
    owner_display_name: "Maaz",
    owned_by_current_principal: true,
    purpose: "Metadata review",
    acquired_at: "2026-08-24T14:00:00Z",
    expires_at: "2026-08-24T15:00:00Z",
  };
}

function otherOwnedTenant(): TenantLockState {
  return {
    is_locked: true,
    owner_display_name: "Elena Morris",
    owned_by_current_principal: false,
    purpose: "Metadata review",
    acquired_at: "2026-08-24T14:00:00Z",
    expires_at: "2026-08-24T15:00:00Z",
  };
}

function renewableActions(): TenantLockActions {
  return {
    can_acquire: false,
    can_renew: true,
    can_release: true,
    can_override: false,
  };
}

function overrideActions(): TenantLockActions {
  return {
    can_acquire: false,
    can_renew: false,
    can_release: false,
    can_override: true,
  };
}

function formatExpectedDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
