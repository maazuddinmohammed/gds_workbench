# Atlas identity and interface studies — temporary

Selected: Paper with Atlas Meridian and an uppercase ATLAS wordmark.

Implementation approved and applied to the web app, Workbench and icon assets on 2026-10-16. This directory remains an isolated, disposable design reference and is excluded from application packages.

## Directions

- Paper / Arch: white masthead, blue identity and headings, quiet side navigation.
- Ink / Monogram: KPMG-blue masthead, vertical project navigation, contextual inspector. Recommended for strongest corporate expression.
- Editorial / Meridian: horizontal navigation, cool canvas, broad white ledger and blue headings.

Theme and logo can be mixed independently. Every direction includes web, local Workbench, tenant entry, logo specimens and reference rationale. URL parameters retain the current review choice; fixture edits are temporary.

## Identity corrections

The previous faceted mark had a pale crossbar with approximately 1.32:1 contrast on white, overlapping colored pieces and inconsistent web/Workbench proportions. New marks use one compound SVG silhouette with positive/reversed treatments and identical 32px symbol / 25px wordmark proportions. The logo lab includes 16, 20, 24, 32 and 48px specimens.

## KPMG foundation

Verified against KPMG's public site on 2026-10-16:

- Brand blue: #00338D; action blue: #1E49E2; ink: #0C233C.
- Canvas: #F5F6FA; white working surfaces; decorative highlight: #76D2FF.
- Open Sans Regular / SemiBold for UI; Open Sans Condensed Bold for page headings.

These application roles are a design synthesis, not a claim of compliance with a complete internal brand guide. Atlas artwork is original. Official KPMG logo is intentionally absent, following the user's request to retain Atlas.

Primary references:

- https://kpmg.com/us/en/capabilities-services/ai/kpmg-workbench.html
- https://kpmg.com/etc.clientlibs/kpmg/clientlibs/clientlib-site.lc-1d2c81ea6172f1a99f3407945e8ea768-lc.min.css
- https://linear.app/now/behind-the-latest-design-refresh
- https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines
- https://www.ibm.com/design/language/iconography/ui-icons/design/

Open Sans WOFF2 files are bundled from KPMG's public stylesheet font paths. License is in assets/fonts/OFL.txt, from https://github.com/google/fonts/blob/main/ofl/opensans/OFL.txt. No external font requests at runtime.

## Review checks

- JavaScript syntax checked; no browser console errors during interaction checks.
- All 15 theme/surface combinations render; no document overflow at 391 CSS pixels.
- Ink inspector remains visible at 1024 CSS pixels; desktop and mobile reviewed visually.
- Search + system/zone filters, tenant search/selection/entry, object details/sample attribute dialog, fixture add dialog, Workbench validation feedback, logo selection, URL state and construction grid checked.
- Same logo geometry and masthead dimensions across web, Workbench and entry; matching generated favicon color.

This is an isolated visual prototype with synthetic data, not the application or a backend regression test. Workflow/dataset navigation demonstrates layout rather than complete domain behavior. No API or database connections. Production source and the existing local app were not changed during this refinement round.

## Run / discard

From repository root:

```sh
python3 -m http.server 4321 --bind 127.0.0.1 --directory web_app/frontend/prototype-atlas-refinement
```

Open http://127.0.0.1:4321/?variant=ink&surface=web&logo=monogram . Stop that server and remove only this directory after the selected design has been implemented and verified. Decision pending user review.

## Ink refinement — review 03, 2026-10-16

- Kept #00338D masthead and the shared Atlas Monogram; removed the continuous cyan stripe.
- Kept #1E49E2 for primary actions and focus/selected-control indicators. Workbench header validation is now a secondary outlined action, leaving Review changes as the main working action.
- Changed selected table rows to neutral #EEF1F5 and navigation selection to #E9EDF4.
- Dark #0C233C section headings and working text; white data surfaces and #F5F6FA supporting surfaces.
- Muted text on tinted surfaces uses #596B81; white header focus outline is visible against blue.
- One shared brand renderer: 32px vector symbol and 25px Open Sans wordmark, identical path and white treatment on both mastheads. Favicon uses the same path in brand blue.
- Prototype defaults to Ink; surface switching scrolls to the top.
- Browser verified: web search/details, Workbench fixture validation, white keyboard focus, no console warnings/errors, 391px mobile no document overflow on either surface, visible 1024px tablet inspector. Desktop screenshots saved for web and Workbench.
- Main contrast pairs measured: white/deep blue 11.30:1; white/action blue 6.76:1; dark text/white 15.89:1. This is targeted contrast verification, not a full accessibility certification.
- Production tracked diff fingerprint unchanged during this round. No application build, packaging, database or API changes.

Review links:
- Web: http://127.0.0.1:4321/?variant=ink&surface=web&logo=monogram
- Workbench: http://127.0.0.1:4321/?variant=ink&surface=workbench&logo=monogram

## Paper / Meridian / ATLAS — review 04, 2026-10-16

- Retained Paper's white masthead, blue headings and quiet supporting surfaces.
- Added optional uppercase ATLAS: shared 32px vector symbol, 23px Open Sans SemiBold wordmark and 1.8px letter spacing across web, Workbench, tenant entry and logo specimens.
- The AA/Aa control switches wordmark case; `wordmark=upper` preserves the choice in review links. Earlier links retain title case.
- Browser verified: uppercase toggle and surface switching preserve state; matching Workbench and web identity; no document overflow at 391 CSS pixels; reviewed 16–48px logo specimens and desktop screens. No console warnings/errors observed.
- This is another review option, not a production selection. Production source, backend and packaging remain unchanged.

Review links:
- Web: http://127.0.0.1:4321/?variant=paper&surface=web&logo=meridian&wordmark=upper
- Workbench: http://127.0.0.1:4321/?variant=paper&surface=workbench&logo=meridian&wordmark=upper
- Logo specimens: http://127.0.0.1:4321/?variant=paper&surface=identity&logo=meridian&wordmark=upper
