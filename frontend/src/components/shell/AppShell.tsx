import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { hasRole, useAuth } from "../../auth/AuthContext";
import type { Role } from "../../api/client";
import { Icon, Logo, type IconName } from "../icons";
import { cx, initials } from "../ui";
import { ToolTour } from "../ToolTour";
import { useTheme, type ThemePreference } from "../../theme/ThemeContext";

export const ROLE_LABEL: Record<Role, string> = {
  clinician: "Clinician",
  researcher: "Researcher",
  administrator: "Administrator",
};

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  roles: Role[];
  end?: boolean;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "dashboard", roles: ["clinician", "researcher", "administrator"], end: true },
  { to: "/worklist", label: "Worklist", icon: "worklist", roles: ["clinician"] },
  { to: "/research", label: "Dataset", icon: "database", roles: ["researcher"] },
  { to: "/research/batches", label: "Batches", icon: "bolt", roles: ["researcher"] },
  { to: "/worklist", label: "Studies", icon: "worklist", roles: ["administrator"] },
  { to: "/cases/new", label: "New study", icon: "new-study", roles: ["clinician", "researcher"] },
  { to: "/models", label: "Models", icon: "models", roles: ["clinician", "researcher", "administrator"] },
  { to: "/admin/health", label: "Governance", icon: "shield", roles: ["administrator"] },
];

function visibleNav(user: Parameters<typeof hasRole>[0]): NavItem[] {
  return NAV.filter((item) => hasRole(user, ...item.roles)).filter(
    (item, index, all) => all.findIndex((other) => other.to === item.to) === index,
  );
}

