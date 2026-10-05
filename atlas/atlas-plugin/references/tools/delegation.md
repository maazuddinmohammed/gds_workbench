# Delegation policy

Load only when delegation is useful and authorized by the user and host. A saved model preference is not permission to delegate. Continue independently when delegation is unavailable.


A sub-agent is a helper agent assigned part of the work. This policy controls its
AI model. It does not change the main chat model or the Atlas data Model.

Ask: **Which model rule should Atlas use for sub-agents?**

| Choice shown to the user | Saved mode | Required behavior |
|---|---|---|
| **Current model only** (recommended) | `current` | Use the model selected by the user in the main chat for every sub-agent. |
| **Agent selects the model** | `auto` | Select an available, permitted model suited to each assigned task. |
| **Specified model only** | `custom` | Use only the exact model specified by the user for every sub-agent. |

For **Specified model only**, resolve the user's choice to one exact model name
or ID supported by the host. Ask only if the name is missing or ambiguous; never
substitute another model or guess a provider ID. Save it as `model` beside `mode`.

The choice lives in `.atlas/session.json` as `subagent_policy`. It applies to
every workflow and task in that working folder until the user changes it.
Old workspaces without this field remain readable; the policy is **Not set**.
Resolve the choice only before authorized delegation; keep independent work in the main agent until then. Report the selected model with the assignment.

Before delegating, use the host's actual supported model controls. For `current`,
resolve the main chat's current model at that time; do not pin yesterday's model
or assume the host's default sub-agent model matches it. Use inherited settings
only when the host guarantees they select that same model. For `auto`, use only
available models and state the selected model with the assignment. For `custom`,
pass the exact saved model using a supported host control.

If the host cannot select or verify the required model, explain the limit and
continue in the main agent. Do not silently use a fallback or change host-wide
settings. Switching between Copilot and Codex requires checking the saved choice
against the new host's available models again.

Pass this policy and the main chat model identity, when required, to each child.
It also applies to nested sub-agents; `current` always refers to the user's main
chat, not a different model chosen by an intermediate agent. A later user change
applies before further delegated work: stop or reassign active sub-agents that
no longer meet the rule. Keep completed files and review their results normally.

Choosing a model policy does not require sub-agents or authorize extra work.
Host and repository limits on delegation still apply. Sub-agents receive only
their assigned scope; the parent remains responsible for reviewing their results
and the normal Stage and Apply approvals.
