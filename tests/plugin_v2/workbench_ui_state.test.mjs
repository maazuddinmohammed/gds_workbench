import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const uiState = require("../../plugins/v2/gds/skills/gds/workbench/ui-state.js");

test("dirty drafts block navigation and validation until saved or discarded", () => {
  assert.throws(
    () => uiState.requireClean(true, "refreshing"),
    /Save or discard the visible draft before refreshing/,
  );
  assert.doesNotThrow(() => uiState.requireClean(false, "refreshing"));
  assert.equal(
    uiState.canValidate(["01", "metadata", "Edit", "review"], "metadata", true, true),
    false,
  );
});

test("editing and validation require the current task for the visible area", () => {
  assert.equal(uiState.canEdit(["01", "metadata", "Edit", "doing"], "metadata", true, false), true);
  assert.equal(uiState.canEdit(["01", "model", "Edit", "doing"], "metadata", true), false);
  assert.equal(uiState.canEdit(["01", "metadata", "Edit", "done"], "metadata", true), false);
  assert.equal(
    uiState.canValidate(["01", "metadata", "Edit", "review"], "metadata", true, false),
    true,
  );
  assert.equal(
    uiState.canValidate(["01", "metadata", "Edit", "doing"], "metadata", true, false),
    false,
  );
});

test("stale Snapshots disable editing and validation", () => {
  const task = ["01", "metadata", "Edit", "review"];
  assert.equal(uiState.canEdit(task, "metadata", true, true), false);
  assert.equal(uiState.canValidate(task, "metadata", true, false, true), false);
});

test("Model Scope stays readable without enabling local edit controls", () => {
  const task = ["01", "model", "Inspect scope", "doing"];
  assert.equal(uiState.canEdit(task, "model", true, false, "model_scope"), false);
  assert.equal(uiState.canEdit(task, "model", true, false, "model_details"), true);
});
