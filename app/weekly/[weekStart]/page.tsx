import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { WeeklyReportView } from "@/components/weekly-report";
import { getWeeklyReport, getWeeklyStarts, weeklyPath, weeklyPeriod } from "@/lib/weekly-reports";

type WeeklyPageProps = { params: Promise<{ weekStart: string }> };

export const dynamicParams = false;

export function generateStaticParams() {
  return getWeeklyStarts().map((weekStart) => ({ weekStart }));
}

export async function generateMetadata({ params }: WeeklyPageProps): Promise<Metadata> {
  const { weekStart } = await params;
  const report = getWeeklyReport(weekStart);
  if (!report) notFound();

  return {
    title: `铜矿供给周报 ${weeklyPeriod(report)}`,
    alternates: { canonical: weeklyPath(weekStart) },
  };
}

export default async function WeeklyPage({ params }: WeeklyPageProps) {
  const report = getWeeklyReport((await params).weekStart);
  if (!report) notFound();
  return <WeeklyReportView report={report} />;
}
