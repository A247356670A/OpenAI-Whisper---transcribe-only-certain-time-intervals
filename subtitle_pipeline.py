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
import struct
import subprocess
import sys
import os
from typing import Any, Callable, Mapping
from SrtMerge import (
    merge_srt,
    parse_srt,
    seconds_to_srt_time,
    srt_time_to_seconds,
    write_srt,
)
from SrtToIntervals import extract_time_intervals
from exclude_segments_by_intervals import exclude_segments_by_intervals
from transcribe import save_srt, transcribe, transcribe_segments
from whisper_options import build_whisper_options


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[str, float, float], None]


# Conservative B-pass audio gate.  The defaults intentionally reject only
# near-digital silence, so quiet dialogue is not lost before Whisper sees it.
B_AUDIO_MIN_RMS = 0.0001
B_AUDIO_MIN_ACTIVE_SECONDS = 0.05
B_AUDIO_SILENCE_TOP_DB = 45
B_VAD_MIN_SPEECH_SECONDS = 0.09

# Browser names accepted by yt-dlp's --cookies-from-browser option.  The GUI
# passes one of these identifiers only; it never exports or stores cookies.
SUPPORTED_COOKIE_BROWSERS = frozenset(
    {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi"}
)




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


@dataclass(frozen=True)
class SubtitlePreviewOutput:
    """A rendered image used to verify subtitle font and colour before burning."""

    preview_image: Path
    preview_time: float
    preview_index: int
    subtitle_count: int


@dataclass(frozen=True)
class DownloadedVideoOutput:
    """The destination directory used for a completed yt-dlp MP4 download."""

    source_url: str
    output_dir: Path


SubtitleEntry = tuple[float, float, str]


SUBTITLE_FONT_CHOICES = (
    "微软雅黑",
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "Noto Sans CJK SC",
    "SimHei",
    "Meiryo",
    "Yu Gothic UI",
)

# Windows exposes the font as Microsoft YaHei to FFmpeg/libass, while the
# Chinese name is easier to recognise in the GUI.
SUBTITLE_FONT_ALIASES = {"微软雅黑": "Microsoft YaHei"}

SUBTITLE_COLOR_CHOICES = {
    "白色": "&H00FFFFFF",
    "黄色": "&H0000FFFF",
    "青色": "&H00FFFF00",
    "绿色": "&H0000FF00",
    "粉红色": "&H00CC66FF",
}


@dataclass(frozen=True)
class SubtitleConflictGroup:
    """All mutually overlapping A/B entries that require one user choice."""

    a_entries: tuple[SubtitleEntry, ...]
    b_entries: tuple[SubtitleEntry, ...]


@dataclass(frozen=True)
class PreparedSubtitleMerge:
    """The automatic and user-review portions of an A+B subtitle merge."""

    subtitle_a: Path
    subtitle_b: Path
    output_path: Path
    non_conflicting_entries: tuple[SubtitleEntry, ...]
    conflicts: tuple[SubtitleConflictGroup, ...]


@dataclass(frozen=True)
class ManualSubtitleMergeOutput:
    """The final SRT generated after the user has resolved all conflicts."""

    output_path: Path
    conflict_count: int


@dataclass(frozen=True)
class SuspiciousSubtitle:
    """A subtitle marked for human review, with its nearby context."""

    entry_index: int
    entry: SubtitleEntry
    reasons: tuple[str, ...]
    previous_entry: SubtitleEntry | None
    next_entry: SubtitleEntry | None


@dataclass(frozen=True)
class PreparedHallucinationCleanup:
    """Source subtitles and the possible hallucinations that need review."""

    source_subtitle: Path
    output_path: Path
    entries: tuple[SubtitleEntry, ...]
    candidates: tuple[SuspiciousSubtitle, ...]


@dataclass(frozen=True)
class HallucinationCleanupOutput:
    """A subtitle file created after the user confirms candidate deletions."""

    output_path: Path
    removed_count: int


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


def build_subtitle_preview_path(video_path: str | Path, output_dir: str | Path) -> Path:
    """Return the disposable PNG path used by the subtitle-style preview."""
    source = Path(video_path)
    return Path(output_dir) / f"{source.stem}_subtitle_style_preview.png"


def build_manual_merge_path(
    subtitle_a_path: str | Path, subtitle_b_path: str | Path, output_dir: str | Path
) -> Path:
    """Return a descriptive, non-destructive output name for a manual A+B merge."""
    subtitle_a = Path(subtitle_a_path)
    subtitle_b = Path(subtitle_b_path)
    return Path(output_dir) / f"{subtitle_a.stem}_{subtitle_b.stem}_merged.srt"


def build_hallucination_cleanup_path(
    subtitle_path: str | Path, output_dir: str | Path
) -> Path:
    """Return the non-destructive output name used by the hallucination review."""
    source = Path(subtitle_path)
    return Path(output_dir) / f"{source.stem}_cleaned.srt"


def _log(callback: LogCallback | None, message: str) -> None:
    if callback:
        callback(message)
    else:
        print(message)


def _progress(
    callback: ProgressCallback | None, stage: str, current: float, total: float
) -> None:
    """Send lightweight progress updates without coupling the pipeline to Tk."""
    if callback:
        callback(stage, current, total)


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


def _reserve_cpu_for_gui(torch: Any) -> None:
    """Avoid letting CPU-only Whisper consume every core needed by Tk."""
    cpu_count = os.cpu_count() or 1
    if cpu_count < 2:
        return
    try:
        torch.set_num_threads(max(1, cpu_count - 1))
    except (AttributeError, RuntimeError):
        # Some Torch builds do not allow changing this after initialization.
        pass


def _probe_media_duration(path: Path) -> float | None:
    """Read media duration via ffprobe when available for an A-pass progress bar."""
    ffprobe = _find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        duration = float(result.stdout.strip())
        return duration if duration > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _probe_video_frame_count(path: Path) -> float | None:
    """Estimate total frames from ffprobe for burn-in progress reporting."""
    ffprobe = _find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_frames,avg_frame_rate,duration",
                "-of",
                "default=noprint_wrappers=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    values = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    try:
        frame_count = float(values.get("nb_frames", "0"))
        if frame_count > 0:
            return frame_count
        numerator, denominator = values["avg_frame_rate"].split("/", 1)
        frame_rate = float(numerator) / float(denominator)
        duration = float(values["duration"])
        return frame_rate * duration if frame_rate > 0 and duration > 0 else None
    except (KeyError, ValueError, ZeroDivisionError):
        return None


def _find_ffprobe() -> str | None:
    """Locate ffprobe beside FFmpeg too, for installations not added fully to PATH."""
    if ffprobe := shutil.which("ffprobe"):
        return ffprobe
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    ffmpeg_path = Path(ffmpeg)
    suffix = ffmpeg_path.suffix
    candidate = ffmpeg_path.with_name(f"ffprobe{suffix}")
    return str(candidate) if candidate.is_file() else None


def filter_silent_b_segments(
    audio_segments: list[list[Any]],
    sample_rate: int,
    librosa: Any,
    *,
    min_rms: float = B_AUDIO_MIN_RMS,
    min_active_seconds: float = B_AUDIO_MIN_ACTIVE_SECONDS,
    silence_top_db: int = B_AUDIO_SILENCE_TOP_DB,
    speech_only: bool = False,
    vad_aggressiveness: int = 2,
) -> tuple[list[list[Any]], list[tuple[float, float]]]:
    """Keep B candidate slices that contain meaningful non-silent audio.

    ``librosa.effects.split`` identifies active portions relative to the
    segment's volume; RMS adds an absolute floor so digital silence is not
    mistaken for audio.  If ``speech_only`` is requested, WebRTC VAD is used
    after the volume test to prefer detected dialogue over music or ambience.
    """
    kept_segments: list[list[Any]] = []
    skipped_intervals: list[tuple[float, float]] = []
    if min_rms < 0 or min_active_seconds < 0 or not 1 <= silence_top_db <= 100:
        raise ValueError("B 音频预筛阈值无效。")
    if not 0 <= vad_aggressiveness <= 3:
        raise ValueError("语音检测强度必须在 0 到 3 之间。")
    for start, end, samples in audio_segments:
        if len(samples) == 0:
            skipped_intervals.append((float(start), float(end)))
            continue
        try:
            # NumPy audio arrays use this vectorized fast path.
            rms = float(((samples * samples).mean()) ** 0.5)
        except (AttributeError, TypeError):
            # Keep the helper import-safe for lightweight test and GUI setups.
            rms = (sum(float(sample) ** 2 for sample in samples) / len(samples)) ** 0.5
        active_ranges = librosa.effects.split(
            samples, top_db=silence_top_db
        )
        active_seconds = sum(
            (int(range_end) - int(range_start)) / sample_rate
            for range_start, range_end in active_ranges
        )
        if rms < min_rms or active_seconds < min_active_seconds:
            skipped_intervals.append((float(start), float(end)))
        elif speech_only and _measure_speech_seconds(
            samples, sample_rate, vad_aggressiveness
        ) < B_VAD_MIN_SPEECH_SECONDS:
            skipped_intervals.append((float(start), float(end)))
        else:
            kept_segments.append([start, end, samples])
    return kept_segments, skipped_intervals


def _measure_speech_seconds(
    samples: Any, sample_rate: int, aggressiveness: int
) -> float:
    """Estimate voiced time with WebRTC VAD without loading another ML model."""
    if sample_rate not in (8_000, 16_000, 32_000, 48_000):
        raise ValueError("语音检测仅支持 8/16/32/48 kHz 单声道音频。")
    try:
        import webrtcvad
    except ImportError as exc:
        raise RuntimeError(
            "语音优先检测需要 webrtcvad-wheels。请在项目目录重新执行：\n"
            "python -m pip install -r requirements.txt"
        ) from exc

    frame_samples = sample_rate * 30 // 1000
    vad = webrtcvad.Vad(aggressiveness)
    speech_seconds = 0.0
    for offset in range(0, len(samples) - frame_samples + 1, frame_samples):
        frame = samples[offset : offset + frame_samples]
        pcm = struct.pack(
            f"<{frame_samples}h",
            *(int(max(-1.0, min(1.0, float(value))) * 32767) for value in frame),
        )
        if vad.is_speech(pcm, sample_rate):
            speech_seconds += 0.03
    return speech_seconds


def run_two_pass_transcription(
    video_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    model_name: str = "large-v2",
    merge_gap: float = 1.0,
    duplicate_threshold: float = 0.5,
    filter_silent_b: bool = True,
    b_audio_min_rms: float = B_AUDIO_MIN_RMS,
    b_audio_min_active_seconds: float = B_AUDIO_MIN_ACTIVE_SECONDS,
    b_audio_silence_top_db: int = B_AUDIO_SILENCE_TOP_DB,
    b_speech_only: bool = False,
    b_vad_aggressiveness: int = 2,
    first_whisper_values: Mapping[str, Any] | None = None,
    second_whisper_values: Mapping[str, Any] | None = None,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
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

    a_duration = _probe_media_duration(source) if progress_callback else None
    _progress(progress_callback, "subtitle_a", 0, a_duration or 0)

    librosa, torch, whisper = _import_dependencies()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        _reserve_cpu_for_gui(torch)
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
    _progress(progress_callback, "subtitle_a", a_duration or 1, a_duration or 1)

    _log(log_callback, "正在读取音频并计算 A 未覆盖的片段…")
    audio_array, sample_rate = librosa.load(str(source), sr=16_000, mono=True)
    full_interval = [[0, len(audio_array) / sample_rate]]
    excluded_intervals = extract_time_intervals(
        str(outputs.first_pass), merge_gap=merge_gap
    )
    audio_segments, remaining_intervals = exclude_segments_by_intervals(
        audio_array, full_interval, excluded_intervals, sample_rate
    )

    if filter_silent_b and audio_segments:
        audio_segments, skipped_intervals = filter_silent_b_segments(
            audio_segments,
            sample_rate,
            librosa,
            min_rms=b_audio_min_rms,
            min_active_seconds=b_audio_min_active_seconds,
            silence_top_db=b_audio_silence_top_db,
            speech_only=b_speech_only,
            vad_aggressiveness=b_vad_aggressiveness,
        )
        if skipped_intervals:
            _log(
                log_callback,
                f"B 音频预筛：跳过 {len(skipped_intervals)} 个未覆盖片段"
                f"（RMS ≥ {b_audio_min_rms:g}，有效声音 ≥ {b_audio_min_active_seconds:g} 秒"
                + ("，语音优先已开启）。" if b_speech_only else "）。"),
            )

    if audio_segments:
        _progress(progress_callback, "subtitle_b", 0, len(audio_segments))
        _log(
            log_callback,
            f"第 2 步/3：识别 {len(audio_segments)} 个未覆盖片段，生成字幕 B…",
        )
        transcribe_segments(
            audio_segments,
            second_options,
            model,
            str(outputs.second_pass),
            progress_callback=lambda current, total: _progress(
                progress_callback, "subtitle_b", current, total
            ),
        )
    else:
        _progress(progress_callback, "subtitle_b", 1, 1)
        _log(log_callback, "第 2 步/3：没有可识别的 B 音频片段，创建空的字幕 B。")
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
    progress_callback: ProgressCallback | None = None,
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

    a_duration = _probe_media_duration(source) if progress_callback else None
    _progress(progress_callback, "subtitle_a", 0, a_duration or 0)

    _librosa, torch, whisper = _import_dependencies()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        _reserve_cpu_for_gui(torch)
    _log(log_callback, f"使用设备：{device.upper()}；正在加载 Whisper 模型 {model_name}…")
    model = whisper.load_model(model_name, device=device)
    first_options = build_whisper_options(
        "first", first_whisper_values, device=device
    )

    _log(log_callback, "仅生成 A：正在识别完整视频…")
    transcribe(str(source), first_options, model, str(first_pass))
    _progress(progress_callback, "subtitle_a", a_duration or 1, a_duration or 1)
    _log(log_callback, f"完成：仅生成字幕 A：{first_pass}")
    return FirstPassOutput(first_pass=first_pass)


def run_second_pass_from_subtitle(
    video_path: str | Path,
    translated_a_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    model_name: str = "large-v2",
    merge_gap: float = 1.0,
    filter_silent_b: bool = True,
    b_audio_min_rms: float = B_AUDIO_MIN_RMS,
    b_audio_min_active_seconds: float = B_AUDIO_MIN_ACTIVE_SECONDS,
    b_audio_silence_top_db: int = B_AUDIO_SILENCE_TOP_DB,
    b_speech_only: bool = False,
    b_vad_aggressiveness: int = 2,
    second_whisper_values: Mapping[str, Any] | None = None,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
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
    if device == "cpu":
        _reserve_cpu_for_gui(torch)
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

    if filter_silent_b and audio_segments:
        audio_segments, skipped_intervals = filter_silent_b_segments(
            audio_segments,
            sample_rate,
            librosa,
            min_rms=b_audio_min_rms,
            min_active_seconds=b_audio_min_active_seconds,
            silence_top_db=b_audio_silence_top_db,
            speech_only=b_speech_only,
            vad_aggressiveness=b_vad_aggressiveness,
        )
        if skipped_intervals:
            _log(
                log_callback,
                f"B 音频预筛：跳过 {len(skipped_intervals)} 个未覆盖片段"
                f"（RMS ≥ {b_audio_min_rms:g}，有效声音 ≥ {b_audio_min_active_seconds:g} 秒"
                + ("，语音优先已开启）。" if b_speech_only else "）。"),
            )

    if audio_segments:
        _progress(progress_callback, "subtitle_b", 0, len(audio_segments))
        _log(
            log_callback,
            f"仅生成 B：正在识别 {len(audio_segments)} 个未覆盖片段…",
        )
        transcribe_segments(
            audio_segments,
            second_options,
            model,
            str(second_pass),
            progress_callback=lambda current, total: _progress(
                progress_callback, "subtitle_b", current, total
            ),
        )
    else:
        _progress(progress_callback, "subtitle_b", 1, 1)
        _log(log_callback, "没有可识别的 B 音频片段，创建空的字幕 B。")
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


def _entries_overlap(first: SubtitleEntry, second: SubtitleEntry) -> bool:
    """Return whether two subtitle intervals overlap by a positive duration."""
    return max(first[0], second[0]) < min(first[1], second[1])


def _read_srt_entries(path: Path) -> list[SubtitleEntry]:
    """Use the project's SrtMerge parser and normalize its mutable lists to tuples."""
    return [(start, end, text) for start, end, text in parse_srt(str(path))]


def format_srt_entries(entries: list[SubtitleEntry] | tuple[SubtitleEntry, ...]) -> str:
    """Format entries as editable SRT text for the conflict-review dialog."""
    blocks = []
    for index, (start, end, text) in enumerate(entries, start=1):
        blocks.append(
            f"{index}\n{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}\n{text}"
        )
    return "\n\n".join(blocks)


def parse_editable_srt_text(text: str) -> list[SubtitleEntry]:
    """Parse a user-edited SRT field and fail clearly if a time range is invalid."""
    pattern = re.compile(
        r"(?:^|\n\s*\n)(?:\s*\d+\s*\n)?"
        r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*"
        r"(\d{2}:\d{2}:\d{2},\d{3})\s*\n(.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )
    entries: list[SubtitleEntry] = []
    for match in pattern.finditer(text.strip()):
        start = srt_time_to_seconds(match.group(1))
        end = srt_time_to_seconds(match.group(2))
        if end <= start:
            raise ValueError("每条字幕的结束时间必须晚于开始时间。")
        entries.append((start, end, match.group(3).strip().replace("\n", " ")))
    if text.strip() and not entries:
        raise ValueError("编辑内容不是有效的 SRT 格式。请保留时间轴行。")
    return entries


def prepare_manual_subtitle_merge(
    subtitle_a_path: str | Path,
    subtitle_b_path: str | Path,
    output_dir: str | Path,
) -> PreparedSubtitleMerge:
    """Split A+B SRT entries into automatic entries and overlap-review groups."""
    subtitle_a = Path(subtitle_a_path).expanduser().resolve()
    subtitle_b = Path(subtitle_b_path).expanduser().resolve()
    if not subtitle_a.is_file() or subtitle_a.suffix.lower() != ".srt":
        raise ValueError("请选择有效的字幕 A（.srt）。")
    if not subtitle_b.is_file() or subtitle_b.suffix.lower() != ".srt":
        raise ValueError("请选择有效的字幕 B（.srt）。")

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    a_entries = _read_srt_entries(subtitle_a)
    b_entries = _read_srt_entries(subtitle_b)

    # Build a bipartite graph: connected overlap groups become one review card.
    a_links: dict[int, set[int]] = {index: set() for index in range(len(a_entries))}
    b_links: dict[int, set[int]] = {index: set() for index in range(len(b_entries))}
    for a_index, a_entry in enumerate(a_entries):
        for b_index, b_entry in enumerate(b_entries):
            if _entries_overlap(a_entry, b_entry):
                a_links[a_index].add(b_index)
                b_links[b_index].add(a_index)

    conflicts: list[SubtitleConflictGroup] = []
    visited_a: set[int] = set()
    visited_b: set[int] = set()
    for first_a in range(len(a_entries)):
        if first_a in visited_a or not a_links[first_a]:
            continue
        component_a: set[int] = set()
        component_b: set[int] = set()
        pending: list[tuple[str, int]] = [("a", first_a)]
        while pending:
            side, index = pending.pop()
            if side == "a":
                if index in visited_a:
                    continue
                visited_a.add(index)
                component_a.add(index)
                pending.extend(("b", linked) for linked in a_links[index])
            else:
                if index in visited_b:
                    continue
                visited_b.add(index)
                component_b.add(index)
                pending.extend(("a", linked) for linked in b_links[index])
        conflicts.append(
            SubtitleConflictGroup(
                a_entries=tuple(a_entries[index] for index in sorted(component_a)),
                b_entries=tuple(b_entries[index] for index in sorted(component_b)),
            )
        )

    non_conflicting = [
        entry for index, entry in enumerate(a_entries) if not a_links[index]
    ] + [entry for index, entry in enumerate(b_entries) if not b_links[index]]
    return PreparedSubtitleMerge(
        subtitle_a=subtitle_a,
        subtitle_b=subtitle_b,
        output_path=build_manual_merge_path(subtitle_a, subtitle_b, destination),
        non_conflicting_entries=tuple(non_conflicting),
        conflicts=tuple(conflicts),
    )


def complete_manual_subtitle_merge(
    prepared: PreparedSubtitleMerge,
    selected_entries: list[list[SubtitleEntry]],
) -> ManualSubtitleMergeOutput:
    """Write non-conflicting entries plus the user-selected conflict entries."""
    if len(selected_entries) != len(prepared.conflicts):
        raise ValueError("冲突处理结果数量与待处理冲突不一致。")
    merged_entries = list(prepared.non_conflicting_entries)
    for entries in selected_entries:
        merged_entries.extend(entries)
    merged_entries.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
    write_srt(merged_entries, str(prepared.output_path))
    return ManualSubtitleMergeOutput(
        output_path=prepared.output_path,
        conflict_count=len(prepared.conflicts),
    )


# These are review signals, not automatic deletion rules.  Their intent is to
# surface boilerplate that Whisper sometimes invents around music or endings.
HALLUCINATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "BGM／音乐标记",
        re.compile(
            r"^[\s♪♫]*[（(]?\s*[♪♫]?\s*(?:bgm|music|音楽)\s*[）)]?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "片尾／结束标记",
        re.compile(r"^[\s♪♫]*[（(]?\s*(?:エンディング|ending|end)\s*[）)]?\s*$", re.IGNORECASE),
    ),
    (
        "感谢观看／片尾致谢",
        re.compile(
            r"(?:ご視聴(?:いただき)?ありがとうございました|"
            r"ご覧(?:いただき)?ありがとうございました|"
            r"感谢观看|感謝觀看|thanks\s+for\s+watching)",
            re.IGNORECASE,
        ),
    ),
    (
        "订阅引导／片尾提示",
        re.compile(r"(?:チャンネル登録|subscribe\s*(?:to|for)?)", re.IGNORECASE),
    ),
)


def _hallucination_reasons(text: str) -> tuple[str, ...]:
    """Return the human-readable review reasons matched by one subtitle."""
    return tuple(label for label, pattern in HALLUCINATION_PATTERNS if pattern.search(text))


def prepare_hallucination_cleanup(
    subtitle_path: str | Path, output_dir: str | Path
) -> PreparedHallucinationCleanup:
    """Find possible boilerplate hallucinations while keeping the source untouched."""
    source = Path(subtitle_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".srt":
        raise ValueError("请选择有效的 .srt 字幕文件。")
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    entries = _read_srt_entries(source)
    candidates: list[SuspiciousSubtitle] = []
    for entry_index, entry in enumerate(entries):
        reasons = _hallucination_reasons(entry[2])
        if reasons:
            candidates.append(
                SuspiciousSubtitle(
                    entry_index=entry_index,
                    entry=entry,
                    reasons=reasons,
                    previous_entry=entries[entry_index - 1] if entry_index else None,
                    next_entry=(
                        entries[entry_index + 1]
                        if entry_index + 1 < len(entries)
                        else None
                    ),
                )
            )
    return PreparedHallucinationCleanup(
        source_subtitle=source,
        output_path=build_hallucination_cleanup_path(source, destination),
        entries=tuple(entries),
        candidates=tuple(candidates),
    )


def complete_hallucination_cleanup(
    prepared: PreparedHallucinationCleanup, delete_indices: set[int]
) -> HallucinationCleanupOutput:
    """Write a new SRT after deleting only candidate entries confirmed by the user."""
    candidate_indices = {candidate.entry_index for candidate in prepared.candidates}
    invalid_indices = delete_indices - candidate_indices
    if invalid_indices:
        raise ValueError("只能删除审核窗口中列出的可疑字幕。")
    kept_entries = [
        entry for index, entry in enumerate(prepared.entries) if index not in delete_indices
    ]
    write_srt(kept_entries, str(prepared.output_path))
    return HallucinationCleanupOutput(
        output_path=prepared.output_path,
        removed_count=len(delete_indices),
    )


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


def _build_subtitle_filter(
    subtitle_path: Path,
    *,
    font_name: str,
    font_size: int,
    font_color: str,
    outline_size: float,
    margin_v: int,
) -> str:
    """Build a libass filter with an explicit, readable CJK subtitle style."""
    font_name = SUBTITLE_FONT_ALIASES.get(font_name.strip(), font_name.strip())
    if not font_name or any(character in font_name for character in "',:"):
        raise ValueError("字体名称不能为空，且不能包含英文逗号、冒号或引号。")
    if not 12 <= font_size <= 160:
        raise ValueError("字幕字号必须在 12 到 160 之间。")
    if not 0 <= outline_size <= 12:
        raise ValueError("字幕描边宽度必须在 0 到 12 之间。")
    if not 0 <= margin_v <= 1000:
        raise ValueError("字幕距底部位置必须在 0 到 1000 之间。")
    try:
        primary_colour = SUBTITLE_COLOR_CHOICES[font_color]
    except KeyError as exc:
        raise ValueError("请选择列表中的字幕颜色。") from exc
    # ASS uses &HAABBGGRR.  A black outline keeps every selectable text colour
    # readable on bright footage; Alignment=2 anchors captions at the bottom.
    force_style = (
        f"FontName={font_name},FontSize={font_size},"
        f"PrimaryColour={primary_colour},OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline={outline_size:g},Shadow=0,Alignment=2,MarginV={margin_v}"
    )
    return (
        f"subtitles=filename='{_ffmpeg_filter_filename(subtitle_path)}':"
        f"force_style='{force_style}'"
    )


def generate_subtitle_preview(
    video_path: str | Path,
    subtitle_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    font_name: str = "微软雅黑",
    font_size: int = 16,
    font_color: str = "白色",
    outline_size: float = 0.8,
    margin_v: int = 10,
    preview_index: int = 0,
    log_callback: LogCallback | None = None,
) -> SubtitlePreviewOutput:
    """Render a single styled subtitle frame without changing the source video."""
    source_video = Path(video_path).expanduser().resolve()
    source_subtitle = Path(subtitle_path).expanduser().resolve()
    if not source_video.is_file():
        raise FileNotFoundError(f"找不到视频文件：{source_video}")
    if not source_subtitle.is_file() or source_subtitle.suffix.lower() != ".srt":
        raise ValueError("请选择有效的 .srt 字幕文件。")
    destination = (
        Path(output_dir).expanduser().resolve() if output_dir else source_video.parent
    )
    destination.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 FFmpeg。请先安装 FFmpeg 并将其加入系统 PATH，然后重新运行。")
    entries = _read_srt_entries(source_subtitle)
    if not entries:
        raise ValueError("字幕文件没有可用于预览的字幕内容。")
    if not 0 <= preview_index < len(entries):
        raise ValueError("预览字幕序号超出字幕文件范围。")
    preview_time = entries[preview_index][0] + 0.05
    preview_image = build_subtitle_preview_path(source_video, destination)
    subtitle_filter = _build_subtitle_filter(
        source_subtitle,
        font_name=font_name,
        font_size=font_size,
        font_color=font_color,
        outline_size=outline_size,
        margin_v=margin_v,
    )
    # Fast seek to the first caption, then restore its source PTS so libass
    # evaluates the SRT at the correct point on the original timeline.
    filter_value = f"setpts=PTS+{preview_time:.3f}/TB,{subtitle_filter},scale='min(960,iw)':-2"
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-ss",
        f"{preview_time:.3f}",
        "-i",
        str(source_video),
        "-vf",
        filter_value,
        "-frames:v",
        "1",
        str(preview_image),
    ]
    _log(log_callback, "正在生成字幕样式预览…")
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
    if process.wait() != 0 or not preview_image.is_file():
        raise RuntimeError("字幕样式预览生成失败。请查看运行日志中的 FFmpeg 错误信息。")
    _log(log_callback, f"字幕样式预览已生成：{preview_image}")
    return SubtitlePreviewOutput(
        preview_image=preview_image,
        preview_time=preview_time,
        preview_index=preview_index,
        subtitle_count=len(entries),
    )
def _find_yt_dlp_js_runtime() -> tuple[str, str] | None:
    """Return the preferred installed JavaScript runtime for yt-dlp EJS.

    Deno is yt-dlp's recommended runtime.  Node and QuickJS are useful
    fallbacks on computers where they are already available.  The actual
    executable remains on PATH, which keeps the command portable between
    Windows and macOS.
    """
    for executable, runtime, label in (
        ("deno", "deno", "Deno"),
        ("node", "node", "Node.js"),
        ("qjs", "quickjs", "QuickJS"),
    ):
        if shutil.which(executable):
            return runtime, label
    return None


def _download_failure_message(output_lines: list[str]) -> str:
    """Turn common yt-dlp/YouTube failures into a useful GUI error."""
    output = "\n".join(output_lines).lower()
    if (
        "sign in to confirm you’re not a bot" in output
        or "sign in to confirm you're not a bot" in output
    ):
        return (
            "YouTube 要求进行真人验证，未能下载。请在本机浏览器登录 YouTube，"
            "如页面出现验证码请先完成验证；然后在“登录 Cookie”选择该浏览器后重试。"
        )
    if "http error 429" in output or "too many requests" in output:
        return (
            "YouTube 暂时限制了当前网络的请求（HTTP 429）。请在同一浏览器完成验证码，"
            "在下载界面选择已登录的浏览器 Cookie 后重试；仍失败时请稍后再试。"
        )
    if "no supported javascript runtime" in output:
        return (
            "yt-dlp 缺少 YouTube 所需的 JavaScript 运行时。请安装 Deno 2.3+"
            "（推荐）或 Node.js 22+，重启程序后重试。"
        )
    return "yt-dlp 下载失败。请查看运行日志中的错误信息。"


def download_video_as_mp4(
    link: str,
    output_dir: str | Path,
    *,
    cookie_browser: str | None = None,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
) -> DownloadedVideoOutput:
    """Download *link* as MP4 with optional local browser authentication."""
    source_url = link.strip()
    if not source_url:
        raise ValueError("请输入视频链接。")
    destination = Path(output_dir).expanduser().resolve()
    if not destination.is_dir():
        raise FileNotFoundError(f"找不到保存文件夹：{destination}")
    try:
        import yt_dlp  # noqa: F401 - verifies the module used by the command exists.
    except ImportError as exc:
        raise RuntimeError(
            "缺少 yt-dlp。请在项目目录执行：\npython -m pip install -r requirements.txt"
        ) from exc

    browser = cookie_browser.strip().lower() if cookie_browser else None
    if browser and browser not in SUPPORTED_COOKIE_BROWSERS:
        raise ValueError(
            "不支持的浏览器 Cookie 来源。请选择 Chrome、Edge、Firefox 等浏览器。"
        )

    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-c",
        "-R",
        "10",
        "--retry-sleep",
        "5",
        "--http-chunk-size",
        "1M",
        "-f",
        "bv*[vcodec^=avc1][ext=mp4]+ba[acodec^=mp4a]/b[ext=mp4]",
        "--merge-output-format",
        "mp4",
    ]
    if browser:
        command.extend(["--cookies-from-browser", browser])

    js_runtime = _find_yt_dlp_js_runtime()
    if js_runtime:
        command.extend(["--js-runtimes", js_runtime[0]])
    command.append(source_url)
    _log(
        log_callback,
        '正在保存到目标文件夹：python -m yt_dlp -c -R 10 --retry-sleep 5 '
        '--http-chunk-size 1M -f "bv*[vcodec^=avc1][ext=mp4]+'
        'ba[acodec^=mp4a]/b[ext=mp4]" --merge-output-format mp4 "(Link)"',
    )
    if browser:
        _log(
            log_callback,
            f"已启用 {browser.title()} 的本机登录 Cookie（不会导出或保存 Cookie）。",
        )
    else:
        _log(
            log_callback,
            "未使用浏览器 Cookie；若 YouTube 要求验证，请选择已登录 YouTube 的浏览器后重试。",
        )
    if js_runtime:
        _log(log_callback, f"已启用 yt-dlp JavaScript 运行时：{js_runtime[1]}。")
    else:
        _log(
            log_callback,
            "未检测到 Deno、Node.js 或 QuickJS；YouTube 可能缺少部分格式或无法下载。",
        )
    _progress(progress_callback, "download", 0, 100)
    process = subprocess.Popen(
        command,
        cwd=str(destination),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output_lines: list[str] = []
    if process.stdout:
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
                _log(log_callback, line)
    if process.wait() != 0:
        raise RuntimeError(_download_failure_message(output_lines))
    _progress(progress_callback, "download", 100, 100)
    _log(log_callback, f"完成：视频已保存到 {destination}")
    return DownloadedVideoOutput(source_url=source_url, output_dir=destination)


def burn_subtitles_to_mp4(
    video_path: str | Path,
    subtitle_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    font_name: str = "微软雅黑",
    font_size: int = 16,
    font_color: str = "白色",
    outline_size: float = 0.8,
    margin_v: int = 10,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
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

    filter_value = _build_subtitle_filter(
        source_subtitle,
        font_name=font_name,
        font_size=font_size,
        font_color=font_color,
        outline_size=outline_size,
        margin_v=margin_v,
    )
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
    total_frames = _probe_video_frame_count(source_video) if progress_callback else None
    _progress(progress_callback, "burn", 0, total_frames or 0)
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
    _progress(progress_callback, "burn", total_frames or 1, total_frames or 1)
    _log(log_callback, f"完成：字幕已烧录到 MP4：{burned_video}")
    return BurnedSubtitleVideoOutput(
        source_video=source_video,
        source_subtitle=source_subtitle,
        burned_video=burned_video,
        input_was_mp4=input_was_mp4,
    )
