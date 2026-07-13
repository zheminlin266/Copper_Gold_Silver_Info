import Link from "next/link";

import { MetalSummary } from "@/components/metal-summary";
import { MetricStrip } from "@/components/metric-strip";
import { SignalCard } from "@/components/signal-card";
import type { Metal } from "@/lib/report-types";
import {
  formatDate,
  formatDateTime,
  getReports,
  getReportStats,
  getReportSummary,
  getSignals,
  metalLabel,
  METALS,
} from "@/lib/reports";

export default function HomePage() {
  const reports = getReports();
  const latest = reports[0];
  const signals = getSignals(latest);
  const stats = getReportStats(latest);

  return (
    <main className="site-main">
      <div className="article-copy">
        <header className="page-intro">
          <p className="eyebrow">Gold · Silver · Copper</p>
          <h1>{formatDate(latest.date)} 矿业供需信号</h1>
          <p className="meta-copy">更新于 {formatDateTime(latest.report_time)} · 北京时间</p>
          <p className="lead-copy">{getReportSummary(latest)}</p>
        </header>

        <MetricStrip report={latest} />
        <MetalSummary report={latest} />

        <section className="content-section" aria-labelledby="latest-signals">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Latest Signals</p>
              <h2 id="latest-signals">今日关键信号</h2>
            </div>
            <Link href={`/daily/${latest.date}`}>完整日报</Link>
          </div>

          {signals.length ? (
            METALS.map((metal: Metal) => {
              const metalSignals = signals.filter(
                (signal) => signal.metalTags.includes(metal),
              );
              if (!metalSignals.length) return null;
              return (
                <section className="metal-section" id={metal} key={metal}>
                  <div className="metal-section__heading">
                    <h3>{metalLabel(metal)}</h3>
                    <span>{metalSignals.length} 条</span>
                  </div>
                  {metalSignals.map((signal) => (
                    <SignalCard key={signal.id} signal={signal} />
                  ))}
                </section>
              );
            })
          ) : (
            <p className="empty-state">本期没有符合筛选标准的新增信号。</p>
          )}
        </section>

        <section className="content-section" aria-labelledby="recent-reports">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Archive</p>
              <h2 id="recent-reports">最近日报</h2>
            </div>
            <Link href="/archive">查看全部</Link>
          </div>
          <div className="recent-list">
            {reports.slice(0, 6).map((report) => {
              const reportStats = getReportStats(report);
              return (
                <Link className="recent-item" href={`/daily/${report.date}`} key={report.date}>
                  <span>{report.date}</span>
                  <span>{reportStats.total} 条信号</span>
                </Link>
              );
            })}
          </div>
        </section>

        <footer className="page-footer">
          <p>研究信息与公开来源整理，不构成投资建议。</p>
          <p>本期共收录 {stats.total} 条合格供需信号。</p>
        </footer>
      </div>
    </main>
  );
}
