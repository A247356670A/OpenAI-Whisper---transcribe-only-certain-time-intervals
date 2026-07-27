import pysrt

subs = pysrt.open(
    "20260625_ボンプの懸念を晴らそう；；第1章「ある夢に遊ぶ者の告白」最後まで！！【Vtuber】_merged_zh_LLM.srt", encoding="utf-8")
for i, sub in enumerate(subs[:5]):
    print("======")
    print(sub.text)
    print(repr(sub.text))

for sub in subs:
    lines = sub.text.splitlines()
    if len(lines) >= 2:
        sub.text = lines[1]

subs.save("20260625_ボンプの懸念を晴らそう；；第1章「ある夢に遊ぶ者の告白」最後まで！！【Vtuber】_zh_LLM.srt", encoding="utf-8")