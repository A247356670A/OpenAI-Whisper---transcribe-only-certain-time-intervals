"""Compatibility command-line entry point for extracting Chinese-only SRT text.

The GUI exposes the same function as “字幕拆分”.  Every SRT entry keeps its
first text line, so the input should place Chinese above Japanese.
"""

from __future__ import annotations

import argparse

from subtitle_pipeline import extract_chinese_subtitles


def main() -> None:
    """Extract first-line Chinese text from a user-supplied bilingual SRT."""
    parser = argparse.ArgumentParser(description="从中日双语 SRT 提取仅中文字幕。")
    parser.add_argument("subtitle", help="中日双语 .srt 文件")
    parser.add_argument("--output-dir", help="中文字幕的保存文件夹")
    args = parser.parse_args()

    # The source subtitle is never changed; a new *_zh.srt file is created.
    output = extract_chinese_subtitles(args.subtitle, args.output_dir)
    print(f"仅中文字幕已生成：{output.chinese_only}")


if __name__ == "__main__":
    main()
