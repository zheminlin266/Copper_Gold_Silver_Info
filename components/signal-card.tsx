import type { ReportSignal } from "@/lib/report-types";
import {
  directionLabel,
  formatDateTime,
  metalLabel,
} from "@/lib/reports";

export function SignalCard({ signal }: { signal: ReportSignal }) {
  return (
    <article className="signal-card">
      <div className="signal-card__meta">
        <span className="tag">{signal.kind}</span>
        <span className={`tag tag--${signal.direction}`}>
          {directionLabel(signal.direction)}
        </span>
        {signal.metalTags.map((metal) => (
          <span className={`tag metal--${metal}`} key={metal}>
            {metalLabel(metal)}
          </span>
        ))}
      </div>
      <h3>
        <a href={signal.url} rel="noreferrer" target="_blank">
          {signal.title}
        </a>
      </h3>
      <p className="signal-card__source">
        {signal.source} · {formatDateTime(signal.publishedAt)}
      </p>
      {signal.fact && (
        <div className="signal-block">
          <h4>事实</h4>
          <p>{signal.fact}</p>
        </div>
      )}
      {signal.interpretation && (
        <div className="signal-block">
          <h4>解释</h4>
          <p>{signal.interpretation}</p>
        </div>
      )}
      {signal.importance && (
        <details className="signal-details">
          <summary>展开重要性判断</summary>
          <p>{signal.importance}</p>
        </details>
      )}
    </article>
  );
}
