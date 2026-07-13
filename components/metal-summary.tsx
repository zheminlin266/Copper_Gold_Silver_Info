import type { DailyReport, Metal } from "@/lib/report-types";
import { getReportStats, metalLabel, METALS } from "@/lib/reports";

export function MetalSummary({ report }: { report: DailyReport }) {
  const counts = getReportStats(report).metalCounts;

  return (
    <div className="metal-summary" aria-label="各金属信号数量">
      {METALS.map((metal: Metal) => (
        <a className={`metal-summary__item metal--${metal}`} href={`#${metal}`} key={metal}>
          <span>{metalLabel(metal)}</span>
          <strong>{counts[metal]}</strong>
          <small>条信号</small>
        </a>
      ))}
    </div>
  );
}
