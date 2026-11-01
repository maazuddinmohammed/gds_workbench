(function (root, factory) {
  "use strict";
  const node = typeof module === "object" && module.exports;
  const api = factory(node ? require("./core.js") : root.GDSCore);
  if (node) module.exports = api;
  root.GDSUIState = api;
})(typeof globalThis === "object" ? globalThis : this, function (core) {
  "use strict";


  function canEdit(task, area, loaded, stale = false, dataset = null) {
    return Boolean(
      loaded &&
        !stale &&
        !(area === "project" && core.WEB_MANAGED_PROJECT_DATASETS.includes(dataset)) &&
        task?.schema_version === "2.0" && typeof task.outcome === "string",
    );
  }

  function canValidate(task, area, hasSnapshot, dirty, stale = false) {
    return Boolean(
      hasSnapshot &&
        !dirty &&
        !stale &&
        task?.schema_version === "2.0" && typeof task.outcome === "string",
    );
  }

  function requireClean(dirty, action) {
    if (dirty) {
      throw new Error(`Save or discard the visible draft before ${action}.`);
    }
  }

  return { canEdit, canValidate, requireClean };
});
