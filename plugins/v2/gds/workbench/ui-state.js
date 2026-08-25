(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSUIState = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const EDIT_STATES = new Set(["doing", "review", "ready", "overridden", "staged"]);

  function canEdit(task, area, loaded, stale = false, dataset = null) {
    return Boolean(
      loaded &&
        !stale &&
        !(area === "model" && dataset === "model_scope") &&
        Array.isArray(task) &&
        task[1] === area &&
        EDIT_STATES.has(task[3]),
    );
  }

  function canValidate(task, area, hasSnapshot, dirty, stale = false) {
    return Boolean(
      hasSnapshot &&
        !dirty &&
        !stale &&
        Array.isArray(task) &&
        task[1] === area &&
        task[3] === "review",
    );
  }

  function requireClean(dirty, action) {
    if (dirty) {
      throw new Error(`Save or discard the visible draft before ${action}.`);
    }
  }

  return { canEdit, canValidate, requireClean };
});
