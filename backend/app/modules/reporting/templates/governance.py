from __future__ import annotations

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from .common import facts_table, findings_table, format_stamp, styles


def _human_bytes(value: int) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def render(ctx: dict, report_id: str) -> list:
    style = styles()
    period = ctx.get("period") or {}
    health = ctx.get("health") or {}
    audit = health.get("audit") or {}
    storage = health.get("storage") or {}
    cases = health.get("cases") or {}
    accounts = ctx.get("accounts") or {}
    approvals = ctx.get("approvals") or []
    retention_runs = ctx.get("retention_runs") or []

    story = [
        Paragraph("Governance report", style["title"]),
        Paragraph(
            f"Reporting period {period.get('from', 'n/a')} to {period.get('to', 'n/a')} · "
            f"{ctx['generated_at']}",
            style["subtitle"],
        ),
        Paragraph(
            "Governance summary for administrators. This report intentionally contains "
            "no patient identity, no images, and no clinical findings.",
            style["small"],
        ),
        Spacer(1, 4 * mm),
    ]

    story.append(Paragraph("Accounts", style["heading"]))
    role_rows = [
        [str(role).capitalize(), str(counts.get("active", 0)), str(counts.get("total", 0))]
        for role, counts in sorted(accounts.items())
    ]
    story.append(
        findings_table(
            [[row[0], row[1], row[2]] for row in role_rows],
            [60, 40, 40],
            ["Role", "Active", "Total"],
        )
    )
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Audit chain", style["heading"]))
    chain_rows = [
        ["Status", "Verified" if audit.get("ok") else "Verification failed"],
        ["Events checked", str(audit.get("checked", 0))],
        ["First failing sequence", str(audit.get("first_bad_seq")) if audit.get("first_bad_seq") else "None"],
        ["Schema version", str((health.get("database") or {}).get("schema_version", "n/a"))],
    ]
    story += [facts_table(chain_rows, style), Spacer(1, 5 * mm)]

    story.append(Paragraph("Model approvals", style["heading"]))
    if approvals:
        rows = [
            [
                f"{item.get('model_id')} {item.get('version')}",
                str(item.get("decision", "")).capitalize(),
                format_stamp(item.get("decided_at")),
                (item.get("benchmark_digest") or "no benchmark")[:24],
            ]
            for item in approvals
        ]
        story.append(
            findings_table(rows, [58, 24, 42, 36], ["Model", "Decision", "Decided", "Benchmark"])
        )
    else:
        story.append(Paragraph("No approval decisions have been recorded.", style["body"]))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Retention runs", style["heading"]))
    if retention_runs:
        rows = [
            [
                format_stamp(item.get("ts")),
                str((item.get("detail") or {}).get("archived_cases", 0)),
                str((item.get("detail") or {}).get("deleted_images", 0)),
                _human_bytes(int((item.get("detail") or {}).get("bytes_freed", 0))),
            ]
            for item in retention_runs
        ]
        story.append(
            findings_table(rows, [52, 32, 32, 44], ["When", "Cases archived", "Images deleted", "Freed"])
        )
    else:
        story.append(Paragraph("No retention runs in this period.", style["body"]))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("Storage", style["heading"]))
    storage_rows = [
        ["Cases", f"{cases.get('total', 0)} total · {cases.get('archived', 0)} archived"],
        ["Cases due for retention", str(cases.get("due_for_retention", 0))],
        ["Results stored", str((health.get("results") or {}).get("total", 0))],
        ["Data directory", _human_bytes(int(storage.get("data_size_bytes", 0)))],
        ["Free disk", _human_bytes(int(storage.get("free_bytes", 0)))],
    ]
    story += [facts_table(storage_rows, style), Spacer(1, 5 * mm)]

    story += [
        Paragraph(
            "Governance reports are generated on request and written to the audit "
            f"chain. Report {report_id}. The stored JSON database is canonical.",
            style["small"],
        )
    ]
    return story
