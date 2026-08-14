"""Reusable two-pass Whisper workflow for Japanese subtitles.

The module deliberately imports Whisper, Torch and Librosa only while a job is
running.  This keeps the GUI responsive at startup and makes import errors
actionable instead of failing when the window opens.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Mapping
from SrtMerge import merge_srt, write_srt
from SrtToIntervals import extract_time_intervals
from exclude_segments_by_intervals import exclude_segments_by_intervals
from transcribe import save_srt, transcribe, transcribe_segments
from whisper_options import build_whisper_options


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class SubtitleOutputs:
    """Files produced by a completed two-pass transcription."""

    first_pass: Path
    second_pass: Path
    merged: Path


@dataclass(frozen=True)
class FirstPassOutput:
    """The A subtitle produced by a full-file first Whisper pass."""

    first_pass: Path


@dataclass(frozen=True)
class SecondPassOutput:
    """The B subtitle produced from an existing, translated A subtitle."""

    source_subtitle: Path
    second_pass: Path


@dataclass(frozen=True)
class SubtitleSplitOutput:
    """The Chinese-only subtitle extracted from a bilingual SRT file."""

    source_subtitle: Path
    chinese_only: Path


@dataclass(frozen=True)
class BurnedSubtitleVideoOutput:
    """An MP4 video whose image permanently includes the selected subtitles."""

    source_video: Path
    source_subtitle: Path
    burned_video: Path
    input_was_mp4: bool


def build_output_paths(video_path: str | Path, output_dir: str | Path) -> SubtitleOutputs:
    """Return predictable, Unicode-safe output names for a video."""
    stem = Path(video_path).stem
    destination = Path(output_dir)
    return SubtitleOutputs(
        first_pass=destination / f"{stem}_A.srt",
        second_pass=destination / f"{stem}_B.srt",
        merged=destination / f"{stem}_merged.srt",
    )


def build_second_pass_path(
    translated_a_path: str | Path, output_dir: str | Path
) -> Path:
    """Name the B output from the supplied subtitle A instead of overwriting it."""
    subtitle_a = Path(translated_a_path)
    return Path(output_dir) / f"{subtitle_a.stem}_B.srt"


def build_chinese_only_path(
    bilingual_subtitle_path: str | Path, output_dir: str | Path
) -> Path:
    """Return the non-destructive output name for Chinese-only subtitles."""
    source = Path(bilingual_subtitle_path)
    return Path(output_dir) / f"{source.stem}_zh.srt"


def build_burned_video_path(video_path: str | Path, output_dir: str | Path) -> Path:
    """Return the non-destructive MP4 filename for a subtitle-burned video."""
    source = Path(video_path)
    return Path(output_dir) / f"{source.stem}_burned_subtitles.mp4"


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
    first_whisper_values: Mapping[str, Any] | None = None,
    second_whisper_values: Mapping[str, Any] | None = None,
    log_callback: LogCallback | None = None,
) -> SubtitleOutputs:
    """Generate A, B and merged Japanese SRT files from *video_path*.

    A is transcribed from the whole source.  The time ranges already covered
    by A are excluded from the source audio; B is then transcribed from the
    remaining gaps. Finally, both files are merged with duplicate removal.
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

    # First and second passes have independent editable Whisper configurations.
    first_options = build_whisper_options(
        "first", first_whisper_values, device=device
    )
    second_options = build_whisper_options(
        "second", second_whisper_values, device=device
    )

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


