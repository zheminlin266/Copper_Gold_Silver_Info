import fs from "node:fs";
import path from "node:path";

export type TcDataPoint = {
  assessmentDate: string;
  value: number;
  change: number;
  sourceUrl: string;
  sourceNote: string;
};

const REQUIRED_HEADERS = [
  "assessment_date",
  "value_usd_per_dmt",
  "change_usd_per_dmt",
  "source_url",
  "source_note",
] as const;

function parseCsvRows(csv: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < csv.length; index += 1) {
    const character = csv[index];

    if (quoted) {
      if (character === '"') {
        if (csv[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        field += character;
      }
      continue;
    }

    if (character === '"' && field.length === 0) {
      quoted = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (character !== "\r") {
      field += character;
    }
  }

  if (quoted) {
    throw new Error("TC CSV contains an unterminated quoted field");
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows.filter((cells) => cells.some((cell) => cell.trim().length > 0));
}

function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function parseFiniteNumber(value: string, field: string, rowNumber: number): number {
  const normalized = value.trim();
  if (normalized === "") {
    throw new Error(`TC CSV row ${rowNumber} has an empty ${field}`);
  }
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(normalized)) {
    throw new Error(`TC CSV row ${rowNumber} has an invalid ${field}: ${value}`);
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) {
    throw new Error(`TC CSV row ${rowNumber} has an invalid ${field}: ${value}`);
  }
  return parsed;
}

export function parseTcCsv(csv: string): TcDataPoint[] {
  const rows = parseCsvRows(csv.replace(/^\uFEFF/, ""));
  if (rows.length < 2) throw new Error("TC CSV has no data rows");

  const headers = rows[0].map((header) => header.trim());
  if (
    headers.length !== REQUIRED_HEADERS.length ||
    REQUIRED_HEADERS.some((header, index) => headers[index] !== header)
  ) {
    throw new Error(`TC CSV headers must be: ${REQUIRED_HEADERS.join(",")}`);
  }

  const seenDates = new Set<string>();
  const points = rows.slice(1).map((cells, index) => {
    const rowNumber = index + 2;
    if (cells.length !== REQUIRED_HEADERS.length) {
      throw new Error(`TC CSV row ${rowNumber} has ${cells.length} fields; expected 5`);
    }

    const assessmentDate = cells[0].trim();
    if (!isIsoDate(assessmentDate)) {
      throw new Error(`TC CSV row ${rowNumber} has an invalid assessment_date: ${assessmentDate}`);
    }
    if (seenDates.has(assessmentDate)) {
      throw new Error(`TC CSV contains duplicate assessment_date: ${assessmentDate}`);
    }
    seenDates.add(assessmentDate);

    const sourceUrl = cells[3].trim();
    let parsedSourceUrl: URL;
    try {
      parsedSourceUrl = new URL(sourceUrl);
    } catch {
      throw new Error(`TC CSV row ${rowNumber} has an invalid source_url: ${sourceUrl}`);
    }
    if (!["http:", "https:"].includes(parsedSourceUrl.protocol)) {
      throw new Error(`TC CSV row ${rowNumber} source_url must use HTTP or HTTPS`);
    }

    return {
      assessmentDate,
      value: parseFiniteNumber(cells[1], "value_usd_per_dmt", rowNumber),
      change: parseFiniteNumber(cells[2], "change_usd_per_dmt", rowNumber),
      sourceUrl,
      sourceNote: cells[4].trim(),
    };
  });

  return points.sort((left, right) => left.assessmentDate.localeCompare(right.assessmentDate));
}

export function getTcData(): TcDataPoint[] {
  const csvPath = path.join(process.cwd(), "data", "smm_copper_concentrate_index_2026.csv");
  return parseTcCsv(fs.readFileSync(csvPath, "utf8"));
}
