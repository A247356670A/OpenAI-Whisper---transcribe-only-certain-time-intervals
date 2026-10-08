import fs from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const report = JSON.parse(fs.readFileSync(path.join(here, "analysis_report.json"), "utf8"));
const glossary = fs.readFileSync(path.join(here, "zenless-zone-zero-ja-zh.tsv"), "utf8")
  .replace(/^\uFEFF/, "")
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => {
    const [ja, zh] = line.split("\t");
    return { ja, zh };
  });

function normalize(value) {
  return value
    .normalize("NFKC")
    .replace(/[・･\s「」『』！!？?：:。、,.]/g, "")
    .replace(/さん|ちゃん|さま|様|君|くん|先生|氏$/g, "");
}

function levenshtein(a, b) {
  const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const curr = [i];
    for (let j = 1; j <= b.length; j += 1) {
      curr[j] = Math.min(
        curr[j - 1] + 1,
        prev[j] + 1,
        prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    for (let j = 0; j < curr.length; j += 1) prev[j] = curr[j];
  }
  return prev[b.length];
}

const rows = [];
for (const candidate of report.uncoveredKatakanaCandidates) {
  const c = normalize(candidate.candidate);
  if (c.length < 3) continue;
  const nearest = glossary
    .map((term) => {
      const g = normalize(term.ja);
      const dist = levenshtein(c, g);
      const similarity = 1 - dist / Math.max(c.length, g.length, 1);
      return { ...term, dist, similarity };
    })
    .sort((a, b) => b.similarity - a.similarity || a.dist - b.dist)
    .slice(0, 4);
  const examples = candidate.examples.slice(0, 3).map((e) => `${e.ja} || ${e.zh}`).join(" /// ");
  rows.push({
    candidate: candidate.candidate,
    count: candidate.count,
    nearest,
    examples,
  });
}

rows.sort((a, b) => {
  const scoreA = (a.nearest[0]?.similarity ?? 0) * Math.log2(a.count + 1);
  const scoreB = (b.nearest[0]?.similarity ?? 0) * Math.log2(b.count + 1);
  return scoreB - scoreA || b.count - a.count;
});

fs.writeFileSync(path.join(here, "ranked_expansion_candidates.json"), JSON.stringify(rows, null, 2));
for (const row of rows.slice(0, 350)) {
  const near = row.nearest.map((n) => `${n.ja}=>${n.zh}(${n.similarity.toFixed(2)})`).join(" | ");
  console.log(`${row.candidate}\t${row.count}\t${near}\t${row.examples}`);
}
