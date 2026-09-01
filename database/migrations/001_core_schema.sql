BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid text NOT NULL UNIQUE,
    email text NOT NULL,
    display_name text,
    photo_url text,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_email_not_blank CHECK (length(btrim(email)) > 0),
    CONSTRAINT users_firebase_uid_not_blank CHECK (length(btrim(firebase_uid)) > 0)
);

CREATE UNIQUE INDEX users_email_unique_ci ON users (lower(email));

CREATE TABLE workspaces (
    workspace_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    slug text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'deleted')),
    created_by_user_id uuid NOT NULL REFERENCES users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT workspaces_name_not_blank CHECK (length(btrim(name)) > 0),
    CONSTRAINT workspaces_slug_format CHECK (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$')
);

CREATE TABLE workspace_members (
    workspace_id uuid NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('owner', 'admin', 'approver', 'editor', 'viewer')),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('invited', 'active', 'suspended')),
    joined_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE INDEX workspace_members_user_idx
    ON workspace_members (user_id, status);

CREATE TABLE campaigns (
    campaign_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces(workspace_id),
    created_by_user_id uuid NOT NULL REFERENCES users(user_id),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'in_progress', 'awaiting_approval', 'completed', 'failed')),
    current_phase text NOT NULL DEFAULT 'planning'
        CHECK (current_phase IN ('planning', 'development', 'execution', 'monitoring')),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT campaigns_metadata_object CHECK (jsonb_typeof(metadata) = 'object'),
    CONSTRAINT campaigns_id_workspace_unique UNIQUE (campaign_id, workspace_id)
);

CREATE INDEX campaigns_workspace_updated_idx
    ON campaigns (workspace_id, updated_at DESC);
CREATE INDEX campaigns_workspace_status_idx
    ON campaigns (workspace_id, status);

-- CampaignBrief: exactly one brief belongs to each CampaignState.
CREATE TABLE campaign_briefs (
    campaign_id uuid PRIMARY KEY REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    brand varchar(200) NOT NULL CHECK (length(btrim(brand)) > 0),
    campaign_goal text NOT NULL CHECK (length(btrim(campaign_goal)) > 0),
    target_audience text[] NOT NULL CHECK (cardinality(target_audience) > 0),
    duration_weeks integer NOT NULL CHECK (duration_weeks > 0 AND duration_weeks <= 260),
    budget numeric NOT NULL CHECK (budget > 0),
    currency varchar(3) NOT NULL DEFAULT 'USD' CHECK (currency ~ '^[A-Z]{3}$'),
    preferred_channels text[] NOT NULL DEFAULT ARRAY[]::text[],
    success_metrics text[] NOT NULL DEFAULT ARRAY[]::text[],
    industry text,
    product text,
    constraints text[] NOT NULL DEFAULT ARRAY[]::text[]
);

-- PlanningOutput: optional until the planning phase completes.
CREATE TABLE planning_outputs (
    campaign_id uuid PRIMARY KEY REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    goals text[] NOT NULL,
    measurable_objectives text[] NOT NULL,
    audience_segments text[] NOT NULL,
    positioning_statement text NOT NULL,
    value_proposition text NOT NULL,
    key_messages text[] NOT NULL,
    recommended_channels text[] NOT NULL,
    budget_by_channel jsonb NOT NULL,
    CONSTRAINT planning_budget_by_channel_object
        CHECK (jsonb_typeof(budget_by_channel) = 'object')
);

-- DevelopmentOutput and its ContentAsset collection.
CREATE TABLE development_outputs (
    campaign_id uuid PRIMARY KEY REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    creative_direction text NOT NULL,
    media_plan jsonb NOT NULL,
    CONSTRAINT development_media_plan_object CHECK (jsonb_typeof(media_plan) = 'object')
);

