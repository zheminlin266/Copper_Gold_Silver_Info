"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import miningNewsLogo from "@/Sources/mining_news_logo.png";

const INVENTORY_URL = "https://sc.macromicro.me/charts/40914/tong-ku-cun-jia-ge";
const TC_URL = "https://www.metal.com/copper/201910240001";

export function SiteHeader() {
  const [isHidden, setIsHidden] = useState(false);
  const lastScrollY = useRef(0);

  useEffect(() => {
    lastScrollY.current = window.scrollY;
    let animationFrame = 0;

    function handleScroll() {
      if (animationFrame) return;

      animationFrame = window.requestAnimationFrame(() => {
        const currentScrollY = window.scrollY;
        const scrollDelta = currentScrollY - lastScrollY.current;

        if (currentScrollY <= 16) {
          setIsHidden(false);
          lastScrollY.current = currentScrollY;
        } else if (Math.abs(scrollDelta) >= 8) {
          setIsHidden(scrollDelta > 0);
          lastScrollY.current = currentScrollY;
        }

        animationFrame = 0;
      });
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.cancelAnimationFrame(animationFrame);
    };
  }, []);

  return (
    <header
      className={`site-header${isHidden ? " site-header--hidden" : ""}`}
      onFocus={() => setIsHidden(false)}
    >
      <div className="site-header__inner">
        <Link className="site-brand" href="/" aria-label="金银铜供需信息首页">
          <Image
            alt=""
            aria-hidden="true"
            className="site-brand__mark"
            height={32}
            priority
            src={miningNewsLogo}
            width={32}
          />
          <span>金银铜供需信息</span>
        </Link>
        <nav aria-label="主导航" className="site-nav">
          <Link href="/">首页</Link>
          <Link href="/archive">搜索</Link>
          <a href={INVENTORY_URL} rel="noopener noreferrer" target="_blank">
            库存
          </a>
          <a href={TC_URL} rel="noopener noreferrer" target="_blank">
            TC
          </a>
        </nav>
      </div>
    </header>
  );
}
