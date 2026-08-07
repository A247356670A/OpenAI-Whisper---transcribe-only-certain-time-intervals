# 日语字幕提取器（Whisper 双重识别）

这个项目会自动完成三步：

1. 对完整视频识别，生成字幕 `A`；
2. 找出 A 未覆盖的时间段，再次识别，生成字幕 `B`；
3. 合并 A 与 B，并去除时间和文本都重复的字幕，生成最终文件。

## 使用图形界面

先安装依赖（只需一次）：

```powershell
python -m pip install -r requirements.txt
```

还需要安装 [FFmpeg](https://ffmpeg.org/download.html) 并将其加入系统 `PATH`。

随后双击或运行：

```powershell
python openai_whisper_transcribe_only_certain_time_intervals.py
```

将视频文件直接拖入窗口（也可点击选择文件），选好字幕保存位置后点击“开始提取字幕”。默认使用原项目的 `large-v2` 模型；第一次使用某个模型时，Whisper 会自动下载它。程序会在保存位置生成：

- `视频名_A.srt`：完整视频的第一次识别结果
- `视频名_B.srt`：A 未覆盖片段的补充识别结果
- `视频名_merged.srt`：最终合并字幕

识别会在后台进行，运行日志会显示在窗口下方，因此界面不会卡死。拖放功能由 `tkinterdnd2` 提供；该包已在 `requirements.txt` 中列出。

## 终端运行（可选）

```powershell
python openai_whisper_transcribe_only_certain_time_intervals.py "D:\\视频\\input.mp4" --output-dir "D:\\字幕"
```
