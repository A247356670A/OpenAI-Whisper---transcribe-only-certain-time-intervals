import fs from "node:fs/promises";
import path from "node:path";

const workDir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const root = path.resolve(workDir, "..");
const inputPath = path.join(root, "glossary_analysis_inputs", "sample_20260829.srt");
const outputDir = path.join(root, "outputs", "subtitle_precision_20260830");
const outputPath = path.join(outputDir, "20260829_ZZZ_Ver3.2_zh_precise_dual.srt");
const reviewPath = path.join(outputDir, "20260829_ZZZ_Ver3.2_zh_precise_changes.md");

const raw = (await fs.readFile(inputPath, "utf8")).replace(/^\uFEFF/, "");
const newline = raw.includes("\r\n") ? "\r\n" : "\n";
const blocks = raw.split(/\r?\n\s*\r?\n/);

const entries = blocks.map((block, blockIndex) => {
  const lines = block.split(/\r?\n/);
  const timeIndex = lines.findIndex((line) => line.includes("-->"));
  return {
    blockIndex,
    index: lines[0] || "",
    timeIndex,
    time: timeIndex >= 0 ? lines[timeIndex] : "",
    ja: timeIndex >= 0 ? (lines[timeIndex + 1] || "") : "",
    zh: timeIndex >= 0 ? lines.slice(timeIndex + 2).join(newline) : "",
    lines,
  };
});

const manual = new Map([
  ["150", ["这是马车专用路线。", "修正日文ASR导致的“马蹄音效路线”幻觉；结合驾驶场景还原"]],
  ["158", ["系好安全带。", "修正“リンドベルト”误听引发的虚构专名；结合驾驶上下文还原"]],
  ["379", ["咦，这是幼年希格莉德？", "统一角色形态短语“幼年希格莉德”"]],
  ["406", ["就连以骸蜂拥而来时……", "移除日文ASR杂音“エネルギー君”，统一世界观术语"]],
  ["435", ["太棒了，林德薇恩大人！这个怎么样？", "统一人名并清除中文行残留的日文假名"]],
  ["439", ["哎呀，这样的林德薇恩大人确实会很受欢迎。", "统一人名；删去无法由上下文支持的“终结者”幻觉"]],
  ["530", ["真想要啊，这个零影希格莉德。", "识别“ムクレン”为“无凸/零影”游戏口语并统一人名"]],
  ["549", ["这些说不定都是林德薇恩曾用来教导、鼓励空巡局时期的希格莉德的话。", "结合前后文重译严重失真的整句并统一两个人名"]],
  ["570", ["抱歉，我刚才在后台看得很开心，还截了图，发了条“希格莉德也太美了”的动态。", "清除中文行残留日文，并统一人名"]],
  ["599", ["呼……弗林特家那种阳光开朗的感觉，居然会变得这么阴沉……", "统一姓氏；修正“西式采光”的机械直译"]],
  ["626", ["看来大小姐比想象中更让人操心啊……", "修正“手被烫伤”的字面幻觉；手を焼く为“令人操心”"]],
  ["630", ["哼，洛克茜，看来Z先生的礼仪课还得继续上啊……", "统一人名并修正“滚动课程”幻觉；结合对话场景重译"]],
  ["634", ["啊，大小姐和侍从这种组合太戳我了。", "修正“住户”误译；结合主仆对话上下文"]],
  ["640", ["弗林特工坊！？", "结合下一句和3.2阵营名，修正严重ASR误听"]],
  ["642", ["弗林特工坊？", "统一3.2阵营正式译名"]],
  ["716", ["哈哈哈，罗斯凯利法虽是黄金之乡，但负责生产的弗林特工坊似乎也非常重要。", "统一阵营名；将“强金”按黄金产地上下文还原"]],
  ["733", ["失踪的黄金。", "结合连续剧情，将ASR“豪菌”还原为“黄金”"]],
  ["735", ["正是这件事。黄金与弗林特工坊……", "移除“黄巾/弗林斯科”幻觉，并保留原句未完语气"]],
  ["736", ["入侵者难道就是那个……", "结合伪装与盗金上下文，将“吃新药”幻觉还原为入侵者"]],
  ["738", ["偷走黄金并据为己有。", "结合上下文，将ASR“豪菌”还原为“黄金”"]],
  ["739", ["确实是入侵者。", "结合连续语境，将“吃了新药”幻觉还原"]],
  ["831", ["一点也不可爱，眼神还鬼鬼祟祟的。", "删除日文原句中不存在的“露西”姓名幻觉"]],
  ["910", ["克拉蕾的技能伤害不是按攻击力，而是按防御力计算。", "结合3.2角色机制资料，修正“包拯伤害”等ASR/翻译幻觉"]],
  ["926", ["阿迪奥努斯廷斯。", "日文源行本身听写不明；仅做保守音译，清除无关的“汀曼大师”和假名残留"]],
  ["928", ["有反击支援！", "将疑似“カウンター支援”的ASR误听按战斗上下文还原"]],
  ["937", ["这种资源叫作“锐利度”，克拉蕾发动特殊技时会消耗它。", "补全角色名和机制关系，避免代词造成专名漂移"]],
  ["1026", ["总之，先在实战中看看洛克茜吧。", "结合后续实战演示，修正无依据的“鞍具”幻觉"]],
  ["1032", ["克拉蕾、洛克茜、丽娜。", "拆分连写的三个人名并统一官方译名"]],
  ["1069", ["已经是普罗米娅了。", "将角色名误译“职业选手”还原"]],
  ["1122", ["“将举办惊喜放映企划。活动期间登录并完成任务，即可免费领取一套心仪的服装，还可获得菲林、头像、电池等奖励。”", "将バリクローム按游戏货币统一为“菲林”，并收紧句意"]],
  ["1197", ["话说妄想天使现在不是也有活动嘛。", "统一阵营名，修正“妄想代理人”"]],
  ["1221", ["一直看这个的话，不也会开始想要普罗米娅吗？", "将角色名误译“造梦机”还原"]],
  ["1234", ["即使撤离失败，寄存的物资也会保留下来。", "结合玩法说明，将“灌木”幻觉还原为物资"]],
  ["1238", ["希望我“不小心”送出去的黄金，能和大小姐收集到的物资价值相当。才不是不小心呢！", "结合黄金剧情修正“合金”漂移并保留吐槽语气"]],
  ["1239", ["这大概就是洛克茜如此信任克拉蕾的原因吧。", "结合后句“两人的关系”重译严重失真句并统一人名"]],
  ["1529", ["谨遵吩咐。所谓洛克茜……", "统一人名并修正“洛克希塔”粘连幻觉"]],
  ["1578", ["还有洛克茜的壁纸也特别棒，真的好可爱。", "统一人名并删除日文不支持的“妖艳”扩写"]],
  ["1583", ["是啊，洛克茜本来就不是暴露度很高的类型；真露到那种程度，做这事的我们可就要被抓了。", "统一人名并修正“露出诺姆”机械转写"]],
  ["1687", ["这张主视觉图里的克拉蕾帅得难以置信。", "将“キービジュ”按上下文还原为主视觉图，并统一人名"]],
  ["1795", ["那么各位，我们下次克拉蕾、洛克茜卡池直播再见。", "还原两个角色名，修正“被抢/罗克希”幻觉"]],
]);

