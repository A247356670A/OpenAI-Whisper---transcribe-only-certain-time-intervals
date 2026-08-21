"""Opt-in, checkpointed A+B transcription without changing the legacy workflow.

The first pass is divided into overlapping windows so cancellation is observed
between complete Whisper calls.  Only completed windows/segments are committed
to the checkpoint.  The ordinary pipeline remains a single uninterrupted
Whisper call and does not import or depend on this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping

from SrtMerge import merge_srt, write_srt
from SrtToIntervals import extract_time_intervals
from exclude_segments_by_intervals import exclude_segments_by_intervals
from subtitle_pipeline import (
    B_AUDIO_MIN_ACTIVE_SECONDS,
    B_AUDIO_MIN_RMS,
    B_AUDIO_SILENCE_TOP_DB,
    LogCallback,
    ProgressCallback,
    _configure_whisper_device,
    _import_dependencies,
    _log,
    _progress,
    _reserve_cpu_for_gui,
    filter_silent_b_segments,
)
from transcribe import save_srt
from whisper_options import build_whisper_options


CancelCheck = Callable[[], bool]
CHECKPOINT_VERSION = 1
DEFAULT_A_CHUNK_SECONDS = 120.0
DEFAULT_A_OVERLAP_SECONDS = 30.0


@dataclass(frozen=True)
class ResumableSubtitleOutputs:
    """Paths and completion state returned by the opt-in resumable workflow."""

    first_pass: Path
    second_pass: Path
    merged: Path
    checkpoint: Path
    partial_first: Path
    partial_second: Path
    completed: bool


def build_resumable_output_paths(
    video_path: str | Path, output_dir: str | Path
) -> ResumableSubtitleOutputs:
    """Use dedicated names so checkpoint runs never overwrite legacy outputs."""
    source = Path(video_path)
    destination = Path(output_dir)
    stem = source.stem
    return ResumableSubtitleOutputs(
        first_pass=destination / f"{stem}_resumable_A.srt",
        second_pass=destination / f"{stem}_resumable_B.srt",
        merged=destination / f"{stem}_resumable_merged.srt",
        checkpoint=destination / f"{stem}_resumable_checkpoint.json",
        partial_first=destination / f"{stem}_resumable_A_partial.srt",
        partial_second=destination / f"{stem}_resumable_B_partial.srt",
        completed=False,
    )


def _source_identity(source: Path) -> dict[str, Any]:
    stat = source.stat()
    return {
        "path": str(source),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _settings_identity(
    *,
    model_name: str,
    merge_gap: float,
    duplicate_threshold: float,
    filter_silent_b: bool,
    b_audio_min_rms: float,
    b_audio_min_active_seconds: float,
    b_audio_silence_top_db: int,
    b_speech_only: bool,
    b_vad_aggressiveness: int,
    cpu_thread_profile: str,
    gpu_acceleration: bool,
    first_whisper_values: Mapping[str, Any] | None,
    second_whisper_values: Mapping[str, Any] | None,
    a_chunk_seconds: float,
    a_overlap_seconds: float,
) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "merge_gap": merge_gap,
        "duplicate_threshold": duplicate_threshold,
        "filter_silent_b": filter_silent_b,
        "b_audio_min_rms": b_audio_min_rms,
        "b_audio_min_active_seconds": b_audio_min_active_seconds,
        "b_audio_silence_top_db": b_audio_silence_top_db,
        "b_speech_only": b_speech_only,
        "b_vad_aggressiveness": b_vad_aggressiveness,
        "cpu_thread_profile": cpu_thread_profile,
        "gpu_acceleration": gpu_acceleration,
        "first_whisper_values": dict(first_whisper_values or {}),
        "second_whisper_values": dict(second_whisper_values or {}),
        "a_chunk_seconds": a_chunk_seconds,
        "a_overlap_seconds": a_overlap_seconds,
    }


def _fresh_checkpoint(source: Path, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": CHECKPOINT_VERSION,
        "source": _source_identity(source),
        "settings": settings,
        "stage": "a",
        "a_completed_chunks": 0,
        "a_subtitles": [],
        "b_completed_segments": 0,
        "b_subtitles": [],
    }


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_srt_atomic(subtitles: list[dict[str, Any]], path: Path) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    save_srt([dict(subtitle) for subtitle in subtitles], str(temporary))
    os.replace(temporary, path)


def _load_matching_checkpoint(
    path: Path, source: Path, settings: dict[str, Any]
) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("断点文件无法读取。请选择重新开始以创建新的断点。") from exc
    if state.get("version") != CHECKPOINT_VERSION:
        raise ValueError("断点文件版本不兼容。请选择重新开始。")
    if state.get("source") != _source_identity(source):
        raise ValueError("断点对应的视频已变化，不能继续。请选择重新开始。")
    if state.get("settings") != settings:
        raise ValueError(
            "当前模型或 Whisper 参数与断点不一致。请恢复原参数，或选择重新开始。"
        )
    return state


def _cancelled_outputs(paths: ResumableSubtitleOutputs) -> ResumableSubtitleOutputs:
    return ResumableSubtitleOutputs(
        first_pass=paths.first_pass,
        second_pass=paths.second_pass,
        merged=paths.merged,
        checkpoint=paths.checkpoint,
        partial_first=paths.partial_first,
        partial_second=paths.partial_second,
        completed=False,
    )


def _completed_outputs(paths: ResumableSubtitleOutputs) -> ResumableSubtitleOutputs:
    return ResumableSubtitleOutputs(
        first_pass=paths.first_pass,
        second_pass=paths.second_pass,
        merged=paths.merged,
        checkpoint=paths.checkpoint,
        partial_first=paths.partial_first,
        partial_second=paths.partial_second,
        completed=True,
    )


def _recent_prompt(
    subtitles: list[dict[str, Any]], base_prompt: Any, before: float
) -> str | None:
    """Carry a short prior-text hint across A windows when that option is enabled."""
    earlier = [item for item in subtitles if float(item.get("end", 0)) <= before]
    recent = "".join(str(item.get("text", "")) for item in earlier[-8:])[-240:]
    base = str(base_prompt or "").strip()
    prompt = "\n".join(part for part in (base, recent) if part)
    return prompt or None


def _append_a_window(
    subtitles: list[dict[str, Any]],
    result: Mapping[str, Any],
    *,
    analysis_start: float,
    core_start: float,
    core_end: float,
    is_last: bool,
) -> None:
    for segment in result.get("segments") or []:
        start = float(segment["start"]) + analysis_start
        end = float(segment["end"]) + analysis_start
        midpoint = (start + end) / 2
        belongs_to_core = core_start <= midpoint < core_end
        if is_last and math.isclose(midpoint, core_end):
            belongs_to_core = True
        if belongs_to_core:
            subtitles.append(
                {"start": start, "end": end, "text": str(segment["text"]).strip()}
            )


def _append_b_segment(
    subtitles: list[dict[str, Any]],
    result: Mapping[str, Any],
    *,
    segment_start: float,
    segment_end: float,
) -> None:
    for segment in result.get("segments") or []:
        start = max(segment_start, float(segment["start"]) + segment_start)
        end = min(segment_end, float(segment["end"]) + segment_start)
        if end > start:
            subtitles.append(
                {"start": start, "end": end, "text": str(segment["text"]).strip()}
            )


def run_resumable_two_pass_transcription(
    video_path: str | Path,
    output_dir: str | Path,
    *,
    resume: bool = True,
    cancel_check: CancelCheck | None = None,
    model_name: str = "large-v2",
    merge_gap: float = 1.0,
    duplicate_threshold: float = 0.5,
    filter_silent_b: bool = False,
    b_audio_min_rms: float = B_AUDIO_MIN_RMS,
    b_audio_min_active_seconds: float = B_AUDIO_MIN_ACTIVE_SECONDS,
    b_audio_silence_top_db: int = B_AUDIO_SILENCE_TOP_DB,
    b_speech_only: bool = False,
    b_vad_aggressiveness: int = 2,
    cpu_thread_profile: str = "balanced",
    gpu_acceleration: bool = False,
    first_whisper_values: Mapping[str, Any] | None = None,
    second_whisper_values: Mapping[str, Any] | None = None,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
    a_chunk_seconds: float = DEFAULT_A_CHUNK_SECONDS,
    a_overlap_seconds: float = DEFAULT_A_OVERLAP_SECONDS,
) -> ResumableSubtitleOutputs:
    """Run the dedicated cancellable A+B workflow and resume matching checkpoints."""
    source = Path(video_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到视频或音频文件：{source}")
    if not output_dir:
        raise ValueError("请选择保存文件夹。")
    if merge_gap < 0 or duplicate_threshold < 0:
        raise ValueError("时间间隔和去重阈值必须大于或等于 0。")
    if a_chunk_seconds <= 0 or not 0 <= a_overlap_seconds < a_chunk_seconds:
        raise ValueError("A 分片时长必须大于 0，重叠时长必须小于分片时长。")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("未找到 FFmpeg。请先安装 FFmpeg 并将其加入系统 PATH。")

    destination.mkdir(parents=True, exist_ok=True)
    paths = build_resumable_output_paths(source, destination)
    settings = _settings_identity(
        model_name=model_name,
        merge_gap=merge_gap,
        duplicate_threshold=duplicate_threshold,
        filter_silent_b=filter_silent_b,
        b_audio_min_rms=b_audio_min_rms,
        b_audio_min_active_seconds=b_audio_min_active_seconds,
        b_audio_silence_top_db=b_audio_silence_top_db,
        b_speech_only=b_speech_only,
        b_vad_aggressiveness=b_vad_aggressiveness,
        cpu_thread_profile=cpu_thread_profile,
        gpu_acceleration=gpu_acceleration,
        first_whisper_values=first_whisper_values,
        second_whisper_values=second_whisper_values,
        a_chunk_seconds=a_chunk_seconds,
        a_overlap_seconds=a_overlap_seconds,
    )
    if resume and paths.checkpoint.is_file():
        state = _load_matching_checkpoint(paths.checkpoint, source, settings)
        _log(log_callback, f"已读取断点：{paths.checkpoint.name}")
    else:
        state = _fresh_checkpoint(source, settings)
        _write_json_atomic(paths.checkpoint, state)
        _write_srt_atomic([], paths.partial_first)
        _write_srt_atomic([], paths.partial_second)
        _log(log_callback, "已创建新的断点任务；原有普通模式及其输出不会被修改。")

    librosa, torch, whisper = _import_dependencies()
    device = _configure_whisper_device(
        torch, gpu_acceleration=gpu_acceleration, log_callback=log_callback
    )
    if device == "cpu":
        worker_threads = _reserve_cpu_for_gui(torch, cpu_thread_profile)
        if worker_threads:
            _log(log_callback, f"CPU 线程：{worker_threads}。")
    _log(log_callback, f"断点模式使用设备：{device.upper()}；加载模型 {model_name}…")
    model = whisper.load_model(model_name, device=device)
    first_options = build_whisper_options("first", first_whisper_values, device=device)
    second_options = build_whisper_options("second", second_whisper_values, device=device)
    if gpu_acceleration:
        first_options["fp16"] = True
        second_options["fp16"] = True

    _log(log_callback, "读取 16 kHz 单声道音频，准备可续传分片…")
    audio_array, sample_rate = librosa.load(str(source), sr=16_000, mono=True)
    duration = len(audio_array) / sample_rate
    total_a_chunks = math.ceil(duration / a_chunk_seconds) if duration else 0
    cancel_check = cancel_check or (lambda: False)

    a_subtitles = [dict(item) for item in state.get("a_subtitles", [])]
    completed_a = int(state.get("a_completed_chunks", 0))
    if state.get("stage") == "a":
        _progress(progress_callback, "resumable_a", completed_a * a_chunk_seconds, duration)
        for chunk_index in range(completed_a, total_a_chunks):
            if cancel_check():
                _log(log_callback, "已安全取消；断点保留在上一个完整 A 分片之后。")
                return _cancelled_outputs(paths)
            core_start = chunk_index * a_chunk_seconds
            core_end = min(duration, core_start + a_chunk_seconds)
            analysis_start = max(0.0, core_start - a_overlap_seconds)
            analysis_end = min(duration, core_end + a_overlap_seconds)
            samples = audio_array[
                int(analysis_start * sample_rate) : int(analysis_end * sample_rate)
            ]
            options = dict(first_options)
            task = options.pop("task", "transcribe")
            if options.get("condition_on_previous_text") and a_subtitles:
                prompt = _recent_prompt(
                    a_subtitles, options.get("initial_prompt"), analysis_start
                )
                if prompt:
                    options["initial_prompt"] = prompt
            _log(
                log_callback,
                f"字幕 A 分片 {chunk_index + 1}/{total_a_chunks}："
                f"{core_start:.1f}s–{core_end:.1f}s（前后重叠复核）。",
            )
            result = model.transcribe(samples, task=task, verbose=True, **options)
            _append_a_window(
                a_subtitles,
                result,
                analysis_start=analysis_start,
                core_start=core_start,
                core_end=core_end,
                is_last=chunk_index == total_a_chunks - 1,
            )
            state["a_subtitles"] = a_subtitles
            state["a_completed_chunks"] = chunk_index + 1
            _write_srt_atomic(a_subtitles, paths.partial_first)
            _write_json_atomic(paths.checkpoint, state)
            _progress(progress_callback, "resumable_a", core_end, duration)
            if cancel_check():
                _log(log_callback, "当前 A 分片已完整保存，任务已安全取消。")
                return _cancelled_outputs(paths)

        _write_srt_atomic(a_subtitles, paths.first_pass)
        state["stage"] = "b"
        state["a_subtitles"] = a_subtitles
        _write_json_atomic(paths.checkpoint, state)

    if not paths.first_pass.is_file():
        _write_srt_atomic(a_subtitles, paths.first_pass)
    if cancel_check():
        _log(log_callback, "字幕 A 已完成；已在进入 B 前安全取消。")
        return _cancelled_outputs(paths)

    _log(log_callback, "根据已完成的字幕 A 计算 B 的未覆盖片段…")
    full_interval = [[0, duration]]
    excluded_intervals = extract_time_intervals(str(paths.first_pass), merge_gap=merge_gap)
    audio_segments, _remaining_intervals = exclude_segments_by_intervals(
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
        _log(log_callback, f"B 音频预筛跳过 {len(skipped_intervals)} 个片段。")
    elif audio_segments:
        _log(log_callback, "B 音频预筛关闭：保留全部反向剪裁片段。")

    b_subtitles = [dict(item) for item in state.get("b_subtitles", [])]
    completed_b = int(state.get("b_completed_segments", 0))
    total_b = len(audio_segments)
    if completed_b > total_b:
        raise ValueError("断点中的 B 片段数量无效，请选择重新开始。")
    _progress(progress_callback, "resumable_b", completed_b, total_b or 1)
    for segment_index in range(completed_b, total_b):
        if cancel_check():
            _log(log_callback, "已安全取消；断点保留在上一个完整 B 片段之后。")
            return _cancelled_outputs(paths)
        segment_start, segment_end, samples = audio_segments[segment_index]
        _log(
            log_callback,
            f"字幕 B 片段 {segment_index + 1}/{total_b}："
            f"{float(segment_start):.1f}s–{float(segment_end):.1f}s。",
        )
        if float(segment_end) - float(segment_start) >= 0.5:
            options = dict(second_options)
            task = options.pop("task", "transcribe")
            result = model.transcribe(samples, task=task, verbose=True, **options)
            _append_b_segment(
                b_subtitles,
                result,
                segment_start=float(segment_start),
                segment_end=float(segment_end),
            )
        state["b_subtitles"] = b_subtitles
        state["b_completed_segments"] = segment_index + 1
        _write_srt_atomic(b_subtitles, paths.partial_second)
        _write_json_atomic(paths.checkpoint, state)
        _progress(progress_callback, "resumable_b", segment_index + 1, total_b)
        if cancel_check():
            _log(log_callback, "当前 B 片段已完整保存，任务已安全取消。")
            return _cancelled_outputs(paths)

    _write_srt_atomic(b_subtitles, paths.second_pass)
    merged_subtitles = merge_srt(
        str(paths.first_pass),
        str(paths.second_pass),
        time_threshold=duplicate_threshold,
    )
    temporary_merged = paths.merged.with_name(f"{paths.merged.name}.tmp")
    write_srt(merged_subtitles, str(temporary_merged))
    os.replace(temporary_merged, paths.merged)
    paths.checkpoint.unlink(missing_ok=True)
    paths.partial_first.unlink(missing_ok=True)
    paths.partial_second.unlink(missing_ok=True)
    _progress(progress_callback, "resumable_b", total_b or 1, total_b or 1)
    _log(log_callback, f"可续传 A+B 已全部完成：{paths.merged}")
    return _completed_outputs(paths)
