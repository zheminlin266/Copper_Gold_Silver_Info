import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { SiteHeader } from "@/components/site-header";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: {
    default: "金银铜供需信息",
    template: "%s · 金银铜供需信息",
  },
  description: "黄金、白银与铜的矿业供需信号每日跟踪。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className={inter.variable}>
      <body>
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
