import type { DailyReport } from "@/lib/report-types";
import { formatDate, getReportStats } from "@/lib/reports";

export function MetricStrip({ report }: { report: DailyReport }) {
  const stats = getReportStats(report);
  const metrics = [
    { label: "报告日期", value: formatDate(report.date) },
    { label: "合格信号", value: `${stats.total} 条` },
    { label: "供给 / 需求", value: `${stats.supply} / ${stats.demand}` },
    { label: "检查来源", value: `${stats.sourceChecks} 个` },
  ];

  return (
    <dl className="metric-strip" aria-label="本期信息概览">
      {metrics.map((metric) => (
        <div className="metric" key={metric.label}>
          <dt>{metric.label}</dt>
          <dd>{metric.value}</dd>
        </div>
      ))}
    </dl>
  );
}
