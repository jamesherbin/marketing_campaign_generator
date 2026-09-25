BEGIN;

-- Row locking normally requires UPDATE privilege. This narrow function permits
-- the runtime to lock identity/membership rows without granting it write access.
CREATE FUNCTION lock_workspace_membership(request_uid text, request_workspace uuid)
RETURNS TABLE (user_id uuid, user_status text, workspace_status text,
               membership_status text, role text)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
AS $$
    SELECT u.user_id, u.status, w.status, m.status, m.role
    FROM public.users u
    JOIN public.workspace_members m ON m.user_id = u.user_id
    JOIN public.workspaces w ON w.workspace_id = m.workspace_id
    WHERE u.firebase_uid = request_uid AND w.workspace_id = request_workspace
    FOR SHARE OF u, w, m
$$;
REVOKE ALL ON FUNCTION lock_workspace_membership(text, uuid) FROM PUBLIC;
INSERT INTO schema_migrations (version) VALUES (4);
COMMIT;
