# 日语字幕提取器（Whisper 双重识别）

这个项目会自动完成三步：

1. 对完整视频识别，生成字幕 `A`；
2. 找出 A 未覆盖的时间段，再次识别，生成字幕 `B`；
3. 合并 A 与 B，并去除时间和文本都重复的字幕，生成最终文件。

## 使用图形界面

请使用 Python 3.11 或更高版本。克隆项目后，先在项目目录完成以下一次性安装。

### macOS（Homebrew）

烧录和预览字幕需要 FFmpeg 的 `subtitles` 滤镜，而这个滤镜依赖 `libass`。Homebrew 的普通 `ffmpeg` 不包含它，因此请安装完整版本：

```zsh
brew install ffmpeg-full
brew link --overwrite --force ffmpeg-full
python -m pip install -r requirements.txt
```

如果之前安装过普通版 `ffmpeg`，先执行 `brew unlink ffmpeg`，再执行上面的 `brew link` 命令。安装后可验证：

```zsh
ffmpeg -hide_banner -filters | grep subtitles
```

输出中出现 `subtitles` 才表示可以预览和烧录字幕。若用双击方式启动程序，请在安装后完全退出并重新打开程序。

### Windows

1. 从 [FFmpeg 下载页](https://ffmpeg.org/download.html) 获取**完整构建版** FFmpeg，解压到固定位置，例如 `C:\ffmpeg`。必须使用包含 `libass` 的构建，否则无法预览或烧录字幕。
2. 将 `C:\ffmpeg\bin` 加入 Windows 的系统 `PATH`，重新打开 PowerShell 或重新登录系统。
3. 在项目目录打开 PowerShell，安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

4. 验证 FFmpeg：

```powershell
ffmpeg -hide_banner -filters | Select-String subtitles
```

输出中出现 `subtitles` 才表示可以预览和烧录字幕。

### Linux / 其他系统

安装包含 `libass` 的完整 FFmpeg 发行版并将其加入 `PATH`，然后执行 `python -m pip install -r requirements.txt`。可用 `ffmpeg -hide_banner -filters | grep subtitles` 验证。

随后双击或运行：

```powershell
python openai_whisper_transcribe_only_certain_time_intervals.py
```

将视频文件直接拖入窗口（也可点击选择文件），选好字幕保存位置后点击“开始提取字幕”。默认使用原项目的 `large-v2` 模型；第一次使用某个模型时，Whisper 会自动下载它。程序会在保存位置生成：

- `视频名_A.srt`：完整视频的第一次识别结果
- `视频名_B.srt`：A 未覆盖片段的补充识别结果
- `视频名_merged.srt`：最终合并字幕

识别会在后台进行，运行日志会显示在窗口下方，因此界面不会卡死。拖放功能由 `tkinterdnd2` 提供；该包已在 `requirements.txt` 中列出。

### 应用设置与完成提示

点击窗口右上角的“应用设置…”可开启或关闭任务成功后的提示音。软件默认播放项目内置的“敲敲来电”，也可改用系统提示音或自定义音频文件。macOS 支持常见音频格式；Windows 的自定义提示音请使用 `.wav`。同一页面还可调整界面字体大小、浅色/深色主题和主题色；设置会保存到用户目录，下次启动自动恢复。字幕样式预览、字幕处理、MP4 烧录和 MP4 下载成功后都会触发提示音。

“转写性能”默认是“平衡（界面优先）”，在 macOS 上会保留更多 CPU 给界面，减少点击卡顿；选择“性能优先”会使用更多 CPU 线程来缩短识别时间，但处理期间界面可能稍有迟滞。Windows 保持原有线程策略。终端运行默认使用性能优先，也可以用 `--cpu-thread-profile balanced` 改为平衡模式。

### GPU 高性能模式

处理设置中新增“GPU 高性能模式（NVIDIA CUDA）”，默认关闭，只作用于字幕 A、字幕 B 和完整 A+B 的 Whisper 识别，不影响字幕拆分、合并、清理、烧录或下载功能。关闭时保持原有设备选择逻辑；开启后会要求 CUDA 可用，并启用 FP16、TF32 和 cuDNN 高性能设置。运行日志会显示实际使用的显卡名称和 `GPU 高性能模式已启用`。

该模式需要 NVIDIA 显卡、兼容驱动以及 CUDA 版 PyTorch。Windows + Python 3.12 的依赖同时安装与 PyTorch 匹配的 `triton-windows`，用于加速 `word_timestamps=True` 所需的 median/DTW 时间轴内核；该轮子自带最小 CUDA 工具链，不要求另外安装完整 CUDA Toolkit。若当前环境只有 CPU 版 PyTorch，程序会在加载模型前给出错误说明，不会静默退回 CPU。命令行也可使用 `--gpu-acceleration` 开启。

### 仅生成字幕 A

选择 GUI 中的“仅生成字幕 A”模式并提供原视频。程序只执行完整视频的第一轮日语识别，输出 `视频名_A.srt`，不会生成 B 或合并字幕。

### 可取消与断点续传 A+B

“可取消/续传 A+B”是独立于原始“开始提取字幕”的新入口。它使用专用的 `_resumable_` 文件名，不会覆盖普通模式生成的 A、B 和合并字幕。字幕 A 会按 120 秒核心区间识别，并在分片前后各保留 30 秒重叠音频用于衔接复核；字幕 B 则按完整未覆盖 segment 保存。

运行期间按钮会变为“取消并保存断点”。点击后不会强制终止正在解码的 Whisper 调用，而是在当前完整 A 分片或 B segment 完成后，以原子方式写入临时 SRT 和 JSON 断点再停止。再次选择相同视频并点击该按钮时，可选择继续断点或放弃旧进度重新开始。续传要求视频文件、模型、Whisper 参数、合并设置和 B 音频筛选设置全部与断点一致；这可以避免把不同参数的识别结果错误拼接。任务全部完成后，断点与临时字幕会自动删除，保留 `_resumable_A.srt`、`_resumable_B.srt` 和 `_resumable_merged.srt`。

### Whisper 高级参数

点击 GUI 中的“第一/二轮 Whisper 高级参数…”，可分别编辑 A 和 B 的识别配置。窗口会为每个参数显示中文解释与推荐默认值。主界面处理设置区的“保存当前参数（下次启动使用）”会保存模型、GPU、Silero、烧录样式及两轮 Whisper 高级参数，下次启动时自动加载；不会保存视频、字幕、链接或输出路径。“恢复默认参数”只恢复当前界面，如需让默认值在以后启动时继续使用，再点击保存即可。温度可填写单个值，或填写逗号分隔的回退序列，例如 `0, 0.2, 0.4`。参数范围覆盖语言、任务、采样/束搜索、提示词、上下文、时间戳、静音和低置信度回退等本地 `Whisper.transcribe()` 识别选项。

### 参数横向对比

`parameter_sweep.py` 会提取指定时间范围的单声道 16 kHz 音频，并连续运行四组 A+B 参数：基线、关闭 A 前文、开启 B 前文、固定温度 0。每组的 A、B、合并字幕及 JSON 参数清单都以参数组名称保存，方便并排比较。

### 仅补全字幕 B

如果已经有一份翻译后的字幕 A，选择 GUI 中的“补全模式”。拖入原视频，并在“翻译字幕 A”处选择或拖入 `.srt` 文件。程序会读取 A 的时间轴，只对未覆盖的原视频片段进行日语识别，生成 `字幕A文件名_B.srt`。该模式不会修改 A，也不会重新识别 A 或生成合并字幕。

完整识别与补全模式默认不启用“Silero B 人声预筛”：此时会完整保留按字幕 A 时间轴反向剪裁出的所有 B 片段，与原始逻辑一致。勾选后，程序使用 Silero VAD 神经网络判断每个候选片段是否包含人声，再决定是否交给 Whisper；这取代了原来的音量预筛和 WebRTC“语音优先”。运行日志会显示每段检测到的人声时长、人声占比以及保留或跳过结果。

“人声概率阈值”默认 `0.4`，调低会更容易保留轻声、远处对白和强 BGM 下的对白；“最少累计人声”默认 `0.10` 秒；“最少人声占比”默认 `0%`，表示只按累计人声时长判断。Silero VAD 能判断是否像人声，但不能区分主播、游戏角色或背景中的其他说话者，因此本功能仍默认关闭。启用前请重新执行一次 `python -m pip install -r requirements.txt` 安装 `silero-vad`。

### 手动合并字幕 A 与 B

选择“合并字幕 A+B”模式，分别选择两份 `.srt` 字幕。没有重叠的字幕会自动保留；有时间轴重叠的部分会在新窗口中按冲突组并排显示。每组可选择保留 A 或 B，并可直接修改所选一侧的完整 SRT 时间轴和文字后再生成输出。输出文件名为 `字幕A名_字幕B名_merged.srt`，两份原字幕都不会修改。

### 清理可能的幻觉字幕

选择“清理可疑幻觉字幕”模式并提供 `.srt` 文件。程序会标记可能由识别产生的 BGM、片尾、感谢观看或订阅引导等文本，例如 `(♪ BGM)`、`(エンディング)`、`ご視聴ありがとうございました`。随后会打开审核窗口，逐项显示字幕时间、文本与前后字幕上下文；默认不删除，只有勾选确认的条目才会从新文件中移除。输出为 `原字幕名_cleaned.srt`，原字幕不会修改。

### 从中日双语字幕提取中文字幕

选择 GUI 中的“字幕拆分”模式，并拖入或选择中日双语 `.srt`。程序会保留每条字幕的第一行，生成 `原字幕文件名_zh.srt`；因此请确保中文翻译位于每条字幕的第一行。原字幕不会被修改。

### 统一中日双语字幕上下行顺序

选择“统一双语字幕行序”模式并提供中日双语 `.srt`，可自动统一为“中文在上、日文在下”或“日文在上、中文在下”，也可强制交换每条字幕的前两行。自动模式通过日语假名识别日文，只交换能够可靠判断的条目；两行语言无法判断时会保持原样并在日志和完成提示中报告数量。输出为 `原字幕文件名_ordered.srt`，单行字幕和原文件不会修改。

### 转换 MP4 并烧录字幕

选择“烧录字幕”模式，选择原视频和要烧录的 `.srt` 字幕。输入已是 MP4 时，程序会直接烧录字幕；其他格式会在生成最终文件时转换为兼容性较好的 H.264/AAC MP4。输出为 `视频名_burned_subtitles.mp4`。字幕会永久写入画面，无法在播放器中关闭；原视频和字幕文件不会修改。

烧录前可选择字体、字号、文字颜色、描边颜色、描边宽度和“距底部”位置。文字与描边颜色都可通过“调色盘…”直观选取，也可选择内置颜色或直接填写 `#RRGGBB`；默认使用微软雅黑、白色、16 号、黑色描边 0.8、距底部 10。距底部数值越大，字幕越向上移动。常用的六项样式可以命名保存为预设，之后从列表直接加载或删除；预设仅保存样式，不保存视频、字幕或输出路径。

点击“预览字幕样式”会从第一条字幕的位置生成一张预览图，不会修改视频。预览窗口中的“刷新”会按当前样式随机跳到后面 5–10 条字幕并重新渲染一帧，方便检查不同对白和画面上的效果；若某种字体仍显示异常，请从下拉列表换用 `Noto Sans CJK SC`、`SimHei`、`Meiryo` 或输入电脑上已安装的字体名称后再预览。

### 从链接下载 MP4

选择“下载 MP4”模式，输入视频链接并选择保存文件夹。程序会优先选择 H.264/AAC 的 MP4，并在网络短暂中断时最多重试 10 次；同时下载视频封面并转换为与视频同名的 JPG 图片。下载日志会显示在窗口底部。

YouTube 目前会要求 `yt-dlp` 使用 JavaScript 运行时。安装依赖时，`yt-dlp[default]` 会同时安装 EJS 解题脚本；还需要在系统 `PATH` 中安装 [Deno 2.3+](https://docs.deno.com/runtime/getting_started/installation/)（推荐）或 [Node.js 22+](https://nodejs.org/en/download/)。程序启动下载时会自动检测并启用可用运行时。

`yt-dlp` 需要随 YouTube 的变更保持更新；尤其是出现下载错误时，请在项目目录运行：

```powershell
python -m pip install --upgrade "yt-dlp[default]"
```

若日志出现 HTTP 429 或“Sign in to confirm you’re not a bot”，请先在同一台电脑、同一网络的 Chrome、Edge、Firefox、Brave 或 Safari 中登录 YouTube；若出现验证码也先完成验证。然后在下载界面的“登录 Cookie”选择该浏览器并重试。程序仅让 `yt-dlp` 临时读取本机 Cookie，不会导出或保存它们；请不要把 Cookie 文件或浏览器配置文件分享给他人。

## 终端运行（可选）

```powershell
python openai_whisper_transcribe_only_certain_time_intervals.py "<视频文件路径>" --output-dir "<字幕保存文件夹>"
```
