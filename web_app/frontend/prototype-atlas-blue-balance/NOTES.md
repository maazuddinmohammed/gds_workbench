# ATLAS: blue and white balance

Throwaway, isolated prototype. No production imports, API calls, persistence,
database access, or application/package changes.

## Question

How can ATLAS retain Paper's light working area while clearly expressing KPMG's
blue identity? Keep the approved Meridian mark and uppercase ATLAS unchanged.

## Run

From the repository root:

```sh
python3 -m http.server 4324 --bind 127.0.0.1 --directory web_app/frontend/prototype-atlas-blue-balance
```

Open <http://127.0.0.1:4324/?variant=signature&surface=web>.
The bottom switcher compares colour placement. Top tabs show web, Workbench,
Tenant entry, logo construction, and the source-backed rationale.
Left/right arrows also switch directions when focus is outside interactive controls.

## Variations

| Direction | Blue placement | Tradeoff |
| --- | --- | --- |
| Current Paper | Logo, headings and controls | Baseline: quiet, weak parent-brand presence. |
| Signature | Continuous deep-blue masthead | Recommended. Recognizable across every surface; data stays white. |
| Navigator | Navigation rail and ATLAS corner | Strongest desktop presence; heavier. Entry retains the blue corner because it has no rail. |
| Horizon | Model context band; entry introduction | More expressive, still light around records. Brand presence depends on contextual content. |

Layout, content, typography, geometry and interactions remain constant to isolate
colour placement. This is intentionally a focused colour comparison, not a new
workflow or layout exploration.

## Colour reasoning

KPMG's current public website defines core blue `#00338D`, cobalt `#1E49E2`, ink
`#0C233C`, white `#FFFFFF`, and gray `#F5F6FA`.
Keeping cobalt mainly for ATLAS actions is our design choice.

- Use core blue for one substantial structural area.
- Leave records, fields and dialogs white; pale gray separates navigation.
- Use cobalt for the main action and active-tab underline.
- Preserve semantic success/warning colours.
- Reverse the same Meridian path on blue; do not redraw it.
- White on core blue has approximately 11.3:1 contrast; pale blue text
  `#D9E5FB` has approximately 8.9:1. Cobalt on core blue is only 1.7:1, so
  Signature's header validation control uses a pale outline and white text.

References checked 2026-10-16:

- [KPMG Workbench](https://kpmg.com/us/en/capabilities-services/ai/kpmg-workbench.html)
- [KPMG live stylesheet](https://kpmg.com/kpmg-us/etc.clientlibs/kpmg/clientlibs/clientlib-site.lc-6e494438867998fc0f0645a6f90090e0-lc.min.css)

These are public-site references, not an internal brand-guide certification.

## Review performed

- JavaScript syntax check.
- Desktop visual review of all three new directions in web, Workbench and entry.
- Shared Meridian construction inspected at 16–176px, positive and reversed.
- 391px responsive checks: no document overflow across all four web variants
  and the three new Workbench variants; data tables retain their own scroll area.
- Search, empty search, Tenant entry enablement, filtering, record inspector,
  attributes dialog, synthetic add-object flow and local validation feedback.
- Comparison buttons preserve keyboard focus after a re-render.
- Production tracked diff fingerprint remains unchanged by this experiment.

## Decision

Pending user selection. Recommendation: Signature. No new production styling
should be inferred from this prototype until a direction is chosen.
