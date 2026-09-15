(function (root, factory) {
  "use strict";
  let common = root.GDSCommonValidation;
  let metadataValidation = root.GDSMetadataValidation;
  if (typeof module === "object" && module.exports) {
    common = require("./validation/common.js");
    metadataValidation = require("./validation/metadata.js");
  }
  const api = factory(common, metadataValidation);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GDSMetadata = api;
})(typeof globalThis === "object" ? globalThis : this, function (common, metadataValidation) {
  "use strict";

  function validate(loaded, _metadataLoaded = null, context = {}) {
    const effective = new Map();
    for (const [name, value] of loaded) {
      effective.set(name, {
        definition: value.definition,
        schema: value.schema,
        records: value.effective,
      });
    }
    return [
      ...common.validateLoaded("metadata", loaded),
      ...metadataValidation.validateLocks(loaded),
      ...metadataValidation.validateTenantScope(loaded, context.tenantCode),
      ...metadataValidation.validateUniqueConstraints(effective),
      ...metadataValidation.validateReferences(effective),
    ];
  }

  return { label: "Metadata", validate };
});
