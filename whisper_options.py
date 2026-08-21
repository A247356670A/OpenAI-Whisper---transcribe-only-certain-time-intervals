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


# Long-form help is opened from the question-mark button beside each advanced
# option.  Keep the short ``description`` above scannable and put comparisons,
# trade-offs, and concrete input examples here.
WHISPER_OPTION_HELP: dict[str, str] = {
    "language": """作用：告诉 Whisper 音频主要使用哪种语言。明确指定语言可以跳过自动语言判断，并减少把日语误判成中文或英语的情况。

怎么选：本项目处理日语主播视频时建议保持 ja。只有输入确实是中文或英语时才选择 zh / en；auto 会让 Whisper 自己判断。

例子：日语直播选择 ja；中日混合但主播主要说日语，仍建议选择 ja；完全未知语言的短片才考虑 auto。

注意：这里控制的是识别语言，不会把字幕翻译成中文。""",
    "task": """作用：决定输出原语言文字，还是把语音直接翻译成英文。

怎么选：生成日语 SRT 时必须使用 transcribe。translate 是 Whisper 自带的“翻译为英文”，不是翻译为中文。

例子：日语音频 + transcribe → 日语字幕；日语音频 + translate → 英文字幕。

注意：如果后续要使用其他工具翻译日语字幕，仍应先选 transcribe。""",
    "temperature": """作用：控制解码随机性，也可以设置失败时依次尝试的温度序列。温度越低结果越稳定；越高越可能跳出重复循环，但文字也更随机。

推荐：0, 0.2, 0.4, 0.6, 0.8, 1.0 是 Whisper 官方常见回退序列。追求可重复对比时可只填 0。

例子：填 0 表示只做确定性解码；填 0, 0.2, 0.4 表示先用 0，检测到低置信度或重复时再逐级重试。

注意：使用多个温度可能增加处理时间。""",
    "best_of": """作用：当实际温度大于 0 时，同时采样多个候选并选取得分最高的一条。

怎么选：默认 5 通常足够；改成 1 更快但选择余地少；提高到 10 可能略微改善困难音频，但速度和显存/内存消耗会上升。

例子：temperature=0.4、best_of=5 时会比较 5 个随机候选。temperature=0 时主要使用 beam_size，本项通常不起作用。

留空：交给 Whisper 默认值。""",
    "beam_size": """作用：温度为 0 时束搜索保留的候选路径数量。更大可能找到更好的句子，但会变慢并增加显存占用。

推荐：5 是准确度和速度的常用平衡；显存紧张可用 1～3；难辨音频可尝试 8～10。

例子：beam_size=1 接近贪心解码；beam_size=5 会同时追踪 5 条较可能的文本路径。

注意：温度大于 0 时使用 best_of，而不是 beam_size。""",
    "patience": """作用：调整束搜索何时停止。大于 1 会允许搜索更多候选，可能改善句尾或长句，但会更慢。

推荐：通常留空。只有在 temperature=0 且发现句子经常过早结束时，再尝试 1.2～2.0。

例子：patience=1.5 表示比标准束搜索更有耐心；留空使用 Whisper 默认行为。

注意：仅束搜索时有效。""",
    "length_penalty": """作用：改变束搜索对长文本和短文本的偏好。它不会简单地规定字幕长度，而是影响候选句子的评分。

推荐：通常留空。只有经过固定测试片段横向比较后再调整，避免为解决一处截断而让整段输出变得冗长。

例子：发现大量句尾无故提前结束时，可小幅试验不同值并对比 SRT；没有明确问题时保持空白。

注意：仅 temperature=0 的束搜索有效。""",
    "condition_on_previous_text": """作用：把前一个解码窗口的文字作为下一个窗口的上下文。开启后人名和语气更连贯；关闭后各窗口更独立，可减少重复循环和错误向后传播。

推荐：第一轮 A 默认 True，因为连续完整视频需要上下文；第二轮 B 默认 False，因为 B 是许多不连续的小片段。

例子：A 中连续讨论同一角色时开启可保持角色名写法；B 的相邻数组片段实际来自不同时间，关闭可避免把上一片段内容带入下一片段。

注意：若长视频出现整句反复复制，可尝试关闭。""",
    "initial_prompt": """作用：给 Whisper 一段文字提示，帮助它优先采用指定的人名、游戏术语、标点和书写风格。提示不是必须输出的字幕。

推荐：填写短而准确的词表或一句自然日语，不要塞入大量无关文字。

例子：四月一日ベレト、ゼンレスゾーンゼロ、レミエール、ニュ－エリドゥ。可提高这些专有名词被正确拼写的概率。

注意：错误提示也会诱导错误识别；修改提示后应在同一片段横向比较。""",
    "carry_initial_prompt": """作用：决定 initial_prompt 是否持续带入后续每个内部解码窗口。关闭时主要影响开头；开启时整段视频都能看到提示。

推荐：术语贯穿整场直播时可开启；提示很长或只与开场有关时保持关闭。

例子：整场都在讲同一游戏角色，可设 True；只有开头自我介绍需要提示，可设 False。

注意：持续提示会占用上下文长度，并可能放大提示中的错误词。""",
    "suppress_tokens": """作用：禁止 Whisper 输出指定的 token ID。它面向熟悉 Whisper tokenizer 的高级用户。

推荐：本项目默认 []，即不额外屏蔽任何 token。-1 表示使用 Whisper 内置的非语音符号抑制列表。

例子：[]；或 [1, 2, 3] / 1,2,3。这里填写的是数字 token ID，不是要删除的文字。

注意：填错 token 可能导致正常日语字符无法输出；删除“感谢观看”等幻觉应使用项目的字幕审核功能。""",
    "suppress_blank": """作用：在每个解码窗口开始时抑制空白 token，减少结果以异常空白开头。

推荐：通常保持 True。只有在研究特殊 token 行为或排查模型解码问题时才关闭。

例子：True 是常规字幕设置；False 允许模型自由产生开头空白，但通常不会改善识别内容。

注意：它不是“跳过静音”的开关。""",
    "without_timestamps": """作用：控制 Whisper 是否禁用时间戳 token。

推荐：本项目生成 SRT 必须保持 False，让识别结果包含可用的开始和结束时间。

例子：False → 得到 00:10.000–00:12.500 等时间轴；True → 主要得到连续文本，字幕时间可能缺失或不可用。

注意：除非只研究纯文本输出，否则不要设为 True。""",
    "max_initial_timestamp": """作用：限制每个 Whisper 解码窗口中，第一个时间戳最晚可以出现在窗口开始后的多少秒。

推荐：默认 1.0。开头确实有较长静音且首句被截断或位置异常时，可试 2～5；一般不要随意增大。

例子：设为 1.0 时，窗口第一条内容不能从窗口内 3 秒处才开始；设为 5.0 则允许更晚的首时间戳。

留空：使用 Whisper 默认值。""",
    "compression_ratio_threshold": """作用：用文本压缩率检测“同一句或同一字符反复循环”。超过阈值时会认为结果异常，并尝试更高温度。

推荐：2.4 是常用默认值。幻觉重复很多时可略微降低，例如 2.2；正常长句频繁被重试时可略微提高。

例子：“ありがとうございました”连续重复十几次会非常容易压缩，因而可能触发该检查。

留空：完全关闭这项重复检测。""",
    "logprob_threshold": """作用：用平均 token 对数概率判断识别置信度。结果低于该值时触发温度回退。

推荐：-1.0 是常用默认值。值调高（例如 -0.7）会更严格、重试更多；调低（例如 -1.2）会更宽松。

例子：某段平均 logprob=-0.9：阈值 -1.0 时通过，阈值 -0.7 时会被视为低置信度。

留空：关闭这项低置信度检查。严格不一定更准确，也可能明显变慢。""",
    "no_speech_threshold": """作用：结合模型的无语音概率和 logprob，判断当前窗口是否应当当作静音跳过。

推荐：0.6 是常用默认值。若安静对白被跳过，可提高到 0.7～0.8；若纯音乐/静音产生很多字幕，可尝试降低到 0.5。

例子：模型判断 no_speech=0.7 且文字置信度低，阈值 0.6 时可能跳过；阈值 0.8 时更可能保留并尝试识别。

注意：它与外层的 Silero B 人声预筛是两套独立判断。""",
    "word_timestamps": """作用：使用词级对齐细化每个词的时间位置，项目再据此组织字幕段落。

推荐：A、B 默认 True，可改善字幕切分和对齐；如果只追求速度且不在意精细时间轴，可测试 False。

例子：True 时可知道一句中每个日语词的大致开始/结束位置；False 时通常只有段级时间。

注意：True 会增加计算量，且 CUDA 环境缺少某些优化组件时可能出现回退警告，但仍可运行。""",
    "prepend_punctuations": """作用：词级时间戳开启时，指定哪些前置标点应并入后一个词，避免标点单独占据时间。

推荐：保持默认字符串，除非目标语言使用特殊引号或括号。

例子：左括号“（”应跟随括号后的第一个词，而不是成为独立字幕片段；可把需要的符号加入此字符串。

注意：这里直接填写连续的标点字符，不用逗号分隔。""",
    "append_punctuations": """作用：词级时间戳开启时，指定哪些后置标点应并入前一个词。

推荐：日语字幕保持包含 。、！、？、」等常用标点的默认值。

例子：“です。”中的句号会继承“です”的结束时间，不会单独形成一个词级区间。

注意：这里直接填写连续的标点字符，不用逗号分隔。""",
    "clip_timestamps": """作用：只让 Whisper 处理指定的音频时间范围。格式是以秒表示的 start,end,start,end……

推荐：正常完整任务保持 0。炼丹或只测试视频局部时再填写范围。

例子：2700,3300 表示只识别 45:00～55:00；0,60,120,180 表示识别 0～60 秒以及 120～180 秒。

注意：该参数作用在每次传给 Whisper 的音频上；B 模式本身已按片段裁切，随意设置可能再次截掉 B 内容。""",
    "hallucination_silence_threshold": """作用：开启词级时间戳时，允许 Whisper 跳过疑似幻觉前后达到指定长度的静音区域。

推荐：默认留空。结尾静音经常生成“ご視聴ありがとうございました”等内容时，可从 1.0～2.0 秒开始测试。

例子：填 2.0，疑似幻觉附近存在超过约 2 秒静音时，Whisper 会尝试跳过该静音区。

注意：数值太小可能跨过真实对白；它不能替代生成后的人工幻觉字幕审核。""",
    "fp16": """作用：控制模型是否使用 16 位浮点推理。FP16 通常能让 NVIDIA GPU 更快并减少显存，但普通 CPU 不适合。

推荐：auto。程序会在 CUDA GPU 上启用 FP16，在 CPU 上使用 FP32。

例子：NVIDIA CUDA + auto → True；CPU + auto → False。遇到 GPU 数值兼容问题时可手动设 False。

注意：设 True 不会让 CPU 获得 GPU 加速；GPU 高性能模式还需要正确安装 CUDA 版 PyTorch。""",
}


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
