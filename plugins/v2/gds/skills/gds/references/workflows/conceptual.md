# Conceptual Model

Create a compact business view of important concepts and their relationships. Use PascalCase by default unless the user or Model policy says otherwise.

1. Understand business purpose and Assertions before proposing concepts.
2. Group evidence from many Objects or Systems under one concept when they describe the same business idea.
3. Define each concept in business language. Do not add Attributes, keys, normalization, table design, or dependency order.
4. Add business relationships. Keep high-level cardinality only when supported; otherwise use unknown. Never infer physical keys.
5. Account for every selected input as represented, context-only, excluded with reason, or blocked.

Reject a mechanical one-concept-per-Object or Conceptual-to-Logical copy unless independently justified. Conceptual improves vocabulary, boundaries, and shared understanding; it never dictates Logical structure.
