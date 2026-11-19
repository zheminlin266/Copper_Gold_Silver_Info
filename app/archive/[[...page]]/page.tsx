import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ArchiveList } from "@/components/archive-list";
import { archivePagePath, getArchivePage } from "@/lib/archive-pagination";
import { getReports, getReportSummaries } from "@/lib/reports";
import { getWeeklyReport, getWeeklyStarts, weeklyPath, weeklyPeriod } from "@/lib/weekly-reports";

type ArchiveProps = { params: Promise<{ page?: string[] }> };

export const dynamicParams = false;

export function generateStaticParams() {
  const { pageCount } = getArchivePage(getReports(), 1);
  return Array.from({ length: pageCount }, (_, index) => ({
    page: index === 0 ? [] : [String(index + 1)],
  }));
}

function pageNumber(segments: string[] = []) {
  if (!segments.length) return 1;
  if (segments.length !== 1 || !/^[1-9]\d*$/.test(segments[0])) notFound();
  const page = Number(segments[0]);
  if (!Number.isSafeInteger(page) || page < 2) notFound();
  return page;
}

export async function generateMetadata({ params }: ArchiveProps): Promise<Metadata> {
  const page = pageNumber((await params).page);
  return {
    title: page === 1 ? "报告归档" : `日报归档 · 第 ${page} 页`,
    description: "查阅历期铜矿供给周报，并按日期、关键词或金属检索历史日报。",
    alternates: { canonical: archivePagePath(page) },
  };
}

export default async function ArchivePage({ params }: ArchiveProps) {
  const page = pageNumber((await params).page);
  const reports = getReportSummaries();
  if (getArchivePage(reports, page).page !== page) notFound();
  const weeklies = page === 1 ? getWeeklyStarts().map(getWeeklyReport) : [];
  return (
    <main className="site-main">
      <div className="article-copy">
        <header className="page-intro page-intro--compact">
          <p className="eyebrow">Archive</p>
          <h1>报告归档</h1>
          {page === 1 && (
            <nav aria-label="归档目录" className="article-nav">
              <a href="#weekly-archive">历期周报</a>
              <a href="#daily-archive">历史日报</a>
            </nav>
          )}
        </header>
        {page === 1 && (
          <section className="content-section" id="weekly-archive" aria-labelledby="weekly-archive-heading">
            <div className="section-heading"><h2 id="weekly-archive-heading">历期周报</h2></div>
            <div className="recent-list">
              {weeklies.map((report) => report && (
                <Link className="recent-item" href={weeklyPath(report.week_start)} key={report.week_start}>
                  {weeklyPeriod(report)}
                </Link>
              ))}
            </div>
          </section>
        )}
        <section className="content-section" id="daily-archive" aria-labelledby="daily-archive-heading">
          <div className="section-heading"><h2 id="daily-archive-heading">历史日报</h2></div>
          <ArchiveList reports={reports} initialPage={page} />
        </section>
      </div>
    </main>
  );
}
