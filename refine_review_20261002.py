"""Apply reviewed editorial decisions to the supplied portable review (read-only input)."""
import hashlib
import json
import re
from pathlib import Path

source = next(Path('Z:/Moives/四月一日').glob('20261002*_zh_Dual_review.json'))
data = json.loads(source.read_text(encoding='utf-8'))
assert hashlib.sha256(data['source_srt'].encode('utf-8')).hexdigest() == data['source_sha256']
original = data['cues']
assert len(original) == 1846 and len(data['annotations']) == 62
for note in data['annotations']:
    assert original[note['cue']]['text'][note['start']:note['end']] == note['quote']

# Keys are zero-based review cue indices, not original SRT numbers (which repeat).
chinese = {
    42:'我是四月一日贝雷特！',
    58:'感觉才开播零秒，四月一日就已经累了，是吧。',
    287:'不，洛克茜真的很了不起啊。',
    289:'等一下，现在还不知道是否平安，洛克茜没事吧？',
    291:'说真的，洛克茜这个角色，',
    301:'不过洛克茜一直戴着眼镜这点，真的很了不起啊。',
    354:'我本来还想追到克拉蕾一命，但现在看来没追也许是对的。',
    592:'各位趁现在，帮弹珠高手四月一日想个外号吧。',
    620:'铃小姐，刚才的体验怎么样？',
    901:'向克拉蕾和洛克茜详细介绍了时尚精品店与弹珠台，尤其是美学实践的内容。',
    1296:'洛克茜，你也说她两句啊。',
    1461:'这里是我特别喜欢洛克茜的一点。',
    1723:'应该也相当认可四月一日了吧。',
    1781:'刚才还有客人特意来体验，', 1782:'就是这样。',
    1783:'嗯嗯。',1784:'我已经能看见了，',1785:'这次美学实践大获成功的景象。',
    1786:'弹珠台？',1787:'做成游戏预装进去了吗？',
    1791:'等等，又来了一位超棒的女士！',1792:'那个……',1793:'虽然有点难以启齿……',
    1795:'小千！',1796:'今天四月一日，',1797:'从一开始就没什么精神，',
    1798:'就这样开始直播了，不过，',1799:'玩了弹珠台之后，',
    1800:'是不是兴奋得脑袋充血了呢，',1801:'越来越……',1802:'头越来越晕了，',
    1803:'所以我先下播了。',1804:'等一下。',1805:'等一下。',1806:'喂，菜鸟！',
    1807:'不好意思。',1808:'糟了，哎呀……',1809:'喂——',
    1810:'我自己都觉得，',1811:'明明只是玩了弹珠台，',1812:'却开始头晕了……',
    1813:'不好意思。',1814:'今天就先到这里吧。',1815:'弹珠台活动也好，',
    1816:'啊啊啊啊……',1817:'总的来说，',1818:'直播里，',1819:'还有不少想做的事，',
}
japanese = {
    42:'四月一日ベレトです!',
    253:'大声で「ロクシー」とお呼びください',
    257:'私の後にロクシー引く方は',
    354:'クラレッタ1凸まで追っかけようかなって思ってたんだけど追わなくて正解だったかもな',
    592:'皆様は今のうちにピンボーラーワタネキの二つ名でも考えておきな',
    1172:'ねえ、ロクシー、止めてこの人',
    1798:'配信始まったんですけど',
}
delete = {n['cue'] for n in data['annotations'] if n['comment'].strip().lower() == 'delete'}
assert len(delete) == 7
changes = []
pending = {
    58:'日文「渡瀬きつかれてない」存在分词/语音识别错误；中文按开播自嘲疲劳的语境整理，具体问句需听原音。',
    185:'「クレタベロ防具」疑为角色全名的误识别；未据猜测重写。珂蕾妲确有独立指代，未全局替换。',
    194:'「自殺される」很可能是「実装される」的误识别，但没有原音不能确认；本次只修正名称，中文“被歪掉之前”也需复听。',
    324:'整句日文「白衣住行の愛に家族」严重损坏；本次仅修正主播名称，其余内容保留待原音确认。',
    346:'「特務なら」可能是「と組むなら」；本次只统一克拉蕾译名，音擎搭配含义需复听。',
    1293:'与后一句组成的日语疑似存在识别错误；只统一洛克茜译名，未猜造整句。',
    1794:'「ちっぴ」的称呼原文未核实，保留原译“小千”。1795沿用相同称呼。',
    1810:'01:30:08–01:30:14 日语断句/识别有损坏，中文按可辨认内容对齐，需复听确认完整句意。',
    1826:'「イノトロ」身份/词形不明；未凭空另造人物名，保留待复听。',
}
rows=[]
for i,cue in enumerate(original):
    old=cue['text']
    if i in delete:
        changes.append((i,'按 review 删除',old,'')); continue
    if not old.strip():
        changes.append((i,'移除无正文空条目（无可显示文字）',old,'')); continue
    lines=old.split('\n')
    text=old
    # Reviewed aliases: only replace Lucy/Kole da when Japanese explicitly says Roxy.
    for a,b in [('洛克希','洛克茜'),('洛克西','洛克茜'),('罗克西','洛克茜'),
                ('克拉蕾妲','克拉蕾'),('可蕾塔','克拉蕾'),('渡濑希','四月一日'),
                ('渡濑','四月一日'),('渡木','四月一日'),('渡边姐','四月一日姐姐'),('渡敷','四月一日')]:
        text=text.replace(a,b)
    if 'ロクシー' in lines[0]:
        text=text.replace('露西','洛克茜')
        if i in {287,289,291,301}:
            text=text.replace('珂蕾妲','洛克茜')
    if i in {877,886,889,901,906,915,924,939,946,1424}:
        text=text.replace('くられた','クラレッタ')
    # Normalize identifiable streamer self-reference, preserving the nickname in Japanese.
    for a in ['渡り木','渡抜き','渡る気','渡瀬希','ワタナキ','ワタニキ','ワトキ','わたるき']:
        text=text.replace(a,'ワタネキ')
    parts=text.split('\n')
    if i in {58,324,329,1796}:
        parts[0]=parts[0].replace('渡瀬','ワタネキ').replace('四月一日','ワタネキ')
    if i in japanese: parts[0]=japanese[i]
    if i in chinese:
        assert len(parts)>=2, i
        parts[-1]=chinese[i]
    text='\n'.join(parts).replace('</|im_end|>','')
    if text != old:
        changes.append((i,'术语统一／结合上下文精校',old,text))
    rows.append(dict(index=i,timing=cue['timing'],text=text))

