import fs from "node:fs";
import path from "node:path";

const inputDir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const glossaryPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(inputDir, "zenless-zone-zero-ja-zh.tsv");
const reportPath = process.argv[3]
  ? path.resolve(process.argv[3])
  : path.join(inputDir, "analysis_report.json");
const glossaryRows = fs.readFileSync(glossaryPath, "utf8")
  .replace(/^\uFEFF/, "")
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line, index) => {
    const [ja, zh, ...extra] = line.split("\t");
    return { row: index + 1, ja, zh, extra };
  });

function kanaCount(text) {
  return (text.match(/[ぁ-んァ-ヶー]/g) || []).length;
}

function hanCount(text) {
  return (text.match(/[\p{Script=Han}]/gu) || []).length;
}

function parseSrt(filePath) {
  const raw = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
  const blocks = raw.split(/\r?\n\s*\r?\n/);
  const entries = [];
  for (const block of blocks) {
    const lines = block.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const timestampIndex = lines.findIndex((line) => /-->/.test(line));
    if (timestampIndex < 0) continue;
    const textLines = lines.slice(timestampIndex + 1);
    if (textLines.length < 2) continue;
    const rankedJa = [...textLines].sort((a, b) => kanaCount(b) - kanaCount(a));
    const ja = rankedJa[0];
    const zhCandidates = textLines.filter((line) => line !== ja);
    const rankedZh = zhCandidates.sort((a, b) => {
      const scoreA = hanCount(a) - kanaCount(a) * 3;
      const scoreB = hanCount(b) - kanaCount(b) * 3;
      return scoreB - scoreA;
    });
    const zh = rankedZh[0] || "";
    if (kanaCount(ja) === 0 && ja === zh) continue;
    entries.push({
      file: path.basename(filePath),
      index: lines[0],
      time: lines[timestampIndex],
      ja,
      zh,
    });
  }
  return entries;
}

const srtFiles = fs.readdirSync(inputDir)
  .filter((name) => name.endsWith(".srt"))
  .map((name) => path.join(inputDir, name));
const entries = srtFiles.flatMap(parseSrt);

const hits = new Map();
const mismatches = [];
for (const term of glossaryRows) {
  const matching = entries.filter((entry) => entry.ja.includes(term.ja));
  if (!matching.length) continue;
  const failures = matching.filter((entry) => !entry.zh.includes(term.zh));
  hits.set(term.ja, {
    row: term.row,
    ja: term.ja,
    expectedZh: term.zh,
    hitCount: matching.length,
    failureCount: failures.length,
    failureRate: failures.length / matching.length,
  });
  for (const entry of failures) {
    mismatches.push({ ...entry, glossaryRow: term.row, term: term.ja, expectedZh: term.zh });
  }
}

const candidateMap = new Map();
for (const entry of entries) {
  const candidates = entry.ja.match(/[ァ-ヶー][ァ-ヶー・･]{1,}/g) || [];
  for (const candidate of new Set(candidates)) {
    if (/^[ー・･]+$/.test(candidate)) continue;
    const coveredBy = glossaryRows.filter((term) => candidate.includes(term.ja) || term.ja.includes(candidate));
    if (!candidateMap.has(candidate)) {
      candidateMap.set(candidate, { candidate, count: 0, coveredBy: coveredBy.map((x) => x.ja), examples: [] });
    }
    const item = candidateMap.get(candidate);
    item.count += 1;
    if (item.examples.length < 8) item.examples.push(entry);
  }
}

const report = {
  glossary: {
    rowCount: glossaryRows.length,
    malformedRows: glossaryRows.filter((row) => !row.ja || !row.zh || row.extra.length).slice(0, 50),
  },
  subtitles: srtFiles.map((filePath) => ({
    file: path.basename(filePath),
    entryCount: parseSrt(filePath).length,
  })),
  matchedTerms: [...hits.values()].sort((a, b) => b.hitCount - a.hitCount),
  highFailureTerms: [...hits.values()]
    .filter((item) => item.failureCount > 0)
    .sort((a, b) => b.failureCount - a.failureCount || b.hitCount - a.hitCount),
  mismatchExamples: mismatches,
  katakanaCandidates: [...candidateMap.values()]
    .sort((a, b) => b.count - a.count || a.candidate.localeCompare(b.candidate, "ja")),
  uncoveredKatakanaCandidates: [...candidateMap.values()]
    .filter((item) => item.coveredBy.length === 0)
    .sort((a, b) => b.count - a.count || a.candidate.localeCompare(b.candidate, "ja")),
};

fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify({
  glossaryRows: report.glossary.rowCount,
  subtitles: report.subtitles,
  matchedTerms: report.matchedTerms.length,
  mismatches: report.mismatchExamples.length,
  uncoveredCandidates: report.uncoveredKatakanaCandidates.length,
}, null, 2));
