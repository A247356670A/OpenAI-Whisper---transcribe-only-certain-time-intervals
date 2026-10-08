import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const rootDir = path.resolve(outputDir, "..", "..");
const inputDir = path.join(rootDir, "glossary_analysis_inputs");
const originalPath = path.join(inputDir, "zenless-zone-zero-ja-zh.tsv");
const reportPath = path.join(inputDir, "analysis_report.json");

const officialMainJa = "https://zenless.hoyoverse.com/ja-jp/main?catchSpider=1";
const officialMainZh = "https://zenless.hoyoverse.com/zh-cn/main?catchSpider=1";
const official32Ja = "https://zenless.hoyoverse.com/ja-jp/news/165865?catchSpider=1";
const officialForumZh = "https://www.taptap.cn/forum/g330333?type=official";

const removals = [
  ["リン", "铃", "会误命中 リング、フリンツ、カリン、イヴリン 等"],
  ["にこ", "妮可", "会误命中 普通にここ、下にこれ 等普通短语"],
  ["ジェン", "简", "会误命中 エージェント"],
  ["るし", "露西", "会误命中 似てるし、いるし 等活用形式"],
  ["まな", "又奈", "会误命中 そのまま、あんまない 等普通短语"],
  ["りな", "丽娜", "会误命中 やりながら 等普通短语"],
  ["ベン", "本", "会误命中 イベント"],
  ["ライト", "莱特", "会误命中 スターライト；保留完整人名并新增敬称形式"],
  ["こら", "柯拉", "会误命中 そこら、ここら、どこら"],
  ["コラ", "柯拉", "会误命中 コラボ"],
  ["えてる", "以太", "会误命中普通动词活用，如 考えてる、抱えてる"],
  ["ダン", "丹", "会误命中 ダンス、インピーダンス"],
  ["セス", "赛斯", "会误命中 アクセス"],
  ["せす", "赛斯", "过短平假名，容易跨词误命中"],
  ["くれた", "珂蕾妲", "会误命中日语普通动词 くれた"],
  ["マナ", "又奈", "会误命中 マナー"],
  ["ルシ", "露西", "会误命中其他片假名词内部"],
  ["キング", "金", "会误命中 クラッキング 等词"],
  ["やお", "耀嘉音", "会误命中 いやおかしい 等普通短语"],
  ["ありす", "爱丽丝", "会误命中 センスありすぎ 等普通短语"],
  ["ありあ", "爱芮", "会误命中 ありあり 等普通表达"],
  ["町", "「小镇」", "普通名词，不适合作为必须统一的专名"],
  ["ホワイト", "怀特", "会误命中 ホワイトスター学会；保留完整姓名"],
  ["だん", "丹", "会误命中 読んだん、だったん 等普通语尾"],
];

