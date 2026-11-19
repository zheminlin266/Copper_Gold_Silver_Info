import Link from "next/link";

import { WEEKLY_GROUPS, weeklyPath, weeklyPeriod, type SourcedFact, type WeeklyReport } from "@/lib/weekly-reports";

function FactCard({ item, heading: Heading }: { item: SourcedFact; heading: "h3" | "h4" }) {
  return (
    <article className="signal-card" id={`event-${item.id}`}>
      <Heading>{item.title}</Heading>
      <p className="signal-block">{item.fact}</p>
      <div className="weekly-sources">
        <time dateTime={item.date}>{item.date.slice(5).replace("-", " 月 ") + " 日"}</time>
        {item.sources.map(({ name, url }) => (
          <a href={url} key={url} rel="noreferrer" target="_blank">{name}</a>
        ))}
      </div>
    </article>
  );
}

export function WeeklyReportView({ report, isHome = false }: { report: WeeklyReport; isHome?: boolean }) {
  const eventTitles = new Map(report.copper_events.map(({ id, title }) => [id, title]));
  return (
    <main className="site-main">
      <article className="article-copy weekly-report" data-week-start={report.week_start}>
        <header className="page-intro">
          <h1>铜矿供给周报</h1>
          <p className="lead-copy">{weeklyPeriod(report)} <span className="meta-copy">北京时间</span></p>
          <nav aria-label="周报目录" className="article-nav">
            <a href="#copper-events">铜矿重要事实</a>
            <a href="#supply-analysis">综合供给影响</a>
            <a href="#gold-briefs">黄金简讯</a>
            {isHome && <Link href={weeklyPath(report.week_start)}>本期链接</Link>}
            <Link href="/archive">归档</Link>
          </nav>
        </header>

        <section className="content-section" id="copper-events" aria-labelledby="copper-events-heading">
          <div className="section-heading"><h2 id="copper-events-heading">铜矿重要事实</h2></div>
          {WEEKLY_GROUPS.map(({ id, label }) => {
            const events = report.copper_events.filter((event) => event.group === id);
            return events.length > 0 && (
              <section className="metal-section" key={id} aria-labelledby={`weekly-group-${id}`}>
                <div className="metal-section__heading"><h3 id={`weekly-group-${id}`}>{label}</h3></div>
                {events.map((event) => <FactCard heading="h4" item={event} key={event.id} />)}
              </section>
            );
          })}
          {report.copper_events.length === 0 && <p className="empty-state">本周未发现符合收录标准的重要铜矿事件。</p>}
        </section>

        <section className="content-section" id="supply-analysis" aria-labelledby="supply-analysis-heading">
          <div className="section-heading"><h2 id="supply-analysis-heading">综合供给影响</h2></div>
          {report.supply_analysis.map(({ title, text, event_ids }) => (
            <article className="signal-card" key={title}>
              <h3>{title}</h3>
              <p className="signal-block">{text}</p>
              {event_ids.length > 0 && (
                <div className="weekly-sources">
                  {event_ids.map((id) => <a href={`#event-${id}`} key={id}>{eventTitles.get(id)}</a>)}
                </div>
              )}
            </article>
          ))}
          {report.supply_analysis.length === 0 && <p className="empty-state">本周事件不足以作出新增供给判断。</p>}
        </section>

        <section className="content-section" id="gold-briefs" aria-labelledby="gold-briefs-heading">
          <div className="section-heading"><h2 id="gold-briefs-heading">黄金简讯</h2></div>
          {report.gold_briefs.map((item) => <FactCard heading="h3" item={item} key={item.id} />)}
          {report.gold_briefs.length === 0 && <p className="empty-state">本周未发现需要收录的黄金动态。</p>}
        </section>
      </article>
    </main>
  );
}