const ruleGroups = [
  {
    ja: /シグリ|シフリ|シフレ/,
    zh: [[/西格莉特|西格丽特|希格莉特|西格尼特|西弗莱德|希芙蕾德|シグリット/g, "希格莉德"]],
    reason: "统一希格莉德的ASR变体译名",
  },
  {
    ja: /リンド|ニンド|ミントベル/,
    zh: [[/铃多贝尔尔|铃德贝尔尔|铃德贝尔鲁|铃多贝尔鲁|铃德维尔娜|铃多维尔纳|铃德贝尔努|铃多贝尔努|林德贝鲁|林德伯格|铃德伯格|铃多维尔诺|铃德贝尔内|宁多贝尔|敏特贝尔斯|铃德贝尔|林德薇恩/g, "林德薇恩"]],
    reason: "统一林德薇恩的多种ASR漂移",
  },
  {
    ja: /ロクシ/,
    zh: [[/罗克西|洛克西|洛希|卢克西|露西|罗克茜|洛克茜/g, "洛克茜"]],
    reason: "统一洛克茜的多种音译漂移",
  },
  {
    ja: /クラレ|イクラレ|キュラレ/,
    zh: [[/克拉蕾特|克拉雷特|伊卡莱特|克拉蕾/g, "克拉蕾"]],
    reason: "统一克拉蕾的ASR变体译名",
  },
  {
    ja: /フリンツ|フリンス|プリンツ/,
    zh: [[/弗林茨|弗林斯|弗铃茨|普林茨|弗林特/g, "弗林特"]],
    reason: "统一弗林特姓氏及工坊名称",
  },
  {
    ja: /ビルリウム|ヴィルリウム/,
    zh: [[/比鲁里乌姆|维尔里乌姆|维尔乌姆/g, "维尔乌姆"]],
    reason: "统一地区名维尔乌姆",
  },
  {
    ja: /エイテリアス|デーテリアス|アテリアス|エーテリアス/,
    zh: [[/艾特里亚斯|阿特利亚斯|戴特莉亚斯|以骸/g, "以骸"]],
    reason: "统一世界观术语“以骸”",
  },
  {
    ja: /シリオン/,
    zh: [[/西里翁|锡里昂|希人/g, "希人"]],
    reason: "统一种族术语“希人”",
  },
  {
    ja: /ドラキナ|トラキナ/,
    zh: [[/特拉基纳/g, "德蕾琪娜"], [/桑布雷德/g, "挽昼"]],
    reason: "统一德蕾琪娜·挽昼的ASR变体",
  },
  {
    ja: /サングリーター|サンブリン|サンムリン|サムリン/,
    zh: [[/桑格利特|桑穆铃格|萨姆铃格|挽昼/g, "挽昼"]],
    reason: "统一“挽昼”的ASR变体",
  },
  {
    ja: /ミスター[・･]?ゼット|ミスター\s*[zZ]|ミスターZ/,
    zh: [[/泽特先生|Z先生/g, "Z先生"]],
    reason: "统一主持人称呼“Z先生”",
  },
  {
    ja: /プロメイヤ/,
    zh: [[/普罗梅耶|普罗梅亚|Pro Mayor|造梦机|职业选手/g, "普罗米娅"]],
    reason: "统一普罗米娅的ASR变体",
  },
  {
    ja: /パイトーン/,
    zh: [[/派特恩/g, "法厄同"]],
    reason: "统一法厄同的ASR变体",
  },
  {
    ja: /ラスタリファ|ロスカリファ/,
    zh: [[/拉斯塔里法|罗斯凯利法/g, "罗斯凯利法"]],
    reason: "统一地点名罗斯凯利法",
  },
  {
    ja: /空巡局/,
    zh: [[/空域巡戍局/g, "空巡局"]],
    reason: "统一组织名空巡局",
  },
];

