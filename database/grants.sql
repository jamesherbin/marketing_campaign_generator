-- Run via psql with runtime_role and operator_role set to existing database roles.
-- Use dedicated non-owner roles without superuser, schema ownership, or inherited
-- broad grants. Migration credentials own the schema and are not application roles.
BEGIN;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM :"runtime_role", :"operator_role";
GRANT USAGE ON SCHEMA public TO :"runtime_role", :"operator_role";
GRANT EXECUTE ON FUNCTION lock_workspace_membership(text, uuid) TO :"runtime_role";

GRANT SELECT ON users, workspaces, workspace_members, campaigns, campaign_briefs,
    planning_outputs, development_outputs, content_assets, execution_outputs,
    scheduled_activities, monitoring_outputs, phase_runs, approval_events,
    legacy_approval_history, schema_migrations TO :"runtime_role";
GRANT INSERT ON campaigns, approval_events TO :"runtime_role";
GRANT UPDATE (status, current_phase, version, metadata, updated_at)
    ON campaigns TO :"runtime_role";
GRANT INSERT, UPDATE, DELETE ON campaign_briefs, planning_outputs,
    development_outputs, content_assets, execution_outputs, scheduled_activities,
    monitoring_outputs, phase_runs TO :"runtime_role";

GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"operator_role";
GRANT INSERT, UPDATE ON users, workspaces, workspace_members TO :"operator_role";
GRANT INSERT ON campaigns, campaign_briefs, planning_outputs, development_outputs,
    content_assets, execution_outputs, scheduled_activities, monitoring_outputs,
    phase_runs, legacy_approval_history, campaign_imports TO :"operator_role";
-- No UPDATE/DELETE/TRUNCATE grants on either history table or the import ledger.
COMMIT;
