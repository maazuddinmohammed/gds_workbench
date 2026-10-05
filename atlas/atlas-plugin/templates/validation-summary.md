# Verification result format

- Requested outcome, selected scope and exact input bindings.
- Structural checks actually run, results and affected records.
- Semantic review: confirmed rules, evidence and unresolved meaning.
- SQL/check definitions authored but not executed.
- Executed evidence: governed route, population/batches, time and aggregate conclusion.
- Checks not run, unavailable or server-only, with reasons.
- Artifact state: drafted, validated, reviewed, staged or applied, supported by actual evidence.
- Remaining defects and the next required action.

Do not report an unexecuted definition, typed placeholder, `review_required` finding or external comparator as a passing data check. Omit inapplicable fields instead of inventing results.
