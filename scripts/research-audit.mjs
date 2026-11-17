import fs from "node:fs";

export const RESEARCH_POLICIES = JSON.parse(fs.readFileSync(new URL("../data/research_policy.json", import.meta.url), "utf8")).policies;
export const GROK_FROM = RESEARCH_POLICIES[0].effective_from;
export const GROK_CHANNEL_ORDER = ["grok_x", "playwright", "twscrape"];
export const GROK_SELECTED_CHANNELS = new Set(Array.from({ length: 7 }, (_, n) => GROK_CHANNEL_ORDER.filter((_, i) => (n + 1) & (1 << i)).join("+")));
const REJECTION_CODES = new Set(["non_target_metal", "no_supply_demand", "no_new_facts", "not_interview", "promotion_only", "duplicate", "out_of_window"]);
const same = (a, b) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());

export function validateResearchAudit(report, filename) {
  const audit = report.search_log.research_audit;
  const fail = (message) => { throw new Error(`${filename}: research audit: ${message}`); };
  if (!audit) {
    if (report.date >= GROK_FROM) fail("research_audit is required for Grok reports");
    return;
  }
  const applicable = RESEARCH_POLICIES.filter((p) => p.effective_from <= report.date).at(-1);
  const policy = RESEARCH_POLICIES.find((p) => p.version === audit.policy_version);
  if (!policy || (applicable && applicable.version !== policy.version)) fail("incorrect research policy version");
  const bySource = new Map();
  const referenced = [];
  for (const source of audit.sources) {
    if (bySource.has(source.source_id)) fail(`duplicate source ${source.source_id}`);
    bySource.set(source.source_id, source);
    if (source.discovered_count !== source.candidate_ids.length) fail(`${source.source_id} discovery count does not match candidate IDs`);
    if (source.status === "complete") {
      if (!["end_of_window", "end_of_results"].includes(source.termination)) fail(`${source.source_id} lacks pagination/window termination`);
      if (!source.entry_urls.length && source.source_id !== "conference-calendar") fail(`${source.source_id} lacks actual discovery URLs`);
    } else if (source.termination !== "error") fail(`${source.source_id} failed discovery must retain an error termination`);
    if (!source.note.trim()) fail(`${source.source_id} lacks discovery/boundary or failure evidence`);
    referenced.push(...source.candidate_ids);
  }
  for (const expected of policy.sources) {
    const source = bySource.get(expected.source_id);
    if (!source || source.kind !== expected.kind) fail(`missing or incorrect source ${expected.source_id}`);
    if (expected.required && source.status !== "complete") fail(`required source incomplete: ${expected.source_id}`);
  }
  for (const [part, kind] of [["part1", "broadcast"], ["part3", "news"]]) {
    const complete = policy.sources.filter((s) => s.kind === kind && s.required).every((s) => bySource.get(s.source_id)?.status === "complete");
    if (report.search_log[`${part}_searched`] !== complete) fail(`${part}_searched conflicts with source coverage`);
  }
  const registry = new Map();
  for (const entry of audit.x_registry) {
    const key = entry.handle.toLowerCase();
    if (registry.has(key)) fail(`duplicate X registry handle ${key}`);
    registry.set(key, entry);
  }
  const accounts = new Map();
  const usedChannels = new Set();
  let completed = 0;
  for (const account of audit.x_accounts) {
    const key = account.handle.toLowerCase();
    if (accounts.has(key) || !registry.has(key)) fail(`unknown or duplicate X account ${key}`);
    accounts.set(key, account);
    if (!account.note.trim()) fail(`X @${key} lacks identity/pagination or failure evidence`);
    if (account.identity_verified && (!account.user_id || account.resolved_handle.toLowerCase() !== key || (registry.get(key).user_id && account.user_id !== registry.get(key).user_id))) fail(`X @${key} identity conflicts with registry`);
    if (account.status === "complete") {
      if (!account.identity_verified || !account.pagination_complete) fail(`X @${key} incomplete identity or pagination cannot count as complete`);
      if (!report.search_log.part2_coverage.attempted_channels.includes(account.channel)) fail(`X @${key} channel was not attempted`);
      completed += 1;
      usedChannels.add(account.channel);
    }
    referenced.push(...account.candidate_ids);
  }
  if (!same(accounts.keys(), registry.keys()) || !registry.size) fail("X account audit must cover the frozen registry exactly");
  const coverage = report.search_log.part2_coverage;
  const selected = GROK_CHANNEL_ORDER.filter((c) => usedChannels.has(c)).join("+") || null;
  if (coverage.accounts_total !== registry.size || coverage.accounts_completed !== completed || coverage.accounts_failed !== registry.size - completed || coverage.selected_channel !== selected) fail("X coverage differs from per-account evidence");
  if (completed < registry.size && !coverage.channel_errors.length) fail("incomplete X coverage requires failure reasons");
  if (completed > 0 && !usedChannels.has(report.search_log.part2_channel)) fail("part2_channel differs from actual successful X channels");
  const candidates = new Map();
  const accepted = { broadcast: [], x: [], news: [] };
  for (const item of audit.candidates) {
    if (candidates.has(item.id)) fail(`duplicate candidate ${item.id}`);
    candidates.set(item.id, item);
    if (item.kind === "x") {
      const key = (item.handle || "").replace(/^@/, "").toLowerCase();
      const account = accounts.get(key);
      if (!account?.candidate_ids.includes(item.id) || item.source_id !== `x-${key}`) fail(`X candidate ${item.id} is not bound to its account`);
      if (item.decision === "accept" && !account.identity_verified) fail(`X candidate ${item.id} has unverified author identity`);
    } else {
      const source = bySource.get(item.source_id);
      if (!source || source.kind !== item.kind || !source.candidate_ids.includes(item.id)) fail(`candidate ${item.id} is not bound to its discovery source`);
    }
    if (item.decision === "reject") {
      if (!REJECTION_CODES.has(item.reason_code) || !item.reason.trim() || item.signal_url !== null) fail(`candidate ${item.id} needs an editorial rejection reason; technical failures remain pending_verification`);
      if (["no_supply_demand", "no_new_facts", "promotion_only"].includes(item.reason_code) && !item.content_checked) fail(`candidate ${item.id} cannot be rejected on content before its source body is checked`);
    } else if (item.decision === "accept") {
      if (!item.signal_url) fail(`accepted candidate ${item.id} lacks a signal URL`);
      accepted[item.kind].push(item.signal_url);
    } else fail(`unresolved candidate ${item.id} cannot be published`);
  }
  if (new Set(referenced).size !== referenced.length || !same(referenced, candidates.keys())) fail("discovery and candidate decisions do not reconcile");
  for (const [kind, field] of [["broadcast", "part1_broadcasts"], ["x", "part2_x_posts"], ["news", "part3_news"]]) {
    const urls = report[field].map((item) => item.url);
    if (new Set(urls).size !== urls.length || !same(accepted[kind], urls)) fail(`${field} does not match accepted candidate decisions`);
  }
  for (const item of report.part2_x_posts) {
    const account = accounts.get(item.handle.replace(/^@/, "").toLowerCase());
    if (!account || item.source_channel !== account.channel || !coverage.attempted_channels.includes(item.source_channel)) fail("X post source_channel differs from its actual account channel");
  }
}
