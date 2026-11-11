# Vendored fonts

All files are latin-subset WOFF2, served from this directory at build time so
the app never calls Google Fonts at runtime (offline LAN deployments, no
third-party request carrying usage metadata).

| File | Family | Weight | Copyright |
|---|---|---|---|
| `schibsted-400.woff2`, `schibsted-500.woff2`, `schibsted-600.woff2` | Schibsted Grotesk | 400, 500, 600 | Copyright 2022 The Schibsted Grotesk Project Authors (https://github.com/schibsted/schibsted-grotesk) |
| `jetbrains-400.woff2` | JetBrains Mono | 400 | Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono) |
| `newsreader-500.woff2`, `newsreader-600.woff2` | Newsreader | 500, 600 | Copyright 2020 The Newsreader Project Authors (https://github.com/productiontype/Newsreader) |

The interface uses Schibsted Grotesk for text and JetBrains Mono for
identifiers. The Newsreader files are retained under the same licence but are
no longer referenced by `src/index.css`; the serif display face was dropped in
the 2026-11-10 interface pass.

All three families are licensed under the SIL Open Font License 1.1; the full
licence text is in `OFL-1.1.txt` and the JetBrains copy is retained verbatim in
`OFL-JetBrainsMono.txt`.

Source: `fonts.gstatic.com` via the Google Fonts CSS API (`css2`), accessed
2026-11-10. Redistribution is permitted by the OFL; the fonts are unmodified
subsets as served by Google.
