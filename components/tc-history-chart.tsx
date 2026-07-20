"use client";

import { useId, useMemo, useRef, useState } from "react";

import type { TcDataPoint } from "@/lib/tc-data";

type TcHistoryChartProps = {
  data: TcDataPoint[];
};

type HoverState = {
  index: number;
  left: number;
  top: number;
};

const CHART_WIDTH = 720;
const CHART_HEIGHT = 360;
const MARGIN = { top: 24, right: 28, bottom: 52, left: 68 };

function niceStep(value: number): number {
  const power = 10 ** Math.floor(Math.log10(value));
  const fraction = value / power;
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return niceFraction * power;
}

function formatDate(date: string): string {
  return date.slice(5);
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

export function TcHistoryChart({ data }: TcHistoryChartProps) {
  const gradientId = useId().replace(/:/g, "");
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<HoverState | null>(null);

  const chart = useMemo(() => {
    const values = data.map((point) => point.value);
    const timestamps = data.map((point) => Date.parse(`${point.assessmentDate}T00:00:00Z`));
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const rawRange = rawMax - rawMin || Math.max(Math.abs(rawMax) * 0.2, 1);
    const step = niceStep(rawRange / 5);
    let yMin = Math.floor(rawMin / step) * step;
    let yMax = Math.ceil(rawMax / step) * step;
    if (yMin === yMax) {
      yMin -= step;
      yMax += step;
    }

    const plotWidth = CHART_WIDTH - MARGIN.left - MARGIN.right;
    const plotHeight = CHART_HEIGHT - MARGIN.top - MARGIN.bottom;
    const firstTimestamp = timestamps[0];
    const lastTimestamp = timestamps.at(-1) ?? firstTimestamp;
    const timeRange = lastTimestamp - firstTimestamp;
    const x = (timestamp: number) =>
      MARGIN.left + (timeRange === 0 ? plotWidth / 2 : ((timestamp - firstTimestamp) / timeRange) * plotWidth);
    const y = (value: number) =>
      MARGIN.top + ((yMax - value) / (yMax - yMin)) * plotHeight;
    const points = data.map((point, index) => ({
      ...point,
      x: x(timestamps[index]),
      y: y(point.value),
    }));
    const yTickCount = Math.round((yMax - yMin) / step);
    const yTicks = Array.from({ length: yTickCount + 1 }, (_, index) => yMin + index * step);
    const labelCount = Math.min(6, data.length);
    const xTickIndices = Array.from(
      new Set(
        Array.from({ length: labelCount }, (_, index) => {
          const target = firstTimestamp + (index / Math.max(labelCount - 1, 1)) * timeRange;
          return timestamps.reduce(
            (closest, timestamp, pointIndex) =>
              Math.abs(timestamp - target) < Math.abs(timestamps[closest] - target)
                ? pointIndex
                : closest,
            0,
          );
        }),
      ),
    );

    return {
      plotWidth,
      plotHeight,
      points,
      y,
      yTicks,
      xTickIndices,
      line: points.map((point) => `${point.x},${point.y}`).join(" "),
      area: `${points[0].x},${MARGIN.top + plotHeight} ${points
        .map((point) => `${point.x},${point.y}`)
        .join(" ")} ${points.at(-1)?.x},${MARGIN.top + plotHeight}`,
    };
  }, [data]);

  function handlePointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const svgRect = event.currentTarget.getBoundingClientRect();
    const containerRect = containerRef.current?.getBoundingClientRect();
    if (!containerRect) return;

    const viewX = ((event.clientX - svgRect.left) / svgRect.width) * CHART_WIDTH;
    const index = chart.points.reduce(
      (closest, point, pointIndex) =>
        Math.abs(point.x - viewX) < Math.abs(chart.points[closest].x - viewX)
          ? pointIndex
          : closest,
      0,
    );
    const tooltipWidth = 176;
    const pointerLeft = event.clientX - containerRect.left + 14;

    setHover({
      index,
      left: Math.max(10, Math.min(pointerLeft, containerRect.width - tooltipWidth - 10)),
      top: Math.max(10, event.clientY - containerRect.top - 72),
    });
  }

  const activePoint = hover ? chart.points[hover.index] : null;

  return (
    <div className="tc-chart" ref={containerRef}>
      <div className="tc-chart__plot" aria-label="SMM 铜精矿指数历史折线图">
        <svg
          className="tc-chart__svg"
          onPointerLeave={() => setHover(null)}
          onPointerMove={handlePointerMove}
          role="img"
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        >
          <title>SMM Copper Concentrate Index weekly values in US dollars per dry metric tonne</title>
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--copper)" stopOpacity="0.2" />
              <stop offset="100%" stopColor="var(--copper)" stopOpacity="0" />
            </linearGradient>
          </defs>

          {chart.yTicks.map((tick) => (
            <g key={tick}>
              <line
                className="tc-chart__grid"
                x1={MARGIN.left}
                x2={CHART_WIDTH - MARGIN.right}
                y1={chart.y(tick)}
                y2={chart.y(tick)}
              />
              <text
                className="tc-chart__axis-label"
                textAnchor="end"
                x={MARGIN.left - 12}
                y={chart.y(tick) + 4}
              >
                {tick}
              </text>
            </g>
          ))}

          {chart.xTickIndices.map((index) => (
            <text
              className="tc-chart__axis-label"
              key={data[index].assessmentDate}
              textAnchor="middle"
              x={chart.points[index].x}
              y={CHART_HEIGHT - 20}
            >
              {formatDate(data[index].assessmentDate)}
            </text>
          ))}

          <text
            className="tc-chart__axis-title"
            textAnchor="middle"
            transform={`translate(16 ${MARGIN.top + chart.plotHeight / 2}) rotate(-90)`}
          >
            USD / dmt
          </text>
          <text
            className="tc-chart__axis-title"
            textAnchor="middle"
            x={MARGIN.left + chart.plotWidth / 2}
            y={CHART_HEIGHT - 2}
          >
            Assessment date
          </text>

          <polygon fill={`url(#${gradientId})`} points={chart.area} />
          <polyline className="tc-chart__line" points={chart.line} />
          {chart.points.map((point) => (
            <circle
              className="tc-chart__point"
              cx={point.x}
              cy={point.y}
              key={point.assessmentDate}
              r={3.2}
            >
              <title>{`${point.assessmentDate}: ${point.value.toFixed(2)} USD/dmt`}</title>
            </circle>
          ))}

          {activePoint ? (
            <g aria-hidden="true">
              <line
                className="tc-chart__guide"
                x1={activePoint.x}
                x2={activePoint.x}
                y1={MARGIN.top}
                y2={MARGIN.top + chart.plotHeight}
              />
              <circle
                className="tc-chart__point tc-chart__point--active"
                cx={activePoint.x}
                cy={activePoint.y}
                r={5.5}
              />
            </g>
          ) : null}

          <rect
            fill="transparent"
            height={chart.plotHeight}
            width={chart.plotWidth}
            x={MARGIN.left}
            y={MARGIN.top}
          />
        </svg>
      </div>

      {activePoint && hover ? (
        <div
          aria-hidden="true"
          className="tc-chart__tooltip"
          style={{ left: hover.left, top: hover.top }}
        >
          <strong>{activePoint.assessmentDate}</strong>
          <span>{activePoint.value.toFixed(2)} USD/dmt</span>
          <small>Weekly change {formatSigned(activePoint.change)}</small>
        </div>
      ) : null}
    </div>
  );
}
