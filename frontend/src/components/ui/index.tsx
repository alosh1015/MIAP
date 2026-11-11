import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Icon, type IconName } from "../icons";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ buttons */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-petrol text-paper hover:brightness-110",
  secondary: "border border-rule bg-surface text-ink hover:border-rule-strong",
  ghost: "border border-transparent text-muted hover:bg-surface-2 hover:text-ink",
  danger: "border border-danger/40 text-danger hover:bg-danger/5",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-2.5 text-xs gap-1.5",
  md: "h-10 px-3.5 text-sm gap-2",
};

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  loading?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center rounded-lg font-medium transition-[background-color,color,border-color,filter] duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-45",
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner size={size === "sm" ? 14 : 16} /> : icon ? <Icon name={icon} size={size === "sm" ? 15 : 17} /> : null}
      {children}
    </button>
  );
}

export function IconButton({
  icon,
  label,
  active = false,
  className,
  size = 20,
  ...rest
}: {
  icon: IconName;
  label: string;
  active?: boolean;
  size?: number;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active || undefined}
      className={cx(
        "inline-flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-150 ease-out",
        active ? "text-petrol" : "text-muted hover:bg-surface-2 hover:text-ink",
        className,
      )}
      {...rest}
    >
      <Icon name={icon} size={size} />
    </button>
  );
}

/* -------------------------------------------------------------------- badges */

type Tone = "neutral" | "petrol" | "signal" | "good" | "danger" | "outline";

const BADGE_DOTS: Record<Tone, string> = {
  neutral: "bg-rule-strong",
  petrol: "bg-petrol",
  signal: "bg-signal",
  good: "bg-petrol",
  danger: "bg-danger",
  outline: "bg-rule-strong",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-ink",
        tone === "outline" && "text-muted",
        className,
      )}
    >
      <span aria-hidden="true" className={cx("h-1.5 w-1.5 shrink-0 rounded-full", BADGE_DOTS[tone])} />
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------- panels */

export function Panel({
  children,
  className,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "aside" | "div" | "article";
}) {
  return <Tag className={cx("rounded-xl bg-surface", className)}>{children}</Tag>;
}

export function PanelHeader({
  title,
  note,
  actions,
  className,
}: {
  title: ReactNode;
  note?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-wrap items-start justify-between gap-3 px-5 pt-4", className)}>
      <div className="min-w-0">
        <h2 className="text-base font-semibold leading-tight text-ink">{title}</h2>
        {note ? <p className="mt-1 text-xs tabular-nums text-muted">{note}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  crumb,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  crumb?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {crumb ? <div className="mb-2 text-xs text-muted">{crumb}</div> : null}
        <h1 className="text-2xl font-semibold leading-tight text-ink">{title}</h1>
        {subtitle ? <div className="mt-2 text-xs text-muted">{subtitle}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function EmptyState({
  icon = "folder",
  title,
  body,
  action,
}: {
  icon?: IconName;
  title: string;
  body?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <Icon name={icon} size={22} className="text-rule-strong" />
      <p className="mt-3 text-base font-medium text-ink">{title}</p>
      {body ? <div className="mt-1 max-w-md text-sm text-muted">{body}</div> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border-2 border-current border-t-transparent opacity-70"
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cx("skeleton", className)} />;
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="border-l-2 border-danger py-1 pl-3 text-sm text-danger" role="alert">
      {message}
    </div>
  );
}

export function Notice({
  tone = "neutral",
  icon = "info",
  children,
  className,
}: {
  tone?: "neutral" | "signal" | "petrol" | "danger";
  icon?: IconName;
  children: ReactNode;
  className?: string;
}) {
  const tones = {
    neutral: "border-rule-strong text-muted",
    signal: "border-signal text-ink",
    petrol: "border-petrol text-ink",
    danger: "border-danger text-danger",
  };
  return (
    <div className={cx("flex items-start gap-2.5 border-l-2 py-1.5 pl-3 text-sm", tones[tone], className)}>
      <Icon
        name={icon}
        size={16}
        className={cx("mt-0.5 shrink-0", tone === "signal" && "text-signal", tone === "petrol" && "text-petrol")}
      />
      <div className="min-w-0 leading-relaxed">{children}</div>
    </div>
  );
}

/* --------------------------------------------------------------------- stats */

export function Stat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "neutral" | "signal" | "petrol" | "danger";
}) {
  const accent = {
    neutral: "text-ink",
    signal: "text-signal",
    petrol: "text-petrol",
    danger: "text-danger",
  }[tone];
  return (
    <div className="border-t border-rule pt-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={cx("mt-2 text-3xl font-medium leading-none tabular-nums", accent)}>{value}</p>
      {hint ? <p className="mt-2 text-xs tabular-nums text-muted">{hint}</p> : null}
    </div>
  );
}

/* --------------------------------------------------------------------- table */

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("w-full overflow-x-auto", className)}>
      <table className="w-full border-collapse text-left text-sm [&>tbody>tr:last-child>td]:border-b-0">{children}</table>
    </div>
  );
}

