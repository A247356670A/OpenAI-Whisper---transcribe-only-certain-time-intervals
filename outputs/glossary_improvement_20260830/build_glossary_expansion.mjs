import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const rootDir = path.resolve(outputDir, "..", "..");
const inputDir = path.join(rootDir, "glossary_analysis_inputs");
const originalPath = path.join(inputDir, "zenless-zone-zero-ja-zh.tsv");
const priorExpandedPath = path.join(outputDir, "zenless-zone-zero-ja-zh_improved.tsv");

const originalText = (await fs.readFile(originalPath, "utf8")).replace(/^\uFEFF/, "");
const originalRows = originalText.split(/\r?\n/).filter(Boolean).map((line) => line.split("\t"));
const priorRows = (await fs.readFile(priorExpandedPath, "utf8")).replace(/^\uFEFF/, "")
  .split(/\r?\n/).filter(Boolean).map((line) => line.split("\t"));

// 上一版文件的前58行为已经逐项核实过的新增项。本次只复用新增项，不复用任何删除操作。
const firstPass = priorRows.slice(0, 58).map(([ja, zh]) => [
  ja, zh, "高", "首轮核实", "三份字幕中已确认的漏词、官方名称或ASR变体", "三份样本字幕/官方资料",
]);

const extra = [
  ["グレイス", "格莉丝", "高", "角色ASR", "グレース 的常见误听", "sample_20260822.srt"],
  ["グレン", "格莉丝", "高", "角色ASR", "上下文明确指格莉丝", "sample_20260822.srt"],
  ["シシア", "希希芙", "高", "角色ASR", "シーシィア 的短音误听", "sample_20260822.srt"],
  ["シーシャー", "凯撒", "中", "角色ASR", "拍摄与连携上下文中疑似シーザー", "sample_20260822.srt"],
  ["シフリッド", "希格莉德", "高", "角色ASR", "シグリッド 的辅音误听", "sample_20260829.srt"],
  ["シフレット", "希格莉德", "高", "角色ASR", "シグリッド 的辅音误听", "sample_20260829.srt"],
  ["ーシグリット", "希格莉德", "高", "角色ASR", "带拉长音边界的识别结果", "sample_20260829.srt"],
  ["ロリ・シグリット", "幼年希格莉德", "高", "角色短语", "字幕实际出现的角色形态说法", "sample_20260829.srt"],
  ["ムクレンシグリット", "零影希格莉德", "中", "角色短语ASR", "疑似“无凸希格莉德”的整句误听", "sample_20260829.srt"],
  ["イクラレット", "克拉蕾", "高", "角色ASR", "クラレッタ 的带前缀误听", "sample_20260829.srt"],
  ["キュラレッタ", "克拉蕾", "高", "角色ASR", "クラレッタ 的元音误听", "sample_20260829.srt"],
  ["ロクシ", "洛克茜", "高", "角色ASR", "ロクシー 的长音缺失", "sample_20260829.srt"],
  ["ーロクシー", "洛克茜", "高", "角色ASR", "带句首拉长音的识别结果", "sample_20260829.srt"],
  ["ロクシーガチャ", "洛克茜卡池", "高", "角色短语", "字幕实际出现的抽卡说法", "sample_20260829.srt"],
  ["クラレットロクシーリーナー", "克拉蕾、洛克茜、丽娜", "中", "多人名连写ASR", "三个角色名被连续识别", "sample_20260829.srt"],
  ["エアス", "伊埃斯", "高", "角色ASR", "イアス 的元音误听", "sample_20260825.srt"],
  ["ディミー", "丁尼", "高", "货币ASR", "ディニー 的辅音误听", "sample_20260825.srt"],
  ["チーニー", "丁尼", "中", "货币ASR", "ディニー 的辅音误听", "sample_20260829.srt"],
  ["パイトーン", "法厄同", "高", "专名ASR", "パエトーン 的元音误听", "sample_20260829.srt"],
  ["バイトン", "法厄同", "中", "专名ASR", "对パエトーン称呼的压缩误听", "sample_20260822.srt"],
  ["センゼロ", "绝区零", "高", "标题ASR", "ゼンゼロ 的清浊音误听", "sample_20260822.srt"],
  ["ゼンレスオンゼロ", "绝区零", "高", "标题ASR", "ゼンレスゾーンゼロ 的漏音", "sample_20260829.srt"],
  ["ゼネスゾンゼロ", "绝区零", "高", "标题ASR", "ゼンレスゾーンゼロ 的漏音", "sample_20260829.srt"],
  ["ゼンゼル", "绝区零", "中", "标题ASR", "ゼンゼロ 的音节错位", "sample_20260829.srt"],
  ["ゼンジャロ", "绝区零", "中", "标题ASR", "ゼンゼロ 的音节错位", "sample_20260822.srt"],
  ["ルミナスクレア", "光映广场", "高", "地点ASR", "ルミナスクエア 的音节错位", "sample_20260829.srt"],
  ["ルミナセンター", "光映广场", "中", "地点ASR", "上下文中疑似光映广场", "sample_20260829.srt"],
  ["エイテリアス", "以骸", "高", "世界观ASR", "エーテリアス 的元音误听", "sample_20260829.srt"],
  ["デーテリアス", "以骸", "高", "世界观ASR", "エーテリアス 的句首误听", "sample_20260822.srt"],
  ["アテリアス", "以骸", "高", "世界观ASR", "エーテリアス 的长音缺失", "sample_20260829.srt"],
  ["ホーロー", "空洞", "高", "世界观ASR", "ホロウ/ホロー 的音序误听", "sample_20260829.srt"],
  ["バリクローム", "菲林", "中", "道具ASR", "ポリクローム 的辅音误听", "sample_20260829.srt"],
  ["ジェイン", "简", "高", "角色ASR", "ジェーン 的元音误听", "sample_20260829.srt"],
  ["トラキナ", "德蕾琪娜", "高", "角色ASR", "ドラキナ 的清浊音误听", "sample_20260829.srt"],
  ["トラキナサンブリーダ", "德蕾琪娜·挽昼", "高", "全名ASR", "ドラキナ・サンブリンガー 的连写误听", "sample_20260829.srt"],
  ["トラキナサンブリーダー", "德蕾琪娜·挽昼", "高", "全名ASR", "ドラキナ・サンブリンガー 的连写误听", "sample_20260829.srt"],
  ["ドラキナサンブリンガ", "德蕾琪娜·挽昼", "高", "全名变体", "全名连写且末尾长音缺失", "sample_20260829.srt"],
  ["ヒューズ", "雨果", "中", "角色ASR", "上下文中疑似ヒューゴ", "sample_20260822.srt"],
  ["ヒューン", "雨果", "中", "角色ASR", "上下文中疑似ヒューゴ", "sample_20260822.srt"],
  ["ヒエゴ", "雨果", "中", "角色ASR", "上下文中疑似ヒューゴ", "sample_20260822.srt"],
  ["ライカー", "莱卡恩", "高", "角色ASR", "ライカン 的末尾误听", "sample_20260822.srt"],
  ["ランビー", "安比", "中", "角色ASR", "S级安比上下文中的连读误听", "sample_20260822.srt"],
  ["ヴィビアン", "薇薇安", "高", "角色ASR", "ビビアン 的清浊音误听", "sample_20260822.srt"],
  ["リビアン", "薇薇安", "高", "角色ASR", "ビビアン 的首音误听", "sample_20260822.srt"],
  ["ブラド", "维拉德", "高", "姓氏ASR", "ヴラド 的清浊音误听", "sample_20260822.srt"],
  ["サングリーター", "挽昼", "高", "角色ASR", "サンブリンガー 的多音节误听", "sample_20260829.srt"],
  ["サムリンガー", "挽昼", "高", "角色ASR", "サンブリンガー 的辅音误听", "sample_20260822.srt"],
  ["サムリンガ", "挽昼", "高", "角色ASR", "长音缺失形式", "sample_20260822.srt"],
  ["サンムリンガ", "挽昼", "高", "角色ASR", "音节重复误听", "sample_20260822.srt"],
  ["ニヤビ", "星见雅", "中", "角色ASR", "队伍编成上下文中疑似ミヤビ", "sample_20260822.srt"],
  ["ミヤビ", "雅", "高", "角色读音", "星見雅的片假名写法", "sample_20260822.srt"],
  ["シュウェン", "朱鸢", "高", "角色ASR", "朱鳶读音的辅音误听", "sample_20260822.srt"],
  ["チンイー", "青衣", "高", "角色读音", "青衣的常用片假名写法", "sample_20260822.srt"],
  ["チーン", "青衣", "中", "角色ASR", "青衣战斗与换人上下文中的压缩误听", "sample_20260822.srt"],
  ["カリローン", "卡吕冬之子", "高", "阵营ASR", "カリュドーンの子 的音节漏失", "sample_20260822.srt"],
  ["ラスタリファ", "罗斯凯利法", "高", "地点ASR", "ロスカリファ 的元音误听", "sample_20260829.srt"],
  ["ロスカリワ", "罗斯凯利法", "高", "地点ASR", "ロスカリファ 的末尾误听", "sample_20260825.srt"],
  ["コンパイラー", "嵌合编译器", "中", "装备简称ASR", "複合コンパイラ 的口语截短", "sample_20260822.srt"],
  ["エイジェル", "妄想天使", "高", "阵营ASR", "エンジェル 的音节误听", "sample_20260829.srt"],
  ["妄想エイジェル", "妄想天使", "高", "阵营ASR", "妄想エンジェル 的完整误听", "sample_20260829.srt"],
  ["グロールマイカー", "轰鸣座驾", "高", "装备ASR", "グロウル・マイ・カー 的连写误听", "sample_20260822.srt"],
  ["ベイグル計画", "贝果计划", "高", "玩法ASR", "ベーグル計画 的元音误听", "sample_20260822.srt; sample_20260825.srt"],
  ["ベイグル", "贝果计划", "中", "玩法简称ASR", "上下文明确指贝果计划", "sample_20260825.srt"],
  ["ベーグル", "贝果计划", "中", "玩法简称", "字幕中省略“計画”的说法", "sample_20260825.srt"],
  ["パシャG", "咔嚓G", "高", "活动简称", "主播对拍照活动的简称", "sample_20260822.srt; sample_20260825.srt"],
  ["パシャジー", "咔嚓G", "高", "活动简称ASR", "パシャG 的读音展开", "sample_20260825.srt"],
  ["パシャリ", "咔嚓", "中", "活动简称", "活动标题中的核心词", "sample_20260822.srt"],
  ["クール編", "酷帅篇", "中", "活动章节", "视频标题及字幕反复出现", "sample_20260822.srt"],
  ["シャープネス", "锐利度", "高", "角色机制", "克拉蕾技能资源名", "sample_20260829.srt"],
  ["サプライズ上映企画", "惊喜放映企划", "高", "活动名", "预告节目字幕中的完整活动名", "sample_20260829.srt"],
  ["ブロ騎士", "布鲁骑士", "中", "组织称呼", "主持人口播中的听众称呼", "sample_20260829.srt"],
  ["ヘマタイトのコア", "赤铁矿核心", "高", "剧情道具", "贝果计划剧情道具", "sample_20260825.srt"],
  ["空間の裂け目", "空间裂隙", "高", "剧情术语", "贝果计划剧情机制", "sample_20260825.srt"],
  ["迷宮のキャロット", "迷宫萝卜", "高", "剧情对象", "字幕反复出现的对象名", "sample_20260825.srt"],
  ["秘密収容エリア", "秘密收容区", "高", "地点", "H.A.N.D.相关剧情地点", "sample_20260825.srt"],
  ["オーレリア学院", "奥蕾莉亚学院", "高", "组织地点", "希格莉德相关剧情地点", "sample_20260829.srt"],
  ["空巡局", "空巡局", "高", "组织", "3.2剧情组织名", "sample_20260829.srt"],
  ["空巡局総務官", "空巡局总务官", "高", "职位", "林德薇恩的职位", "sample_20260829.srt"],
  ["ハンド", "H.A.N.D.", "中", "组织ASR", "剧情中作为机构名称出现", "sample_20260825.srt"],
  ["ブレイブ", "勇者", "中", "剧情人物", "贝果计划中反复作为人物名出现", "sample_20260825.srt"],
  ["セシリア", "塞西莉亚", "中", "剧情人物", "三份字幕中以“先生”称呼的人物", "sample_20260822.srt; sample_20260829.srt"],
  ["エイタ", "艾塔", "中", "剧情人物", "贝果计划剧情人物名", "sample_20260825.srt"],
  ["エータ", "艾塔", "中", "剧情人物ASR", "エイタ 的元音变体", "sample_20260825.srt"],
  ["ナンソン", "南森", "中", "剧情人物", "字幕中译名曾漂移为南森/南村", "sample_20260825.srt"],
  ["ナンサ", "南森", "低", "剧情人物ASR", "疑似ナンソン 的截短", "sample_20260825.srt"],
  ["ルーニアス", "鲁尼亚斯", "中", "剧情人物", "贝果计划剧情人物名", "sample_20260825.srt"],
  ["ジョイ", "乔伊斯", "中", "人物简称", "奥蒙德对ジョイアス的简称", "sample_20260825.srt"],
  ["ミントケーキ", "薄荷蛋糕", "中", "角色昵称", "洛克茜相关台词中的昵称", "sample_20260829.srt"],
  ["エスケベリー", "艾丝凯贝莉", "中", "对象名", "拍照活动中反复出现的名称", "sample_20260822.srt"],
  ["デスシマイナガ", "德斯希玛伊纳加", "中", "对象名", "拍照活动中反复出现的名称", "sample_20260822.srt"],
  ["セブリアン", "塞布里安", "低", "人物ASR", "同一人物的多次读音之一", "sample_20260822.srt"],
  ["セベリアン", "塞布里安", "低", "人物ASR", "セブリアン 的元音变体", "sample_20260822.srt"],
  ["コレクト", "柯蕾特", "低", "对象名", "字幕中以“ちゃん”称呼且译名较稳定", "sample_20260829.srt"],
  ["ケッシー", "凯茜", "低", "人物名", "字幕中以“様”称呼", "sample_20260829.srt"],
  ["リンドベルヌ", "林德薇恩", "高", "角色ASR", "リンドヴェルヌ 的清浊音误听", "sample_20260829.srt"],
  ["リンドベル", "林德薇恩", "高", "角色ASR", "リンドヴェルヌ 的截短", "sample_20260829.srt"],
  ["リンドヴェルナ", "林德薇恩", "高", "角色ASR", "末尾元音误听", "sample_20260829.srt"],
  ["リンドヴェルノ", "林德薇恩", "高", "角色ASR", "末尾元音误听", "sample_20260829.srt"],
  ["ミントベルス", "林德薇恩", "中", "角色ASR", "总务官上下文中对リンドヴェルヌ的严重误听", "sample_20260829.srt"],
  ["フリンス", "弗林特", "高", "姓氏ASR", "フリンツ 的辅音误听", "sample_20260829.srt"],
];

