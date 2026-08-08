import type { Metadata } from "next";
import localFont from "next/font/local";
import { Analytics } from "@vercel/analytics/next";

import { SiteHeader } from "@/components/site-header";
import { SITE_URL } from "@/lib/site";

import "./globals.css";

const localSans = localFont({
  src: "../assets/fonts/Geist-Regular.ttf",
  display: "swap",
  variable: "--font-local-sans",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "金银铜供需信息",
    template: "%s · 金银铜供需信息",
  },
  description: "黄金、白银与铜的矿业供需信号每日跟踪。",
  alternates: {
    canonical: "/",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className={localSans.variable}>
      <body id="top">
        <SiteHeader />
        {children}
        <footer className="site-footer">
          <a className="back-to-top" href="#top">
            返回顶部 <span aria-hidden="true">↑</span>
          </a>
        </footer>
        <Analytics />
      </body>
    </html>
  );
}