export function Th({
  children,
  sortKey,
  sort,
  order,
  onSort,
  align = "left",
  className,
}: {
  children: ReactNode;
  sortKey?: string;
  sort?: string;
  order?: "asc" | "desc";
  onSort?: (key: string) => void;
  align?: "left" | "right" | "center";
  className?: string;
}) {
  const active = sortKey !== undefined && sort === sortKey;
  const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <th
      scope="col"
      aria-sort={active ? (order === "asc" ? "ascending" : "descending") : undefined}
      className={cx("border-b border-rule px-3 py-2.5 text-xs font-medium text-muted", alignClass, className)}
    >
      {sortKey && onSort ? (
        <button
          type="button"
          onClick={() => onSort(sortKey)}
          className={cx("inline-flex items-center gap-1 hover:text-ink", active && "text-ink")}
        >
          {children}
          <Icon
            name={active && order === "asc" ? "chevron-up" : "chevron-down"}
            size={13}
            className={active ? "text-petrol" : "opacity-40"}
          />
        </button>
      ) : (
        children
      )}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className,
  colSpan,
}: {
  children: ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  colSpan?: number;
}) {
  const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <td colSpan={colSpan} className={cx("border-b border-rule px-3 py-3 align-middle text-ink", alignClass, className)}>
      {children}
    </td>
  );
}

/* -------------------------------------------------------------------- fields */

export const inputClass =
  "w-full rounded-lg border border-rule bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted/60 transition-[border-color,box-shadow] duration-150 ease-out focus:border-petrol focus:ring-2 focus:ring-petrol/15 focus:outline-none";

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
  className,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  htmlFor?: string;
  className?: string;
}) {
  return (
    <div className={cx("block", className)}>
      <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-muted">
        {label}
      </label>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-danger">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(inputClass, className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(inputClass, className)} {...rest}>
      {children}
    </select>
  );
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx(inputClass, "min-h-20 resize-y", className)} {...rest} />;
}

export function Switch({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  description?: ReactNode;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-start justify-between gap-4 rounded-lg bg-surface px-4 py-3 text-left transition-colors duration-150 ease-out hover:bg-surface-2/60"
    >
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink">{label}</span>
        {description ? <span className="mt-0.5 block text-xs text-muted">{description}</span> : null}
      </span>
      <span
        className={cx(
          "relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors duration-150 ease-out",
          checked ? "bg-petrol" : "bg-rule-strong",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-surface shadow-sm transition-transform duration-150 ease-out",
            checked && "translate-x-4",
          )}
        />
      </span>
    </button>
  );
}

/* -------------------------------------------------------------------- dialog */

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  width = "max-w-md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    const previous = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-viewer/50 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cx("dialog-in w-full rounded-2xl bg-surface shadow-2xl outline-none", width)}
      >
        <div className="flex items-start justify-between gap-3 px-5 pt-5">
          <h2 id={titleId} className="text-lg font-semibold text-ink">
            {title}
          </h2>
          <IconButton icon="close" label="Close" onClick={onClose} />
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer ? <div className="flex justify-end gap-2 px-5 pb-5">{footer}</div> : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ expander */

export function Expander({
  title,
  children,
  note,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  note?: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-rule">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 py-2.5 text-left text-sm text-ink hover:text-petrol"
      >
        <span>
          {title}
          {note ? <span className="ml-2 text-xs font-normal text-muted">{note}</span> : null}
        </span>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={16} className="text-muted" />
      </button>
      {open ? <div className="pb-3">{children}</div> : null}
    </div>
  );
}

/* ---------------------------------------------------------------------- tabs */

export function Tabs({
  items,
  value,
  onChange,
  className,
}: {
  items: { id: string; label: string; count?: number }[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div role="tablist" className={cx("flex flex-wrap gap-1 border-b border-rule", className)}>
      {items.map((item) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(item.id)}
            className={cx(
              "-mb-px border-b-2 px-3 py-2 text-sm transition-colors duration-150 ease-out",
              active ? "border-petrol font-medium text-ink" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {item.label}
            {typeof item.count === "number" ? (
              <span className={cx("ml-1.5 font-mono text-xs", active ? "text-petrol" : "text-muted")}>{item.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------- toasts */

type ToastTone = "info" | "success" | "error";
interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

const ToastContext = createContext<((message: string, tone?: ToastTone) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const push = useCallback((message: string, tone: ToastTone = "info") => {
    const id = nextId.current++;
    setItems((current) => [...current.slice(-2), { id, message, tone }]);
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 5000);
  }, []);

  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            role="status"
            className="pointer-events-auto flex items-start gap-2 rounded-xl bg-ink px-3.5 py-3 text-sm text-paper shadow-lg"
          >
            <Icon
              name={item.tone === "error" ? "warn" : item.tone === "success" ? "check" : "info"}
              size={16}
              className={cx(
                "mt-0.5",
                item.tone === "error" ? "text-signal" : item.tone === "success" ? "text-paper" : "text-paper/60",
              )}
            />
            <span className="min-w-0">{item.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): (message: string, tone?: ToastTone) => void {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside ToastProvider");
  return value;
}

/* --------------------------------------------------------------------- utils */

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDay(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  if (seconds < 86400 * 7) return `${Math.floor(seconds / 86400)} d ago`;
  return formatDay(value);
}

export function shortDigest(value: string | null | undefined, length = 12): string {
  if (!value) return "—";
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes < 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

const LABEL_FIXES: Record<string, string> = { xray: "X-ray", ct: "CT", mri: "MRI" };

export function prettyLabel(label: string): string {
  const text = label.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  return LABEL_FIXES[text.toLowerCase()] ?? text;
}
