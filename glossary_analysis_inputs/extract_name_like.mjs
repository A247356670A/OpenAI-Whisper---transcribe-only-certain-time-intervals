import fs from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const glossary = fs.readFileSync(path.join(here, "zenless-zone-zero-ja-zh.tsv"), "utf8")
  .replace(/^\uFEFF/, "").split(/\r?\n/).filter(Boolean)
  .map((line) => line.split("\t")[0]);

function parse(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "");
  const out = [];
  for (const block of raw.split(/\r?\n\s*\r?\n/)) {
    const lines = block.split(/\r?\n/).filter(Boolean);
    const ti = lines.findIndex((x) => x.includes("-->"));
    if (ti < 0) continue;
    const texts = lines.slice(ti + 1);
    const ja = texts.find((x) => /[ぁ-んァ-ヶー]/.test(x)) || "";
    const zh = texts.find((x) => x !== ja) || "";
    if (ja) out.push({ file: path.basename(file), ja, zh });
  }
  return out;
}

const entries = fs.readdirSync(here).filter((x) => x.endsWith(".srt")).flatMap((x) => parse(path.join(here, x)));
const map = new Map();
for (const entry of entries) {
  const matches = entry.ja.matchAll(/([ァ-ヶー][ァ-ヶー・･ー]{1,})(?:さん|様|先生|君|氏|先輩|ちゃん)/g);
  for (const m of matches) {
    const term = m[1].replace(/^[ー]+|[ー]+$/g, "");
    if (!term) continue;
    if (!map.has(term)) map.set(term, { term, count: 0, examples: [], covered: [] });
    const item = map.get(term);
    item.count += 1;
    if (item.examples.length < 5) item.examples.push(`${entry.ja} || ${entry.zh}`);
  }
}
for (const item of map.values()) {
  item.covered = glossary.filter((g) => g.includes(item.term) || item.term.includes(g)).slice(0, 8);
}
const rows = [...map.values()].sort((a, b) => b.count - a.count || a.term.localeCompare(b.term, "ja"));
fs.writeFileSync(path.join(here, "name_like_candidates.json"), JSON.stringify(rows, null, 2));
for (const x of rows) console.log(`${x.term}\t${x.count}\t${x.covered.join("|")}\t${x.examples.join(" /// ")}`);
