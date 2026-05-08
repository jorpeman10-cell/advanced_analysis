#!/usr/bin/env python
"""Run the v2 data support audit and write reports to reports/."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from modules.data_audit import AuditConfig, DataSupportAuditor, render_markdown_report


def main() -> None:
    import db_config_manager
    from gllue_db_client import GllueDBClient

    if not db_config_manager.has_config():
        raise SystemExit("Database config is missing. Configure DB connection in the app first.")

    config = AuditConfig.default()
    db_client = GllueDBClient(db_config_manager.get_gllue_db_config())
    auditor = DataSupportAuditor(db_client, config)
    reports = auditor.run()

    out_dir = Path(__file__).parent / "reports"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for name, df in reports.items():
        df.to_csv(out_dir / f"data_audit_{name}_{stamp}.csv", index=False, encoding="utf-8-sig")

    markdown = render_markdown_report(reports, config)
    md_path = out_dir / f"data_support_audit_{stamp}.md"
    md_path.write_text(markdown, encoding="utf-8")

    readiness = reports["metric_readiness"]
    print("\nData Support Audit complete")
    print(f"Report: {md_path}")
    print("\nMetric readiness:")
    for _, row in readiness.iterrows():
        print(
            f"- {row['metric']}: {row['confidence']} "
            f"({row['support_score_display']}) -> {row['decision']}"
        )

    db_client.close()


if __name__ == "__main__":
    main()

