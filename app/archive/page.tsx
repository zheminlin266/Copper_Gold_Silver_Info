import type { Metadata } from "next";

import { ArchiveList } from "@/components/archive-list";
import { getReportSummaries } from "@/lib/reports";

export const metadata: Metadata = {
  title: "日报归档",
  description: "按日期、关键词和金属检索历史矿业供需日报。",
  alternates: {
    canonical: "/archive",
  },
};

export default function ArchivePage() {
  return (
    <main className="site-main">
      <div className="article-copy">
        <header className="page-intro page-intro--compact">
          <p className="eyebrow">Archive</p>
          <h1>日报归档</h1>
          <p className="lead-copy">按日期、关键词或金属查找历史供需信号。</p>
        </header>
        <ArchiveList reports={getReportSummaries()} />
      </div>
    </main>
  );
}
