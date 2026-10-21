"""Reproducible conservative refinement plan for the attached 2026-10-18 package."""

import csv
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parent

# Longer/specific forms must precede their substrings.  Names verified against
# the official Japanese ZZZ site are labelled "official" in the report.
REPLACEMENTS = [
    ("渡根希弁", "四月一日ベレト", "主播姓名"),
    ("渡瀬貴", "四月一日", "主播姓名"),
    ("ワタニキ", "四月一日", "主播姓名"),
    ("ワタネキ", "四月一日", "主播姓名"),
    ("わタニキ", "四月一日", "主播姓名"),
    ("渡瀬", "四月一日", "主播姓名"),
    ("シーシーアドロ", "シーシィア殿", "官方角色名"),
    ("シーシーア", "シーシィア", "官方角色名"),
    ("シーシア", "シーシィア", "官方角色名"),
    ("シリシア", "シーシィア", "官方角色名"),
    ("シシア", "シーシィア", "官方角色名"),
    ("シグニット", "シグリッド", "官方角色名"),
    ("シグリット", "シグリッド", "官方角色名"),
    ("セベリアン", "セヴェリアン", "官方角色名"),
    ("プロメイヤー", "プロメイア", "官方角色名"),
    ("パルセルグループ", "マルセルグループ", "官方专名与Qwen依据"),
    ("リンドベルのなけ", "リンドベルヌだけ", "Qwen对照与语法"),
    ("ロスカリファー", "ロスカリファ", "官方地名"),
    ("ロスカリフォ", "ロスカリファ", "官方地名"),
    ("ロスカリバ", "ロスカリファ", "官方地名"),
    ("ロスカリワ", "ロスカリファ", "官方地名"),
    ("ノースカリファニーコネ", "ロスカリファにコネ", "官方地名与句法"),
    ("ノースカリファ", "ロスカリファ", "官方地名"),
    ("シンゲリート", "新エリー都", "官方地名"),
    ("シンエリート", "新エリー都", "官方地名"),
    ("新エリート", "新エリー都", "官方地名"),
    ("算数局", "算理中枢局", "官方机构名"),
    ("ホーブリング", "ホブリング", "官方专名"),
    ("クローンさん", "クロウさん", "官方角色名与上下文"),
    ("クローン", "クロウ", "官方角色名与上下文"),
    ("クロヲ", "クロウ", "官方角色名"),
    ("グロウさん", "クロウさん", "官方角色名与Qwen依据"),
    ("クロー", "クロウ", "官方角色名"),
    ("ホブリングクロウ", "ホブリング・クロウ", "官方事件/事务所名"),
    ("クロウダー", "クロウだ", "角色名与句法"),
    ("苦労殿", "クロウ殿", "角色名与上下文"),
    ("プロ騎士", "プロキシ", "官方术语"),
    ("イヤッスー", "イアス", "官方角色名"),
    ("ディミー", "ディニー", "官方货币名"),
    ("ボンブ", "ボンプ", "官方术语"),
    ("キャラッド", "キャロット", "事件核心术语"),
    ("ギャロット", "キャロット", "事件核心术语"),
    ("キャロットウリ", "キャロット売り", "明显分词错误"),
    ("キャロットウ横流し", "キャロット横流し", "明显分词错误"),
    ("ロゼタデータ", "ロゼッタデータ", "官方术语"),
    ("全列増ゼロ", "ゼンレスゾーンゼロ", "作品名"),
    ("ゼンレスゾンジェロ", "ゼンレスゾーンゼロ", "作品名"),
    ("ゼンジャロ", "ゼンゼロ", "作品简称"),
    ("全ゼロ", "ゼンゼロ", "作品简称"),
    ("身柄を抑えて", "身柄を押さえて", "日语用字与Qwen依据"),
    ("影ながら", "陰ながら", "日语用字与Qwen依据"),
    ("甲羅総務次官", "コーラ総務次官", "人物名与上下文"),
    ("ジャンドラ", "チャンドラ", "人物名与上下文"),
    ("ちゃんどら", "チャンドラ", "人物名统一"),
    ("チャンドラー", "チャンドラ", "人物名统一"),
    ("ベッグフォードライフ近", "ベックフォード街付近", "Qwen对照与句法"),
    ("文部の記憶素子", "ボンプの記憶素子", "上下文术语"),
    ("演習率ではなく123123", "円周率ではなく1、2、3、1、2、3", "Qwen对照与上下文"),
    ("アスラム算理中枢局禁制", "ブーアストラム算理中枢局謹製", "地名、机构名与固定表达"),
]


