"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { getArchivePage } from "@/lib/archive-pagination";
import type { Metal, ReportSummary } from "@/lib/report-types";

export function ArchiveList({ reports }: { reports: ReportSummary[] }) {
  const [query, setQuery] = useState("");
  const [metal, setMetal] = useState<Metal | "all">("all");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return reports.filter((report) => {
      const matchesText =
        !normalized ||
        report.searchText.toLocaleLowerCase().includes(normalized);
      const matchesMetal = metal === "all" || report.stats.metalCounts[metal] > 0;
      return matchesText && matchesMetal;
    });
  }, [metal, query, reports]);

  const current = getArchivePage(filtered, page);

  function updateQuery(value: string) {
    setQuery(value);
    setPage(1);
  }

  function updateMetal(value: Metal | "all") {
    setMetal(value);
    setPage(1);
  }

  return (
    <div>
      <div className="archive-controls">
        <label>
          <span>搜索日报</span>
          <input
            onChange={(event) => updateQuery(event.target.value)}
            placeholder="公司、项目、关键词"
            type="search"
            value={query}
          />
        </label>
        <label>
          <span>金属</span>
          <select
            onChange={(event) => updateMetal(event.target.value as Metal | "all")}
            value={metal}
          >
            <option value="all">全部</option>
            <option value="gold">黄金</option>
            <option value="silver">白银</option>
            <option value="copper">铜</option>
          </select>
        </label>
      </div>

      <p className="archive-count meta-copy" aria-live="polite">
        共 {filtered.length} 期
        {current.pageCount > 1 ? ` · 第 ${current.page} / ${current.pageCount} 页` : ""}
      </p>

      {filtered.length ? (
        <>
          <div className="archive-list">
            {current.items.map((report) => (
              <article className="archive-item" key={report.date}>
                <div className="archive-item__topline">
                  <Link href={`/daily/${report.date}`}>{report.date}</Link>
                  <span>{report.stats.total} 条信号</span>
                </div>
                <p>{report.summary}</p>
                <div className="archive-item__counts" aria-label="金属信号数量">
                  <span>金 {report.stats.metalCounts.gold}</span>
                  <span>银 {report.stats.metalCounts.silver}</span>
                  <span>铜 {report.stats.metalCounts.copper}</span>
                </div>
              </article>
            ))}
          </div>

          {current.pageCount > 1 ? (
            <nav className="archive-pagination" aria-label="日报分页">
              <button
                disabled={current.page === 1}
                onClick={() => setPage(current.page - 1)}
                type="button"
              >
                上一页
                <span>较新的日报</span>
              </button>
              <p aria-live="polite">
                第 <strong>{current.page}</strong> 页，共 {current.pageCount} 页
              </p>
              <button
                disabled={current.page === current.pageCount}
                onClick={() => setPage(current.page + 1)}
                type="button"
              >
                下一页
                <span>更早的日报</span>
              </button>
            </nav>
          ) : null}
        </>
      ) : (
        <p className="empty-state">没有符合条件的日报，请更换关键词或金属筛选。</p>
      )}
    </div>
  );
}
