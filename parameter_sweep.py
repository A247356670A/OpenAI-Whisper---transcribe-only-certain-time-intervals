"""Run repeatable A+B Whisper experiments over one time slice of a media file.

The script is intentionally parameterised: media paths are supplied on the
command line, and each result is renamed after the tested parameter set.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys

from subtitle_pipeline import SubtitleOutputs, run_two_pass_transcription
from whisper_options import default_option_values


@dataclass(frozen=True)
class Experiment:
    """One controlled parameter variation, relative to the GUI defaults."""

    name: str
    description: str
    first_overrides: dict[str, str]
    second_overrides: dict[str, str]


EXPERIMENTS = (
    Experiment(
        "01_default_AprevOn_BprevOff",
        "基线：第一轮参考前文，第二轮不参考前文，使用默认温度回退序列。",
        {},
        {},
    ),
    Experiment(
        "02_AprevOff_BprevOff",
        "仅关闭第一轮的前文关联，观察重复循环、连贯性与切段边界变化。",
        {"condition_on_previous_text": "False"},
        {},
    ),
    Experiment(
        "03_AprevOn_BprevOn",
        "仅开启第二轮的前文关联，观察补全片段之间的上下文影响。",
        {},
        {"condition_on_previous_text": "True"},
    ),
    Experiment(
        "04_fixedTemperature0_A_B",
        "两轮均固定温度 0，不使用更高温度回退，观察稳定性与低置信度片段。",
        {"temperature": "0"},
        {"temperature": "0"},
    ),
)


def format_timestamp(seconds: float) -> str:
    """Create a filesystem-safe label such as ``45m00s``."""
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}m{remainder:02}s"


def create_audio_slice(source: Path, destination: Path, start: float, duration: float) -> None:
    """Extract a mono 16 kHz WAV slice once; every experiment uses this input."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 FFmpeg，无法创建测试切片。")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(start), "-t", str(duration), "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination),
    ]
    print(f"创建 {start / 60:.0f} 分钟开始、时长 {duration / 60:.0f} 分钟的音频切片…")
    subprocess.run(command, check=True)


def build_values(pass_name: str, overrides: dict[str, str]) -> dict[str, str]:
    """Start from GUI defaults so an experiment changes only its named parameter."""
    values = default_option_values(pass_name)
    values.update(overrides)
    return values


def rename_outputs(outputs: SubtitleOutputs, output_dir: Path, experiment_name: str) -> dict[str, Path]:
    """Rename A, B and merged SRTs so comparison does not require opening folders."""
    renamed = {
        "A": output_dir / f"{experiment_name}_A.srt",
        "B": output_dir / f"{experiment_name}_B.srt",
        "merged": output_dir / f"{experiment_name}_merged.srt",
    }
    for source, target in (
        (outputs.first_pass, renamed["A"]),
        (outputs.second_pass, renamed["B"]),
        (outputs.merged, renamed["merged"]),
    ):
        if target.exists():
            target.unlink()
        source.replace(target)
    return renamed


def run_experiment(
    audio_slice: Path,
    output_dir: Path,
    experiment: Experiment,
    model_name: str,
) -> None:
    """Run one A+B configuration and store a JSON manifest beside its SRTs."""
    print(f"\n{'=' * 72}\n开始：{experiment.name}\n{experiment.description}")
    first_values = build_values("first", experiment.first_overrides)
    second_values = build_values("second", experiment.second_overrides)
    outputs = run_two_pass_transcription(
        audio_slice,
        output_dir,
        model_name=model_name,
        first_whisper_values=first_values,
        second_whisper_values=second_values,
    )
    renamed = rename_outputs(outputs, output_dir, experiment.name)
    manifest = {
        **asdict(experiment),
        "model": model_name,
        "input_slice": audio_slice.name,
        "outputs": {name: path.name for name, path in renamed.items()},
        "first_whisper_values": first_values,
        "second_whisper_values": second_values,
    }
    (output_dir / f"{experiment.name}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"完成：{experiment.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="在固定时间片段上对 Whisper A+B 参数进行横向比较。")
    parser.add_argument("source", type=Path, help="原视频或音频文件")
    parser.add_argument("--start", type=float, default=45 * 60, help="切片起点（秒），默认 45 分钟")
    parser.add_argument("--duration", type=float, default=10 * 60, help="切片时长（秒），默认 10 分钟")
    parser.add_argument("--model", default="large-v2", help="Whisper 模型，默认 large-v2")
    parser.add_argument("--output-dir", type=Path, help="实验结果文件夹")
    parser.add_argument("--reuse-slice", action="store_true", help="存在相同切片时复用，不重新提取")
    parser.add_argument("--log-file", type=Path, help="将运行日志写入指定 UTF-8 文件")
    args = parser.parse_args()

    if args.log_file:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        log_stream = args.log_file.open("w", encoding="utf-8", buffering=1)
        sys.stdout = log_stream
        sys.stderr = log_stream

    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到输入文件：{source}")
    label = f"{format_timestamp(args.start)}_{format_timestamp(args.start + args.duration)}"
    output_dir = (args.output_dir or source.parent / f"参数对比_{label}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_slice = output_dir / f"slice_{label}.wav"
    if not (args.reuse_slice and audio_slice.is_file()):
        create_audio_slice(source, audio_slice, args.start, args.duration)

    for experiment in EXPERIMENTS:
        run_experiment(audio_slice, output_dir, experiment, args.model)

    print(f"\n全部实验完成。结果目录：{output_dir}")


if __name__ == "__main__":
    main()
