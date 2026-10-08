"""Apply human review decisions without altering the source review or timestamps."""
import hashlib
import json
from pathlib import Path

source = next(Path('Z:/Moives/四月一日').glob('20261006*_zh_Dual_review.json'))
source_bytes = source.read_bytes()
data = json.loads(source_bytes.decode('utf-8-sig'))
original = data['cues']
assert len(original) == 2075 and len(data['annotations']) == 81
assert hashlib.sha256(data['source_srt'].encode('utf-8')).hexdigest() == data['source_sha256']
for note in data['annotations']:
    assert original[note['cue']]['text'][note['start']:note['end']] == note['quote']

# Indices are review array offsets, not the sometimes duplicated SRT numbers.
delete = {n['cue'] for n in data['annotations'] if n['comment'].strip() in {'删', '删除'}}
zh = {
    23: '我是四月一日，让大家久等了呢。',
    348: '好像掉着一个瓶盖。', 352: '嗯，几乎全新的瓶盖。', 356: '说到瓶盖，',
    382: '维琳娜她，', 383: '最后占了相当多的戏份，',
    384: '虽然同样是庆祝，', 385: '却形成了对比，', 386: '特别……',
    387: '有味道。', 388: '（嘿嘿～）', 389: '不是，就是啊……',
    390: '诺姆那段，', 391: '快要哭出来的那段表演也特别好啊。',
    392: '“初次见面”这句话，', 393: '诺姆究竟已经多少次，',
    394: '被别人这样说过了呢……我忍不住这么想。',
    398: '邦布的好朋友，也是瓶盖收藏大师候选人——希希芙！',
    403: '交换瓶盖？', 404: '最近大家都在交换瓶盖呢。',
    414: '看来还有几个独一无二的瓶盖呢。', 428: '您鉴赏瓶盖的眼光真是太好了。',
    437: '啊，不过，别人拜托我找的瓶盖还……', 441: '瓶盖的话，我有收藏。',
    443: '缝纫邦布从自己收藏的瓶盖中，', 444: '拿出几个递给她后，',
    445: '希希芙把每一个瓶盖，', 457: '说了好多话啊。',
    596: '希希芙，你居然让免费的 AI 代写啊。',
    601: '希希芙居然会说“笑都笑不出来”这种话啊。',
    869: '在我昏迷不醒的时候，一直陪在我身边。',
    871: '因为是精心设计的姿势，所以又用了一次。',
    1010: '感觉好像有过呢。', 1038: '趁追击一直没停、球还没回来的时候，',
    1448: '打得漂亮！', 1514: '这个也太可爱了。',
    1664: '像公开六科日常那样的。', 1783: '只能逃跑。',
}
streamers = {
    192: '渡磨木', 284: '绵根木', 526: '渡边木', 1070: '渡濑希',
    1071: '渡濑希', 1170: '绵根木', 1199: '绵根木', 1251: '渡月木',
    1344: '渡狸', 1647: '渡根君', 1831: '绵根木', 2021: '渡根君',
}
names = {
    91: ('梅丽娜', '维琳娜'), 662: ('凛', '铃'), 1271: ('珊瑚', '瞬光'),
    1289: ('安姆林小姐', '挽昼小姐'), 1628: ('米埃尔', '雷米埃尔'),
    1674: ('凛', '铃'), 1700: ('凛', '铃'),
    1874: ('诺鲁努', '诺姆'), 1911: ('诺鲁努', '诺姆'),
}
shishifu = {596,601,610,617,620,630,634,635,637,650,655,665,1060,1088,1106,1108}
changes = []
rows = []
for i, cue in enumerate(original):
    old = cue['text']
    if i in delete or not old.strip():
        changes.append((i, '按标记删除整条（55、2061含无法可靠还原标题的提示词污染）' if i in delete else '移除空正文', old, ''))
        continue
    parts = old.split('\n')
    # Modify the translation only; uncertain Japanese speech remains available for listening review.
    if i in streamers:
        parts[-1] = parts[-1].replace(streamers[i], '四月一日')
    if i in names:
        parts[-1] = parts[-1].replace(*names[i])
    if i in shishifu:
        for alias in ('凯撒', '希希亚', '谢希雅'):
            parts[-1] = parts[-1].replace(alias, '希希芙')
    parts[-1] = parts[-1].replace('蕾米埃尔', '雷米埃尔')
    if i in zh:
        parts = [parts[0], zh[i]]
    text = '\n'.join(parts)
    if text != old:
        changes.append((i, '依据批注及相邻上下文修正中文／清理提示词污染', old, text))
    rows.append({'index': i, 'timing': cue['timing'], 'text': text})

