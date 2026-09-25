BEGIN;

-- Prevent concurrent membership writes between the preflight and constraint change.
LOCK TABLE workspace_members IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM workspace_members WHERE role IN ('owner', 'admin')
    ) THEN
        RAISE EXCEPTION 'Legacy owner/admin memberships require explicit role reassignment'
            USING HINT = 'Assign each legacy membership viewer, editor, or approver before retrying; runner becomes available after this migration.';
    END IF;
END;
$$;

ALTER TABLE workspace_members
    DROP CONSTRAINT workspace_members_role_check;

ALTER TABLE workspace_members
    ADD CONSTRAINT workspace_members_role_check
    CHECK (role IN ('viewer', 'editor', 'runner', 'approver'));

COMMIT;
