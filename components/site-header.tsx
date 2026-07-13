import Image from "next/image";
import Link from "next/link";

import miningNewsLogo from "@/Sources/mining_news_logo.png";

const INVENTORY_URL = "https://sc.macromicro.me/charts/40914/tong-ku-cun-jia-ge";

export function SiteHeader() {
  return (
    <header className="site-header">
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
          <a href={INVENTORY_URL}>库存</a>
        </nav>
      </div>
    </header>
  );
}
