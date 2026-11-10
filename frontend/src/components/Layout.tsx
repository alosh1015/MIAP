import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth, hasRole } from "../auth/AuthContext";
import type { Role } from "../api/client";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
  roles: Role[];
}

const NAV: NavItem[] = [
  { to: "/", label: "Worklist", end: true, roles: ["clinician", "researcher", "administrator"] },
  { to: "/cases/new", label: "New study", roles: ["clinician", "researcher"] },
  { to: "/models", label: "Model library", roles: ["clinician", "researcher", "administrator"] },
  { to: "/audit", label: "Audit trail", roles: ["administrator"] },
];

const ROLE_LABEL: Record<Role, string> = {
  clinician: "Clinician",
  researcher: "Researcher",
  administrator: "Administrator",
};

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen bg-slate-100">
      <aside className="hidden w-64 shrink-0 flex-col bg-ink-900 px-5 py-6 text-slate-300 md:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-clinical-500 font-bold text-white">M</div>
          <div>
            <p className="text-sm font-semibold text-white">MIAP</p>
            <p className="text-[11px] text-slate-500">Decision support</p>
          </div>
        </div>
        <nav className="mt-9 space-y-1">
          {NAV.filter((item) => hasRole(user, ...item.roles)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `focus-ring block rounded-md px-3 py-2 text-sm transition ${
                  isActive ? "bg-clinical-600 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-4">
          <div className="rounded-lg border border-white/10 bg-white/5 p-3">
            <p className="text-xs font-medium text-white">{user?.display_name}</p>
            <p className="mt-0.5 text-[11px] text-slate-400">{user ? ROLE_LABEL[user.role] : ""}</p>
            <button
              type="button"
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="focus-ring mt-3 w-full rounded-md border border-white/10 px-2 py-1.5 text-[11px] text-slate-300 hover:bg-white/10"
            >
              Sign out
            </button>
          </div>
          <p className="text-[10px] leading-relaxed text-slate-600">
            Decision support only. Not a diagnostic device. Every image is de-identified before storage.
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3 md:px-8">
          <div className="flex items-center gap-3 md:hidden">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-clinical-600 text-sm font-bold text-white">M</div>
            <span className="text-sm font-semibold">MIAP</span>
          </div>
          <p className="hidden text-xs text-slate-500 md:block">
            Medical Image AI Pipeline · Mbarara University of Science and Technology
          </p>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="hidden sm:inline">{ROLE_LABEL[user?.role ?? "clinician"]}</span>
            <span className="h-1.5 w-1.5 rounded-full bg-clinical-500" />
          </div>
        </header>
        <main className="min-w-0 flex-1 px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
