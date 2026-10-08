import fs from "node:fs";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1")), "..");
const raw = fs.readFileSync(path.join(root, "glossary_analysis_inputs", "sample_20260829.srt"), "utf8").replace(/^\uFEFF/, "");
const entries = raw.split(/\r?\n\s*\r?\n/).filter(Boolean).map((block) => {
  const lines = block.split(/\r?\n/);
  return { index: lines[0], time: lines[1], ja: lines[2] || "", zh: lines.slice(3).join("\n") };
});

const groups = [
  ["希格莉德", /西格|希格莉|西弗莱德|希芙蕾德/, /シグリ|シフリ|シフレ/],
  ["洛克茜", /洛克茜|洛克西|罗克茜|罗克西|洛希|卢克西|露西/, /ロクシ|ロキシ|ルーシー/],
  ["克拉蕾", /克拉蕾|克拉雷|伊卡莱特/, /クラレ|イクラレ/],
  ["林德薇恩", /林德薇恩|铃德|铃多|林德伯|林德贝|敏特贝尔|宁多贝尔/, /リンド|ニンド|ミントベル/],
  ["弗林特", /弗林特|弗林茨|弗林斯|弗铃茨/, /フリン|フリンス/],
  ["普罗米娅", /普罗米娅|普罗梅|造梦机|Pro Mayor/, /プロメ/],
  ["蕾米埃尔", /蕾米埃尔/, /レミ|メミ/],
  ["Z先生", /Z先生|泽特先生/, /ミスター[・･]?ゼット|ミスターZ/],
  ["以骸", /以骸|艾特里亚斯|阿特利亚斯|戴特莉亚斯/, /エーテリアス|エイテリアス|アテリアス|デーテリアス/],
  ["希人", /希人|西里翁|锡里昂/, /シリオン/],
  ["德蕾琪娜", /德蕾琪娜|特拉基纳/, /ドラキナ|トラキナ/],
  ["挽昼", /挽昼|桑格利特|桑布雷德/, /サンブリン|サンムリン|サムリン|サングリ/],
  ["法厄同", /法厄同|派特恩/, /パエト|パイト|バイト/],
  ["薇薇安", /薇薇安|利维安/, /ビビアン|ヴィビアン|リビアン/],
  ["朱鸢", /朱鸢|雪文/, /朱鳶|シュウェン/],
  ["青衣", /青衣|叮前辈/, /青衣|チンイ|チーン/],
  ["雨果", /雨果|希耶戈/, /ヒューゴ|ヒュゴ|ヒューズ|ヒューン|ヒエゴ/],
];

const flags = [];
for (const entry of entries) {
  for (const [name, zhRe, jaRe] of groups) {
    if (zhRe.test(entry.zh) && !jaRe.test(entry.ja)) flags.push({ ...entry, name });
  }
}
console.log(JSON.stringify(flags, null, 2));
