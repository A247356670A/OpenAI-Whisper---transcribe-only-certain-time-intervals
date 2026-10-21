# Qwen3-ASR 完整 A+B

主界面选择“完整识别”，将“识别引擎”切换为 `Qwen3-ASR`，使用原开始按钮。
默认仍是 Whisper，原 Whisper 模型、参数和输出命名不变。

## 安装

在启动 GUI 的同一 Python 环境中安装可选依赖：

```powershell
python -m pip install -r requirements-qwen.txt
```

需要项目原有依赖及 FFmpeg。建议备份环境或在新虚拟环境安装项目依赖后测试，
因为 Qwen 会引入 Transformers 等依赖。不会自动安装依赖或下载模型。
首次选择 Qwen 并运行时，官方加载器会下载 ASR 与 ForcedAligner 权重，需要网络和磁盘空间。
无需 API key、vLLM 或 FlashAttention。使用本地 Transformers 推理。

## 设置

- 模型：默认 `Qwen/Qwen3-ASR-1.7B`，另可选 0.6B。
- 自动使用 `Qwen/Qwen3-ForcedAligner-0.6B` 定位日语文字。
- 自动优先 CUDA，否则 CPU；勾选 GPU 后 CUDA 不可用会明确报错。
- 切片：10～120 秒，默认 60；显存不足时先试 30 或 0.6B。
- 背景：可填简短日语人名，例如 `配信者：四月一日ベレト。登場人物：ロクシー、クロウ。`
  A、B 共用背景，不是中日翻译提示词。
- 主界面“保存当前参数”可保留引擎和 Qwen 设置。

Whisper 高级参数不影响 Qwen。合并间隔、去重阈值和可选 B 人声筛选仍生效。
B 人声筛选关闭时不会额外过滤，但保留既有反向剪裁流程的 0.5 秒最短片段限制。

## 文件和进度

输出为原视频名加 `_Qwen_A.srt`、`_Qwen_B.srt`、`_Qwen_merged.srt`。
程序开始前会使用这些实际路径检查是否需要覆盖确认。
A 进度按完成的音频秒数更新，B 按完成的反向剪裁片段数更新。
每个片段完成识别和对齐后才推进进度，片段内暂不更新。

当前 Qwen 仅接入普通完整 A+B；“仅 A／仅 B”和“可取消／续传”仍限 Whisper。
没有声称支持 Qwen 断点；失败后需重新运行，已成功生成的 A 文件可能保留。
日语识别结果还需另外翻译为中文。对齐不是内容正确性验证，仍应人工审核。

官方接口参考：https://github.com/QwenLM/Qwen3-ASR
