import type { ReactNode } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth, hasRole } from "../auth/AuthContext";
import type { Role } from "../api/client";

export function RequireAuth() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
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
      <div className="rounded-xl border border-slate-200 bg-white p-8">
        <h1 className="text-lg font-semibold">Not available for this role</h1>
        <p className="mt-2 max-w-prose text-sm text-slate-600">
          This area is restricted. Your administrator can change your role if you need access.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
