import type { DailyReport } from "@/lib/report-types";

function SourceList({ items }: { items?: string[] }) {
  if (!items?.length) return <p className="empty-copy">无记录</p>;
  return (
    <ul>
      {items.map((item, index) => (
        <li key={`${index}-${item}`}>{item}</li>
      ))}
    </ul>
  );
}

export function ReportAudit({ report }: { report: DailyReport }) {
  const deduped = [
    ...(report.dedup_log.part1_deduped_urls || []),
    ...(report.dedup_log.part3_deduped_events || []),
  ];

  return (
    <details className="audit-panel">
      <summary>搜索覆盖与去重记录</summary>
      <div className="audit-panel__body">
        <h3>访谈与播客</h3>
        <SourceList items={report.search_log.part1_sources_checked} />
        {report.search_log.part1_result && <p>{report.search_log.part1_result}</p>}

        <h3>X 原帖</h3>
        <SourceList items={report.search_log.part2_sources_checked} />
        {report.search_log.part2_result && <p>{report.search_log.part2_result}</p>}

        <h3>新闻来源</h3>
        <SourceList items={report.search_log.part3_sources_checked} />
        {report.search_log.part3_result && <p>{report.search_log.part3_result}</p>}

        <h3>去重</h3>
        <SourceList items={deduped} />
      </div>
    </details>
  );
}
