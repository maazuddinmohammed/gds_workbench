# Modeling interview

Use for Atlas Grill Me modeling workflows. Adapt the interview and domain-awareness techniques of grill-me/grill-with-docs to the actual Model scope. This reference owns questioning and decision capture; the selected skill owns entry, layer-specific methods and the outer workflow. Personal GrillMe skills are not plugin dependencies.

## Understand before asking

1. Resolve the requested outcome and starting business area from the user's message. Read the selected workflow's eligible inputs: active applied Model Input Scope for Logical work, or eligible Silver Logical contributions for Dimensional work. Read selected Objects/Attributes, existing Model records, relevant Assertions and pending decisions through the shared Snapshot guides.
2. Read relevant definitions and [Atlas terminology](terminology.md). Compare actual meanings, not just names. Inspect neighboring scoped records when they may explain an identifier, shared concept or cross-group relationship. Preserve the user's scope; reading context does not authorize unrelated changes.
3. Establish what is known, what is inferred and what would change the design. Do not ask the user to recite names, types or saved choices already available in metadata. If metadata and the user's stated behavior conflict, show the concrete difference and resolve it before relying on the disputed fact.

## Resolve one consequential decision

4. Pick the next decision whose answer affects the requested model: meaning/grain before normalization, identity before key lookup, lifecycle before historical representation. Use the topic guides where relevant; do not turn their checks into a mandatory questionnaire or work through all twelve normalization factors aloud.
5. Ask one focused decision at a time. Provide a recommended answer, a short evidence-based reason and meaningful alternatives when useful. Group tightly related clarifications when that makes answering easier or the user prefers grouped questions. Wait for the answer when dependent work needs it; continue independent inspection meanwhile.
6. Test the answer with a concrete scenario. Examples: can the same Product appear on two Order Lines; can a CustomerNumber repeat in another System; should an old Order retain its original price after the Product price changes? Use only scenarios relevant to the current scope. Synthetic scenarios test rules; they are not observed source data.
7. Follow material branches until the current part is understood well enough to model. Clarify overloaded language by naming the alternatives, such as Customer Account versus Ledger Account. State uncertainty where evidence remains incomplete. Do not manufacture difficult edge cases, require agreement on every future part, or ask for confirmation of unchanged decisions.

Useful question shape:

> Can the same Product appear on more than one line of an Order? I recommend identifying a line by OrderNumber and LineNumber, because the scoped metadata defines a separate LineNumber. Is that the intended business identity, or is each Product limited to one line?

The example illustrates the question format, not a universal Order rule. If the user's request or authoritative existing definition already answers it, use that answer rather than asking again.

## Capture the answer and use it

8. Record the concise decision, its evidence/basis and affected records in the existing task's progress/evidence. Update the relevant local Model definitions, grain, aliases or relationship basis when authorized authoring is part of the request. Keep model-specific business meanings with that Model's records/evidence; do not overwrite the plugin's shared terminology with a tenant-specific definition.
9. Use [Assertions](model/assertions.md) only when an attributable business rule needs durable reusable representation. An existing explicit user answer is evidence; do not ask for it again merely to record it. Ordinary design reasoning does not need an Assertion. Keep unknowns explicit instead of promoting an inference into a confirmed rule.
10. Build or revise the agreed local part using the selected skill's layer-specific topic and record guides. Logical work uses [logical design](logical-build/logical-design.md) and applicable Conceptual/Analysis rules; Dimensional work uses [dimensional design](dimensional-build/design.md) and [history](dimensional-build/history.md) when relevant. If the user requested discussion only, retain findings without authoring Model changes. Preserve locks, inactive history, exact scope and other pending work.
11. Follow [local validation](local-validation.md), including quality review, before treating an authored part as complete. Then show the resulting decision/change, remaining uncertainty and the next useful subject. Revisit affected earlier decisions if new evidence contradicts them; preserve unaffected work.

Use the existing task and Model artifacts for continuity. Do not create a parallel CONTEXT.md, ADR series, transcript or handoff kit for each interview. Shared plugin terminology changes only when a reusable Atlas meaning has actually been established.

## Keep the interaction useful

- Default to collaborative reasoning around meaningful parts. If the user asks the agent to follow an agreed plan independently, do so and return for consequential unresolved business decisions.
- Reuse existing profiles and Analysis; SQL is optional under [query scope](query-scope.md), including its batch rules. Asking the user is not a pretext to ignore evidence already available.
- Check both local correctness and whole-request coherence. Partial progress remains partial; working group by group must not lose cross-group relationships or overall coverage.
- Discussion answers authorize the associated local design work only within the request. They are not substitutes for the shared Change Set review/Stage/Apply process.

Guided skills do not load this interview method. Changing questions or conversational pacing here must not change their phase sequence or the shared modeling rules.