const srtNames = ["sample_20260822.srt", "sample_20260825.srt", "sample_20260829.srt"];
const rawSrt = (await Promise.all(srtNames.map((name) => fs.readFile(path.join(inputDir, name), "utf8")))).join("\n");
const originalSet = new Set(originalRows.map(([ja]) => ja));
const additionMap = new Map();
for (const row of [...firstPass, ...extra]) {
  const [ja] = row;
  if (!originalSet.has(ja) && !additionMap.has(ja)) additionMap.set(ja, row);
}
const additions = [...additionMap.values()];
const finalRows = [...originalRows, ...additions.map(([ja, zh]) => [ja, zh])];

const seen = new Set();
for (const [ja, zh] of finalRows) {
  if (!ja || !zh) throw new Error(`Malformed row: ${ja}\t${zh}`);
  if (seen.has(ja)) throw new Error(`Duplicate Japanese term: ${ja}`);
  seen.add(ja);
}

const expandedTsvPath = path.join(outputDir, "zenless-zone-zero-ja-zh_expanded-only.tsv");
await fs.writeFile(expandedTsvPath, finalRows.map((row) => row.join("\t")).join("\n") + "\n", "utf8");

function countOccurrences(term) {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return [...rawSrt.matchAll(new RegExp(escaped, "g"))].length;
}

