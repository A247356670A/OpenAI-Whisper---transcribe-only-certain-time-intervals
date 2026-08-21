"""Start the subtitle GUI, or run the same two-pass workflow from a terminal.

Double-clicking this file (or running it without arguments) opens the GUI.
"""

from __future__ import annotations
import argparse
from pathlib import Path
from subtitle_pipeline import CPU_THREAD_PROFILES, run_two_pass_transcription


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用 Whisper 生成日语字幕 A、B 和合并字幕。"
    )
    parser.add_argument("video", nargs="?", help="视频或音频文件；省略时启动图形界面")
    parser.add_argument("--output-dir", help="字幕保存文件夹，默认与视频相同")
    parser.add_argument("--model", default="large-v2", help="Whisper 模型，默认 large-v2")
    parser.add_argument("--merge-gap", type=float, default=1.0, help="A 字幕间的合并间隔（秒）")
    parser.add_argument("--duplicate-threshold", type=float, default=0.5, help="合并去重阈值（秒）")
    parser.add_argument(
        "--cpu-thread-profile",
        choices=CPU_THREAD_PROFILES,
        default="performance",
        help="CPU 模式：performance 使用更多线程；balanced 为 GUI 流畅预留核心",
    )
    parser.add_argument(
        "--gpu-acceleration",
        action="store_true",
        help="启用 NVIDIA CUDA 高性能模式（FP16/TF32）；CUDA 不可用时直接报错",
    )
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
        cpu_thread_profile=args.cpu_thread_profile,
        gpu_acceleration=args.gpu_acceleration,
    )
    print(f"\n完成，合并字幕：{outputs.merged}")


if __name__ == "__main__":
    main()
