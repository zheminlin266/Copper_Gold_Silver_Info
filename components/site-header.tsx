"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import miningNewsLogo from "@/Sources/mining_news_logo.png";

const INVENTORY_URL = "https://sc.macromicro.me/charts/40914/tong-ku-cun-jia-ge";
const TC_URL = "https://www.metal.com/copper/201910240001";

export function SiteHeader() {
  const [isHidden, setIsHidden] = useState(false);
  const [isTcMenuOpen, setIsTcMenuOpen] = useState(false);
  const lastScrollY = useRef(0);
  const tcMenuCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tcMenuRef = useRef<HTMLDivElement>(null);

  function cancelTcMenuClose() {
    if (tcMenuCloseTimer.current) {
      clearTimeout(tcMenuCloseTimer.current);
      tcMenuCloseTimer.current = null;
    }
  }

  function closeTcMenu() {
    cancelTcMenuClose();
    setIsTcMenuOpen(false);
  }

  function scheduleTcMenuClose() {
    cancelTcMenuClose();
    tcMenuCloseTimer.current = setTimeout(() => {
      setIsTcMenuOpen(false);
      tcMenuCloseTimer.current = null;
    }, 280);
  }

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

  useEffect(() => {
    if (!isTcMenuOpen) return;

    function handlePointerDown(event: PointerEvent) {
      if (!tcMenuRef.current?.contains(event.target as Node)) {
        closeTcMenu();
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeTcMenu();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isTcMenuOpen]);

  useEffect(() => () => cancelTcMenuClose(), []);

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
          <div
            className={`tc-menu${isTcMenuOpen ? " tc-menu--open" : ""}`}
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget)) {
                closeTcMenu();
              }
            }}
            onFocus={() => {
              cancelTcMenuClose();
              setIsTcMenuOpen(true);
            }}
            onPointerEnter={(event) => {
              if (event.pointerType === "mouse") {
                cancelTcMenuClose();
                setIsTcMenuOpen(true);
              }
            }}
            onPointerLeave={(event) => {
              if (event.pointerType === "mouse") scheduleTcMenuClose();
            }}
            ref={tcMenuRef}
          >
            <button
              aria-controls="tc-menu-panel"
              aria-expanded={isTcMenuOpen}
              className="tc-menu__trigger"
              onClick={() => {
                cancelTcMenuClose();
                setIsTcMenuOpen(true);
              }}
              type="button"
            >
              TC
            </button>
            <div className="tc-menu__panel" id="tc-menu-panel">
              <a href={TC_URL} rel="noopener noreferrer" target="_blank">
                <span>SMM Copper Concentrate Index</span>
                <small>Shanghai Metals Market</small>
              </a>
              <Link href="/historical-tc">
                <span>Historical TC</span>
                <small>Weekly history and interactive chart</small>
              </Link>
            </div>
          </div>
        </nav>
      </div>
    </header>
  );
}