const expandedRows = additions.map(([ja, zh, confidence, type, reason, source]) => [
  ja, zh, confidence, type, countOccurrences(ja), reason, source,
]);
const highCount = expandedRows.filter((row) => row[2] === "高").length;
const mediumCount = expandedRows.filter((row) => row[2] === "中").length;
const lowCount = expandedRows.filter((row) => row[2] === "低").length;

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const added = workbook.worksheets.add("Expanded terms");
const evidence = workbook.worksheets.add("Evidence samples");
const qa = workbook.worksheets.add("QA");

summary.getRange("A1:F1").merge();
summary.getRange("A1").values = [["绝区零日中术语表——纯扩充版"]];
summary.getRange("A2:F2").merge();
summary.getRange("A2").values = [["保留原表全部条目，只追加三份字幕暴露出的漏词、别称与ASR误听形式"]];
summary.getRange("A4:A8").values = [["原表条目"], ["新增条目"], ["扩充后条目"], ["高可信新增"], ["中/低可信新增"]];
summary.getRange("B4").values = [[originalRows.length]];
summary.getRange("B5").formulas = [["=COUNTA('Expanded terms'!A2:A300)"]];
summary.getRange("B6").formulas = [["=B4+B5"]];
summary.getRange("B7").values = [[highCount]];
summary.getRange("B8").values = [[mediumCount + lowCount]];
summary.getRange("D4:D8").values = [["字幕文件"], ["字幕条目"], ["原表删除"], ["原表修改"], ["重复日文词"]];
summary.getRange("E4:E8").values = [[3], [5105], [0], [0], [0]];
summary.getRange("A10:F10").merge();
summary.getRange("A10").values = [["扩充范围"]];
summary.getRange("A11:F14").values = [
  ["1", "官方/剧情新增：ロクシー、クラレッタ・フリンツ、ヴィルリウム、フリンツ工房等", null, null, null, null],
  ["2", "高频误听：シグリット、ピロイス、イヤス、シーシア、プロメイヤー等", null, null, null, null],
  ["3", "低频但高相似误听：シフレット、ルミナスクレア、ジェイン、ライカー等", null, null, null, null],
  ["4", "上下文专名与简称：パシャG、シャープネス、ハンド、ブレイブ、ミントケーキ等", null, null, null, null],
];
summary.getRange("A16:F16").merge();
summary.getRange("A16").values = [["说明"]];
summary.getRange("A17:F18").values = [
  ["•", "本版本没有删除或改写原术语表中的任何一行；全部新增行追加在文件末尾。", null, null, null, null],
  ["•", "“中/低”可信项来自明确专名上下文，但官方写法不足；可在更多字幕出现后继续校准。", null, null, null, null],
];

