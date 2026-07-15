import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { MetalSummary } from "@/components/metal-summary";
import { MetricStrip } from "@/components/metric-strip";
import { ReportAudit } from "@/components/report-audit";
import { SignalCard } from "@/components/signal-card";
import type { Metal } from "@/lib/report-types";
import {
  formatDate,
  formatDateTime,
  getAdjacentReports,
  getReportByDate,
  getReports,
  getReportSummary,
  getSignals,
  metalLabel,
  METALS,
} from "@/lib/reports";

type DailyPageProps = { params: Promise<{ date: string }> };

export function generateStaticParams() {
  return getReports().map((report) => ({ date: report.date }));
}

export async function generateMetadata({ params }: DailyPageProps): Promise<Metadata> {
  const { date } = await params;
  const report = getReportByDate(date);
  if (!report) return { title: "日报不存在" };
  return {
    title: `${formatDate(report.date)} 矿业供需信号`,
    description: getReportSummary(report).slice(0, 150),
  };
}

export default async function DailyPage({ params }: DailyPageProps) {
  const { date } = await params;
  const report = getReportByDate(date);
  if (!report) notFound();

  const signals = getSignals(report);
  const adjacent = getAdjacentReports(report.date);

  return (
    <main className="site-main">
      <article className="article-copy">
        <header className="page-intro">
          <p className="eyebrow">Daily Report</p>
          <h1>{formatDate(report.date)} 矿业供需信号</h1>
          <p className="meta-copy">
            生成于 {formatDateTime(report.report_time)} · 北京时间
          </p>
          <p className="lead-copy">{getReportSummary(report)}</p>
        </header>

        <MetricStrip report={report} />
        <MetalSummary report={report} />

        <nav className="article-nav" aria-label="日报内导航">
          {METALS.map((metal) => (
            <a href={`#${metal}`} key={metal}>
              {metalLabel(metal)}
            </a>
          ))}
          <a href="#audit">来源审计</a>
        </nav>

        <section className="content-section" aria-labelledby="signals-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Supply &amp; Demand</p>
              <h2 id="signals-heading">本期信号</h2>
            </div>
          </div>

          {signals.length ? (
            METALS.map((metal: Metal) => {
              const metalSignals = signals.filter(
                (signal) => signal.primaryMetal === metal,
              );
              return (
                <section className="metal-section" id={metal} key={metal}>
                  <div className="metal-section__heading">
                    <h3>{metalLabel(metal)}</h3>
                    <span>{metalSignals.length} 条</span>
                  </div>
                  {metalSignals.length ? (
                    metalSignals.map((signal) => (
                      <SignalCard key={signal.id} signal={signal} />
                    ))
                  ) : (
                    <p className="empty-copy">本期没有该金属的新增合格信号。</p>
                  )}
                </section>
              );
            })
          ) : (
            <p className="empty-state">本期没有符合筛选标准的新增信号。</p>
          )}
        </section>

        <section className="content-section" id="audit" aria-labelledby="audit-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Methodology</p>
              <h2 id="audit-heading">来源与审计</h2>
            </div>
          </div>
          <ReportAudit report={report} />
        </section>

        <nav className="report-pagination" aria-label="相邻日报">
          {adjacent.older ? (
            <Link href={`/daily/${adjacent.older.date}`}>
              <span>上一篇</span>
              <strong>{adjacent.older.date}</strong>
            </Link>
          ) : (
            <span />
          )}
          {adjacent.newer ? (
            <Link href={`/daily/${adjacent.newer.date}`}>
              <span>下一篇</span>
              <strong>{adjacent.newer.date}</strong>
            </Link>
          ) : (
            <Link href="/">
              <span>返回</span>
              <strong>最新首页</strong>
            </Link>
          )}
        </nav>
      </article>
    </main>
  );
}
