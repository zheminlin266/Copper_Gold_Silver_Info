const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATE_TIME_WITH_ZONE = /^(\d{4}-\d{2}-\d{2})T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?(?:Z|[+-](?:[01]\d|2[0-3]):?[0-5]\d)$/;
const MIN_REPORT_TIME = Number.MIN_SAFE_INTEGER;

function isCalendarDate(value: string): boolean {
  const match = DATE_ONLY.exec(value);
  if (!match) return false;
  const [, year, month, day] = match.map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

export function parseReportTime(value: unknown): number {
  if (typeof value !== "string") return MIN_REPORT_TIME;

  const dateOnly = DATE_ONLY.exec(value);
  if (dateOnly) {
    if (!isCalendarDate(value)) return MIN_REPORT_TIME;
    return Date.parse(`${value}T00:00:00+08:00`);
  }

  if (!DATE_TIME_WITH_ZONE.test(value)) return MIN_REPORT_TIME;
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? MIN_REPORT_TIME : timestamp;
}

export function compareReportTimesDesc(left: string, right: string): number {
  return parseReportTime(right) - parseReportTime(left);
}