const additions = [
  ["ロクシー・イフリータ・プライス", "洛克茜·伊芙莉塔·普莱斯", "官方全名", "official", officialMainJa],
  ["ロクシー･イフリータ･プライス", "洛克茜·伊芙莉塔·普莱斯", "分隔符变体", "official_variant", officialMainJa],
  ["ロクシーイフリータプライス", "洛克茜·伊芙莉塔·普莱斯", "无分隔符变体", "official_variant", officialMainJa],
  ["ロクシー", "洛克茜", "3.2角色名；字幕中曾漂移为罗克西、洛希、露西", "observed_variant", officialMainZh],
  ["クラレッタ・フリンツ", "克拉蕾·弗林特", "官方全名", "official", officialMainJa],
  ["クラレッタ･フリンツ", "克拉蕾·弗林特", "分隔符变体", "official_variant", officialMainJa],
  ["クラレッタフリンツ", "克拉蕾·弗林特", "无分隔符变体", "official_variant", officialMainJa],
  ["クラレット", "克拉蕾", "クラレッタ 的高频ASR变体", "observed_variant", "sample_20260829.srt"],
  ["スクラレッタ", "克拉蕾", "クラレッタ 的带前缀ASR变体", "observed_variant", "sample_20260829.srt"],
  ["シグリット", "希格莉德", "シグリッド 的高频清浊音ASR变体", "observed_variant", "sample_20260822.srt; sample_20260829.srt"],
  ["シグニット", "希格莉德", "シグリッド 的ASR变体", "observed_variant", "sample_20260822.srt"],
  ["ピロイス", "佩洛伊斯", "ピュロイス 的高频ASR变体", "observed_variant", "sample_20260822.srt; sample_20260825.srt"],
  ["シーシア", "希希芙", "シーシィア 的高频ASR变体", "observed_variant", "sample_20260822.srt"],
  ["プロメイヤー", "普罗米娅", "プロメイア 的高频ASR变体", "observed_variant", "sample_20260822.srt; sample_20260829.srt"],
  ["プロメイヤ", "普罗米娅", "プロメイア 的短音ASR变体", "observed_variant", "sample_20260822.srt"],
  ["ベギナ", "维琳娜", "ヴェリナ 的ASR变体", "observed_variant", "sample_20260822.srt"],
  ["グレッシュ", "格莉丝", "グレース 的ASR变体", "observed_variant", "sample_20260822.srt"],
  ["イヤス", "伊埃斯", "イアス 的高频ASR变体", "observed_variant", "sample_20260825.srt"],
  ["メミエル", "蕾米埃尔", "レミエール 的ASR变体", "observed_variant", "sample_20260825.srt; sample_20260829.srt"],
  ["レミエリ", "蕾米埃尔", "レミエール 的ASR变体", "observed_variant", "sample_20260822.srt"],
  ["サンムリンガー", "挽昼", "サンブリンガー 的ASR变体", "observed_variant", "sample_20260825.srt"],
  ["リンドベルル", "林德薇恩", "リンドヴェルヌ 的ASR变体", "observed_variant", "sample_20260829.srt"],
  ["リンドベルネ", "林德薇恩", "リンドヴェルヌ 的ASR变体", "observed_variant", "sample_20260829.srt"],
  ["ニンドベル", "林德薇恩", "リンドヴェルヌ 的ASR变体", "observed_variant", "sample_20260829.srt"],
  ["ウリディンム", "乌利迪姆", "3.1敌人官方日文名", "official", "sample_20260825.srt"],
  ["猟犬・ウリディンム", "猎犬·乌利迪姆", "带称号完整形式", "official", "sample_20260825.srt"],
  ["ウリリム", "乌利迪姆", "ウリディンム 的ASR变体", "observed_variant", "sample_20260825.srt"],
  ["迷い路の謎", "迷宫诡域", "3.1玩法名", "official", "sample_20260825.srt"],
  ["ベーグル計画", "贝果计划", "3.1玩法副标题", "official", "sample_20260825.srt"],
  ["ベイブル計画", "贝果计划", "ベーグル計画 的ASR变体", "observed_variant", "sample_20260825.srt"],
  ["オーモンド・フリンツ", "奥蒙德·弗林特", "角色完整姓名", "verified_context", "sample_20260825.srt"],
  ["オーモンド･フリンツ", "奥蒙德·弗林特", "分隔符变体", "verified_context", "sample_20260825.srt"],
  ["オーモンドフリンツ", "奥蒙德·弗林特", "无分隔符变体", "observed_variant", "sample_20260825.srt"],
  ["オーモンドフリンズ", "奥蒙德·弗林特", "姓名ASR变体", "observed_variant", "sample_20260825.srt"],
  ["オーモンドフリンチ", "奥蒙德·弗林特", "姓名ASR变体", "observed_variant", "sample_20260825.srt"],
  ["オーモンド", "奥蒙德", "角色名；原表只有调查基地全称", "observed_missing", "sample_20260825.srt"],
  ["ジョイアス", "乔伊斯", "3.1剧情人物", "verified_context", "sample_20260825.srt"],
  ["フリンツ工房", "弗林特工坊", "3.2阵营官方名称", "official", official32Ja],
  ["フリンス工房", "弗林特工坊", "フリンツ工房 的ASR变体", "observed_variant", "sample_20260829.srt"],
  ["フリンツ", "弗林特", "姓氏及工坊简称", "official", officialMainZh],
  ["ヴィルリウム", "维尔乌姆", "3.2地区官方名称", "official", officialForumZh],
  ["ビルリウム", "维尔乌姆", "ヴィルリウム 的ASR变体", "observed_variant", "sample_20260829.srt"],
  ["業核", "业核", "3.2剧情术语", "official", official32Ja],
  ["ミスター・ゼット", "Z先生", "主持人称呼完整形式", "official", official32Ja],
  ["ミスターZ", "Z先生", "字幕中实际形式", "observed_variant", "sample_20260829.srt"],
  ["ミスターゼット", "Z先生", "无分隔符形式", "official_variant", official32Ja],
  ["シリオン", "希人", "世界观种族术语；三份字幕中译名漂移严重", "verified_context", "sample_20260822.srt; sample_20260829.srt"],
  ["パシャリ！フォーカスの陣！", "咔嚓！焦点对决！", "3.1活动名", "verified_context", "sample_20260822.srt"],
  ["ポテンシャル解放", "潜能解放", "系统功能名", "observed_missing", "sample_20260822.srt"],
  ["ポテ解", "潜能解放", "ポテンシャル解放 的玩家简称", "observed_variant", "sample_20260822.srt"],
  ["ゼロビー", "零比", "主播对零号·安比的简称", "streamer_alias", "sample_20260822.srt"],
  ["シルビー", "希尔比", "主播使用的简称", "streamer_alias", "sample_20260822.srt"],
  ["ライトさん", "莱特", "用敬称限定，避免误命中 スターライト", "safe_alias", "sample_20260822.srt"],
  ["ライト様", "莱特", "用敬称限定，避免误命中 スターライト", "safe_alias", "sample_20260822.srt"],
  ["ライト君", "莱特", "用敬称限定，避免误命中 スターライト", "safe_alias", "sample_20260822.srt"],
  ["ベンさん", "本", "用敬称限定，避免误命中 イベント", "safe_alias", "sample_20260822.srt"],
  ["セス君", "赛斯", "用敬称限定，避免误命中 アクセス", "safe_alias", "sample_20260822.srt"],
  ["セスさん", "赛斯", "用敬称限定，避免误命中 アクセス", "safe_alias", "sample_20260822.srt"],
];

