from dataclasses import dataclass
from uuid import UUID


ROLE_RANK = {"viewer": 0, "editor": 1, "runner": 2, "approver": 3}


class AccessDeniedError(Exception):
    def __init__(self, status_code=403, detail="Permission denied"):
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class Membership:
    user_id: UUID
    role: str

    def require(self, minimum: str):
        if ROLE_RANK.get(self.role, -1) < ROLE_RANK[minimum]:
            raise AccessDeniedError()


async def resolve_membership(connection, uid: str, workspace_id: UUID, *, lock=False) -> Membership:
    user = await connection.fetchrow("SELECT user_id, status FROM users WHERE firebase_uid = $1", uid)
    if user is not None and user["status"] != "active":
        raise AccessDeniedError(403, "Account disabled")
    if lock:
        row = await connection.fetchrow("SELECT * FROM lock_workspace_membership($1, $2)", uid, workspace_id)
    else:
        row = await connection.fetchrow("""
            SELECT u.user_id, u.status AS user_status, w.status AS workspace_status,
                   m.status AS membership_status, m.role
            FROM users u JOIN workspace_members m USING (user_id)
            JOIN workspaces w USING (workspace_id)
            WHERE u.firebase_uid = $1 AND w.workspace_id = $2
        """, uid, workspace_id)
    if row is not None and row["user_status"] != "active":
        raise AccessDeniedError(403, "Account disabled")
    if row is None or row["workspace_status"] != "active" or row["membership_status"] != "active":
        raise AccessDeniedError(404, "Resource not found")
    return Membership(row["user_id"], row["role"])


async def list_workspaces(connection, uid):
    status = await connection.fetchval("SELECT status FROM users WHERE firebase_uid = $1", uid)
    if status is not None and status != "active":
        raise AccessDeniedError(403, "Account disabled")
    return [dict(row) for row in await connection.fetch("""
        SELECT w.workspace_id, w.name, w.slug, m.role FROM workspaces w
        JOIN workspace_members m USING (workspace_id) JOIN users u USING (user_id)
        WHERE u.firebase_uid = $1 AND u.status = 'active' AND m.status = 'active'
          AND w.status = 'active' ORDER BY w.name, w.workspace_id
    """, uid)]
