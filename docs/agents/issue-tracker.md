# Issue tracker: Local Markdown

Issues and PRDs for this repo live as Markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- PRD: `.scratch/<feature-slug>/PRD.md`
- Issues: `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, starting at `01`
- Triage state: a `Status:` line near the top of each issue
- Comments: append under a `## Comments` heading

When a skill publishes an issue or PRD, create the corresponding file under
`.scratch/<feature-slug>/`. When fetching a ticket, read the referenced file.
