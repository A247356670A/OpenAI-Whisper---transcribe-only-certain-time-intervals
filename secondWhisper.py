"""Compatibility command-line entry point for the GUI's “only generate B” mode.

This file intentionally contains no sample media paths.  For daily use, open
the GUI and choose “补全模式”; this command remains useful for automation.
"""

from __future__ import annotations

import argparse

from subtitle_pipeline import run_second_pass_from_subtitle


def main() -> None:
    """Read user-supplied paths and generate B from an existing subtitle A."""
    parser = argparse.ArgumentParser(description="使用已有字幕 A，仅识别并生成日语字幕 B。")
    parser.add_argument("video", help="原视频或音频文件")
    parser.add_argument("subtitle_a", help="已有翻译字幕 A（.srt）")
    parser.add_argument("--output-dir", help="B 字幕的保存文件夹")
    parser.add_argument("--model", default="large-v2", help="Whisper 模型")
    parser.add_argument("--merge-gap", type=float, default=1.0, help="字幕 A 覆盖区间的合并间隔（秒）")
    args = parser.parse_args()

    # The pipeline uses A only as a read-only timeline; it writes B separately.
    output = run_second_pass_from_subtitle(
        args.video,
        args.subtitle_a,
        args.output_dir,
        model_name=args.model,
        merge_gap=args.merge_gap,
    )
    print(f"字幕 B 已生成：{output.second_pass}")


if __name__ == "__main__":
    main()
