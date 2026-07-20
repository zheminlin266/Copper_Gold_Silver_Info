import type { Metadata } from "next";

import { TcHistoryChart } from "@/components/tc-history-chart";
import { getTcData } from "@/lib/tc-data";

const SMM_TC_URL = "https://www.metal.com/copper/201910240001";

export const metadata: Metadata = {
  title: "Historical TC",
  description: "SMM 铜精矿指数（周）的历史走势与交互式数据图。",
  alternates: {
    canonical: "/historical-tc",
  },
};

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

export default function HistoricalTcPage() {
  const data = getTcData();
  const latest = data.at(-1);
  const first = data[0];
  if (!latest || !first) throw new Error("Historical TC page requires at least one data point");

  return (
    <main className="site-main">
      <article className="article-copy">
        <header className="page-intro">
          <p className="eyebrow">Copper Concentrate</p>
          <h1>Historical TC</h1>
          <p className="meta-copy">SMM Copper Concentrate Index · Weekly · USD/dmt</p>
          <p className="lead-copy">
            SMM 铜精矿指数（周）的历史走势。将鼠标移入图表，可查看对应日期、指数值及周度变化。
          </p>
        </header>

        <dl className="tc-summary" aria-label="TC 数据摘要">
          <div>
            <dt>Latest</dt>
            <dd>{latest.value.toFixed(2)} USD/dmt</dd>
            <span>{latest.assessmentDate}</span>
          </div>
          <div>
            <dt>Weekly change</dt>
            <dd className={latest.change < 0 ? "tc-value--negative" : "tc-value--positive"}>
              {formatSigned(latest.change)}
            </dd>
            <span>USD/dmt</span>
          </div>
          <div>
            <dt>Coverage</dt>
            <dd>{data.length} observations</dd>
            <span>{first.assessmentDate} — {latest.assessmentDate}</span>
          </div>
        </dl>

        <section className="content-section tc-history" aria-labelledby="tc-chart-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Weekly history</p>
              <h2 id="tc-chart-heading">SMM Copper Concentrate Index</h2>
            </div>
            <span className="tc-history__unit">USD / dmt</span>
          </div>
          <TcHistoryChart data={data} />
          <p className="tc-chart__mobile-note">在窄屏设备上可左右滑动查看完整图表。</p>
        </section>

        <section className="content-section tc-method" aria-labelledby="tc-method-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Source &amp; methodology</p>
              <h2 id="tc-method-heading">数据说明</h2>
            </div>
          </div>
          <p>
            数据来自 SMM 公开发布的周度铜精矿指数资料，页面直接读取本站 CSV 数据文件；CSV 更新后，折线图会在下一次站点构建时同步更新。
          </p>
          <a href={SMM_TC_URL} rel="noopener noreferrer" target="_blank">
            查看 SMM Copper Concentrate Index 原始页面
          </a>
          <details className="tc-data-table">
            <summary>查看全部 {data.length} 条数据</summary>
            <div>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Index (USD/dmt)</th>
                    <th scope="col">Change</th>
                    <th scope="col">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {[...data].reverse().map((point) => (
                    <tr key={point.assessmentDate}>
                      <td>{point.assessmentDate}</td>
                      <td>{point.value.toFixed(2)}</td>
                      <td>{formatSigned(point.change)}</td>
                      <td>
                        <a href={point.sourceUrl} rel="noopener noreferrer" target="_blank">
                          SMM
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </section>
      </article>
    </main>
  );
}
