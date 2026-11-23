# Issue Tracker: Local Markdown

Issues, feature specs, research tickets, and wayfinding artifacts live as Markdown files in `.scratch/`.

## Conventions

- One feature or effort per directory: `.scratch/<feature-slug>/`
- The specification is `.scratch/<feature-slug>/spec.md`
- Implementation tickets are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`.
- Research findings live under `docs/research/` or `.scratch/<feature-slug>/research/`.
- Triage state is recorded as a `Status:` line (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`).
