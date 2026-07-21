"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import miningNewsLogo from "@/Sources/mining_news_logo.png";

const INVENTORY_URL = "https://sc.macromicro.me/charts/40914/tong-ku-cun-jia-ge";
const TC_URL = "https://www.metal.com/copper/201910240001";

export function SiteHeader() {
  const [isHidden, setIsHidden] = useState(false);
  const [openMenu, setOpenMenu] = useState<"inventory" | "tc" | null>(null);
  const lastScrollY = useRef(0);
  const menuCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const navRef = useRef<HTMLElement>(null);

  function cancelMenuClose() {
    if (menuCloseTimer.current) {
      clearTimeout(menuCloseTimer.current);
      menuCloseTimer.current = null;
    }
  }

  function closeMenu() {
    cancelMenuClose();
    setOpenMenu(null);
  }

  function scheduleMenuClose() {
    cancelMenuClose();
    menuCloseTimer.current = setTimeout(() => {
      setOpenMenu(null);
      menuCloseTimer.current = null;
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
    if (!openMenu) return;

    function handlePointerDown(event: PointerEvent) {
      if (!navRef.current?.contains(event.target as Node)) {
        closeMenu();
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeMenu();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openMenu]);

  useEffect(() => () => cancelMenuClose(), []);

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
        <nav aria-label="主导航" className="site-nav" ref={navRef}>
          <Link href="/">首页</Link>
          <Link href="/archive">搜索</Link>
          <div
            className={`nav-menu inventory-menu${openMenu === "inventory" ? " nav-menu--open" : ""}`}
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget)) {
                closeMenu();
              }
            }}
            onFocus={() => {
              cancelMenuClose();
              setOpenMenu("inventory");
            }}
            onPointerEnter={(event) => {
              if (event.pointerType === "mouse") {
                cancelMenuClose();
                setOpenMenu("inventory");
              }
            }}
            onPointerLeave={(event) => {
              if (event.pointerType === "mouse") scheduleMenuClose();
            }}
          >
            <button
              aria-controls="inventory-menu-panel"
              aria-expanded={openMenu === "inventory"}
              aria-haspopup="true"
              className="nav-menu__trigger"
              onClick={() => {
                cancelMenuClose();
                setOpenMenu((current) => current === "inventory" ? null : "inventory");
              }}
              type="button"
            >
              库存
            </button>
            <div className="nav-menu__panel inventory-menu__panel" id="inventory-menu-panel">
              <a href={INVENTORY_URL} rel="noopener noreferrer" target="_blank">
                <span>三大交易所铜库存</span>
              </a>
            </div>
          </div>
          <div
            className={`nav-menu tc-menu${openMenu === "tc" ? " nav-menu--open" : ""}`}
            onBlur={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget)) {
                closeMenu();
              }
            }}
            onFocus={() => {
              cancelMenuClose();
              setOpenMenu("tc");
            }}
            onPointerEnter={(event) => {
              if (event.pointerType === "mouse") {
                cancelMenuClose();
                setOpenMenu("tc");
              }
            }}
            onPointerLeave={(event) => {
              if (event.pointerType === "mouse") scheduleMenuClose();
            }}
          >
            <button
              aria-controls="tc-menu-panel"
              aria-expanded={openMenu === "tc"}
              aria-haspopup="true"
              className="nav-menu__trigger"
              onClick={() => {
                cancelMenuClose();
                setOpenMenu((current) => current === "tc" ? null : "tc");
              }}
              type="button"
            >
              TC
            </button>
            <div className="nav-menu__panel" id="tc-menu-panel">
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
