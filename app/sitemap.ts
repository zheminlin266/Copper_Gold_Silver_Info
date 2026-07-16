import type { MetadataRoute } from "next";

import { getReports } from "@/lib/reports";
import { SITE_URL } from "@/lib/site";

function reportLastModified(date: string, reportTime: string): Date {
  const parsed = new Date(reportTime);
  return Number.isNaN(parsed.getTime())
    ? new Date(`${date}T00:00:00+08:00`)
    : parsed;
}

export default function sitemap(): MetadataRoute.Sitemap {
  const reports = getReports();
  const newestReport = reports[0];

  return [
    {
      url: SITE_URL,
      lastModified: newestReport
        ? reportLastModified(newestReport.date, newestReport.report_time)
        : new Date(),
    },
    {
      url: `${SITE_URL}/archive`,
      lastModified: newestReport
        ? reportLastModified(newestReport.date, newestReport.report_time)
        : new Date(),
    },
    ...reports.map((report) => ({
      url: `${SITE_URL}/daily/${report.date}`,
      lastModified: reportLastModified(report.date, report.report_time),
    })),
  ];
}