def run_first_pass_transcription(
    video_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    model_name: str = "large-v2",
    first_whisper_values: Mapping[str, Any] | None = None,
    log_callback: LogCallback | None = None,
) -> FirstPassOutput:
    """Transcribe the entire source once and create only subtitle A."""
    source = Path(video_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到视频或音频文件：{source}")

    destination = (
        Path(output_dir).expanduser().resolve() if output_dir else source.parent
    )
    destination.mkdir(parents=True, exist_ok=True)
    first_pass = build_output_paths(source, destination).first_pass

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "未找到 FFmpeg。请先安装 FFmpeg 并将其加入系统 PATH，然后重新运行。"
        )

    _librosa, torch, whisper = _import_dependencies()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _log(log_callback, f"使用设备：{device.upper()}；正在加载 Whisper 模型 {model_name}…")
    model = whisper.load_model(model_name, device=device)
    first_options = build_whisper_options(
        "first", first_whisper_values, device=device
    )

    _log(log_callback, "仅生成 A：正在识别完整视频…")
    transcribe(str(source), first_options, model, str(first_pass))
    _log(log_callback, f"完成：仅生成字幕 A：{first_pass}")
    return FirstPassOutput(first_pass=first_pass)


def run_second_pass_from_subtitle(
    video_path: str | Path,
    translated_a_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    model_name: str = "large-v2",
    merge_gap: float = 1.0,
    second_whisper_values: Mapping[str, Any] | None = None,
    log_callback: LogCallback | None = None,
) -> SecondPassOutput:
    """Create only B from a video and an existing (for example translated) A.

    The supplied A is read only for its time ranges.  It is never overwritten,
    and this mode intentionally does not create a merged subtitle file.
    """
    source = Path(video_path).expanduser().resolve()
    subtitle_a = Path(translated_a_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到视频或音频文件：{source}")
    if not subtitle_a.is_file():
        raise FileNotFoundError(f"找不到字幕 A 文件：{subtitle_a}")
    if subtitle_a.suffix.lower() != ".srt":
        raise ValueError("字幕 A 必须是 .srt 文件。")
    if merge_gap < 0:
        raise ValueError("时间间隔必须大于或等于 0。")

    destination = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else subtitle_a.parent
    )
    destination.mkdir(parents=True, exist_ok=True)
    second_pass = build_second_pass_path(subtitle_a, destination)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "未找到 FFmpeg。请先安装 FFmpeg 并将其加入系统 PATH，然后重新运行。"
        )

    librosa, torch, whisper = _import_dependencies()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _log(log_callback, f"使用设备：{device.upper()}；正在加载 Whisper 模型 {model_name}…")
    model = whisper.load_model(model_name, device=device)
    second_options = build_whisper_options(
        "second", second_whisper_values, device=device
    )

    _log(log_callback, "正在读取视频，并按已有字幕 A 的时间轴寻找未覆盖片段…")
    audio_array, sample_rate = librosa.load(str(source), sr=16_000, mono=True)
    full_interval = [[0, len(audio_array) / sample_rate]]
    excluded_intervals = extract_time_intervals(str(subtitle_a), merge_gap=merge_gap)
    audio_segments, remaining_intervals = exclude_segments_by_intervals(
        audio_array, full_interval, excluded_intervals, sample_rate
    )

    if remaining_intervals:
        _log(
            log_callback,
            f"仅生成 B：正在识别 {len(remaining_intervals)} 个未覆盖片段…",
        )
        transcribe_segments(audio_segments, second_options, model, str(second_pass))
    else:
        _log(log_callback, "字幕 A 已覆盖全部音频，创建空的字幕 B。")
        save_srt([], str(second_pass))

    _log(log_callback, f"完成：仅生成字幕 B：{second_pass}")
    return SecondPassOutput(source_subtitle=subtitle_a, second_pass=second_pass)