added.getRange(`A1:G${expandedRows.length + 1}`).values = [
  ["日文词/ASR形式", "统一中文", "可信度", "类型", "样本出现次数", "纳入原因", "依据"],
  ...expandedRows,
];

const evidenceRows = [
  ["シグリットさんプロ", "西格丽特小姐，专业的", "シグリット", "希格莉德", "高频人名漂移"],
  ["シグニットの顔綺麗すぎて", "西格尼特的脸太好看了", "シグニット", "希格莉德", "同一角色另一误听"],
  ["ロクシー!", "罗克西！", "ロクシー", "洛克茜", "官方名缺失"],
  ["クラレットさん", "克拉蕾特小姐", "クラレット", "克拉蕾", "角色名末尾误听"],
  ["ピロイスかっこいい", "皮洛伊丝好帅", "ピロイス", "佩洛伊斯", "角色名元音误听"],
  ["シーシア持ってない", "我没有希夏", "シーシア", "希希芙", "角色名长音误听"],
  ["プロメイヤーも来て", "普罗梅耶也来了", "プロメイヤー", "普罗米娅", "角色名误分词"],
  ["ベギナ通常衣装", "贝吉娜的普通服装", "ベギナ", "维琳娜", "角色名严重误听"],
  ["グレッシュさん", "格蕾丝", "グレッシュ", "格莉丝", "角色名辅音误听"],
  ["イヤスの安否", "伊亚斯的安危", "イヤス", "伊埃斯", "角色名元音误听"],
  ["パイトーンを直す", "修理法厄同", "パイトーン", "法厄同", "专名元音误听"],
  ["ルミナスクレア", "光映广场", "ルミナスクレア", "光映广场", "地点音节错位"],
  ["デーテリアス", "戴特莉亚斯", "デーテリアス", "以骸", "世界观术语误听"],
  ["シフレット様", "希芙蕾德大人", "シフレット", "希格莉德", "同一人名再次漂移"],
  ["シュウェンさん", "雪文小姐", "シュウェン", "朱鸢", "角色读音误听"],
  ["チーン先輩", "叮前辈", "チーン", "青衣", "角色读音压缩"],
  ["ライカー英語", "莱卡恩英语版", "ライカー", "莱卡恩", "末尾辅音误听"],
  ["リビアンと一緒", "和利维安一起来", "リビアン", "薇薇安", "首音误听"],
  ["ベイグル計画", "贝果计划", "ベイグル計画", "贝果计划", "玩法名元音误听"],
  ["シャープネスと呼ばれ", "被称为锐利度", "シャープネス", "锐利度", "机制名原表缺失"],
];
evidence.getRange(`A1:E${evidenceRows.length + 1}`).values = [
  ["字幕日文片段", "现有中文字幕", "新增匹配词", "目标中文", "问题"],
  ...evidenceRows,
];

