"""Entry point for python -m bot.reports."""

import os
from bot.reports.build import ReportBuilder

if __name__ == "__main__":
    builder = ReportBuilder()
    builder.build_all_reports()
    abs_index = os.path.abspath(os.path.join(builder.out_dir, "index.html"))
    print("\n" + "=" * 65)
    print("📊 AUTONOMOUS AI TRADING AGENTS: REPORT BUILD COMPLETE")
    print("=" * 65)
    print(f"• Generated 6 strategy reports + dashboard in: {builder.out_dir}/")
    print(f"• Open in browser: file://{abs_index}")
    print("=" * 65 + "\n")