# Only join split bilingual single-line pairs with an identical original timeline.
import re
merged = []
for row in rows:
    if (merged and merged[-1]['timing'] == row['timing']
            and '\n' not in merged[-1]['text'] and '\n' not in row['text']
            and re.search('[ぁ-ヿ]', merged[-1]['text'])
            and not re.search('[ぁ-ヿ]', row['text'])):
        before = row['text']
        merged[-1]['text'] += '\n' + before
        changes.append((row['index'], '同时间轴分离中日文合并', before, merged[-1]['text']))
    else:
        merged.append(row.copy())

changed = {i for i, _, _, _ in changes}
assert all(n['cue'] in changed for n in data['annotations'])
assert all(r['timing'] == original[r['index']]['timing'] for r in merged)
assert not any('严格术语表' in r['text'] or '严格词汇表' in r['text'] for r in merged)
assert source.read_bytes() == source_bytes
out = Path(__file__).parent / 'outputs' / 'review_20261006'
out.mkdir(parents=True, exist_ok=True)
srt = out / '20261006_中日双语_精校.srt'
report = out / '20261006_精校修改记录.md'
assert not srt.exists() and not report.exists(), 'Do not overwrite previous deliveries'
content = '\n\n'.join(f"{n}\n{r['timing']}\n{r['text']}" for n, r in enumerate(merged, 1)) + '\n'
from subtitle_proofreading import _parse_cues
parsed = _parse_cues(content)
assert len(parsed) == len(merged)
assert all(a['text'] == b['text'] and a['timing'] == b['timing'] for a,b in zip(parsed,merged))
srt.write_text(content, encoding='utf-8-sig')
notes = ['# 20261006 双语字幕精校记录', '',
    '依据用户 review 的全部 81 条标记（含重复标记）与相关字幕上下文进行文本精校，未听原音。原 review 和源字幕未修改。',
    f'输入 {len(original)} 条；输出 {len(merged)} 条；按标记删除 {len(delete)} 条；移除 {sum(not c["text"].strip() for c in original)} 条空正文。保留原时间轴，重新连续编号。',
    '修正重点：四月一日、希希芙、铃、瞬光、挽昼、雷米埃尔、六科、诺姆；瓶盖误译；无根据添加的角色名；翻译提示词污染；382–394 附近中文错位。',
    '只修正有上下文依据的称呼；没有全局替换凯撒、珂蕾妲、露西或帽子。日文正文保留，便于对照原音。', '',
    '## 需确认与处理边界', '',
    '- 标记对同一人物分别写了“维琳娜”“维林娜”，暂统一为“维琳娜”；若你的术语表采用后者，可再统一。',
    '- 索引 55 的删除选区包含日文和提示词，但未包含末尾混合残文；按删除意见移除整条，避免留下无意义残文。2061 同样删除。活动名的准确日文仍需原音确认。',
    '- 索引 596 的 AI 代写句按前后文纠正施事关系，日文识别本身有误，整句语气建议复听。',
    '- 索引 403 的日文「タンバル交換」不清；中文按批注及瓶盖交换语境修改。443 的“缝纫邦布”日文识别尚未验证。',
    '- 各处日文人名误识别未凭中文批注倒推拼写；本次人名规范主要落实在中文行。未标记的含糊短句不擅自删去。', '',
    '## 全部标记处理清单', '']
for n in data['annotations']:
    i = n['cue']
    notes.append(f"- 索引 {i} · {original[i]['timing']} · 意见：{n['comment'].strip() or '无评论（同条另有删除标记）'} · {'已删除' if i in delete else '已修改'}")
notes.extend(['', '## 修改明细（索引为 review 的零基索引）', ''])
for i, reason, before, after in changes:
    notes.extend([f"### 索引 {i} · {original[i]['timing']}", reason, '', '原文：',
                  *['> ' + line for line in before.splitlines()], '', '修改后：',
                  *['> ' + line for line in (after or '（删除）').splitlines()], ''])
report.write_text('\n'.join(notes), encoding='utf-8-sig')
print(json.dumps({'input': len(original), 'output': len(merged), 'annotations':81,
                  'deleted':len(delete), 'changed_entries':len(changed), 'verified':True,
                  'srt':str(srt), 'report':str(report)}, ensure_ascii=True))
