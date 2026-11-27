undefined

## Implementation update — 2026-11-27 (persistent CRM prospect-to-project workflow)

- CRM prospects now support nullable `project_id` with migration 071, a workspace-safe composite foreign key and scoped index. Existing records remain valid and unlinked; deleting a project clears only the association.
- Prospect create/update validates that selected projects are active and belong to the same workspace. Older update clients preserve existing links; explicit null unlinks. Existing archived associations can be retained or removed.
- CRM listing returns linked project metadata and supports project-name search. Dashboard prospect creation and contact editing support project selection; CRM cards display the association. CSV imports remain backward-compatible and unlinked unless later associated manually.
- Migration 071 is included in database diagnostics, launch preflight and API readiness. No database migration was applied; no tests/build/CI/browser acceptance/deployment were run.