const qaSamples = [
  ["シグリットさんプロ", "西格丽特小姐，专业的", "希格莉德小姐，太专业了", "ASR变体未收录"],
  ["シグニットの顔綺麗すぎて", "西格尼特的脸太好看了", "希格莉德的脸太好看了", "同一人名再次漂移"],
  ["ロクシー!", "罗克西！", "洛克茜！", "缺少3.2官方角色名"],
  ["ロクシーとは?", "洛希是谁？", "洛克茜是谁？", "同一角色缩写漂移"],
  ["クラレットさん", "克拉蕾特小姐", "克拉蕾小姐", "标准名的ASR变体"],
  ["ピロイスかっこいい", "皮洛伊丝好帅", "佩洛伊斯好帅", "标准名的ASR变体"],
  ["シーシア持ってない", "我没有希夏", "我没有希希芙", "标准名的ASR变体"],
  ["プロメイヤーも来て", "普罗梅耶也来了", "普罗米娅也来了", "标准名的ASR变体"],
  ["ベギナ通常衣装", "贝吉娜的普通服装", "维琳娜的普通服装", "标准名的ASR变体"],
  ["グレッシュさん", "格蕾丝", "格莉丝", "标准名的ASR变体"],
  ["イヤスの安否", "伊亚斯的安危", "伊埃斯的安危", "标准名的ASR变体"],
  ["ビルリウムにいる", "在比鲁里乌姆", "在维尔乌姆", "地区名缺失"],
  ["フリンツ工房", "弗林茨工坊", "弗林特工坊", "阵营官方名称缺失"],
  ["オオカミのシリオン", "狼的西里翁", "狼希人", "种族术语缺失"],
  ["エージェント", "代理人", "代理人", "ジェン→简 会误命中"],
  ["イベント", "活动", "活动", "ベン→本 会误命中"],
  ["スターライト", "星徽", "星徽", "ライト→莱特 会误命中"],
  ["ケンタッキーコラボ", "肯德基联动", "肯德基联动", "コラ→柯拉 会误命中"],
  ["アクセス", "访问", "访问", "セス→赛斯 会误命中"],
  ["ダンスバトル", "斗舞", "斗舞", "ダン→丹 会误命中"],
];

const originalText = (await fs.readFile(originalPath, "utf8")).replace(/^\uFEFF/, "");
const originalRows = originalText.split(/\r?\n/).filter(Boolean).map((line) => line.split("\t"));
const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
const removalSet = new Set(removals.map(([ja]) => ja));
const retainedRows = originalRows.filter(([ja]) => !removalSet.has(ja));
const existingTerms = new Set(retainedRows.map(([ja]) => ja));
const uniqueAdditions = additions.filter(([ja]) => !existingTerms.has(ja));
const finalRows = [...uniqueAdditions.map(([ja, zh]) => [ja, zh]), ...retainedRows];

const duplicateCheck = new Set();
for (const [ja] of finalRows) {
  if (duplicateCheck.has(ja)) throw new Error(`Duplicate Japanese term: ${ja}`);
  duplicateCheck.add(ja);
}

const improvedTsvPath = path.join(outputDir, "zenless-zone-zero-ja-zh_improved.tsv");
await fs.writeFile(improvedTsvPath, finalRows.map((row) => row.join("\t")).join("\n") + "\n", "utf8");