# Inline number/time artifacts made the two bilingual lines separate cues.
# Merge only adjacent identical timelines, preserving their original text order.
merged=[]
for row in rows:
    if merged and merged[-1]['timing']==row['timing']:
        prev=merged[-1]
        prev['text']+='\n'+row['text']
        changes.append((row['index'],'相同时间轴的分离文本合并到上一条',row['text'],prev['text']))
    else: merged.append(row.copy())
# Fix one bilingual pair whose Chinese line was demonstrably shifted from the next sentence.
for row in merged:
    if row['index']==1788:
        before=row['text']; row['text']='当然なのだ\n那是当然的！'
        changes.append((1788,'结尾错位译文对齐',before,row['text']))

out=Path(__file__).parent/'outputs'/'review_20261002'
out.mkdir(parents=True,exist_ok=True)
srt=out/'20261002_中日双语_精校.srt'
report=out/'20261002_精校修改记录.md'
assert not srt.exists() and not report.exists(), 'Refuse to overwrite an existing delivery'
srt.write_text('\n\n'.join(f"{n}\n{r['timing']}\n{r['text']}" for n,r in enumerate(merged,1))+'\n',encoding='utf-8-sig')
notes=['# 20261002 字幕精校记录','',
       '依据：用户提供的 62 条 review 标记、内嵌日中字幕及前后文。未听取原音。本文件内容为文本精校，不代表日语识别已全部核实。',
       '名称采用用户指定：四月一日、洛克茜、克拉蕾、铃。仅在有相应日语及上下文证据时纠正误译为其他角色的名称；未全局替换珂蕾妲。',
       f'输入 {len(original)} 个解析条目；输出 {len(merged)} 条。按标记删除 {len(delete)} 条，移除空正文 {sum(not c["text"].strip() for c in original)} 条。相同时间轴的分离中日文合并，字幕编号重新连续排列，保留各保留条目的时间轴原字符串。',
       '保留未标记且不能确认的开场短句/拟声词，不将它们一律作为幻觉删除。',
       '', '## 仍需原音确认','']
for i,reason in pending.items(): notes += [f'- review 索引 {i} · {original[i]["timing"]}：{reason}']
notes += ['', '## 62 条标记处理清单','']
for n in data['annotations']:
    i=n['cue']; notes += [f'- 索引 {i} · {original[i]["timing"]} · 意见：{n["comment"].strip()} · '+('已删除' if i in delete else '已落实名称修正'+('；整句待复听' if i in pending else ''))]
notes += ['', '## 逐项修改','']
for i,reason,before,after in changes:
    notes += [f'### 索引 {i} · {original[i]["timing"]}',reason,'','原文：',*['> '+l for l in before.splitlines()], '', '修改后：',*['> '+l for l in (after or '（删除）').splitlines()],'']
report.write_text('\n'.join(notes),encoding='utf-8')
# Verification: no timing invention; all marked non-delete entries were edited.
changed={i for i,_,_,_ in changes}
assert all(n['cue'] in changed for n in data['annotations'])
assert all(r['timing']==original[r['index']]['timing'] for r in merged)
assert all('-->' not in r['text'] for r in merged)
assert all(original[i]['timing'] not in [r['timing'] for r in merged] for i in delete)
print(json.dumps(dict(input_cues=len(original), output_cues=len(merged), annotations=62,
    deletes=len(delete), changed_entries=len(changed), srt=str(srt), report=str(report)),ensure_ascii=False))
