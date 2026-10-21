"""Optional Qwen ASR + forced alignment workflow; no heavy startup imports.

Uses the Transformers backend (not vLLM), keeps absolute video offsets, and
reuses the established opt-in B filtering and merge behavior.
"""
from pathlib import Path
import math
import unicodedata
from types import SimpleNamespace

import subtitle_pipeline as pipeline

QWEN_MODELS = ('Qwen/Qwen3-ASR-1.7B', 'Qwen/Qwen3-ASR-0.6B')
ALIGNER = 'Qwen/Qwen3-ForcedAligner-0.6B'


def build_qwen_output_paths(video, output_dir):
    source = Path(video)
    return pipeline.build_output_paths(source.with_name(source.stem + '_Qwen' + source.suffix), output_dir)


def _load_runtime(model_name, gpu, log):
    """Load on demand, so missing optional dependencies never break Whisper."""
    try:
        import torch
        import librosa
        from qwen_asr import Qwen3ASRModel
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            'Qwen3-ASR 可选依赖未安装或加载失败。请在运行 GUI 的同一 Python 环境执行：\n'
            'python -m pip install -r requirements-qwen.txt\n'
            '建议先在独立虚拟环境测试，原 Whisper 环境不必修改。\n'
            f'具体原因：{exc}'
        ) from exc
    if gpu and not torch.cuda.is_available():
        raise RuntimeError('已选择 GPU，但 PyTorch 无法使用 CUDA。请检查 CUDA 版 PyTorch。')
    device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
    dtype = (torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16) if device != 'cpu' else torch.float32
    log(f'Qwen 使用 {device}；加载 {model_name} 和时间对齐模型。首次运行需下载模型。')
    model = Qwen3ASRModel.from_pretrained(
        model_name, device_map=device, dtype=dtype,
        max_inference_batch_size=1, max_new_tokens=4096,
        forced_aligner=ALIGNER,
        forced_aligner_kwargs=dict(device_map=device, dtype=dtype),
    )
    return model, torch, librosa


def _kept(char):
    return char == "'" or unicodedata.category(char).startswith(('L', 'N'))


def _has_spoken_text(text):
    """Punctuation/music symbols alone cannot be aligned as spoken words."""
    return any(unicodedata.category(c).startswith(('L', 'N')) for c in text)


def ensure_alignment(model, result, audio, sample_rate, offset, log):
    """Handle empty token output; retry missing alignment once for real text.

    Never replace missing timestamps with a whole-slice span: that would hide
    unrecognized speech from pass B. Do not infer silence from missing times.
    """
    text = result.text.strip()
    if not _has_spoken_text(text):
        if text:
            log(f'Qwen {offset:.1f} 秒：仅返回符号 {text[:100]!r}，不生成字幕；未覆盖时间仍可进入 B。')
        return SimpleNamespace(text='', time_stamps=[])
    stamps = getattr(result, 'time_stamps', None)
    if stamps is not None and len(stamps):
        return result
    detail = f'片段起点 {offset:.3f} 秒，识别文字 {text[:180]!r}'
    log(f'Qwen 缺少时间轴，单独重试 ForcedAligner：{detail}')
    aligner = getattr(model, 'forced_aligner', None)
    if aligner is None:
        raise ValueError(f'Qwen 对齐模型未加载。{detail}')
    try:
        aligned = aligner.align(audio=(audio, sample_rate), text=text, language='Japanese')
        if len(aligned) != 1 or aligned[0] is None or not len(aligned[0]):
            raise ValueError('对齐器仍返回空结果')
    except Exception as exc:
        raise ValueError(f'Qwen 独立时间对齐失败：{detail}。原因：{exc}') from exc
    return SimpleNamespace(text=text, time_stamps=aligned[0])


def aligned_entries(result, offset, duration):
    """Restore punctuation stripped by the aligner; split on pauses/length.

    Reject incomplete alignment instead of silently losing recognized words or
    inventing whole-chunk timestamps that would incorrectly cover B gaps.
    """
    text = result.text.strip()
    if not _has_spoken_text(text):
        return []
    if result.time_stamps is None:
        raise ValueError('Qwen 返回了文字但没有时间轴；请检查 ForcedAligner。')
    items = list(result.time_stamps)
    source_chars = [(i, char) for i, char in enumerate(text) if _kept(char)]
    expected = ''.join(char for _, char in source_chars)
    actual = ''.join(''.join(c for c in item.text if _kept(c)) for item in items)
    if not items or not expected or actual != expected:
        raise ValueError('Qwen 文字与时间对齐结果不一致，已停止以避免丢字。请尝试较短切片。')
    pieces = []
    cursor = 0
    source_start = 0
    for item in items:
        count = sum(_kept(c) for c in item.text)
        if not count:
            continue
        cursor += count
        source_end = source_chars[cursor][0] if cursor < len(source_chars) else len(text)
        start, end = float(item.start_time), float(item.end_time)
        if not math.isfinite(start) or not math.isfinite(end) or end < start or start < -0.1 or end > duration + 0.5:
            raise ValueError('Qwen 返回无效时间轴，已停止生成。')
        start, end = max(0.0, min(start, duration)), max(0.0, min(end, duration))
        # Aligner can quantize a short token to a zero-duration span.
        if end <= start:
            start = max(0.0, start - 0.04)
            end = min(duration, max(end, start + 0.04))
        pieces.append((start, end, text[source_start:source_end]))
        source_start = source_end
    entries = []
    group = []
    def flush():
        if group:
            entries.append((offset + group[0][0], offset + max(p[1] for p in group), ''.join(p[2] for p in group).strip()))
            group.clear()
    for piece in pieces:
        if group and (piece[0] - group[-1][1] > 0.6 or piece[1] - group[0][0] > 6 or sum(len(p[2]) for p in group) + len(piece[2]) > 42):
            flush()
        group.append(piece)
        if piece[2].rstrip().endswith(('。', '！', '？', '!', '?')):
            flush()
    flush()
    return entries