const changes = [];
for (const entry of entries) {
  if (entry.timeIndex < 0 || !entry.zh) continue;
  const before = entry.zh;
  let after = before;
  const reasons = [];

  for (const group of ruleGroups) {
    if (!group.ja.test(entry.ja)) continue;
    let groupChanged = false;
    for (const [pattern, replacement] of group.zh) {
      const next = after.replace(pattern, replacement);
      if (next !== after) groupChanged = true;
      after = next;
    }
    if (groupChanged) reasons.push(group.reason);
  }

  if (manual.has(entry.index)) {
    const [manualText, reason] = manual.get(entry.index);
    after = manualText;
    reasons.push(reason);
  }

  if (after !== before) {
    const textStart = entry.timeIndex + 2;
    entry.lines.splice(textStart, entry.lines.length - textStart, after);
    changes.push({ index: entry.index, time: entry.time, ja: entry.ja, before, after, reasons: [...new Set(reasons)] });
  }
}

await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(outputPath, entries.map((entry) => entry.lines.join(newline)).join(newline + newline), "utf8");

const byIndex = new Map(entries.map((entry, pos) => [entry.index, { entry, pos }]));
const md = [];
md.push("# 绝区零 Ver.3.2 字幕精校修改记录", "");
md.push(`- 原字幕条目：${entries.filter((entry) => entry.timeIndex >= 0).length}`);
md.push(`- 修改中文条目：${changes.length}`);
md.push("- 时间轴与日文行：未修改");
md.push("- 核心范围：专有名词漂移、术语一致性、明显AI幻觉或机械直译", "");
md.push("说明：上下文展示修改项前后各一条；“原中文”与“新中文”便于逐项确认。", "");

for (const change of changes) {
  const hit = byIndex.get(change.index);
  const previous = hit?.pos > 0 ? entries[hit.pos - 1] : null;
  const next = hit && hit.pos + 1 < entries.length ? entries[hit.pos + 1] : null;
  md.push(`## #${change.index} · ${change.time}`, "");
  if (previous?.timeIndex >= 0) md.push(`- 上文 #${previous.index}：${previous.ja} / ${previous.zh}`);
  md.push(`- 日文：${change.ja}`);
  md.push(`- 原中文：${change.before}`);
  md.push(`- 新中文：${change.after}`);
  md.push(`- 修改原因：${change.reasons.join("；")}`);
  if (next?.timeIndex >= 0) md.push(`- 下文 #${next.index}：${next.ja} / ${next.zh}`);
  md.push("");
}

await fs.writeFile(reviewPath, md.join("\n"), "utf8");
await fs.writeFile(path.join(outputDir, "changes.json"), JSON.stringify(changes, null, 2), "utf8");
console.log(JSON.stringify({ outputPath, reviewPath, entryCount: entries.filter((entry) => entry.timeIndex >= 0).length, changedEntries: changes.length }, null, 2));
