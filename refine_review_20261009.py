"""Reviewed, contextual corrections; never overwrite source subtitles or reviews."""
import json
import hashlib
import re
from pathlib import Path
from subtitle_proofreading import load_review, _parse_cues

source = next(Path('Z:/Moives/四月一日').glob('20261009*_zh_Dual_review.json'))
data = load_review(source)
cues = data['cues']
assert len(cues) == 1288 and len(data['annotations']) == 63
out = Path(__file__).parent/'outputs/review_20261009'
out.mkdir(exist_ok=True, parents=True)
zh = {
35:'塞布里安先生真是让人觉得什么都愿意为他做。',
51:'（洛克茜的呻吟声）',53:'（洛克茜的呻吟声）',54:'（洛克茜的呻吟声）',56:'（洛克茜的呻吟声）',
67:'呜哦——！像圣约十字架一样的东西！',260:'糟了！特里薇娅也……！',
306:'大概是三位挽昼的业核。',309:'普罗米亚酱！',323:'我懂，喜欢业核。',
328:'塞布里安先生的站姿有点像性感的大姐姐。',353:'等等，这个 PV 画面也太棒了。',
359:'他们建造了高志的战斗机甲，对吧？',420:'后悔把维琳娜放进队伍了。',
427:'维琳娜也会很为难吧。',456:'不要把我跟你们相提并论。',
618:'四月一日当然也喜欢塞布里安先生啦。',
639:'没关系！有临时侦探助手四月一日在呢！',640:'各位贵安，我是临时侦探助手四月一日！',
645:'「小镇」跑活动。',830:'铃和哲都可爱得不得了。',
940:'诶！知更鸟和卡芙卡吗！',946:'确实是卡芙卡啊！也就是说，是联动亲善大使吗？',
948:'等等，不妙！卡芙卡！卡芙卡的游玩体验也太不得了吧？',
1015:'喂，特里薇娅，你还记得吗？',
}
deleted = {452,732,1204}
aliases = [('渡濑贝尔特','四月一日'),('渡木贝尔特','四月一日'),('渡濑','四月一日'),
 ('渡木','四月一日'),('绵狸','四月一日'),('棉根木','四月一日'),('绵根木','四月一日'),('渡崎','四月一日'),
 ('克洛埃达','黑枝'),('克劳','科洛'),('特里维亚','特里薇娅'),('特里比亚','特里薇娅'),('特里比娅','特里薇娅'),
 ('塞梅里安','塞布里安'),('维丽娜','维琳娜'),('罗宾','知更鸟'),('普罗梅娅','普罗米亚'),('普罗米娅','普罗米亚')]
changes=[]
rows=[]
pending={35:'日语「万事して」识别不清；依批注改男性称谓及代词，保留原译主要句意。',
78:'日语「断念十分小兵」损坏；仅修正科洛，未猜造描述。',
287:'仅移除无依据的说话人标签；「黄泉」是否为专名需原音验证。',
306:'依批注将考核改为业核，但“三位挽昼”的识别及句法仍需复听。',
353:'依人工批注重译为 PV 画面，未由中文反推日语。',
359:'按人工整句意见纠正；日语「公使」误识别保留供对照。',
420:'仅修正名称，日语不完整，“后悔放进队伍”的含义尚待原音确认。',
618:'称呼结合上下文统一为塞布里安，句法由中文重整；日语仍需复听。',
645:'删除提示词污染，保留原有活动译文；活动名识别仍不确定。',
1224:'仅统一特里薇娅；佩洛伊斯的准确名称待确认。'}
for i,c in enumerate(cues):
    before=c['text']
    if i in deleted or not before.strip():
        changes.append(dict(index=i,timing=c['timing'],before=before,after='',action='删除标记整条' if i in deleted else '移除空正文'))
        continue
    lines=before.split('\n')
    if len(lines)>=2:
        for a,b in aliases: lines[-1]=lines[-1].replace(a,b)
        if i in {632,633,648,649}: lines[-1]=lines[-1].replace('克洛','科洛')
        if i==962: lines[-1]=lines[-1].replace('柯拉','可乐')
    if i in zh: lines=[lines[0],zh[i]]
    if i==287:
        lines=[re.sub(r'^(?:ミク|米库)[:：]\s*','',s) for s in lines]
    if i==288:
        lines=[re.sub(r'^(?:ランス|兰斯)[:：]\s*','',s) for s in lines]
    after='\n'.join(lines)
    if before!=after: changes.append(dict(index=i,timing=c['timing'],before=before,after=after,action='按批注及上下文精校'))
    rows.append(dict(index=i,timing=c['timing'],text=after))
changed={x['index'] for x in changes}
assert all(n['cue'] in changed for n in data['annotations'])
content='\n\n'.join(f"{j}\n{r['timing']}\n{r['text']}" for j,r in enumerate(rows,1))+'\n'
parsed=_parse_cues(content)
assert len(parsed)==len(rows)
assert all(a['text']==b['text'] and a['timing']==b['timing'] for a,b in zip(parsed,rows))
assert '严格术语表' not in content
srt=out/'20261009_中日双语_精校.srt'
assert not srt.exists()
srt.write_text(content,encoding='utf-8-sig')
report=['# 20261009 精校记录','',f'依据全部63条人工标记与相关上下文。输入{len(cues)}条，输出{len(rows)}条；删除3条已标记整条，其余保留原时间轴并连续编号。未听原音。',
'日文基本保留，仅删除287、288的错误说话人标签。中文按人工批注修正及统一同名指代；没有把整份字幕视为经过原音核实的训练数据。',
'维琳娜／维林娜冲突：沿用现有词汇表及前期精校的“维琳娜”。普罗米亚采用本次批注，词汇表中相关“普罗米娅”同步更新。',
'语料库交付为更新版词汇表及带来源时间轴的上下文纠错案例 JSON；不覆盖 NAS 原词汇表，不自动修改软件词库路径。',
'', '## 待复听项目']
for i,n in pending.items(): report.append(f'- 索引{i} · {cues[i]["timing"]}：{n}')
report+=['','## 63条标记核对']
for n in data['annotations']: report.append(f'- 索引{n["cue"]}：{n["comment"].strip() or "无评论，同条已有名称标记"} → 已处理')
report+=['','## 修改明细']
for c in changes:
    report += [f'### 索引{c["index"]} · {c["timing"]}',c['action'],'原文：',c['before'],'修改后：',c['after'] or '（删除）','']
(out/'20261009_精校修改记录.md').write_text('\n'.join(report),encoding='utf-8-sig')
corpus={'format':'contextual-subtitle-corrections','version':1,'source_name':source.name,'source_sha256':data['source_sha256'],
 'usage':'上下文参考案例，非无条件替换规则；未听原音，不应作为全量高置信训练语料。',
 'examples':[dict(c,review_comments=[n['comment'] for n in data['annotations'] if n['cue']==c['index']],
                 previous=cues[c['index']-1]['text'] if c['index'] else '',
                 next=cues[c['index']+1]['text'] if c['index']+1<len(cues) else '',
                 needs_audio_review=pending.get(c['index'],'')) for c in changes]}
(out/'20261009_上下文纠错语料.json').write_text(json.dumps(corpus,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(input=len(cues),output=len(rows),changes=len(changes),annotations=63)))
