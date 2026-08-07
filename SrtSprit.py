import pysrt

subs = pysrt.open(
    "20260804_【ゼンレスゾーンゼロ】レミエールの動画が山ほど来てるぞ！！今夜は観賞パーティですわ！！【Vtuber】_zh_LLM_merged.srt", encoding="utf-8")
for i, sub in enumerate(subs[:5]):
    print("======")
    print(sub.text)
    print(repr(sub.text))

for sub in subs:
    lines = sub.text.splitlines()
    if len(lines) >= 2:
        sub.text = lines[0]

subs.save("20260804_【ゼンレスゾーンゼロ】レミエールの動画が山ほど来てるぞ！！今夜は観賞パーティですわ！！【Vtuber】_zh_LLM.srt", encoding="utf-8")