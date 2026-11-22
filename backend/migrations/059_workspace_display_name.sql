-- Give every tenant a stable human-readable name for platform administration.
-- Existing workspaces are backfilled from their owner email; registration writes a
-- deterministic initial name and future workspace settings may allow owner-managed edits.
ALTER TABLE workspaces
    ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT 'Workspace';

UPDATE workspaces w
SET name = COALESCE(
    NULLIF(
        (SELECT initcap(split_part(u.email, '@', 1)) || '''s workspace'
         FROM workspace_memberships m
         JOIN app_users u ON u.id = m.user_id
         WHERE m.workspace_id = w.id AND m.role = 'owner'
         ORDER BY m.created_at ASC
         LIMIT 1),
        ''
    ),
    'Workspace'
)
WHERE name = 'Workspace';

ALTER TABLE workspaces
    ADD CONSTRAINT workspaces_name_length_check
    CHECK (length(trim(name)) BETWEEN 1 AND 160);
