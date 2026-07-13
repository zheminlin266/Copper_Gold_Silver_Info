import Link from "next/link";

export default function NotFound() {
  return (
    <main className="site-main">
      <div className="article-copy empty-page">
        <p className="eyebrow">404</p>
        <h1>没有找到这份日报</h1>
        <p>链接可能已失效，或者该日期的内容尚未发布。</p>
        <Link className="text-button" href="/archive">查看日报归档</Link>
      </div>
    </main>
  );
}
