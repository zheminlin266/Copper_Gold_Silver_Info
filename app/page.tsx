import { WeeklyReportView } from "@/components/weekly-report";
import { getWeeklyReport, getWeeklyStarts } from "@/lib/weekly-reports";

export default function HomePage() {
  const latest = getWeeklyReport(getWeeklyStarts()[0]);
  if (!latest) throw new Error("The homepage needs a published weekly report.");
  return <WeeklyReportView isHome report={latest} />;
}
