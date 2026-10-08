import fs from "node:fs";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1")), "..");
const srtPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(root, "glossary_analysis_inputs", "sample_20260829.srt");
const glossaryPath = path.join(root, "outputs", "glossary_improvement_20260830", "zenless-zone-zero-ja-zh_expanded-only.tsv");
const outputDir = path.join(root, "subtitle_precision_work");

const raw = fs.readFileSync(srtPath, "utf8").replace(/^\uFEFF/, "");
const blocks = raw.split(/\r?\n\s*\r?\n/).filter(Boolean);
const entries = blocks.map((block, i) => {
  const lines = block.split(/\r?\n/);
  const ti = lines.findIndex((line) => line.includes("-->"));
  return {
    blockIndex: i,
    index: lines[0],
    time: lines[ti],
    before: lines.slice(0, ti + 1),
    jaLines: lines.slice(ti + 1, ti + 2),
    zhLines: lines.slice(ti + 2),
    ja: lines[ti + 1] || "",
    zh: lines.slice(ti + 2).join("\n"),
    raw: block,
  };
});

const glossary = fs.readFileSync(glossaryPath, "utf8").replace(/^\uFEFF/, "")
  .split(/\r?\n/).filter(Boolean).map((line, rowIndex) => {
    const [ja, zh] = line.split("\t");
    return { ja, zh, rowIndex, isAdded: rowIndex >= 1468 };
  });

const punctuationOnly = /^[\s♪~～!?！？…—ー・、。,.()（）「」『』\-]+$/;
const termFlags = [];
for (const entry of entries) {
  const matches = glossary.filter((term) => {
    if (!term.ja || term.ja.length < 3) return false;
    if (punctuationOnly.test(term.ja)) return false;
    return entry.ja.includes(term.ja);
  }).sort((a, b) => b.ja.length - a.ja.length);
  const maximal = matches.filter((term, idx) => !matches.some((other, j) => j < idx && other.ja.includes(term.ja)));
  for (const term of maximal) {
    if (!entry.zh.includes(term.zh)) {
      termFlags.push({
        index: entry.index,
        time: entry.time,
        ja: entry.ja,
        zh: entry.zh,
        term: term.ja,
        expected: term.zh,
        isAdded: term.isAdded,
      });
    }
  }
}

function visibleLength(value) {
  return [...value.replace(/[\s♪~～!?！？…—ー・、。,.()（）「」『』\-]/g, "")].length;
}

const zhFrequency = new Map();
for (const entry of entries) {
  if (visibleLength(entry.zh) >= 8) zhFrequency.set(entry.zh, (zhFrequency.get(entry.zh) || 0) + 1);
}

const hallucinationFlags = [];
for (const entry of entries) {
  const jl = visibleLength(entry.ja);
  const zl = visibleLength(entry.zh);
  const reasons = [];
  if (jl >= 10 && zl / jl >= 2.35) reasons.push(`中文/日文长度比 ${(zl / jl).toFixed(2)}`);
  if (jl >= 12 && zl <= 2) reasons.push("长日文仅译出极短中文");
  if (/[ぁ-んァ-ヶ]/.test(entry.zh)) reasons.push("中文行残留日文假名");
  if (/字幕(组|由)|感谢观看|请点赞|订阅频道|本视频由|翻译校对/.test(entry.zh) && !/字幕|チャンネル|登録|動画/.test(entry.ja)) reasons.push("疑似模板化幻觉文本");
  if ((zhFrequency.get(entry.zh) || 0) >= 4 && jl >= 8) reasons.push(`相同长中文重复${zhFrequency.get(entry.zh)}次`);
  if (reasons.length) hallucinationFlags.push({ index: entry.index, time: entry.time, ja: entry.ja, zh: entry.zh, reasons });
}

function addContext(flags) {
  return flags.map((flag) => {
    const pos = entries.findIndex((entry) => entry.index === flag.index);
    return {
      ...flag,
      context: entries.slice(Math.max(0, pos - 2), Math.min(entries.length, pos + 3)).map((e) => ({ index: e.index, time: e.time, ja: e.ja, zh: e.zh })),
    };
  });
}

const report = {
  source: srtPath,
  entryCount: entries.length,
  blockShapeCounts: [...entries.reduce((m, e) => {
    const key = `${e.jaLines.length}ja/${e.zhLines.length}zh`;
    m.set(key, (m.get(key) || 0) + 1);
    return m;
  }, new Map()).entries()],
  addedGlossaryTermFlags: addContext(termFlags.filter((x) => x.isAdded)),
  originalGlossaryTermFlags: addContext(termFlags.filter((x) => !x.isAdded)),
  hallucinationFlags: addContext(hallucinationFlags),
  entries,
};

fs.mkdirSync(outputDir, { recursive: true });
const reportName = process.argv[3] || "target_analysis.json";
fs.writeFileSync(path.join(outputDir, reportName), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify({
  entryCount: report.entryCount,
  blockShapeCounts: report.blockShapeCounts,
  addedGlossaryTermFlags: report.addedGlossaryTermFlags.length,
  originalGlossaryTermFlags: report.originalGlossaryTermFlags.length,
  hallucinationFlags: report.hallucinationFlags.length,
}, null, 2));
