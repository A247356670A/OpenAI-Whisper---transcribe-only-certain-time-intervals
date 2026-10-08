import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
const root=path.resolve('subtitle_review_20260916');
const out=path.resolve('outputs/subtitle_review_20260916');
await fs.mkdir(out,{recursive:true});
const raw=await fs.readFile(path.join(root,'original.srt'),'utf8');
const cues=raw.replace(/^\uFEFF/,'').trim().split(/\r?\n\s*\r?\n/).map(b=>{
 const [n,time,...lines]=b.split(/\r?\n/);return {id:Number(n),time,text:lines.join('\n')};
});
assert.equal(cues.length,990);
const edited=new Map(cues.map(c=>[c.id,{...c,reasons:[],category:[]} ]));
function sub(ids,from,to,reason,category='专名/术语纠错'){
 for(const id of ids){const c=edited.get(id);assert(c.text.includes(from),`${id}: missing ${from}`);c.text=c.text.split(from).join(to);c.reasons.push(reason);c.category.push(category);}
}
function put(id,text,reason,category='画面核对纠错') {const c=edited.get(id);c.text=text;c.reasons.push(reason);c.category.push(category);}
function del(ids,reason,category='疑似幻觉清理'){for(const id of ids){const c=edited.get(id);c.deleted=true;c.reasons.push(reason);c.category.push(category);}}
function all(from,to,reason,category){sub(cues.filter(c=>edited.get(c.id).text.includes(from)).map(c=>c.id),from,to,reason,category);}
// All replacements are reviewed against the exact source cue, not fuzzy global substitution.
all('クラレット','クラレッタ','官网角色名与本片其他清晰出现一致；不改独立角色「クレタ」。');
sub([853],'グラレッタ','クラレッタ','角色近音误识别；官网角色名。');
sub([224],'喰らえたの','クラレッタ','谈论克拉蕾脸红；邻句及 PV 角色画面支持。');
sub([413],'振られたら','クラレッタが','讨论克拉蕾按停遥控器；邻句及 PV 画面支持，属上下文推定。');
sub([415],'振られてたのか','クラレッタか','谈论脸红的克拉蕾；上下文推定，未逐句听校。');
sub([747],'くられた','クラレッタ','抽卡前在选择克拉蕾；画面与邻句支持。');
all('セベリアン','セヴェリアン','日文官网角色介绍；中文标准名为赛维里安，不沿用旧扩充表的塞布里安。');
sub([531],'ロッジ','ロクシー','EP 语境中讨论两人关系，前后反复提及ロクシー。');
sub([902],'ロックシートの','ロクシーとの','本句在说克拉蕾与洛克茜之间的爱心；角色名和助词切分错误。');
sub([482],'トレミエール','レミエール','官方角色名及后文抽卡回顾；多识别一个ト。');
sub([772],'レミエル','レミエール','官网标准角色名，统一长音。');
sub([908],'ドルム','ノルムー','00:57:03 视频角色选择界面直接显示ノルムー。');
sub([484],'ノルムの','ノルムーの','官网标准角色名，统一长音。');
all('ビクトリア火星','ヴィクトリア家政','官方阵营名；火星是家政的近音误写。');
sub([766],'白衣住行','白祇重工','抽卡出现白祇重工角色，上下文及官方阵营名一致。');
sub([751],'雑屋','邪兎屋','抽卡界面在谈邪兎屋成员，官方阵营名。');
all('全ゼロ','ゼンゼロ','游戏简称，现有术语表及全片语境。');
sub([180],'前列ゾーンゼロ','ゼンレスゾーンゼロ','游戏标题近音误识别。');
sub([979],'全列ゾーンゼロ','ゼンレスゾーンゼロ','游戏标题近音误识别。');
all('新エリート','新エリー都','官方地名；不是普通的「新精英」。');
sub([372],'シンゲリエイト','新エリー都','谈论 PV 中新艾利都的两位主角，地名近音误识别。');
all('ロスカリワ','ロスカリファ','现有术语表地名；同片00:60:13有清晰标准形式。');
sub([957],'ベイフレー計画','ベーグル計画','领取委托收益的玩法；3.2 官方更新与既有扩充表一致。');
all('ゼロゴーホロー','零号ホロウ','现有术语表正式玩法名称。');
sub([537],'フリンツボーキン','フリンツ合金','锻造/音动机语境，工坊名和合金近音误识别。');
all('プリンツ工房','フリンツ工房','PV 00:06:08、00:13:44 画面直接显示フリンツ工房。');
sub([109],'プリンツ家の投資様','フリンツ家の当主様','PV 00:05:50 画面直接显示フリンツ家の当主様。');
sub([184],'月の投資様','フリンツ家の当主様','同一 PV 重播；00:09:34 画面显示フリンツ家の当主様。');
sub([423],'投資様','当主様','同一 PV 开头台词；00:05:50 画面支持。');
sub([894],'フリンチ一族投資','フリンツ一族当主','00:56:12 服装详情画面直接核对。');
sub([901],'東大の投資','当代の当主','紧接着朗读一族当主描述，近音词组的上下文纠错。','上下文纠错');
sub([893],'金を焼く火の炎','金を灼く緋の炎','00:56:12 服装标题直接显示。');
sub([897],'目立つ嫉妬','目立つ失態','00:56:18 描述直接显示「目立つ失態」。','画面核对纠错');
sub([885],'トゲマトウバラ','棘まとう薔薇','00:55:48 驱动盘界面及现有术语表。');
sub([879],'衛撃ダメージ','鋭撃ダメージ','00:55:28 音动机说明显示「電気属性鋭撃ダメージ」。');
// Numbers may be spoken incorrectly; fix only recognizer confusion directly anchored in UI.
sub([879],'40%','40秒','同帧显示+10%、継続時間40秒；原稿把单位识别为百分号。','画面核对纠错');
sub([880],'計測時間','継続時間','同帧音动机说明，持续时间而非测量时间。','画面核对纠错');
all('ポテカイ','ポテ解','潜能解放的口语简称，不能解释为另一角色名。');
sub([433],'秘密と過去と彼女達勝って','秘密と過去と彼女たちとって','官方3.2版本标题；修正标题与引用助词的切分。');
sub([866],'カウント','完凸','后续明确谈1凸、2枚抜き；抽卡术语同音纠错。');
sub([813],'すぎ抜け','すり抜け','抽卡歪池术语。');
// Streamer and non-ZZZ named entities. Kept out of the ZZZ translation glossary.
sub([12],'渡瀬ベルト','四月一日ベレト','主播本人公开资料确认四月一日（わたぬき）ベレト。');
for(const term of ['ワタニキ','ワタネキ','ワトリキ','ワタリケ','渡瀬希','渡れ木','渡り木']) all(term,'ワタヌキ','本片主播自称四月一日（わたぬき）；仅在已逐句审查的本文件执行。');
sub([281],'サワタヌキ','さ、ワタヌキ','句边界误合并，主语是主播的自称。');
all('保佑クリエイター','HoYoクリエイター','提及简介兑换码与创作者身份；HoYo 近音误识别。');
sub([830],'保育リエイター','HoYoクリエイター','同上；与前文同一身份。');
sub([722],'篠沢ヒロ','篠澤広','学园偶像大师官方角色名；不改成绝区零角色。');
for(const term of ['トウホーコーマ卿','東宏光真教']) all(term,'東方紅魔郷','后文 CD-ROM、弹幕游戏、六芒星及符卡语境，作品名明确。');
sub([792],'スターオブナビレー','スターオブダビデ','東方紅魔郷的符卡名，六芒星语境明确。');
sub([799],'ティッシュユウスケ','貴志祐介','紧接着书名クリムゾンの迷宮；出版社资料确认作者。');
sub([800],'クリムソン','クリムゾン','出版社正式书名クリムゾンの迷宮。');
sub([232],'スポッティファー','Spotify','听歌平台名。');
for(const term of ['オンリーマイレールガー','オンリーマイレール']) all(term,'only my railgun','评论唱片封面，与REAL FORCE和sister’s noise同一超电磁炮语境。');
sub([228],'リアルフォース','REAL FORCE','歌曲标题，原文读音正确，标准书写统一。');
sub([231],'シスターズノイズ',"sister’s noise",'歌曲标题，保留与绝区零不同的作品来源。');
sub([276],'ラキスタ','らき☆すた','动漫标题；不改变主播随后对面包的自我纠正。');
// Ordinary homophone errors: minimal edits without rewriting speech into polished prose.
for(const [ids,a,b,why] of [
 [[18],'タイキ','待機','开场感谢等待'],[[23],'色質','露出','前句讲露出皮肤方便吸血'],
 [[39],'反抗声明','犯行声明','用犯罪预告比喻观众提醒'],[[43,44],'オート','嘔吐','随后明确说エチケット袋'],
 [[166,170],'揺り','百合','讨论女女关系题材'],[[187],'超人料理','精進料理','用素斋与家系拉面作比喻'],
 [[208],'フォンフォン虹装着','東方二次創作','IOSYS、ボーカルアレンジ语境'],
 [[210],'作成','作風','讨论 PV 突然转变风格'],[[212],'コウハ','硬派','硬派动作游戏'],
 [[265],'戦壁','性癖','讨论同人趣味'],[[286],'制約と制約','制約と誓約','固定用语'],
 [[293],'お礼芋','俺妹','轻小说/动画致敬语境'],[[307],'デルマク','出る幕','固定说法出る幕'],
 [[358,712],'エアップ','エアプ','未体验过却评论的网络用语'],[[400],'ポジックメタル','ゴシックメタル','讨论曲风，非角色名'],
 [[466],'炭造','鍛造','铸造与锻造的场景'],[[488,489,493],'職場合','触媒','抽卡前准备红茶和红魔乡CD作触媒'],
 [[774,784],'職バイト','触媒','同一抽卡触媒话题'],[[774],'職業','触媒','同一抽卡触媒话题'],
 [[786],'アンダーマック','弾幕','東方紅魔郷是弹幕射击游戏'],[[788,789,792],'六望星','六芒星','几何图形'],
 [[789],'八望星','八芒星','保留主播梦中说法，不当作现实发行事实更改'],
 [[514],'千円卓上','一蓮托生','并列固定成语'],[[514],'飛翼連に','比翼連理','并列固定成语'],
 [[628,630],'歯がん','破顔','后句明确解释为笑容'],[[630],'エミ','笑み','原句正在解释破颜一词']
]) sub(ids,a,b,why+'；仅文本上下文推定，未逐句听校。','上下文纠错');
// Official Japanese on-screen dialogue fixes; time windows stay unchanged.
sub([116],'顔に加わった皆様は','フリンツ工房に加わった皆様は','00:06:08 画面确认工坊培训台词。','画面核对纠错');
sub([126],'ごうきんはおろせない','合金は卸せない','00:06:35 画面确认合金供货台词。','画面核对纠错');
all('合金は下ろせない','合金は卸せない','00:06:35 画面确认，卸す是供货。','画面核对纠错');
all('合金はおろせない','合金は卸せない','00:06:35 画面确认；保留主播疑问语气。','画面核对纠错');
put(156,'なに見せてんのよーっ！？','00:07:59 官方画面字幕，删除误加的(みんな)说话人标记。');
sub([410],'何見ててんのよ','何見せてんのよ','同一 PV 台词重播。','画面核对纠错');
sub([412],'秘密か何かだ','機密か何かかな','00:25:43 官方画面显示「機密か何かかな…！」。','画面核对纠错');
// Corrupt nested SRT cue with usable internal timing and visually confirmed dialogue.
put(247,'フリンツ工房に加わった皆様はすぐ気づくはずです','恢复正文中误嵌的完整条目；00:13:44 画面直接确认。','结构恢复');
edited.get(247).time='00:13:42,460 --> 00:13:46,980';
del([11,361,363,364,524,525,526,527],'零时长记录，正文只有另一组序号/时间码；不是对白。','结构垃圾删除');
del([149,528],'零时长记录内嵌其他时间码和可疑短句。无法可靠恢复原对白，移出成品并在此保留原文。','结构垃圾删除');
del([309,311,312],'重复的「何かを見つけたり」不是可识别对白，疑似生成式场景旁注；删除可回溯。');
del([603],'伪造工作人员/评论操作的括号说明，非正常转写；原文完整存档。');
del([661],'「施術水の Taco Bell」混杂乱码式括号旁注；视频处于英文 PV 播放段，非真实店名证据。','不可用识别文本删除');
del([685],'日英拼接的括号乱码，无法可靠重建外语对白；不把它认定为音轨静音。','不可用识别文本删除');
del([692,693],'重复的「听取人们烦恼的声音」是推测心理活动的伪音效说明，非对白。');
// Pending cases deliberately do not become global aliases or invented Japanese dialogue.
const pendingGroups=[
 [[2,3,4,5,6,7,8,9],'开场连续鸟鸣标注：可能是真实环境音，也可能是非语音段误识别。没有音频听校证据，保留，不判定为已证实幻觉。'],
 [[10],'开场后半「インターネットバージョンをご利用いただきありがとうございます」不自然；可能与主播固定开场白混淆。不能凭固定开场白补造，保留待听。'],
 [[15,48,66,82,102,119,125,131,144],'普通话语仍有明显错词/漏词；多个合理候选，保留待听，不用游戏术语强行解释。'],
 [[148,157,158,162,163,172,176,195,202,214,222],'短音节、主角名リン/ミン、主播隐语及重叠台词存在歧义。尤其ポーセルメックス可能是刻意避讳表达，不擅自还原为直白词汇。'],
 [[245,246],'「あなたのおかげで、私はあなたを愛しています」与该时刻 PV 官方画面不吻合，但下一句主播又复述「あなたのおかげで？」；可能在读自动字幕或评论，不能直接删除。'],
 [[281,293,295,297,314,318,321,325,328,333,336,339,342,343,350,352],'二次元致敬、口语与截断词待听。保留シンク/ゴシック等普通或外作品词，不强行对应绝区零角色。333仅统一クラレッタ，残句不补写。'],
 [[360,362],'PV 尾段的两条长句高度可疑，画面在黑屏台词/片尾标志间变化；不能排除主播/评论叠音，暂保留待听。'],
 [[379,380,392,395,397,401,408,427,449,451,471],'语义不通或多人重叠；408「提供衛生大学」也可能是主播玩梗，缺少听校不得编成官方台词。'],
 [[484,512,516,521,523,530,547,552],'曲名、制作方和口語切分待听。カオス.エグゼ、ホヨフヨ、レミ作等没有足够直接证据，不作为术语表别名。'],
 [[557,558,561,562,563,564,568,569,571,572,573,574,576,579,580,583,585,586,587,590,591,592,593,594,595,596,597,598,599,624,631],
  '00:37–00:41 为中文版 PV 与日语解说混合。存在中文直出、中文近音被写成日语，以及画面自动翻译。保留待多语听校；这些不能全部叫做无声音幻觉，不能用日文PV台词直接覆盖。'],
 [[644,647,650,654,658,659,662,664,673,674,686,687,688,689,705,706],
  '00:42–00:46 为英文版 PV 与解说混合。外语识别损坏/说话人标签可疑，保留待听；女性クレアリッ可能对应称呼Lady Claret，但未听清，不直接替换。'],
 [[748,750,758,764,765,771,802,805,811,815,826,828,829,833,834,837,838,845,850,851,883,889,909,926,927,928,929,949,955,963,990],
  '抽卡/角色界面对白、观众昵称、尾句及短音节存在歧义。保留；不得把弹幕用户名作为游戏人物收录。955可能是「まあ、リナ」，但暂不改为角色マリナ或强行删掉助词。']
];
const pending=pendingGroups.flatMap(([ids,reason])=>ids.map(id=>({...cues[id-1],after:edited.get(id).text,reason})));
const retained=cues.map(c=>edited.get(c.id)).filter(c=>!c.deleted).sort((a,b)=>a.time.localeCompare(b.time)||a.id-b.id);
retained.forEach((c,i)=>c.newId=i+1);
const changes=cues.map(c=>{const e=edited.get(c.id);return e.deleted||c.text!==e.text||c.time!==e.time?{originalId:c.id,newId:e.newId??null,time:c.time,newTime:e.time,before:c.text,after:e.deleted?'':e.text,action:e.deleted?'删除':c.time!==e.time?'恢复条目并改时码':'修改',categories:[...new Set(e.category)],reasons:[...new Set(e.reasons)],previous:cues[c.id-2]??null,next:cues[c.id]??null}:null}).filter(Boolean);
const srt=retained.map(c=>`${c.newId}\n${c.time}\n${c.text}`).join('\n\n')+'\n';
function ms(t){const a=t.match(/^(\d{2}):(\d{2}):(\d{2}),(\d{3})$/);assert(a,t);return (+a[1]*3600 + +a[2]*60 + +a[3])*1000 + +a[4];}
let prior=-1;for(const c of retained){const [a,b]=c.time.split(' --> ').map(ms);assert(a<b,`nonpositive ${c.id}`);assert(a>=prior);prior=a;assert(!c.text.includes('-->'));}
for(const c of retained){if(c.id!==247)assert.equal(c.time,cues[c.id-1].time);}
await fs.writeFile(path.join(out,'20260915_クラレッタ_JA_reviewed.srt'),srt,'utf8');
await fs.writeFile(path.join(root,'changes.json'),JSON.stringify({changes,pending},null,2));
const summary={sourceCues:cues.length,outputCues:retained.length,changed:changes.filter(c=>c.action!=='删除').length,deleted:changes.filter(c=>c.action==='删除').length,pending:pending.length,sha256:crypto.createHash('sha256').update(raw).digest('hex'),timeChanges:[247]};
await fs.writeFile(path.join(root,'summary.json'),JSON.stringify(summary,null,2));
console.log(summary);
// Report is finalized by the glossary builder, which adds glossary change evidence.
const esc=s=>String(s).replaceAll('|','\\|').replaceAll('\n',' / ');
let report=`# 20260915 克拉蕾直播日语字幕审核\n\n审核日期：2026-09-16。\n\n## 范围与结论\n\n通读 ${cues.length} 条字幕（00:00:26–01:02:07），修改 ${summary.changed} 条、移除 ${summary.deleted} 条，输出 ${summary.outputCues} 条。保留原文件，重新连续编号。除恢复原第247条的内嵌时间码外，保留条目的起止时间完全不变。\n\n这是**全文文本审核＋相关原视频关键画面核对**，不是62分钟全程逐句听校。未能确认的 ${pending.length} 条列在文末；不能据此声称已清除所有误听或音频幻觉。\n\n以 Z 盘实际现有术语表为基础（1468行），未直接合并上一版扩充表中的全部猜测别名。已核对官网新角色、3.2信息、两条指定视频的官方标题/频道，并抽查同目录原视频中播放的日文/英文/中文PV及游戏界面。网页工具未直接取得YouTube完整字幕。原视频画面所见的自动翻译不作为官方日文台词证据。\n\n不把重复播放PV产生的重复对白、真实笑声和喘气、主播口误/玩梗、外语对白一概删除。删除项分为结构垃圾、疑似伪旁注和不可用识别文本，均完整保留原文及上下文。普通语句的修正均标明为上下文推定。\n\n## 来源\n\n- 日文官网角色与阵营：https://zenless.hoyoverse.com/ja-jp/main\n- 中文官网角色介绍（动态角色目录）：https://zenless.hoyoverse.com/m/zh-cn/character?id=155659\n- 官方发行方3.2版本说明：https://play.google.com/store/apps/details?hl=zh&id=com.HoYoverse.Nap\n- 指定EP：Claret EP - Link Up，https://www.youtube.com/watch?v=Ln0ilmPqXU0\n- 指定英文角色展示：https://www.youtube.com/watch?v=VjNhciBWgug\n- 对应日文角色展示：https://www.youtube.com/watch?v=_Q6RmpJjZHs\n- 已发布角色页面（核对新角色名称，未使用未发布性能预测）：https://wikiwiki.jp/zenless/実装予定エージェント\n- 3.2日文更新报道：https://www.4gamer.net/s/G063081.260828066\n- 角色/音动机中日文数据：https://zzz.honeyhunterworld.com/1611-char/?lang=JP 与 https://zzz.honeyhunterworld.com/1611-char/?lang=CN\n- 主播公开身份：https://marshmallow-qa.com/watanuki_beleth?hl=ja\n- 小说作者和书名：https://www.kadokawa.co.jp/product/200399008683/\n- 篠澤広官方名录：https://idollist.idolmaster-official.jp/search/detail/60008?order_direction=1&order_type=3\n- 東方符卡名称：https://wikiwiki.jp/thk/紅/6\n\n## 逐项修改（原序号定位）\n\n`;
for(const c of changes){report+=`### 原 #${c.originalId} → ${c.newId?'新 #'+c.newId:'已删除'} · ${c.time}\n\n- 操作：${c.action}；${c.categories.join('、')}\n- 修改前：${c.before.replaceAll('\n',' / ')}\n- 修改后：${c.after||'（移除；未补造对白）'}\n- 依据：${c.reasons.join('；')}\n${c.time!==c.newTime?'- 恢复后时间：'+c.newTime+'\n':''}- 前文：${c.previous?.text??'（开头）'}\n- 后文：${c.next?.text??'（结尾）'}\n\n`;}
report+='## 保留待核对（未确认，不自动套词）\n\n';
for(const [ids,reason] of pendingGroups){report+=`### 原 #${ids.join('、')}\n\n${reason}\n\n| 原序号 | 时间 | 保留文本 |\n|---|---|---|\n`;for(const id of ids){const c=edited.get(id);report+=`| ${id} | ${c.time} | ${esc(c.text)} |\n`;}report+='\n';}
report+='## 术语使用边界\n\n- クレタ是珂蕾妲，不改成クラレッタ。リン可能是铃或观众昵称，不全局替换ミン/リーン。\n- セクシー、合金、当主、触媒、ゴシック、シンク均可能是普通词或外作品词，不单凭近音映射角色。\n- 振られた、喰らえた、ドルム等只在本片明确语境修正，不加入无条件翻译术语表。\n- 四月一日/ワタヌキ及其他作品名称仅用于本片字幕纠错，不污染绝区零游戏术语表。\n- 第37–46分钟混合外语段仍需多语音频复核，勿把画面自动翻译当原日语。\n\n';
await fs.writeFile(path.join(root,'report_base.md'),report);
// TSV is the application's interchange format: preserve its two-column, no-header contract.
const {Workbook}=await import('@oai/artifact-tool');
const glossaryRaw=await fs.readFile(path.join(root,'original_glossary.tsv'),'utf8');
const originalRows=glossaryRaw.replace(/^\uFEFF/,'').trim().split(/\r?\n/).map(s=>s.split('\t'));
assert(originalRows.every(r=>r.length===2&&r.every(Boolean)));
const glossary=Workbook.create();
const sheet=glossary.worksheets.add('日中术语');
sheet.getRange(`A1:B${originalRows.length}`).values=originalRows;
const newTerms=[
 ['クラレッタ・フリンツ','克拉蕾·弗林特','官网角色介绍'],
 ['クラレッタ･フリンツ','克拉蕾·弗林特','中点字符兼容'],
 ['クラレッタフリンツ','克拉蕾·弗林特','无中点兼容'],
 ['クラレット','克拉蕾','本片#333/354/549反复出现的误听'],
 ['グラレッタ','克拉蕾','本片#853'],
 ['くられった','克拉蕾','标准读音，平假名兼容'],
 ['ロクシー','洛克茜','官网角色介绍及本片反复提及'],
 ['ロクシー・イフリータ・プライス','洛克茜·伊芙莉塔·普莱斯','中日官网角色介绍'],
 ['ロクシー･イフリータ･プライス','洛克茜·伊芙莉塔·普莱斯','中点字符兼容'],
 ['ロクシーイフリータプライス','洛克茜·伊芙莉塔·普莱斯','无中点兼容'],
 ['ロックシー','洛克茜','本片#902词干误听；不能连同后面的助词一起替换'],
 ['ろくしー','洛克茜','标准读音，平假名兼容'],
 ['セヴェリアン','赛维里安','中日官网角色介绍'],
 ['セヴェリアン・ローウェル','赛维里安·洛威尔','中日官网角色介绍'],
 ['セヴェリアン･ローウェル','赛维里安·洛威尔','中点字符兼容'],
 ['セヴェリアンローウェル','赛维里安·洛威尔','无中点兼容'],
 ['セベリアン','赛维里安','本片#723/725/727/730；旧扩充表译名错误，不沿用'],
 ['せヴぇりあん','赛维里安','标准读音兼容'],
 ['フィオニー','菲欧妮','中日官网角色介绍；本片#719/722/726/727'],
 ['フィオニー・レファエラ','菲欧妮·蕾法爱菈','中日官网角色介绍'],
 ['フィオニー･レファエラ','菲欧妮·蕾法爱菈','中点字符兼容'],
 ['フィオニーレファエラ','菲欧妮·蕾法爱菈','无中点兼容'],
 ['ふぃおにー','菲欧妮','标准读音，平假名兼容'],
 ['フリンツ工房','弗林特工坊','官网阵营；本地PV字幕'],
 ['プリンツ工房','弗林特工坊','本片#247/253误听'],
 ['フリンツ家','弗林特家族','PV字幕，必须优先匹配长词'],
 ['プリンツ家','弗林特家族','本片#109误听'],
 ['フリンツ一族','弗林特家族','00:56:12游戏服装说明'],
 ['フリンチ一族','弗林特家族','本片#894误听；只收带一族的完整词组'],
 ['フリンツ家の当主','弗林特家主','PV官方字幕与中文官网'],
 ['フリンツ一族当主','弗林特家主','00:56:12游戏界面'],
 ['フリンツ合金','弗林特辉金','中日术语对照；本片#388/537'],
 ['フリンツボーキン','弗林特辉金','本片#537完整误听词组，避免通用合金被误套'],
 ['迷い路の謎','迷宫诡域','3.2更新及既有扩充表'],
 ['ベーグル計画','贝果计划','3.2更新及既有扩充表'],
 ['迷い路の謎：ベーグル計画','迷宫诡域：贝果计划','正式玩法完整名'],
 ['ベイフレー計画','贝果计划','本片#957，保留計画限定，避免把面包误译成玩法'],
 ['ロスカリワ','罗斯凯利法','本片#264；现有标准名ロスカリファ'],
 ['シンゲリエイト','新艾利都','本片#372完整地名误听'],
 ['全ゼロ','绝区零','本片多次游戏简称误听'],
 ['前列ゾーンゼロ','绝区零','本片#180完整标题误听'],
 ['全列ゾーンゼロ','绝区零','本片#979完整标题误听'],
 ['ビクトリア火星','维多利亚家政','本片#445/941；不收単独火星'],
 ['白衣住行','白祇重工','本片#766完整阵营误听'],
 ['ゼロゴーホロー','零号空洞','本片#958/959完整玩法误听'],
 ['ポテンシャル解放','潜能解放','本片#911及3.2强化说明'],
 ['ポテ解','潜能解放','本片#932简称'],
 ['ポテカイ','潜能解放','本片#932简称误听'],
 ['鋭御','锋御','中日3.2角色特性'],
 ['深紅の渇望','猩红渴望','00:55:28装备名与角色中日数据'],
 ['金を灼く緋の炎','灼金绯焰','00:56:12界面与中日服装数据'],
 ['金を焼く火の炎','灼金绯焰','本片#893完整服装名误听'],
 ['トゲマトウバラ','荆棘玫瑰','本片#885；沿用现有棘まとう薔薇译名'],
 ['秘密と、過去と、彼女たちと','她与她的隐秘往事','3.2官方版本标题'],
 ['秘密と過去と彼女たちと','她与她的隐秘往事','本片#165/167，标点兼容'],
 ['Link Up','Link Up','官方EP标题，不翻译成临时歌名'],
 ['リンクアップ','Link Up','本片#437的EP标题读音']
];
const index=new Map();const existingConflicts=[];const duplicateRows=[];
for(const [i,row] of originalRows.entries()){
 if(index.has(row[0])){if(index.get(row[0])!==row[1])existingConflicts.push({row:i+1,key:row[0],first:index.get(row[0]),other:row[1]});else duplicateRows.push(i+1);}else index.set(row[0],row[1]);
}
const additions=[];const skipped=[];
for(const [ja,zh,evidence] of newTerms){
 if(index.has(ja)){assert.equal(index.get(ja),zh,`new glossary conflict ${ja}`);skipped.push(ja);continue;}
 additions.push([ja,zh,evidence]);index.set(ja,zh);
}
const values=[...originalRows,...additions.map(r=>r.slice(0,2))];
sheet.getRange(`A${originalRows.length+1}:B${values.length}`).values=additions.map(r=>r.slice(0,2));
glossary.recalculate();
assert.deepEqual(sheet.getRange(`A1:B${originalRows.length}`).values,originalRows,'existing rows changed');
assert.deepEqual(sheet.getRange(`A1:B${values.length}`).values,values);
console.log((await glossary.inspect({kind:'table',range:`日中术语!A${originalRows.length+1}:B${Math.min(values.length,originalRows.length+6)}`,tableMaxRows:6,tableMaxCols:2,maxChars:1200})).ndjson);
// No visual styling/rendering applies to a plain application-consumed TSV.
const tsv=sheet.getRange(`A1:B${values.length}`).values.map(r=>r.join('\t')).join('\n')+'\n';
await fs.writeFile(path.join(out,'zenless-zone-zero-ja-zh_20260916.tsv'),tsv,'utf8');
assert.deepEqual(tsv.trim().split('\n').map(r=>r.split('\t')),values);
report+=`## 本次术语表更新\n\n磁盘原表 ${originalRows.length} 行，保留原有行和顺序，新增 ${additions.length} 行，输出 ${values.length} 行。无表头、两列Tab分隔、UTF-8，可直接供现有程序使用。本次新增项没有产生同源不同译冲突。原表自身同源不同译冲突：${existingConflicts.length}；完全重复行：${duplicateRows.length}（均未擅自清理）。\n\n术语表处理按表格规范检查了两列结构、重复和冲突；不把普通词的逐句纠错扩散为全局规则。`;
report+='\n\n注意：此次是基于Z盘现用原表的独立更新，并非此前1626行扩充版的超集。若你实际使用此前扩充版，应先合并核对；尤其不要再次引入「セベリアン→塞布里安」。\n\n| 新增日文 | 中文 | 依据/适用范围 |\n|---|---|---|\n';
for(const r of additions)report+='| '+r.map(esc).join(' | ')+' |\n';
report+='\n「新エリート」仍有普通词义，仅在本片指定条目修改；本次未新增此映射，但原表第1361行已经包含它，为保留原表未删除。使用时必须限制游戏地名语境。这份是绝区零领域翻译表，不可当作任意日语的无条件替换表。日语纠错应显式使用标准日文词形，不从同一中文译名的第一行推断标准写法。\n';
report+='\n已确认日文但不盲目新增整句翻译：服装/武器文字按界面修正；无音频证据的缩略词、观众名、外语拼接词不收录。\n';
if(existingConflicts.length)report+='\n原表已有冲突（未改）：\n\n'+existingConflicts.map(c=>`- 第${c.row}行 ${c.key}：${c.first} / ${c.other}`).join('\n')+'\n';
report+='\n## 关键画面证据\n\n以下仅展示实际核对画面，不代表全程听校。\n\n';
await fs.mkdir(path.join(out,'evidence'),{recursive:true});
for(const [sec,label] of [[350,'00:05:50：フリンツ家の当主'],[368,'00:06:08：フリンツ工房'],[395,'00:06:35：合金は卸せない'],[824,'00:13:44：恢复原第247条'],[1543,'00:25:43：機密か何かかな'],[3328,'00:55:28：深紅の渇望／鋭撃／40秒'],[3372,'00:56:12：金を灼く緋の炎／フリンツ一族当主'],[3378,'00:56:18：目立つ失態'],[3423,'00:57:03：ノルムー']]){
 await fs.copyFile(path.join(root,`frame_${sec}.jpg`),path.join(out,'evidence',`frame_${sec}.jpg`));
 report+=`### ${label}\n\n![${label}](evidence/frame_${sec}.jpg)\n\n`;
}
await fs.writeFile(path.join(out,'审核与修改记录.md'),report,'utf8');
const validation={...summary,glossaryOriginalRows:originalRows.length,glossaryAddedRows:additions.length,glossaryOutputRows:values.length,originalGlossaryPreserved:true,newConflicts:0,existingConflicts,existingDuplicateRows:duplicateRows,srtChecks:{continuousNumbering:true,positiveDuration:true,sorted:true,noEmbeddedTimecodes:true,unchangedTimesExceptRecovered247:true},glossarySha256:crypto.createHash('sha256').update(glossaryRaw).digest('hex')};
await fs.writeFile(path.join(root,'validation.json'),JSON.stringify(validation,null,2));
console.log(JSON.stringify(validation,null,2));