def timestamp_seconds(cue):
    match = re.search(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})", cue["timing"])
    h, m, s, ms = map(int, match.groups())
    return h * 3600 + m * 60 + s + ms / 1000


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text) if not c.isspace())


def main(package_path):
    package = json.loads(Path(package_path).read_text(encoding="utf-8"))
    whisper = package["whisper"]["cues"]
    qwen = package["qwen"]["cues"]
    matches = package["matches"]
    output = []
    changes = []
    removed = []

    for internal_id, cue in enumerate(whisper):
        text = cue["text"]
        # Both ASR tracks indicate that the actual greeting starts around
        # 00:04:24.  Earlier Whisper text is multilingual/nonsensical BGM ASR.
        if timestamp_seconds(cue) < 263.5:
            removed.append((internal_id, cue, "开场待机音乐误识别；Qwen无对应有效对白"))
            continue
        if not text.strip():
            removed.append((internal_id, cue, "空白零时长条目"))
            continue
        original = text
        reasons = []
        for old, new, reason in REPLACEMENTS:
            if old in text:
                text = text.replace(old, new)
                reasons.append(f"{old} → {new}（{reason}）")
        if text != original:
            changes.append((internal_id, cue["number"], cue["timing"], original, text, "；".join(reasons)))
        output.append(dict(cue, text=text))

    srt_path = OUTPUT_DIR / "20261018_日语字幕_双模型精准校对.srt"
    srt_text = "\n\n".join(
        f"{index}\n{cue['timing']}\n{cue['text']}" for index, cue in enumerate(output, 1)
    ) + "\n"
    srt_path.write_text(srt_text, encoding="utf-8-sig")

    # Keep every unresolved large disagreement available for later listening.
    pending = []
    for i, js in enumerate(matches):
        if not js or not whisper[i]["text"].strip() or timestamp_seconds(whisper[i]) < 263.5:
            continue
        qtext = "".join(qwen[j]["text"] for j in js)
        left, right = normalized(whisper[i]["text"]), normalized(qtext)
        similarity = difflib.SequenceMatcher(None, left, right).ratio() if left or right else 1.0
        if similarity < 0.20:
            pending.append(("模型分歧", i, whisper[i]["timing"], whisper[i]["text"], qtext,
                            f"相似度 {similarity:.1%}；未听音，不自动覆盖"))

    for j in package.get("addition_candidates", []):
        cue = qwen[j]
        start = timestamp_seconds(cue)
        stamp = re.findall(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})", cue["timing"])
        end = sum(int(x) * factor for x, factor in zip(stamp[1], (3600, 60, 1, .001)))
        duration = end - start
        pending.append(("Qwen独有", j, cue["timing"], "", cue["text"],
                        f"时长 {duration:.3f}s；缺少Whisper/音频确认，未自动加入"))

    pending_path = OUTPUT_DIR / "20261018_待听音确认.tsv"
    with pending_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["类别", "内部ID", "时间轴", "Whisper", "Qwen", "处理说明"])
        writer.writerows(pending)

    report_path = OUTPUT_DIR / "20261018_精准校对修改记录.md"
    report = [
        "# 20261018 双模型精准校对记录", "",
        f"- Whisper 原条目：{len(whisper)}",
        f"- 成品条目：{len(output)}",
        f"- 修改条目：{len(changes)}",
        f"- 排除条目：{len(removed)}（仅开场明显误识别及空白条目）",
        f"- 待听音确认：{len(pending)}",
        "- 原则：保留 Whisper 时间轴和正文结构；Qwen 只作佐证；未听音问题不猜测。", "",
        "## 已修改", "",
    ]
    for _, number, timing, before, after, reason in changes:
        report.extend([f"### 原编号 {number} · {timing}", "", f"- 原文：{before}",
                       f"- 修正：{after}", f"- 依据：{reason}", ""])
    report.extend(["## 已排除", ""])
    for internal_id, cue, reason in removed:
        report.extend([f"- ID {internal_id} · {cue['timing']} · `{cue['text']}` · {reason}"])
    report.extend(["", "## 限制", "",
                   "本轮没有音频，仅完成双模型文本对照、官方专名统一和明确错字修正。",
                   "待确认表中的内容没有自动写入或覆盖成品；需要听音后才能继续判定。"])
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    summary = {
        "source": package["whisper"]["source_name"],
        "output_srt": str(srt_path),
        "changes": len(changes),
        "removed": len(removed),
        "pending": len(pending),
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
