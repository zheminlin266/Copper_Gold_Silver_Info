"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import type { Metal, ReportSummary } from "@/lib/report-types";

export function ArchiveList({ reports }: { reports: ReportSummary[] }) {
  const [query, setQuery] = useState("");
  const [metal, setMetal] = useState<Metal | "all">("all");

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

  return (
    <div>
      <div className="archive-controls">
        <label>
          <span>搜索日报</span>
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="公司、项目、关键词"
            type="search"
            value={query}
          />
        </label>
        <label>
          <span>金属</span>
          <select
            onChange={(event) => setMetal(event.target.value as Metal | "all")}
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
      </p>

      {filtered.length ? (
        <div className="archive-list">
          {filtered.map((report) => (
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
      ) : (
        <p className="empty-state">没有符合条件的日报，请更换关键词或金属筛选。</p>
      )}
    </div>
  );
}
