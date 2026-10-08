import fs from "node:fs";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1")), "..");
const originalPath = path.join(root, "glossary_analysis_inputs", "sample_20260829.srt");
const revisedPath = path.join(root, "outputs", "subtitle_precision_20260830", "20260829_ZZZ_Ver3.2_zh_precise_dual.srt");
const changesPath = path.join(root, "outputs", "subtitle_precision_20260830", "changes.json");

function parse(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "");
  return raw.split(/\r?\n\s*\r?\n/).map((block) => {
    const lines = block.split(/\r?\n/);
    const ti = lines.findIndex((line) => line.includes("-->"));
    return { index: lines[0] || "", time: ti >= 0 ? lines[ti] : "", ja: ti >= 0 ? (lines[ti + 1] || "") : "", zh: ti >= 0 ? lines.slice(ti + 2).join("\n") : "" };
  });
}

const original = parse(originalPath);
const revised = parse(revisedPath);
const changes = JSON.parse(fs.readFileSync(changesPath, "utf8"));
const structuralDifferences = [];
for (let i = 0; i < Math.max(original.length, revised.length); i += 1) {
  const a = original[i] || {};
  const b = revised[i] || {};
  if (a.index !== b.index || a.time !== b.time || a.ja !== b.ja) structuralDifferences.push({ pos: i + 1, original: a, revised: b });
}

const changedByDiff = revised.filter((row, i) => row.zh !== original[i]?.zh).length;
const remainingDriftPatterns = [
  "西格丽特", "西格莉特", "希格莉特", "西弗莱德", "希芙蕾德",
  "罗克西", "洛克西", "洛希", "卢克西",
  "克拉蕾特", "克拉雷特", "伊卡莱特",
  "铃德贝尔", "铃多贝尔", "林德伯格", "林德贝鲁", "敏特贝尔斯", "宁多贝尔",
  "弗林茨", "弗林斯工坊", "普林茨工坊", "比鲁里乌姆", "维尔里乌姆",
  "阿特利亚斯", "艾特里亚斯", "戴特莉亚斯", "普罗梅耶", "造梦机", "妄想代理人",
];
const residuals = [];
for (const row of revised) {
  for (const pattern of remainingDriftPatterns) {
    if (row.zh.includes(pattern)) residuals.push({ index: row.index, pattern, ja: row.ja, zh: row.zh });
  }
  if (/[ぁ-んァ-ヶ]/.test(row.zh)) residuals.push({ index: row.index, pattern: "中文残留假名", ja: row.ja, zh: row.zh });
}

const result = {
  originalBlocks: original.length,
  revisedBlocks: revised.length,
  structuralDifferences: structuralDifferences.length,
  changesRecorded: changes.length,
  changedByDiff,
  residualCount: residuals.length,
  residuals,
};
fs.writeFileSync(path.join(root, "outputs", "subtitle_precision_20260830", "validation.json"), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