const hitMap = new Map(report.matchedTerms.map((item) => [item.ja, item]));
const rawSrt = (await Promise.all(
  ["sample_20260822.srt", "sample_20260825.srt", "sample_20260829.srt"].map((name) =>
    fs.readFile(path.join(inputDir, name), "utf8")
  )
)).join("\n");

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const added = workbook.worksheets.add("Added terms");
const removed = workbook.worksheets.add("Removed risky terms");
const qa = workbook.worksheets.add("QA samples");

summary.showGridLines = false;
summary.getRange("A1:F1").merge();
summary.getRange("A1").values = [["绝区零日中术语表改进报告"]];
summary.getRange("A2:F2").merge();
summary.getRange("A2").values = [["基于3份双语字幕的实际误译与ASR变体，并以官方角色/3.2资料校准译名"]];
summary.getRange("A4:A7").values = [["原始条目"], ["移除高风险短词"], ["新增/补充条目"], ["改进版条目"]];
summary.getRange("B4").values = [[originalRows.length]];
summary.getRange("B5").formulas = [["=COUNTA('Removed risky terms'!A2:A200)"]];
summary.getRange("B6").formulas = [["=COUNTA('Added terms'!A2:A200)"]];
summary.getRange("B7").formulas = [["=B4-B5+B6"]];
summary.getRange("D4:D7").values = [["字幕条目"], ["原表命中术语"], ["检测到的冲突"], ["其中由24个短词造成"]];
summary.getRange("E4").values = [[report.subtitles.reduce((sum, item) => sum + item.entryCount, 0)]];
summary.getRange("E5").values = [[report.matchedTerms.length]];
summary.getRange("E6").values = [[report.mismatchExamples.length]];
summary.getRange("E7").values = [[removals.reduce((sum, [ja]) => sum + (hitMap.get(ja)?.failureCount || 0), 0)]];
summary.getRange("A9:F9").merge();
summary.getRange("A9").values = [["关键结论"]];
summary.getRange("A10:F13").values = [
  ["1", "主要问题不是条目不足，而是短别名误命中", null, null, null, null],
  ["2", "24个高风险词贡献了179/180次检测冲突；删除后可显著减少错误强制译名", null, null, null, null],
  ["3", "新增项优先覆盖三份字幕真实出现的ASR变体，如シグリット、ロクシー、ピロイス", null, null, null, null],
  ["4", "TSV仍建议按当前批次筛选相关术语后送给LLM，不要每次注入全部条目", null, null, null, null],
];
summary.getRange("A15:F15").merge();
summary.getRange("A15").values = [["使用建议"]];
summary.getRange("A16:F18").values = [
  ["•", "翻译前先从日文批次中匹配术语，只向模型提供命中的条目和必要的官方全名。", null, null, null, null],
  ["•", "按日文词长度从长到短匹配；完整姓名优先于简称，避免部分字符串抢先命中。", null, null, null, null],
  ["•", "译后检查：原文命中术语时，中文必须包含指定译名；失败句单独重试。", null, null, null, null],
];

