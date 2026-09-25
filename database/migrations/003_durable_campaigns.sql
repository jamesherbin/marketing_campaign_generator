BEGIN;

DO $$
DECLARE role_check text;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO role_check FROM pg_constraint
    WHERE conrelid = 'workspace_members'::regclass AND conname = 'workspace_members_role_check';
    IF role_check IS NULL OR position('''runner''' IN role_check) = 0
        OR position('''owner''' IN role_check) > 0 OR position('''admin''' IN role_check) > 0 THEN
        RAISE EXCEPTION 'Migration 002 must be applied before migration 003';
    END IF;
END;
$$;

-- New Firebase accounts need not have an email address. UID is the identity key.
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
DROP INDEX users_email_unique_ci;
CREATE UNIQUE INDEX users_email_unique_ci ON users (lower(email)) WHERE email IS NOT NULL;

CREATE FUNCTION prevent_firebase_uid_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.firebase_uid IS DISTINCT FROM OLD.firebase_uid THEN
        RAISE EXCEPTION 'Firebase UID is immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER users_uid_immutable BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION prevent_firebase_uid_change();

ALTER TABLE approval_events ADD COLUMN actor_firebase_uid text;
-- The table lock and trigger change are confined to this migration transaction.
ALTER TABLE approval_events DISABLE TRIGGER approval_events_no_update;
UPDATE approval_events AS event SET actor_firebase_uid = actor.firebase_uid
FROM users AS actor WHERE event.actor_user_id = actor.user_id;
ALTER TABLE approval_events ENABLE TRIGGER approval_events_no_update;
ALTER TABLE approval_events ALTER COLUMN actor_firebase_uid SET NOT NULL;
ALTER TABLE approval_events ADD CONSTRAINT approval_uid_not_blank
    CHECK (length(btrim(actor_firebase_uid)) > 0);

CREATE FUNCTION snapshot_approval_identity() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE verified_uid text;
BEGIN
    SELECT firebase_uid INTO STRICT verified_uid FROM users WHERE user_id = NEW.actor_user_id;
    IF NEW.actor_firebase_uid IS NOT NULL AND NEW.actor_firebase_uid <> verified_uid THEN
        RAISE EXCEPTION 'Approval UID does not match its actor';
    END IF;
    NEW.actor_firebase_uid = verified_uid;
    RETURN NEW;
END;
$$;
CREATE TRIGGER approval_events_identity BEFORE INSERT ON approval_events
FOR EACH ROW EXECUTE FUNCTION snapshot_approval_identity();

CREATE TABLE legacy_approval_history (
    campaign_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    phase text NOT NULL CHECK (phase IN ('planning', 'development', 'execution', 'monitoring')),
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    comment text,
    decided_at timestamptz NOT NULL,
    PRIMARY KEY (campaign_id, position),
    FOREIGN KEY (campaign_id, workspace_id) REFERENCES campaigns(campaign_id, workspace_id)
);
CREATE TRIGGER legacy_approval_no_update BEFORE UPDATE ON legacy_approval_history
FOR EACH ROW EXECUTE FUNCTION prevent_approval_event_mutation();
CREATE TRIGGER legacy_approval_no_delete BEFORE DELETE ON legacy_approval_history
FOR EACH ROW EXECUTE FUNCTION prevent_approval_event_mutation();

CREATE TABLE campaign_imports (
    import_id uuid PRIMARY KEY,
    export_sha256 text NOT NULL CHECK (export_sha256 ~ '^[0-9a-f]{64}$'),
    workspace_id uuid NOT NULL UNIQUE REFERENCES workspaces(workspace_id),
    owner_user_id uuid NOT NULL REFERENCES users(user_id),
    workspace_name text NOT NULL,
    workspace_slug text NOT NULL,
    campaign_count integer NOT NULL CHECK (campaign_count >= 0),
    imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER campaign_imports_no_update BEFORE UPDATE ON campaign_imports
FOR EACH ROW EXECUTE FUNCTION prevent_approval_event_mutation();
CREATE TRIGGER campaign_imports_no_delete BEFORE DELETE ON campaign_imports
FOR EACH ROW EXECUTE FUNCTION prevent_approval_event_mutation();

CREATE TABLE schema_migrations (
    version integer PRIMARY KEY CHECK (version > 0),
    applied_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations (version) VALUES (1), (2), (3);

COMMIT;
