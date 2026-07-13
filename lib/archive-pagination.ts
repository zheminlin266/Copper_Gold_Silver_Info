export const REPORTS_PER_PAGE = 20;

export function getArchivePage<T>(items: T[], requestedPage: number) {
  const pageCount = Math.max(1, Math.ceil(items.length / REPORTS_PER_PAGE));
  const page = Math.min(Math.max(1, requestedPage), pageCount);
  const start = (page - 1) * REPORTS_PER_PAGE;

  return {
    items: items.slice(start, start + REPORTS_PER_PAGE),
    page,
    pageCount,
  };
}