const addedRows = uniqueAdditions.map(([ja, zh, reason, type, source]) => [
  ja,
  zh,
  type,
  [...rawSrt.matchAll(new RegExp(ja.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"))].length,
  reason,
  source,
]);
added.getRange(`A1:F${addedRows.length + 1}`).values = [
  ["日文词/ASR变体", "统一中文", "类型", "样本出现次数", "纳入原因", "依据"],
  ...addedRows,
];

const removedRows = removals.map(([ja, zh, reason]) => {
  const hit = hitMap.get(ja) || {};
  return [ja, zh, hit.hitCount || 0, hit.failureCount || 0, hit.failureRate || 0, reason];
});
removed.getRange(`A1:F${removedRows.length + 1}`).values = [
  ["移除日文词", "原中文", "样本命中", "明显冲突", "冲突率", "移除原因"],
  ...removedRows,
];
removed.getRange(`E2:E${removedRows.length + 1}`).format.numberFormat = "0%";

qa.getRange(`A1:D${qaSamples.length + 1}`).values = [
  ["日文样例", "现有译文", "建议译文", "问题类型"],
  ...qaSamples,
];

for (const sheet of [summary, added, removed, qa]) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const used = sheet.getUsedRange();
  used.format.font = { name: "Microsoft YaHei", size: 10, color: "#1F2937" };
  used.format.verticalAlignment = "center";
}

summary.getRange("A1:F1").format = {
  fill: "#16324F",
  font: { name: "Microsoft YaHei", size: 18, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  rowHeight: 34,
};
summary.getRange("A2:F2").format = {
  fill: "#DCEAF5",
  font: { name: "Microsoft YaHei", size: 10, color: "#334155" },
  horizontalAlignment: "center",
  rowHeight: 26,
};
summary.getRange("A4:B7").format.borders = { preset: "outside", style: "thin", color: "#94A3B8" };
summary.getRange("D4:E7").format.borders = { preset: "outside", style: "thin", color: "#94A3B8" };
summary.getRange("A4:A7").format = { fill: "#E8F1F8", font: { bold: true, color: "#16324F" } };
summary.getRange("D4:D7").format = { fill: "#E8F1F8", font: { bold: true, color: "#16324F" } };
summary.getRange("B4:B7").format = { font: { bold: true, size: 13, color: "#0F766E" }, horizontalAlignment: "center" };
summary.getRange("E4:E7").format = { font: { bold: true, size: 13, color: "#B45309" }, horizontalAlignment: "center" };
summary.getRange("A9:F9").format = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF" } };
summary.getRange("A15:F15").format = { fill: "#B45309", font: { bold: true, color: "#FFFFFF" } };
summary.getRange("A10:A13").format = { font: { bold: true, color: "#0F766E" }, horizontalAlignment: "center" };
summary.getRange("A16:A18").format = { font: { bold: true, color: "#B45309" }, horizontalAlignment: "center" };
summary.getRange("B10:F13").merge(true);
summary.getRange("B16:F18").merge(true);
summary.getRange("A10:F13").format.wrapText = true;
summary.getRange("A16:F18").format.wrapText = true;
summary.getRange("A10:F13").format.rowHeight = 30;
summary.getRange("A16:F18").format.rowHeight = 34;
summary.getRange("A1:F18").format.columnWidth = 15;
summary.getRange("A:A").format.columnWidth = 12;
summary.getRange("B:B").format.columnWidth = 20;
summary.getRange("C:C").format.columnWidth = 12;
summary.getRange("D:D").format.columnWidth = 22;
summary.getRange("E:E").format.columnWidth = 14;
summary.getRange("F:F").format.columnWidth = 14;

for (const [sheet, rowCount, widths] of [
  [added, addedRows.length + 1, [30, 28, 18, 14, 46, 48]],
  [removed, removedRows.length + 1, [18, 18, 12, 12, 12, 54]],
  [qa, qaSamples.length + 1, [42, 42, 42, 28]],
]) {
  const header = sheet.getRange(`A1:${String.fromCharCode(64 + widths.length)}1`);
  header.format = {
    fill: "#16324F",
    font: { name: "Microsoft YaHei", size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    rowHeight: 28,
    borders: { preset: "outside", style: "thin", color: "#0F172A" },
  };
  sheet.getRange(`A2:${String.fromCharCode(64 + widths.length)}${rowCount}`).format.wrapText = true;
  sheet.getRange(`A2:${String.fromCharCode(64 + widths.length)}${rowCount}`).format.rowHeight = 34;
  widths.forEach((width, index) => {
    sheet.getRange(`${String.fromCharCode(65 + index)}:${String.fromCharCode(65 + index)}`).format.columnWidth = width;
  });
}
added.getRange(`C2:C${addedRows.length + 1}`).conditionalFormats.add("containsText", {
  text: "official",
  format: { fill: "#DCFCE7", font: { color: "#166534" } },
});
removed.getRange(`E2:E${removedRows.length + 1}`).conditionalFormats.add("colorScale", {
  colors: ["#FEF3C7", "#FCA5A5", "#DC2626"],
  thresholds: ["min", "50%", "max"],
});

const xlsxPath = path.join(outputDir, "zenless-zone-zero-glossary-review.xlsx");
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(xlsxPath);

const inspections = {};
for (const [name, range] of [["Summary", "A1:F18"], ["Added terms", `A1:F${addedRows.length + 1}`], ["Removed risky terms", `A1:F${removedRows.length + 1}`], ["QA samples", `A1:D${qaSamples.length + 1}`]]) {
  inspections[name] = (await workbook.inspect({ kind: "table", range: `${name}!${range}`, include: "values,formulas", tableMaxRows: 8, tableMaxCols: 6 })).ndjson;
  const preview = await workbook.render({ sheetName: name, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, `preview_${name.replaceAll(" ", "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
await fs.writeFile(path.join(outputDir, "verification.json"), JSON.stringify({
  originalRows: originalRows.length,
  removedRows: removals.length,
  addedRows: uniqueAdditions.length,
  finalRows: finalRows.length,
  inspections,
  formulaErrors: formulaErrors.ndjson,
}, null, 2), "utf8");

console.log(JSON.stringify({ improvedTsvPath, xlsxPath, originalRows: originalRows.length, removed: removals.length, added: uniqueAdditions.length, finalRows: finalRows.length }, null, 2));