def extract_chinese_subtitles(
    bilingual_subtitle_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    log_callback: LogCallback | None = None,
) -> SubtitleSplitOutput:
    """Keep the first text line of every SRT entry as the Chinese subtitle.

    This is the behavior of the original ``SrtSprit.py`` helper: bilingual
    files are expected to place the Chinese translation on the first text line
    and Japanese on the following line(s).  Timing and subtitle numbering are
    preserved exactly in the newly written SRT.
    """
    source = Path(bilingual_subtitle_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到中日双语字幕文件：{source}")
    if source.suffix.lower() != ".srt":
        raise ValueError("请选择 .srt 字幕文件。")

    destination = (
        Path(output_dir).expanduser().resolve() if output_dir else source.parent
    )
    destination.mkdir(parents=True, exist_ok=True)
    chinese_only = build_chinese_only_path(source, destination)

    content = source.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\r?\n[ \t]*\r?\n", content.strip()) if content.strip() else []
    extracted_blocks: list[str] = []
    converted_count = 0

    for block in blocks:
        lines = block.splitlines()
        time_line_index = next(
            (index for index, line in enumerate(lines) if "-->" in line), None
        )
        if time_line_index is None:
            continue
        text_lines = [line for line in lines[time_line_index + 1 :] if line.strip()]
        if not text_lines:
            continue
        extracted_blocks.append("\n".join(lines[: time_line_index + 1] + [text_lines[0]]))
        converted_count += 1

    chinese_only.write_text(
        "\n\n".join(extracted_blocks) + ("\n" if extracted_blocks else ""),
        encoding="utf-8",
    )
    _log(log_callback, f"已从 {converted_count} 条字幕中保留第一行中文：{chinese_only}")
    return SubtitleSplitOutput(source_subtitle=source, chinese_only=chinese_only)


def _ffmpeg_filter_filename(path: Path) -> str:
    """Escape a subtitle path for FFmpeg's ``subtitles`` video filter."""
    value = path.resolve().as_posix()
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(",", "\\,")
    )


def burn_subtitles_to_mp4(
    video_path: str | Path,
    subtitle_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    log_callback: LogCallback | None = None,
) -> BurnedSubtitleVideoOutput:
    """Convert a video to H.264/AAC MP4 while permanently burning in an SRT.

    FFmpeg's ``subtitles`` filter (libass) draws the text into each video
    frame. The resulting MP4 therefore shows captions in any player, but the
    captions can no longer be switched off.
    """
    source_video = Path(video_path).expanduser().resolve()
    source_subtitle = Path(subtitle_path).expanduser().resolve()
    if not source_video.is_file():
        raise FileNotFoundError(f"找不到视频文件：{source_video}")
    if not source_subtitle.is_file() or source_subtitle.suffix.lower() != ".srt":
        raise ValueError("请选择有效的 .srt 字幕文件。")
    input_was_mp4 = source_video.suffix.lower() == ".mp4"

    destination = (
        Path(output_dir).expanduser().resolve() if output_dir else source_video.parent
    )
    destination.mkdir(parents=True, exist_ok=True)
    burned_video = build_burned_video_path(source_video, destination)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 FFmpeg。请先安装 FFmpeg 并将其加入系统 PATH，然后重新运行。")

    filter_value = f"subtitles=filename='{_ffmpeg_filter_filename(source_subtitle)}'"
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(source_video),
        "-vf",
        filter_value,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(burned_video),
    ]
    if input_was_mp4:
        _log(log_callback, "输入已是 MP4，直接烧录字幕到新的 MP4 文件…")
    else:
        _log(log_callback, f"输入为 {source_video.suffix or '未知格式'}，正在转换为 MP4 并烧录字幕…")
    _log(log_callback, "烧录字幕必须重新编码视频；时长取决于视频长度和电脑性能。")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout:
        for line in process.stdout:
            line = line.strip()
            if line:
                _log(log_callback, line)
    if process.wait() != 0:
        raise RuntimeError("FFmpeg 烧录字幕失败。请查看运行日志中的 FFmpeg 错误信息。")
    _log(log_callback, f"完成：字幕已烧录到 MP4：{burned_video}")
    return BurnedSubtitleVideoOutput(
        source_video=source_video,
        source_subtitle=source_subtitle,
        burned_video=burned_video,
        input_was_mp4=input_was_mp4,
    )