export function AppShell() {
  const { user } = useAuth();
  const items = visibleNav(user);
  const location = useLocation();
  const [lastCase, setLastCase] = useState<string | null>(() =>
    window.localStorage.getItem("miap.last-case"),
  );

  useEffect(() => {
    setLastCase(window.localStorage.getItem("miap.last-case"));
  }, [location.pathname]);

  const railClass = (isActive: boolean) =>
    cx(
      "relative flex w-[62px] flex-col items-center gap-1.5 rounded-lg py-2.5 text-xs font-medium leading-none transition-colors duration-150 ease-out",
      isActive ? "text-petrol" : "text-muted hover:text-ink",
    );

  return (
    <div className="flex min-h-screen bg-paper">
      <aside className="sticky top-0 hidden h-screen w-[76px] shrink-0 flex-col items-center border-r border-rule py-4 lg:flex">
        <Link to="/" aria-label="MIAP dashboard" className="text-petrol">
          <Logo size={34} />
        </Link>
        <nav aria-label="Main" className="mt-7 flex w-full flex-col items-center gap-0.5">
          {items.slice(0, 2).map((item) => (
            <RailLink key={`${item.to}-${item.label}`} item={item} className={railClass} />
          ))}
          {lastCase ? (
            <NavLink to={`/cases/${lastCase}`} className={({ isActive }) => railClass(isActive)}>
              <Icon name="image" size={20} />
              <span className="text-center leading-tight">Workspace</span>
            </NavLink>
          ) : (
            <span
              className="flex w-[62px] cursor-not-allowed flex-col items-center gap-1.5 rounded-lg py-2.5 text-xs font-medium leading-none text-muted/60"
              title="Open a study to pin its workspace here"
            >
              <Icon name="image" size={20} />
              <span className="text-center leading-tight">Workspace</span>
            </span>
          )}
          {items.slice(2).map((item) => (
            <RailLink key={`${item.to}-${item.label}`} item={item} className={railClass} />
          ))}
        </nav>
        <div className="mt-auto flex w-full flex-col items-center gap-1">
          <NavLink to="/settings" className={({ isActive }) => railClass(isActive)}>
            <Icon name="settings" size={19} />
            Settings
          </NavLink>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 bg-paper/90 px-4 backdrop-blur lg:px-8">
          <Link to="/" className="text-petrol lg:hidden" aria-label="MIAP dashboard">
            <Logo size={28} />
          </Link>
          <div className="ml-auto flex shrink-0 items-center gap-1">
            <ThemeMenuButton />
            <UserMenu />
          </div>
        </header>

        <main className="min-w-0 flex-1 px-4 pb-28 lg:px-8 lg:pb-14">
          <Outlet />
        </main>

        <nav
          aria-label="Main"
          className="fixed inset-x-0 bottom-0 z-30 flex border-t border-rule bg-paper pb-[env(safe-area-inset-bottom)] lg:hidden"
        >
          {items.slice(0, 5).map((item) => (
            <NavLink
              key={`${item.to}-${item.label}`}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cx(
                  "relative flex flex-1 flex-col items-center gap-1 py-2.5 text-xs font-medium",
                  isActive
                    ? "text-petrol before:absolute before:-top-px before:h-0.5 before:w-8 before:rounded-full before:bg-petrol"
                    : "text-muted",
                )
              }
            >
              <Icon name={item.icon} size={20} />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <ToolTour />
    </div>
  );
}

function RailLink({
  item,
  className,
}: {
  item: NavItem;
  className: (isActive: boolean) => string;
}) {
  return (
    <NavLink to={item.to} end={item.end} className={({ isActive }) => className(isActive)}>
      <Icon name={item.icon} size={20} />
      <span className="text-center leading-tight">{item.label}</span>
    </NavLink>
  );
}

/* --------------------------------------------------------------- theme menu */

const THEME_OPTIONS: { id: ThemePreference; label: string; icon: IconName }[] = [
  { id: "light", label: "Light", icon: "sun" },
  { id: "dark", label: "Dark", icon: "moon" },
  { id: "system", label: "System", icon: "monitor" },
];

function useThemeMenu() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return { theme, setTheme, open, setOpen, ref };
}

function ThemeMenuButton() {
  const { theme, setTheme, open, setOpen, ref } = useThemeMenu();
  const icon: IconName = theme === "light" ? "sun" : theme === "dark" ? "moon" : "monitor";
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={`Theme: ${theme}`}
        aria-expanded={open}
        className="flex h-10 w-10 items-center justify-center rounded-lg text-muted transition-colors duration-150 ease-out hover:bg-surface-2 hover:text-ink"
      >
        <Icon name={icon} size={18} />
      </button>
      {open ? (
        <div className="popover absolute right-0 z-40 mt-1 w-40 rounded-xl bg-surface p-1.5 shadow-lg">
          {THEME_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => {
                setTheme(option.id);
                setOpen(false);
              }}
              className={cx(
                "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors duration-150 ease-out",
                theme === option.id ? "text-petrol" : "text-ink hover:bg-surface-2",
              )}
            >
              <Icon name={option.icon} size={16} />
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------- user menu */

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Account menu"
        aria-expanded={open}
        className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-2 text-xs font-semibold text-ink transition-colors duration-150 ease-out hover:bg-rule"
      >
        {initials(user.display_name)}
      </button>
      {open ? (
        <div className="popover absolute right-0 z-40 mt-1 w-64 rounded-xl bg-surface p-1.5 shadow-lg">
          <div className="px-2.5 pb-2 pt-1.5">
            <p className="truncate text-sm font-medium text-ink">{user.display_name}</p>
            <p className="truncate text-xs text-muted">{user.email}</p>
            <p className="mt-1.5 text-xs text-petrol">{ROLE_LABEL[user.role]}</p>
          </div>
          <Link
            to="/settings"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-ink transition-colors duration-150 ease-out hover:bg-surface-2"
          >
            <Icon name="settings" size={16} />
            Settings
          </Link>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-ink transition-colors duration-150 ease-out hover:bg-surface-2"
          >
            <Icon name="logout" size={16} />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------ admin sub-nav */

const ADMIN_TABS = [
  { to: "/admin/health", label: "Health", icon: "health" as IconName },
  { to: "/admin/users", label: "Users", icon: "users" as IconName },
  { to: "/admin/audit", label: "Audit", icon: "audit" as IconName },
  { to: "/admin/retention", label: "Retention", icon: "retention" as IconName },
  { to: "/admin/models", label: "Approvals", icon: "models" as IconName },
];

export function AdminSubnav() {
  return (
    <nav aria-label="Governance" className="mb-6 flex flex-wrap gap-1 border-b border-rule">
      {ADMIN_TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            cx(
              "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm",
              isActive ? "border-petrol font-medium text-ink" : "border-transparent text-muted hover:text-ink",
            )
          }
        >
          <Icon name={tab.icon} size={15} />
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