def audio_chunks(audio, sample_rate, seconds):
    """Contiguous bounded slices; choose a quiet boundary within the last second."""
    import numpy as np
    start = 0
    limit = int(seconds * sample_rate)
    while start < len(audio):
        end = min(start + limit, len(audio))
        if end < len(audio):
            low = max(start + limit // 2, end - sample_rate)
            width = max(1, sample_rate // 20)
            candidates = range(low, end - width + 1, width)
            end = min(candidates, key=lambda p: float(np.mean(np.abs(audio[p:p + width])))) + width // 2
        yield start / sample_rate, audio[start:end]
        start = end


def run_qwen_two_pass(video_path, output_dir, *, model_name=QWEN_MODELS[0],
                      context='', chunk_seconds=60, gpu_acceleration=False,
                      merge_gap=1.0, duplicate_threshold=0.5, filter_b_speech=False,
                      b_silero_threshold=pipeline.B_SILERO_THRESHOLD,
                      b_silero_min_speech_seconds=pipeline.B_SILERO_MIN_SPEECH_SECONDS,
                      b_silero_min_speech_ratio=pipeline.B_SILERO_MIN_SPEECH_RATIO,
                      log_callback=None, progress_callback=None):
    """Full A pass, inverse A coverage, optional VAD, B pass, then merge."""
    if model_name not in QWEN_MODELS:
        raise ValueError('请选择支持的 Qwen3-ASR 模型。')
    if not 10 <= float(chunk_seconds) <= 120:
        raise ValueError('Qwen 切片长度必须在 10～120 秒之间。')
    if not all(math.isfinite(x) and x >= 0 for x in (merge_gap, duplicate_threshold)):
        raise ValueError('合并间隔及去重阈值必须为非负有限数。')
    source = Path(video_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f'找不到视频：{source}')
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    outputs = build_qwen_output_paths(source, destination)
    log = lambda message: pipeline._log(log_callback, message)
    progress = lambda stage, current, total: pipeline._progress(progress_callback, stage, current, total)
    model, torch, librosa = _load_runtime(model_name, gpu_acceleration, log)
    audio, sr = pipeline._load_audio_mono_16k(source, librosa, log_callback)
    duration = len(audio) / sr
    if duration <= 0:
        raise ValueError('输入音频为空。')
    def recognize(samples, offset):
        # Padding affects only model input, not absolute timeline or coverage.
        import numpy as np
        real_duration = len(samples) / sr
        padded = np.pad(samples, (0, max(0, int(sr * .5) - len(samples))))
        results = model.transcribe(audio=(padded, sr), language='Japanese',
                                   context=context, return_time_stamps=True)
        if len(results) != 1:
            raise ValueError('Qwen 返回的识别结果数量异常。')
        result = ensure_alignment(model, results[0], padded, sr, offset, log)
        try:
            return aligned_entries(result, offset, real_duration)
        except ValueError as exc:
            raise ValueError(f'{exc} 片段起点 {offset:.3f} 秒，识别文字 {result.text[:180]!r}') from exc
    log('第 1 步/3：Qwen 识别完整视频并对齐，生成字幕 A…')
    progress('subtitle_a', 0, duration)
    a = []
    for offset, samples in audio_chunks(audio, sr, float(chunk_seconds)):
        log(f'Qwen A：{offset:.1f} → {offset + len(samples)/sr:.1f} 秒')
        a.extend(recognize(samples, offset))
        progress('subtitle_a', offset + len(samples)/sr, duration)
    pipeline.write_srt(a, str(outputs.first_pass))
    excluded = pipeline.extract_time_intervals(str(outputs.first_pass), merge_gap=merge_gap)
    segments, _ = pipeline.exclude_segments_by_intervals(audio, [[0,duration]], excluded, sr)
    log(f'B 反向剪裁：{len(segments)} 个片段（沿用原流程的 0.5 秒最短片段）。')
    if filter_b_speech and segments:
        segments, skipped = pipeline.filter_b_segments_with_silero(
            segments, sr, torch, threshold=b_silero_threshold,
            min_speech_seconds=b_silero_min_speech_seconds,
            min_speech_ratio=b_silero_min_speech_ratio, log_callback=log_callback)
        log(f'Silero 跳过 {len(skipped)} 个 B 片段。')
    else:
        log('Silero 未启用：保留全部反向剪裁出的 B 片段。')
    log(f'第 2 步/3：Qwen 识别 {len(segments)} 个 B 片段…')
    progress('subtitle_b', 0, len(segments) or 1)
    b = []
    for number, (start, end, samples) in enumerate(segments, 1):
        log(f'Qwen B：片段 {number}/{len(segments)}，{start:.1f} → {end:.1f} 秒')
        for local_offset, chunk in audio_chunks(samples, sr, float(chunk_seconds)):
            b.extend(recognize(chunk, start + local_offset))
        progress('subtitle_b', number, len(segments))
    pipeline.write_srt(b, str(outputs.second_pass))
    progress('subtitle_b', len(segments) or 1, len(segments) or 1)
    log('第 3 步/3：合并 Qwen 字幕 A+B…')
    merged = pipeline.merge_srt(str(outputs.first_pass), str(outputs.second_pass), time_threshold=duplicate_threshold)
    pipeline.write_srt(merged, str(outputs.merged))
    log(f'完成：{outputs.merged}')
    return outputs
