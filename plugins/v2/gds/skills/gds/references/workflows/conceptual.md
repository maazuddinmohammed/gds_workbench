# Conceptual Model

Create a compact business view of important concepts and their relationships. Use PascalCase by default unless the user or Model policy says otherwise.

1. Start with a table-by-table pass. For every scoped Object, state its business purpose and identify the concept or concepts it supports; an Object may be context-only or support several concepts.
2. Consolidate candidates across Objects and Systems when they describe the same business idea. Several Objects may support one concept; do not create a concept merely because a table exists.
3. Define each concept in business language. Do not add Attributes, keys, normalization, table design, or dependency order.
4. Add business relationships using the completed relationship Analysis. Keep high-level cardinality only when supported; otherwise use unknown. Never infer physical keys.
5. Account for every selected input as represented, context-only, excluded with reason, or blocked.

Conceptual is a required Logical Build phase. Reject a mechanical one-concept-per-Object or Conceptual-to-Logical copy unless independently justified. Conceptual informs Logical vocabulary, business boundaries, and relationships, while grain and normalization remain evidence-driven.
