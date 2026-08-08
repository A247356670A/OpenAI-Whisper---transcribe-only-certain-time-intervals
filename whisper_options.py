"""Whisper decoding options, descriptions, and safe GUI-to-Python conversion.

The options are the recognition-related arguments accepted by
``Whisper.transcribe()`` and its decoding layer.  File/output settings are not
included here because this application manages SRT paths itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping


@dataclass(frozen=True)
class WhisperOptionSpec:
    """Metadata used to render one editable Whisper option in the GUI."""

    key: str
    label: str
    kind: str
    default: str
    description: str
    choices: tuple[str, ...] = ()


# These descriptions are displayed beside every control in the advanced dialog.
WHISPER_OPTION_SPECS = (
    WhisperOptionSpec(
        "language", "语言", "choice", "ja",
        "强制指定音频语言。ja 代表日语；留为 ja 可避免自动语言识别误判。",
        ("ja", "zh", "en", "auto"),
    ),
    WhisperOptionSpec(
        "task", "任务", "choice", "transcribe",
        "transcribe 输出原语言字幕；translate 会把语音翻译为英文。",
        ("transcribe", "translate"),
    ),
    WhisperOptionSpec(
        "temperature", "温度 / 回退序列", "float_list", "0, 0.2, 0.4, 0.6, 0.8, 1.0",
        "解码随机性。0 最稳定；逗号分隔多个值时，遇到低置信度或重复会依次用更高温度重试。",
    ),
    WhisperOptionSpec(
        "best_of", "Best-of", "optional_int", "5",
        "温度大于 0 时采样的候选数量，选择得分最高的结果；数值更高更慢。",
    ),
    WhisperOptionSpec(
        "beam_size", "Beam size", "optional_int", "5",
        "温度为 0 时的束搜索宽度；更大可能更准确，但更慢、更占显存。",
    ),
    WhisperOptionSpec(
        "patience", "Beam patience", "optional_float", "",
        "束搜索的额外耐心系数；留空使用 Whisper 默认行为。仅温度为 0 时有效。",
    ),
    WhisperOptionSpec(
        "length_penalty", "长度惩罚", "optional_float", "",
        "束搜索中对输出长度的偏好；留空使用默认值。仅温度为 0 时有效。",
    ),
    WhisperOptionSpec(
        "condition_on_previous_text", "参考前文", "bool", "True",
        "把上一段结果作为下一段提示，可增强连贯性；关闭可减少重复循环和时间轴漂移。",
        ("True", "False"),
    ),
    WhisperOptionSpec(
        "initial_prompt", "初始提示词", "optional_text", "",
        "给第一段的提示，可加入人名、术语或固定写法，提高这些词被正确识别的概率。",
    ),
    WhisperOptionSpec(
        "carry_initial_prompt", "每段携带初始提示", "bool", "False",
        "启用后会把初始提示词带到每个内部解码窗口；长视频术语一致性更好，但会占用上下文。",
        ("True", "False"),
    ),
    WhisperOptionSpec(
        "suppress_tokens", "抑制 token", "token_list", "[]",
        "禁止输出指定 token ID。[] 表示不额外抑制；-1 使用 Whisper 的特殊符号抑制列表。",
    ),
    WhisperOptionSpec(
        "suppress_blank", "抑制空白开头", "bool", "True",
        "禁止解码结果以空白 token 开头，通常应保持开启。",
        ("True", "False"),
    ),
    WhisperOptionSpec(
        "without_timestamps", "不生成时间戳", "bool", "False",
        "关闭时正常输出时间轴。生成 SRT 必须保持 False，否则字幕时间可能不可用。",
        ("False", "True"),
    ),
    WhisperOptionSpec(
        "max_initial_timestamp", "首时间戳上限", "optional_float", "1.0",
        "限制每个窗口首个时间戳的最大秒数；留空交给 Whisper 默认值。",
    ),
    WhisperOptionSpec(
        "compression_ratio_threshold", "重复压缩阈值", "optional_float", "2.4",
        "文本 gzip 压缩率高于此值时视为过度重复并触发温度回退；留空关闭该检查。",
    ),
    WhisperOptionSpec(
        "logprob_threshold", "低置信度阈值", "optional_float", "-1.0",
        "平均 token 对数概率低于此值时触发温度回退；留空关闭该检查。",
    ),
    WhisperOptionSpec(
        "no_speech_threshold", "静音阈值", "optional_float", "0.6",
        "无语音概率高于此值、且低置信度时将片段视为静音；留空关闭静音判断。",
    ),
    WhisperOptionSpec(
        "word_timestamps", "词级时间戳", "bool", "True",
        "使用交叉注意力和动态时间规整细化词级时间戳；更慢，但可改善分段与字幕对齐。",
        ("True", "False"),
    ),
    WhisperOptionSpec(
        "prepend_punctuations", "前接标点", "text", "\"'“¿([{-",
        "词级时间戳开启时，将这些标点并入后一个词。",
    ),
    WhisperOptionSpec(
        "append_punctuations", "后接标点", "text", "\"'.。,，!！?？:：”)]}、",
        "词级时间戳开启时，将这些标点并入前一个词。",
    ),
    WhisperOptionSpec(
        "clip_timestamps", "处理时间范围", "text", "0",
        "以秒填写 start,end,start,end…；0 表示完整音频。可只识别指定片段。",
    ),
    WhisperOptionSpec(
        "hallucination_silence_threshold", "幻觉静音跳过", "optional_float", "",
        "词级时间戳开启时，疑似幻觉附近超过该秒数的静音会被跳过；留空关闭。",
    ),
    WhisperOptionSpec(
        "fp16", "FP16 精度", "fp16", "auto",
        "auto：GPU 用 FP16、CPU 用 FP32；False 可提升兼容性但 GPU 可能更慢。",
        ("auto", "True", "False"),
    ),
)


def default_option_values(pass_name: str) -> dict[str, str]:
    """Return editable display values for the first or second recognition pass."""
    values = {spec.key: spec.default for spec in WHISPER_OPTION_SPECS}
    values["condition_on_previous_text"] = "True" if pass_name == "first" else "False"
    return values


def _parse_bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{key} 必须是 True 或 False。")


def _parse_token_list(value: Any) -> list[int]:
    if isinstance(value, list):
        return [int(item) for item in value]
    text = str(value).strip()
    if not text or text == "[]":
        return []
    if text.startswith("["):
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("抑制 token 必须是 JSON 数组或逗号分隔的整数。")
        return [int(item) for item in parsed]
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def build_whisper_options(
    pass_name: str,
    values: Mapping[str, Any] | None,
    *,
    device: str,
) -> dict[str, Any]:
    """Validate GUI values and convert them to ``model.transcribe`` arguments."""
    raw = default_option_values(pass_name)
    if values:
        raw.update(values)
    options: dict[str, Any] = {}

    for spec in WHISPER_OPTION_SPECS:
        value = raw[spec.key]
        text = str(value).strip() if value is not None else ""
        try:
            if spec.kind == "bool":
                options[spec.key] = _parse_bool(value, spec.label)
            elif spec.kind == "fp16":
                options[spec.key] = device == "cuda" if text.lower() == "auto" else _parse_bool(value, spec.label)
            elif spec.kind == "optional_int":
                options[spec.key] = int(text) if text else None
            elif spec.kind == "optional_float":
                options[spec.key] = float(text) if text else None
            elif spec.kind == "float_list":
                numbers = [float(item.strip()) for item in text.split(",") if item.strip()]
                if not numbers:
                    raise ValueError("至少填写一个温度值。")
                options[spec.key] = tuple(numbers) if len(numbers) > 1 else numbers[0]
            elif spec.kind == "token_list":
                options[spec.key] = _parse_token_list(value)
            elif spec.kind == "optional_text":
                options[spec.key] = text or None
            elif spec.kind == "choice" and spec.key == "language":
                options[spec.key] = None if text.lower() == "auto" else text
            elif spec.kind == "choice" and spec.choices and text not in spec.choices:
                raise ValueError(f"{spec.label} 必须是：{', '.join(spec.choices)}。")
            else:
                options[spec.key] = str(value)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith(spec.label):
                raise
            raise ValueError(f"Whisper 参数“{spec.label}”格式不正确：{value!r}") from exc

    return options