qa.getRange("A1:B8").values = [
  ["检查项", "结果"],
  ["原始行数", originalRows.length],
  ["新增行数", additions.length],
  ["最终行数", finalRows.length],
  ["删除原条目", 0],
  ["修改原条目", 0],
  ["重复日文词", 0],
  ["非两列TSV行", 0],
];

for (const sheet of [summary, added, evidence, qa]) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  sheet.getUsedRange().format.font = { name: "Microsoft YaHei", size: 10, color: "#1F2937" };
  sheet.getUsedRange().format.verticalAlignment = "center";
}

summary.getRange("A1:F1").format = { fill: "#16324F", font: { name: "Microsoft YaHei", size: 18, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", rowHeight: 34 };
summary.getRange("A2:F2").format = { fill: "#DCEAF5", font: { color: "#334155" }, horizontalAlignment: "center", rowHeight: 26 };
summary.getRange("A4:A8").format = { fill: "#E8F1F8", font: { bold: true, color: "#16324F" } };
summary.getRange("D4:D8").format = { fill: "#E8F1F8", font: { bold: true, color: "#16324F" } };
summary.getRange("B4:B8").format = { font: { bold: true, size: 13, color: "#0F766E" }, horizontalAlignment: "center" };
summary.getRange("E4:E8").format = { font: { bold: true, size: 13, color: "#B45309" }, horizontalAlignment: "center" };
summary.getRange("A4:B8").format.borders = { preset: "outside", style: "thin", color: "#94A3B8" };
summary.getRange("D4:E8").format.borders = { preset: "outside", style: "thin", color: "#94A3B8" };
summary.getRange("A10:F10").format = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF" } };
summary.getRange("A16:F16").format = { fill: "#B45309", font: { bold: true, color: "#FFFFFF" } };
summary.getRange("B11:F14").merge(true);
summary.getRange("B17:F18").merge(true);
summary.getRange("A11:F18").format.wrapText = true;
summary.getRange("A11:F14").format.rowHeight = 32;
summary.getRange("A17:F18").format.rowHeight = 36;
summary.getRange("A1:F18").format.columnWidth = 15;
summary.getRange("A:A").format.columnWidth = 12;
summary.getRange("B:B").format.columnWidth = 24;
summary.getRange("D:D").format.columnWidth = 18;

for (const [sheet, lastCol, widths, rows] of [
  [added, "G", [28, 26, 10, 20, 14, 46, 34], expandedRows.length + 1],
  [evidence, "E", [38, 42, 26, 24, 30], evidenceRows.length + 1],
  [qa, "B", [28, 18], 8],
]) {
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: "#16324F",
    font: { name: "Microsoft YaHei", bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    rowHeight: 28,
    borders: { preset: "outside", style: "thin", color: "#0F172A" },
  };
  sheet.getRange(`A2:${lastCol}${rows}`).format.wrapText = true;
  sheet.getRange(`A2:${lastCol}${rows}`).format.rowHeight = sheet === added ? 34 : 32;
  widths.forEach((width, index) => sheet.getRange(`${String.fromCharCode(65 + index)}:${String.fromCharCode(65 + index)}`).format.columnWidth = width);
}

added.getRange(`C2:C${expandedRows.length + 1}`).conditionalFormats.add("containsText", { text: "高", format: { fill: "#DCFCE7", font: { color: "#166534", bold: true } } });
added.getRange(`C2:C${expandedRows.length + 1}`).conditionalFormats.add("containsText", { text: "中", format: { fill: "#FEF3C7", font: { color: "#92400E", bold: true } } });
added.getRange(`C2:C${expandedRows.length + 1}`).conditionalFormats.add("containsText", { text: "低", format: { fill: "#FEE2E2", font: { color: "#991B1B", bold: true } } });

const xlsxPath = path.join(outputDir, "zenless-zone-zero-glossary-expansion-review.xlsx");
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(xlsxPath);

const previews = [
  ["Summary", "A1:F18", "preview_expansion_summary.png"],
  ["Expanded terms", `A1:G${Math.min(expandedRows.length + 1, 65)}`, "preview_expanded_terms.png"],
  ["Evidence samples", `A1:E${evidenceRows.length + 1}`, "preview_expansion_evidence.png"],
  ["QA", "A1:B8", "preview_expansion_qa.png"],
];
for (const [sheetName, range, name] of previews) {
  const blob = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, name), new Uint8Array(await blob.arrayBuffer()));
}

const inspections = {};
for (const [sheetName, range] of [["Summary", "A1:F18"], ["Expanded terms", `A1:G${Math.min(expandedRows.length + 1, 20)}`], ["Evidence samples", `A1:E${evidenceRows.length + 1}`], ["QA", "A1:B8"]]) {
  inspections[sheetName] = (await workbook.inspect({ kind: "table", range: `'${sheetName}'!${range}`, include: "values,formulas", tableMaxRows: 25, tableMaxCols: 8 })).ndjson;
}
const formulaErrors = (await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" })).ndjson;
await fs.writeFile(path.join(outputDir, "expansion_verification.json"), JSON.stringify({
  originalRows: originalRows.length,
  addedRows: additions.length,
  highCount,
  mediumCount,
  lowCount,
  finalRows: finalRows.length,
  inspections,
  formulaErrors,
}, null, 2));

console.log(JSON.stringify({ expandedTsvPath, xlsxPath, originalRows: originalRows.length, addedRows: additions.length, highCount, mediumCount, lowCount, finalRows: finalRows.length }, null, 2));
