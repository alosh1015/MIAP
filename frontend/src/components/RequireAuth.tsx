import type { ReactNode } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth, hasRole } from "../auth/AuthContext";
import type { Role } from "../api/client";
import { EmptyState, Panel } from "./ui";
import { Icon } from "./icons";

export function RequireAuth() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted">
        Restoring session…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!hasRole(user, ...roles)) {
    return (
      <Panel>
        <EmptyState
          icon="lock"
          title="Not available for this role"
        />
        <p className="flex items-center justify-center gap-1.5 border-t border-rule px-6 py-3 text-xs text-muted">
          <Icon name="shield" size={14} />
          Enforced by the server as well as this screen.
        </p>
      </Panel>
    );
  }
  return <>{children}</>;
}
