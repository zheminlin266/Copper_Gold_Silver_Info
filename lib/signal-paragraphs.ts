/** Exact/whitespace-only deduplication; semantic overlap needs editorial review. */
export function getSignalParagraphs(fact: string, interpretation: string): string[] {
  const summary = fact.trim();
  const explanation = interpretation.trim();
  const paragraphs = summary ? [summary] : [];
  const normalize = (text: string) => text.replace(/\s+/gu, " ");
  if (explanation && normalize(explanation) !== normalize(summary)) {
    paragraphs.push(explanation);
  }
  return paragraphs;
}
