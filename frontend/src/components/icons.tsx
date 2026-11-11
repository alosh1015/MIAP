import type { SVGProps } from "react";

/*
 * One inline sprite, rendered once at the app root. Every icon is a 24px
 * stroke drawing at 1.5px, monochrome via currentColor. Paths follow the
 * mockups; no icon package is loaded.
 */
const ICONS = {
  worklist: <path d="M4 6h2M4 12h2M4 18h2M9 6h11M9 12h11M9 18h11" />,
  "new-study": (
    <path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4M12 9v6M9 12h6" />
  ),
  models: <path d="M12 4 4 8l8 4 8-4-8-4ZM4 12l8 4 8-4M4 16l8 4 8-4" />,
  level: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4v16a8 8 0 0 0 0-16Z" fill="currentColor" stroke="none" />
    </>
  ),
  pan: <path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3" />,
  zoom: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.5 4.5M11 8.5v5M8.5 11h5" />
    </>
  ),
  measure: <path d="m4 16 12-12 4 4L8 20l-4-4ZM8 12l2 2M11 9l2 2M14 6l2 2" />,
  lasso: (
    <>
      <path d="M4.5 12c0-4 3.4-7 7.5-7s7.5 2.6 7.5 6.5c0 3.1-2.5 5.5-5.8 5.5-1.7 0-3.1-.6-4.2-1.6M4.5 12c0 1.8 1 3.3 2.7 4.4M12.5 19l6 3" strokeDasharray="2.5 2.5" />
      <circle cx="12.5" cy="19" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  reset: <path d="M4 12a8 8 0 1 0 2.5-5.8M4 4v4h4" />,
  heat: (
    <>
      <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="9.5" strokeDasharray="2 3" />
    </>
  ),
  pdf: <path d="M6 3h8l4 4v14H6V3ZM14 3v4h4M9 13h6M9 17h6" />,
  shield: (
    <>
      <path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6l-7-3Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  warn: <path d="M12 4 3 19h18L12 4ZM12 10v4M12 16.5v.5" />,
  dashboard: <path d="M4 11l8-7 8 7M6 10v10h12V10M10 20v-6h4v6" />,
  settings: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </>
  ),
  users: (
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
  ),
  user: <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />,
  health: <path d="M3 12h4l2-6 3 12 2-6h7" />,
  audit: (
    <path d="M9 4H6a1 1 0 0 0-1 1v15a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1h-3M9 4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2H9V4ZM9 12h6M9 16h6" />
  ),
  retention: <path d="M4 7h16M4 7v12a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V7M4 7l1.5-3h13L20 7M10 11h4" />,
  "chevron-down": <path d="m6 9 6 6 6-6" />,
  "chevron-up": <path d="m6 15 6-6 6 6" />,
  "chevron-left": <path d="m14 6-6 6 6 6" />,
  "chevron-right": <path d="m10 6 6 6-6 6" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  check: <path d="m5 13 4 4 10-11" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  filter: <path d="M4 6h16l-6 7v6l-4 2v-8L4 6Z" />,
  split: <path d="M4 5h16v14H4V5ZM12 3v18M8 12h8" />,
  fullscreen: <path d="M8 4H4v4M16 4h4v4M8 20H4v-4M16 20h4v-4" />,
  opacity: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5" />
    </>
  ),
  moon: <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z" />,
  monitor: <path d="M4 5h16v11H4V5ZM9 20h6M12 16v4" />,
  logout: <path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 8l-4 4 4 4M6 12h10" />,
  upload: <path d="M12 16V4M8 8l4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />,
  download: <path d="M12 4v12M8 12l4 4 4-4M4 19h16" />,
  plus: <path d="M12 5v14M5 12h14" />,
  link: <path d="M10 14a4 4 0 0 0 6 .5l2-2a4 4 0 0 0-5.5-5.5l-1 1M14 10a4 4 0 0 0-6-.5l-2 2a4 4 0 0 0 5.5 5.5l1-1" />,
  "arrow-left": <path d="M19 12H5M11 6l-6 6 6 6" />,
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  eye: (
    <>
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  "eye-off": <path d="M3 3l18 18M10.6 6.2A10 10 0 0 1 22 12s-1.2 2-3.3 3.7M6.2 6.9C3.6 8.6 2 12 2 12s3.5 6 10 6c1.4 0 2.7-.3 3.9-.8" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5M12 8v.5" />
    </>
  ),
  lock: <path d="M6 11h12v9H6v-9ZM9 11V8a3 3 0 0 1 6 0v3" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
  folder: <path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z" />,
  image: (
    <>
      <path d="M4 5h16v14H4V5ZM4 15l4-4 4 4 3-3 5 5" />
      <circle cx="9" cy="9" r="1.3" />
    </>
  ),
  flag: <path d="M5 21V4c4-2 8 2 12 0v9c-4 2-8-2-12 0" />,
  database: <path d="M12 7c4.4 0 8-1.3 8-3s-3.6-3-8-3-8 1.3-8 3 3.6 3 8 3ZM4 4v16c0 1.7 3.6 3 8 3s8-1.3 8-3V4M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />,
  beaker: <path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3" />,
  bolt: <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />,
} as const;

export type IconName = keyof typeof ICONS;

export function IconSprite() {
  return (
    <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}>
      {Object.entries(ICONS).map(([name, paths]) => (
        <symbol
          key={name}
          id={`i-${name}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {paths}
        </symbol>
      ))}
    </svg>
  );
}

export function Icon({
  name,
  size = 20,
  className = "",
  ...rest
}: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      aria-hidden="true"
      className={`shrink-0 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      <use href={`#i-${name}`} />
    </svg>
  );
}

/** Brand mark: an aperture ring around an M whose middle vertex is the finding. */
export function Logo({ size = 40, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 44 44"
      className={className}
      role="img"
      aria-label="MIAP"
    >
      <circle
        cx="22"
        cy="22"
        r="19"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeDasharray="88 31"
        strokeLinecap="round"
        transform="rotate(-70 22 22)"
      />
      <path
        d="M13 29V15l9 10 9-10v14"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="22" cy="25" r="3" fill="var(--signal)" />
    </svg>
  );
}
