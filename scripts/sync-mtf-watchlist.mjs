#!/usr/bin/env node
// Re-read the TradingView watchlist used by the Multi-Timeframe page and rewrite the
// repository snapshot. Read-only: it issues one GET to TradingView's custom-list
// endpoint inside the running Desktop page and never changes watchlists, charts, or layouts.
//
// Usage: node scripts/sync-mtf-watchlist.mjs [--list "PS_DailyWatch_Favourite"] [--dry-run]

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const snapshotPath = join(root, "src/god_market_api/data/ps_dailywatch_favourite.json");
const defaultSymbol = "NSE:NIFTY";

const args = process.argv.slice(2);
const listName = args.includes("--list") ? args[args.indexOf("--list") + 1] : "PS_DailyWatch_Favourite";
const dryRun = args.includes("--dry-run");

function bridgeCliPath() {
  if (process.env.TRADINGVIEW_DESKTOP_BRIDGE_CLI) return process.env.TRADINGVIEW_DESKTOP_BRIDGE_CLI;
  const envFile = join(root, ".env.local");
  if (!existsSync(envFile)) return null;
  const line = readFileSync(envFile, "utf8")
    .split("\n")
    .find((entry) => entry.startsWith("TRADINGVIEW_DESKTOP_BRIDGE_CLI="));
  return line ? line.split("=").slice(1).join("=").trim().replace(/^["']|["']$/g, "") : null;
}

function sectionName(marker) {
  return marker
    .replace(/^#+/, "")
    .replace(/[\u200B-\u200F\u2060-\u206F\uFEFF]/g, "")
    .trim();
}

function toSections(symbols) {
  const sections = [];
  let current = null;
  for (const entry of symbols) {
    if (entry.startsWith("###")) {
      current = { name: sectionName(entry), symbols: [] };
      sections.push(current);
      continue;
    }
    if (!current) {
      current = { name: "Watchlist", symbols: [] };
      sections.push(current);
    }
    current.symbols.push(entry);
  }
  return sections.filter((section) => section.symbols.length > 0);
}

const cli = bridgeCliPath();
if (!cli || !existsSync(cli)) {
  console.error("Set TRADINGVIEW_DESKTOP_BRIDGE_CLI (or .env.local) to the bridge src/cli/index.js.");
  process.exit(1);
}

const { evaluateAsync } = await import(pathToFileURL(join(dirname(dirname(cli)), "connection.js")).href);
const expression = `(async () => {
  const response = await fetch('/api/v1/symbols_list/custom/', { credentials: 'include' });
  if (!response.ok) return { error: 'HTTP ' + response.status };
  const lists = await response.json();
  const match = lists.find((list) => list.name === ${JSON.stringify(listName)});
  return match ? { symbols: match.symbols } : { error: 'Watchlist not found' };
})()`;

let result;
try {
  result = await evaluateAsync(expression);
} catch (error) {
  console.error(`TradingView Desktop is not reachable over CDP: ${error.message}`);
  process.exit(1);
}
if (result?.error) {
  console.error(`Could not read "${listName}": ${result.error}`);
  process.exit(1);
}

const sections = toSections(result.symbols);
const allSymbols = sections.flatMap((section) => section.symbols);
const snapshot = {
  watchlist_name: listName,
  recorded_at: new Date().toISOString(),
  default_symbol: allSymbols.includes(defaultSymbol) ? defaultSymbol : allSymbols[0],
  sections,
};

if (dryRun) {
  console.log(JSON.stringify(snapshot, null, 2));
} else {
  writeFileSync(snapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`);
  console.log(`Wrote ${allSymbols.length} instruments in ${sections.length} sections to ${snapshotPath}`);
}
process.exit(0);
