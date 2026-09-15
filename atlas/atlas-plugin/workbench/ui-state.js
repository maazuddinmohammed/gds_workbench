(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSUIState = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";


  function canEdit(task, area, loaded, stale = false, dataset = null) {
    return Boolean(
      loaded &&
        !stale &&
        task?.schema_version === "1.0" && typeof task.outcome === "string",
    );
  }

  function canValidate(task, area, hasSnapshot, dirty, stale = false) {
    return Boolean(
      hasSnapshot &&
        !dirty &&
        !stale &&
        task?.schema_version === "1.0" && typeof task.outcome === "string",
    );
  }

  function requireClean(dirty, action) {
    if (dirty) {
      throw new Error(`Save or discard the visible draft before ${action}.`);
    }
  }

  return { canEdit, canValidate, requireClean };
});
