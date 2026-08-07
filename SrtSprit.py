import pysrt

subs = pysrt.open(
    "20260806_【ゼンレスゾーンゼロ】波乱万丈Ver.3.1メインストーリー「ロング・グッドバイ」前半戦【Vtuber】_zh_merged.srt", encoding="utf-8")
for i, sub in enumerate(subs[:5]):
    print("======")
    print(sub.text)
    print(repr(sub.text))

for sub in subs:
    lines = sub.text.splitlines()
    if len(lines) >= 2:
        sub.text = lines[0]

subs.save("20260806_【ゼンレスゾーンゼロ】波乱万丈Ver.3.1メインストーリー「ロング・グッドバイ」前半戦【Vtuber】_zh_LLM.srt", encoding="utf-8")