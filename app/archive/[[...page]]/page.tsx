import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ArchiveList } from "@/components/archive-list";
import { archivePagePath, getArchivePage } from "@/lib/archive-pagination";
import { getReports, getReportSummaries } from "@/lib/reports";

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
    title: page === 1 ? "日报归档" : `日报归档 · 第 ${page} 页`,
    description: "按日期、关键词和金属检索历史矿业供需日报。",
    alternates: { canonical: archivePagePath(page) },
  };
}

export default async function ArchivePage({ params }: ArchiveProps) {
  const page = pageNumber((await params).page);
  const reports = getReportSummaries();
  if (getArchivePage(reports, page).page !== page) notFound();
  return (
    <main className="site-main">
      <div className="article-copy">
        <header className="page-intro page-intro--compact">
          <p className="eyebrow">Archive</p>
          <h1>日报归档</h1>
          <p className="lead-copy">按日期、关键词或金属查找历史供需信号。</p>
        </header>
        <ArchiveList reports={reports} initialPage={page} />
      </div>
    </main>
  );
}