CREATE TABLE content_assets (
    asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid NOT NULL REFERENCES development_outputs(campaign_id) ON DELETE CASCADE,
    position integer NOT NULL CHECK (position >= 0),
    channel text NOT NULL,
    format text NOT NULL,
    headline text NOT NULL,
    body text NOT NULL,
    call_to_action text,
    status text NOT NULL DEFAULT 'draft',
    UNIQUE (campaign_id, position)
);

CREATE INDEX content_assets_campaign_idx ON content_assets (campaign_id);

-- ExecutionOutput and its ScheduledActivity collection. ScheduledActivity has no
-- model identifier, so the database supplies one while position preserves list order.
CREATE TABLE execution_outputs (
    campaign_id uuid PRIMARY KEY REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    publication_summary text NOT NULL
);

CREATE TABLE scheduled_activities (
    scheduled_activity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid NOT NULL REFERENCES execution_outputs(campaign_id) ON DELETE CASCADE,
    position integer NOT NULL CHECK (position >= 0),
    channel text NOT NULL,
    action text NOT NULL,
    scheduled_for timestamptz,
    status text NOT NULL DEFAULT 'prepared',
    UNIQUE (campaign_id, position)
);

CREATE INDEX scheduled_activities_campaign_idx
    ON scheduled_activities (campaign_id);

-- MonitoringOutput. KPI values remain JSONB because the model permits numbers,
-- strings, and null values under dynamic metric names.
CREATE TABLE monitoring_outputs (
    campaign_id uuid PRIMARY KEY REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    kpis jsonb NOT NULL,
    analysis text[] NOT NULL,
    recommendations text[] NOT NULL,
    stakeholder_summary text NOT NULL,
    CONSTRAINT monitoring_kpis_object CHECK (jsonb_typeof(kpis) = 'object')
);

-- PhaseRun: CampaignState always has one record for every phase.
CREATE TABLE phase_runs (
    campaign_id uuid NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    phase text NOT NULL CHECK (phase IN ('planning', 'development', 'execution', 'monitoring')),
    status text NOT NULL DEFAULT 'not_started'
        CHECK (status IN ('not_started', 'running', 'awaiting_approval', 'completed', 'failed')),
    started_at timestamptz,
    completed_at timestamptz,
    error text,
    PRIMARY KEY (campaign_id, phase),
    CONSTRAINT phase_runs_time_order
        CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at)
);

-- ApprovalRecord plus authenticated actor identity. `actor` is retained as the
-- display snapshot expected by the Pydantic model; actor_user_id is authoritative.
CREATE TABLE approval_events (
    approval_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid NOT NULL,
    workspace_id uuid NOT NULL REFERENCES workspaces(workspace_id),
    actor_user_id uuid NOT NULL REFERENCES users(user_id),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    phase text NOT NULL CHECK (phase IN ('planning', 'development', 'execution', 'monitoring')),
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
    comment text,
    campaign_version integer NOT NULL CHECK (campaign_version > 0),
    decided_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT approval_events_campaign_workspace_fk
        FOREIGN KEY (campaign_id, workspace_id)
        REFERENCES campaigns(campaign_id, workspace_id)
);

CREATE INDEX approval_events_campaign_decided_idx
    ON approval_events (campaign_id, decided_at DESC);
CREATE INDEX approval_events_workspace_decided_idx
    ON approval_events (workspace_id, decided_at DESC);

CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER workspaces_set_updated_at
BEFORE UPDATE ON workspaces
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER workspace_members_set_updated_at
BEFORE UPDATE ON workspace_members
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER campaigns_set_updated_at
BEFORE UPDATE ON campaigns
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE FUNCTION prevent_approval_event_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'approval events are immutable';
END;
$$;

CREATE TRIGGER approval_events_no_update
BEFORE UPDATE ON approval_events
FOR EACH ROW EXECUTE FUNCTION prevent_approval_event_mutation();

CREATE TRIGGER approval_events_no_delete
BEFORE DELETE ON approval_events
FOR EACH ROW EXECUTE FUNCTION prevent_approval_event_mutation();

COMMIT;
