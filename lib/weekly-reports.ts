import fs from "node:fs";
import path from "node:path";

export type SourcedFact = {
  id: string;
  date: string;
  title: string;
  fact: string;
  sources: { name: string; url: string }[];
};

export type WeeklyReport = {
  week_start: string;
  week_end: string;
  generated_at: string;
  coverage: string[];
  copper_events: SourcedFact[];
  supply_analysis: { title: string; text: string; event_ids: string[] }[];
  gold_briefs: SourcedFact[];
};

const WEEK_FILE = /^(\d{4}-\d{2}-\d{2})\.json$/;
const WEEKLY_DIR = path.join(process.cwd(), "data", "weekly");

export function getWeeklyStarts() {
  return fs.readdirSync(WEEKLY_DIR)
    .filter((filename) => WEEK_FILE.test(filename))
    .sort()
    .reverse()
    .map((filename) => filename.slice(0, -5));
}

export function getWeeklyReport(weekStart: string): WeeklyReport | undefined {
  const filename = `${weekStart}.json`;
  if (!WEEK_FILE.test(filename)) return undefined;
  try {
    return JSON.parse(fs.readFileSync(path.join(WEEKLY_DIR, filename), "utf8")) as WeeklyReport;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

export function weeklyPath(weekStart: string) {
  return `/weekly/${weekStart}`;
}

export function weeklyPeriod(report: WeeklyReport) {
  return `${report.week_start} – ${report.week_end}`;
}
