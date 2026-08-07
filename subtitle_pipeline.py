"""Reusable two-pass Whisper workflow for Japanese subtitles.

The module deliberately imports Whisper, Torch and Librosa only while a job is
running.  This keeps the GUI responsive at startup and makes import errors
actionable instead of failing when the window opens.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Callable

from SrtMerge import merge_srt, write_srt
from SrtToIntervals import extract_time_intervals
from exclude_segments_by_intervals import exclude_segments_by_intervals
from transcribe import save_srt, transcribe, transcribe_segments


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class SubtitleOutputs:
    """Files produced by a completed two-pass transcription."""

    first_pass: Path
    second_pass: Path
    merged: Path


def build_output_paths(video_path: str | Path, output_dir: str | Path) -> SubtitleOutputs:
    """Return predictable, Unicode-safe output names for a video."""
    stem = Path(video_path).stem
    destination = Path(output_dir)
    return SubtitleOutputs(
        first_pass=destination / f"{stem}_A.srt",
        second_pass=destination / f"{stem}_B.srt",
        merged=destination / f"{stem}_merged.srt",
    )


def _log(callback: LogCallback | None, message: str) -> None:
    if callback:
        callback(message)
    else:
        print(message)


def _import_dependencies():
    """Import large optional dependencies at run time with a helpful error."""
    try:
        import librosa
        import torch
        import whisper
    except ImportError as exc:
        raise RuntimeError(
            "缺少运行依赖。请在项目目录执行：\n"
            "python -m pip install -r requirements.txt"
        ) from exc
    return librosa, torch, whisper


def run_two_pass_transcription(
    video_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    model_name: str = "large-v2",
    merge_gap: float = 1.0,
    duplicate_threshold: float = 0.5,
    log_callback: LogCallback | None = None,
) -> SubtitleOutputs:
    """Generate A, B and merged Japanese SRT files from *video_path*.

    A is transcribed from the whole source.  The time ranges already covered
    by A are excluded from the source audio; B is then transcribed from the
    remaining gaps.  Finally both files are merged with duplicate removal.
    """
    source = Path(video_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到视频或音频文件：{source}")
    if merge_gap < 0 or duplicate_threshold < 0:
        raise ValueError("时间间隔和去重阈值必须大于或等于 0。")

    destination = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else source.parent
    )
    destination.mkdir(parents=True, exist_ok=True)
    outputs = build_output_paths(source, destination)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "未找到 FFmpeg。请先安装 FFmpeg 并将其加入系统 PATH，然后重新运行。"
        )

    librosa, torch, whisper = _import_dependencies()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _log(log_callback, f"使用设备：{device.upper()}；正在加载 Whisper 模型 {model_name}…")
    model = whisper.load_model(model_name, device=device)

    first_options = {
        "language": "ja",
        "word_timestamps": True,
        "suppress_tokens": [],
        "condition_on_previous_text": True,
        "fp16": device == "cuda",
    }
    second_options = {
        "language": "ja",
        "word_timestamps": True,
        "suppress_tokens": [],
        "condition_on_previous_text": False,
        "fp16": device == "cuda",
    }

    _log(log_callback, "第 1 步/3：识别完整视频，生成字幕 A…")
    transcribe(str(source), first_options, model, str(outputs.first_pass))

    _log(log_callback, "正在读取音频并计算 A 未覆盖的片段…")
    audio_array, sample_rate = librosa.load(str(source), sr=16_000, mono=True)
    full_interval = [[0, len(audio_array) / sample_rate]]
    excluded_intervals = extract_time_intervals(
        str(outputs.first_pass), merge_gap=merge_gap
    )
    audio_segments, remaining_intervals = exclude_segments_by_intervals(
        audio_array, full_interval, excluded_intervals, sample_rate
    )

    if remaining_intervals:
        _log(
            log_callback,
            f"第 2 步/3：识别 {len(remaining_intervals)} 个未覆盖片段，生成字幕 B…",
        )
        transcribe_segments(
            audio_segments, second_options, model, str(outputs.second_pass)
        )
    else:
        _log(log_callback, "第 2 步/3：A 已覆盖全部音频，创建空的字幕 B。")
        save_srt([], str(outputs.second_pass))

    _log(log_callback, "第 3 步/3：合并 A 与 B，并移除重复字幕…")
    merged_subtitles = merge_srt(
        str(outputs.first_pass),
        str(outputs.second_pass),
        time_threshold=duplicate_threshold,
    )
    write_srt(merged_subtitles, str(outputs.merged))
    _log(log_callback, f"完成：{outputs.merged}")
    return outputs
