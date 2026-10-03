import type { ReportSignal } from "@/lib/report-types";
import { getSignalParagraphs } from "@/lib/signal-paragraphs";
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
        {signal.verificationStatus === "unverified" && (
          <span className="tag tag--unverified">来源未核验</span>
        )}
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
      {signal.verificationStatus === "unverified" && (
        <p className="signal-card__verification">
          来源未核验：{signal.verificationNote}
        </p>
      )}
      {signal.verificationStatus !== "unverified" && getSignalParagraphs(signal.fact, signal.interpretation).map((paragraph, index) => (
        <p className="signal-block" key={index}>{paragraph}</p>
      ))}
      {signal.verificationStatus !== "unverified" && signal.importance && (
        <details className="signal-details">
          <summary>展开重要性判断</summary>
          <p>{signal.importance}</p>
        </details>
      )}
    </article>
  );
}
