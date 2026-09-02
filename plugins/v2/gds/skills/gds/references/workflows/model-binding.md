# Model Binding

Run only after target Metadata Apply succeeds and a fresh Metadata Snapshot confirms every target Object and Attribute.

- `model_object_binding` binds one Logical Entity to one Silver Object or one Dimensional Entity to one Gold Object.
- `model_attribute_binding` binds each modeled Attribute to one Attribute under that Object Binding.
- Bind every modeled and physical target Attribute exactly once, including audit, technical, and constant-valued Attributes.
- Derive Model, Object, and Entity type from the parent binding instead of repeating them in Attribute Binding.
- A target Object's `source_tenant_id` must equal the Model Tenant.

Missing or ambiguous metadata blocks. Apply Binding through a Model Change Set, refresh the Model Snapshot, and stop before Mapping. Mapping never establishes Binding.
