"""Start the subtitle GUI, or run the same two-pass workflow from a terminal.

Double-clicking this file (or running it without arguments) opens the GUI.
"""

from __future__ import annotations
import argparse
from pathlib import Path
from subtitle_pipeline import run_two_pass_transcription


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用 Whisper 生成日语字幕 A、B 和合并字幕。"
    )
    parser.add_argument("video", nargs="?", help="视频或音频文件；省略时启动图形界面")
    parser.add_argument("--output-dir", help="字幕保存文件夹，默认与视频相同")
    parser.add_argument("--model", default="large-v2", help="Whisper 模型，默认 large-v2")
    parser.add_argument("--merge-gap", type=float, default=1.0, help="A 字幕间的合并间隔（秒）")
    parser.add_argument("--duplicate-threshold", type=float, default=0.5, help="合并去重阈值（秒）")
    args = parser.parse_args()

    if not args.video:
        from subtitle_gui import main as gui_main
        gui_main()
        return

    outputs = run_two_pass_transcription(
        args.video,
        args.output_dir or Path(args.video).parent,
        model_name=args.model,
        merge_gap=args.merge_gap,
        duplicate_threshold=args.duplicate_threshold,
    )
    print(f"\n完成，合并字幕：{outputs.merged}")


if __name__ == "__main__":
    main()
