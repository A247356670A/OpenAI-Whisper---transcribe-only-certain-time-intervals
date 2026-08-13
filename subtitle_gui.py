"""Desktop GUI for the two-pass Japanese Whisper subtitle workflow."""

from __future__ import annotations

import contextlib
import ctypes
import os
from pathlib import Path
from queue import Empty, Queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from subtitle_pipeline import (
    build_output_paths,
    build_chinese_only_path,
    build_burned_video_path,
    build_second_pass_path,
    burn_subtitles_to_mp4,
    extract_chinese_subtitles,
    run_first_pass_transcription,
    run_second_pass_from_subtitle,
    run_two_pass_transcription,
)
from whisper_options import WHISPER_OPTION_SPECS, default_option_values

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # The rest of the GUI is still useful without drag/drop.
    DND_FILES = None
    TkinterDnD = None


VIDEO_FILE_TYPES = [
    ("视频或音频", "*.mp4 *.mkv *.avi *.mov *.webm *.m4v *.mp3 *.wav *.flac *.m4a"),
    ("所有文件", "*.*"),
]


def enable_high_dpi_awareness() -> None:
    """Ask Windows to render the Tk window at the monitor's native DPI."""
    if not sys.platform.startswith("win"):
        return
    try:
        # Windows 10 1703+: Per-monitor V2 gives the sharpest result when a
        # window is moved between displays using different scale factors.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            # Compatible fallback for older Windows releases.
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass


class _QueueWriter:
    """Expose legacy helper-module print output in the GUI log panel."""

    def __init__(self, queue: Queue[tuple[str, object]]):
        self.queue = queue

    def write(self, text: str) -> int:
        text = text.strip()
        if text:
            self.queue.put(("log", text))
        return len(text)

    def flush(self) -> None:
        pass


class WhisperOptionsDialog:
    """Scrollable two-tab editor for independent A/B Whisper options."""

    def __init__(
        self,
        parent: tk.Tk,
        first_values: dict[str, tk.StringVar],
        second_values: dict[str, tk.StringVar],
    ):
        self.window = tk.Toplevel(parent)
        self.window.title("Whisper 高级参数（第一轮 A / 第二轮 B）")
        self.window.geometry("1420x920")
        self.window.minsize(1060, 700)
        self.window.transient(parent)
        self.window.configure(padx=16, pady=14)

        ttk.Label(
            self.window,
            text="两轮参数彼此独立。每项说明均显示在右侧；恢复默认只影响当前标签页。",
            style="Hint.TLabel",
            wraplength=1320,
        ).pack(anchor="w", pady=(0, 10))
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill="both", expand=True)
        self._build_tab(notebook, "第一轮 A（完整视频）", "first", first_values)
        self._build_tab(notebook, "第二轮 B（补全片段）", "second", second_values)

        buttons = ttk.Frame(self.window)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="关闭并保存设置", command=self.window.destroy).pack(side="right")

    def _build_tab(
        self,
        notebook: ttk.Notebook,
        title: str,
        pass_name: str,
        values: dict[str, tk.StringVar],
    ) -> None:
        page = ttk.Frame(notebook, padding=8)
        notebook.add(page, text=title)
        canvas = tk.Canvas(page, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        content.columnconfigure(1, weight=1)
        content.columnconfigure(2, weight=3)
        ttk.Label(content, text="参数", style="Hint.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(content, text="值", style="Hint.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Label(content, text="说明", style="Hint.TLabel").grid(row=0, column=2, sticky="w")

        for row, spec in enumerate(WHISPER_OPTION_SPECS, start=1):
            ttk.Label(content, text=f"{spec.label}\n{spec.key}", justify="left").grid(
                row=row, column=0, sticky="nw", padx=(0, 10), pady=7
            )
            if spec.choices:
                editor = ttk.Combobox(
                    content,
                    textvariable=values[spec.key],
                    values=spec.choices,
                    state="readonly",
                    width=26,
                )
            else:
                editor = ttk.Entry(content, textvariable=values[spec.key], width=34)
            editor.grid(row=row, column=1, sticky="ew", padx=(0, 14), pady=7)
            ttk.Label(
                content,
                text=spec.description,
                style="Hint.TLabel",
                justify="left",
                wraplength=700,
            ).grid(row=row, column=2, sticky="nw", pady=7)

        reset = ttk.Button(
            content,
            text="恢复本轮推荐默认值",
            command=lambda: self._reset_values(pass_name, values),
        )
        reset.grid(row=len(WHISPER_OPTION_SPECS) + 1, column=0, columnspan=2, sticky="w", pady=(12, 8))

        def refresh_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content_width(event) -> None:
            canvas.itemconfigure(content_window, width=event.width)

        content.bind("<Configure>", refresh_scroll_region)
        canvas.bind("<Configure>", fit_content_width)

    @staticmethod
    def _reset_values(pass_name: str, values: dict[str, tk.StringVar]) -> None:
        for key, value in default_option_values(pass_name).items():
            values[key].set(value)


class SubtitleApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("日语字幕提取器 · Whisper 双重识别")
        self.root.geometry("1280x900")
        self.root.minsize(1280, 900)
        self.root.configure(padx=24, pady=20)

        self.events: Queue[tuple[str, object]] = Queue()
        self.running = False
        self.video_path = tk.StringVar()
        self.subtitle_a_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.run_mode = tk.StringVar(value="full")
        self.model_name = tk.StringVar(value="large-v2")
        self.merge_gap = tk.StringVar(value="1.0")
        self.duplicate_threshold = tk.StringVar(value="0.5")
        self.output_preview = tk.StringVar(value="请先选择视频文件。")
        self.first_whisper_values = {
            key: tk.StringVar(value=value)
            for key, value in default_option_values("first").items()
        }
        self.second_whisper_values = {
            key: tk.StringVar(value=value)
            for key, value in default_option_values("second").items()
        }

        self._configure_style()
        self._build()
        self.root.after(120, self._consume_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        # Tk's default font can look soft on scaled Windows displays.  Use the
        # ClearType-aware UI font consistently for labels, buttons and inputs.
        for font_name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
        ):
            try:
                tkfont.nametofont(font_name).configure(
                    family="Microsoft YaHei UI", size=17
                )
            except tk.TclError:
                pass
        try:
            tkfont.nametofont("TkFixedFont").configure(
                family="Consolas", size=17
            )
        except tk.TclError:
            pass

        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 26, "bold"))
        style.configure("Hint.TLabel", foreground="#5b6472")
        style.configure("Drop.TLabel", anchor="center", padding=22, relief="solid")

    def _build(self) -> None:
        ttk.Label(self.root, text="日语字幕提取器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.root,
            text="完整模式：识别 A → 补全 B → 合并；补全模式：使用已有翻译 A，只生成 B",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(3, 16))

        mode_frame = ttk.LabelFrame(self.root, text="运行模式", padding=8)
        mode_frame.pack(fill="x", pady=(0, 12))
        ttk.Radiobutton(
            mode_frame,
            text="完整识别：自动生成 A、B 和合并字幕",
            value="full",
            variable=self.run_mode,
            command=self._on_mode_changed,
        ).pack(anchor="w")
        ttk.Radiobutton(
            mode_frame,
            text="仅生成字幕 A：只进行完整视频的第一轮日语识别",
            value="first_only",
            variable=self.run_mode,
            command=self._on_mode_changed,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(
            mode_frame,
            text="补全模式：提供翻译字幕 A，仅生成日语字幕 B",
            value="second_only",
            variable=self.run_mode,
            command=self._on_mode_changed,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(
            mode_frame,
            text="字幕拆分：中日双语字幕 → 仅中文字幕",
            value="split_chinese",
            variable=self.run_mode,
            command=self._on_mode_changed,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(
            mode_frame,
            text="烧录字幕：转换为 MP4 并把选定 SRT 永久写入画面",
            value="burn_subtitles",
            variable=self.run_mode,
            command=self._on_mode_changed,
        ).pack(anchor="w", pady=(4, 0))

        self.drop_zone = ttk.Label(
            self.root,
            text="将视频拖到这里\n或点击“选择视频”",
            style="Drop.TLabel",
        )
        self.drop_zone.pack(fill="x")
        self.drop_zone.bind("<Button-1>", lambda _event: self._choose_video())
        if TkinterDnD is not None:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)
        else:
            ttk.Label(
                self.root,
                text="提示：安装 requirements.txt 中的 tkinterdnd2 后可使用拖放；当前仍可点击选择文件。",
                style="Hint.TLabel",
                wraplength=700,
            ).pack(anchor="w", pady=(5, 0))

        self.video_row = ttk.Frame(self.root)
        self.video_row.pack(fill="x", pady=(14, 7))
        ttk.Label(self.video_row, text="视频文件", width=10).pack(side="left")
        self.video_entry = ttk.Entry(self.video_row, textvariable=self.video_path)
        self.video_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.video_button = ttk.Button(self.video_row, text="选择视频", command=self._choose_video)
        self.video_button.pack(side="left")

        self.subtitle_row = ttk.Frame(self.root)
        self.subtitle_label = ttk.Label(self.subtitle_row, text="翻译字幕 A", width=10)
        self.subtitle_label.pack(side="left")
        self.subtitle_entry = ttk.Entry(
            self.subtitle_row, textvariable=self.subtitle_a_path
        )
        self.subtitle_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.subtitle_button = ttk.Button(
            self.subtitle_row, text="选择 SRT", command=self._choose_subtitle_a
        )
        self.subtitle_button.pack(side="left")
        if TkinterDnD is not None:
            self.subtitle_entry.drop_target_register(DND_FILES)
            self.subtitle_entry.dnd_bind("<<Drop>>", self._on_subtitle_drop)

        output_row = ttk.Frame(self.root)
        output_row.pack(fill="x", pady=7)
        ttk.Label(output_row, text="保存位置", width=10).pack(side="left")
        self.output_entry = ttk.Entry(output_row, textvariable=self.output_dir)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.output_button = ttk.Button(output_row, text="选择文件夹", command=self._choose_output_dir)
        self.output_button.pack(side="left")

        options = ttk.LabelFrame(self.root, text="识别设置（默认值沿用原项目）", padding=10)
        options.pack(fill="x", pady=(10, 7))
        ttk.Label(options, text="Whisper 模型").grid(row=0, column=0, sticky="w")
        self.model_box = ttk.Combobox(
            options,
            state="readonly",
            textvariable=self.model_name,
            values=("tiny", "base", "small", "medium", "large-v2", "large-v3"),
            width=14,
        )
        self.model_box.grid(row=0, column=1, sticky="w", padx=(8, 26))
        ttk.Label(options, text="合并间隔（秒）").grid(row=0, column=2, sticky="w")
        self.gap_entry = ttk.Entry(options, textvariable=self.merge_gap, width=8)
        self.gap_entry.grid(row=0, column=3, sticky="w", padx=(8, 26))
        ttk.Label(options, text="去重阈值（秒）").grid(row=0, column=4, sticky="w")
        self.threshold_entry = ttk.Entry(options, textvariable=self.duplicate_threshold, width=8)
        self.threshold_entry.grid(row=0, column=5, sticky="w", padx=(8, 0))
        ttk.Button(
            options,
            text="第一/二轮 Whisper 高级参数…",
            command=self._show_whisper_options,
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(12, 0))

        preview = ttk.LabelFrame(self.root, text="将生成的文件", padding=9)
        preview.pack(fill="x", pady=(7, 10))
        ttk.Label(
            preview,
            textvariable=self.output_preview,
            justify="left",
            style="Hint.TLabel",
            wraplength=700,
        ).pack(anchor="w")

        button_row = ttk.Frame(self.root)
        button_row.pack(fill="x", pady=(0, 9))
        self.start_button = ttk.Button(button_row, text="开始提取字幕", command=self._start)
        self.start_button.pack(side="left")
        self.open_button = ttk.Button(
            button_row, text="打开保存文件夹", command=self._open_output_directory
        )
        self.open_button.pack(side="left", padx=8)
        self.status = tk.StringVar(value="等待选择视频文件。")
        ttk.Label(button_row, textvariable=self.status, style="Hint.TLabel").pack(
            side="right"
        )

        log_box = ttk.LabelFrame(self.root, text="运行日志", padding=7)
        log_box.pack(fill="both", expand=True)
        self.log = tk.Text(log_box, height=12, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(log_box, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _show_whisper_options(self) -> None:
        WhisperOptionsDialog(
            self.root, self.first_whisper_values, self.second_whisper_values
        )

    def _on_mode_changed(self) -> None:
        mode = self.run_mode.get()
        if mode == "second_only":
            self.video_row.pack(fill="x", pady=(14, 7), after=self.drop_zone)
            self.subtitle_label.configure(text="翻译字幕 A")
            self.subtitle_button.configure(text="选择 SRT")
            self.subtitle_row.pack(fill="x", pady=7, after=self.video_row)
            self.drop_zone.configure(text="将视频拖到这里\n补全模式还需要在下方选择或拖入翻译字幕 A")
            self.threshold_entry.configure(state="disabled")
        elif mode == "burn_subtitles":
            self.video_row.pack(fill="x", pady=(14, 7), after=self.drop_zone)
            self.subtitle_label.configure(text="烧录字幕")
            self.subtitle_button.configure(text="选择 SRT")
            self.subtitle_row.pack(fill="x", pady=7, after=self.video_row)
            self.drop_zone.configure(text="将视频拖到这里\n然后在下方选择或拖入要烧录的 SRT 字幕")
            self.threshold_entry.configure(state="disabled")
        elif mode == "split_chinese":
            self.video_row.pack_forget()
            self.subtitle_label.configure(text="中日双语字幕")
            self.subtitle_button.configure(text="选择 SRT")
            self.subtitle_row.pack(fill="x", pady=(14, 7), after=self.drop_zone)
            self.drop_zone.configure(text="将中日双语 SRT 拖到这里\n或在下方点击“选择 SRT”")
            self.threshold_entry.configure(state="disabled")
        else:
            self.subtitle_row.pack_forget()
            self.video_row.pack(fill="x", pady=(14, 7), after=self.drop_zone)
            if mode == "first_only":
                self.drop_zone.configure(text="将视频拖到这里\n仅生成第一轮字幕 A")
                self.threshold_entry.configure(state="disabled")
            else:
                self.drop_zone.configure(text="将视频拖到这里\n或点击“选择视频”")
                self.threshold_entry.configure(state="normal")
        self._update_preview()

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(title="选择视频或音频文件", filetypes=VIDEO_FILE_TYPES)
        if path:
            self._set_video(path)

    def _on_drop(self, event) -> None:
        paths = self.root.tk.splitlist(event.data)
        if paths:
            if self.run_mode.get() == "split_chinese":
                self._set_subtitle_a(paths[0])
            else:
                self._set_video(paths[0])

    def _on_subtitle_drop(self, event) -> None:
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self._set_subtitle_a(paths[0])

    def _set_video(self, path: str) -> None:
        video = Path(path).expanduser()
        if not video.is_file():
            messagebox.showerror("无法读取文件", f"找不到文件：\n{video}")
            return
        self.video_path.set(str(video.resolve()))
        self.output_dir.set(str(video.parent.resolve()))
        self._update_preview()
        self.status.set("已选择视频，可以开始。")

    def _choose_subtitle_a(self) -> None:
        path = filedialog.askopenfilename(
            title="选择已翻译的字幕 A",
            filetypes=[("SRT 字幕", "*.srt"), ("所有文件", "*.*")],
        )
        if path:
            self._set_subtitle_a(path)

    def _set_subtitle_a(self, path: str) -> None:
        subtitle = Path(path).expanduser()
        if not subtitle.is_file() or subtitle.suffix.lower() != ".srt":
            messagebox.showerror("无法读取字幕", "请选择一个有效的 .srt 字幕文件。")
            return
        self.subtitle_a_path.set(str(subtitle.resolve()))
        if self.run_mode.get() == "split_chinese" and not self.output_dir.get():
            self.output_dir.set(str(subtitle.parent.resolve()))
        self._update_preview()

    def _choose_output_dir(self) -> None:
        initial = self.output_dir.get() or str(Path.cwd())
        path = filedialog.askdirectory(title="选择字幕保存文件夹", initialdir=initial)
        if path:
            self.output_dir.set(path)
            self._update_preview()

    def _update_preview(self) -> None:
        mode = self.run_mode.get()
        if mode == "split_chinese":
            if not self.subtitle_a_path.get():
                self.output_preview.set("字幕拆分模式：请选择中日双语字幕文件。")
                return
            output_dir = self.output_dir.get() or str(Path(self.subtitle_a_path.get()).parent)
            chinese_only = build_chinese_only_path(self.subtitle_a_path.get(), output_dir)
            self.output_preview.set(
                f"原中日双语字幕（不会修改）：{Path(self.subtitle_a_path.get()).name}\n"
                f"仅中文字幕输出：{chinese_only.name}\n"
                "保留每条字幕的第一行，请确认中文位于第一行。"
            )
            return
        if not self.video_path.get() or not self.output_dir.get():
            self.output_preview.set("请先选择视频文件。")
            return
        if mode == "second_only":
            if not self.subtitle_a_path.get():
                self.output_preview.set("补全模式：请在下方选择已翻译的字幕 A。")
                return
            second_pass = build_second_pass_path(
                self.subtitle_a_path.get(), self.output_dir.get()
            )
            self.output_preview.set(
                f"已有翻译字幕 A（不会修改）：{Path(self.subtitle_a_path.get()).name}\n"
                f"仅生成日语补全字幕 B：{second_pass.name}\n"
                "本模式不会重新识别 A，也不会合并字幕。"
            )
            return
        if mode == "burn_subtitles":
            if not self.subtitle_a_path.get():
                self.output_preview.set("烧录字幕模式：请选择要写入画面的 .srt 字幕。")
                return
            burned_video = build_burned_video_path(
                self.video_path.get(), self.output_dir.get()
            )
            self.output_preview.set(
                f"原视频（不会修改）：{Path(self.video_path.get()).name}\n"
                f"烧录字幕（不会修改）：{Path(self.subtitle_a_path.get()).name}\n"
                f"输出 MP4（字幕永久写入画面）：{burned_video.name}"
            )
            return
        if mode == "first_only":
            first_pass = build_output_paths(
                self.video_path.get(), self.output_dir.get()
            ).first_pass
            self.output_preview.set(
                f"仅生成完整视频的第一轮日语字幕 A：{first_pass.name}\n"
                "本模式不会生成字幕 B，也不会合并字幕。"
            )
            return
        outputs = build_output_paths(self.video_path.get(), self.output_dir.get())
        self.output_preview.set(
            f"A（完整识别）：{outputs.first_pass.name}\n"
            f"B（补全片段）：{outputs.second_pass.name}\n"
            f"合并结果：{outputs.merged.name}"
        )

    def _start(self) -> None:
        if self.running:
            return
        video = self.video_path.get().strip()
        subtitle_a = self.subtitle_a_path.get().strip()
        output = self.output_dir.get().strip()
        mode = self.run_mode.get()
        if mode != "split_chinese" and not video:
            messagebox.showwarning("请选择视频", "请拖入视频文件，或点击“选择视频”。")
            return
        if not output and mode != "split_chinese":
            messagebox.showwarning("请选择保存位置", "请选择字幕保存文件夹。")
            return
        if mode in ("second_only", "split_chinese", "burn_subtitles") and not subtitle_a:
            required_name = {
                "split_chinese": "中日双语字幕",
                "second_only": "翻译字幕 A",
                "burn_subtitles": "要烧录的字幕",
            }[mode]
            messagebox.showwarning("请选择字幕", f"请选择{required_name}（.srt）。")
            return
        if mode == "split_chinese" and not output:
            output = str(Path(subtitle_a).parent)
            self.output_dir.set(output)
        if mode in ("split_chinese", "burn_subtitles"):
            merge_gap, duplicate_threshold = 1.0, 0.5
        else:
            try:
                merge_gap = float(self.merge_gap.get())
                duplicate_threshold = float(self.duplicate_threshold.get())
                if merge_gap < 0 or duplicate_threshold < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("设置不正确", "合并间隔和去重阈值必须是大于或等于 0 的数字。")
                return

        if mode == "split_chinese":
            split_output = build_chinese_only_path(subtitle_a, output)
            existing = [split_output.name] if split_output.exists() else []
        elif mode == "burn_subtitles":
            burned_video = build_burned_video_path(video, output)
            existing = [burned_video.name] if burned_video.exists() else []
        elif mode == "second_only":
            existing = [
                build_second_pass_path(subtitle_a, output).name
                if build_second_pass_path(subtitle_a, output).exists()
                else ""
            ]
        elif mode == "first_only":
            first_pass = build_output_paths(video, output).first_pass
            existing = [first_pass.name] if first_pass.exists() else []
        else:
            outputs = build_output_paths(video, output)
            existing = [
                path.name
                for path in (outputs.first_pass, outputs.second_pass, outputs.merged)
                if path.exists()
            ]
        existing = [name for name in existing if name]
        if existing and not messagebox.askyesno(
            "确认覆盖", "以下文件已存在，继续会覆盖它们：\n\n" + "\n".join(existing)
        ):
            return

        self.running = True
        self.start_button.configure(state="disabled")
        self.status.set("正在识别，请保持此窗口打开…")
        self._append_log("=" * 54)
        action = {
            "full": "完整识别",
            "first_only": "仅生成 A",
            "second_only": "仅生成 B",
            "split_chinese": "提取中文字幕",
            "burn_subtitles": "转换 MP4 并烧录字幕",
        }[mode]
        self._append_log(f"开始处理（{action}）：{video}")
        worker = threading.Thread(
            target=self._run_worker,
            args=(
                mode,
                video,
                subtitle_a,
                output,
                self.model_name.get(),
                merge_gap,
                duplicate_threshold,
                self._snapshot_whisper_values(self.first_whisper_values),
                self._snapshot_whisper_values(self.second_whisper_values),
            ),
            daemon=True,
        )
        worker.start()

    @staticmethod
    def _snapshot_whisper_values(values: dict[str, tk.StringVar]) -> dict[str, str]:
        """Freeze editable Tk variables before the background thread starts."""
        return {key: value.get() for key, value in values.items()}

    def _run_worker(
        self,
        mode: str,
        video: str,
        subtitle_a: str,
        output: str,
        model_name: str,
        merge_gap: float,
        duplicate_threshold: float,
        first_whisper_values: dict[str, str],
        second_whisper_values: dict[str, str],
    ) -> None:
        writer = _QueueWriter(self.events)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                if mode == "second_only":
                    result = run_second_pass_from_subtitle(
                        video,
                        subtitle_a,
                        output,
                        model_name=model_name,
                        merge_gap=merge_gap,
                        second_whisper_values=second_whisper_values,
                        log_callback=lambda message: self.events.put(("log", message)),
                    )
                elif mode == "first_only":
                    result = run_first_pass_transcription(
                        video,
                        output,
                        model_name=model_name,
                        first_whisper_values=first_whisper_values,
                        log_callback=lambda message: self.events.put(("log", message)),
                    )
                elif mode == "split_chinese":
                    result = extract_chinese_subtitles(
                        subtitle_a,
                        output,
                        log_callback=lambda message: self.events.put(("log", message)),
                    )
                elif mode == "burn_subtitles":
                    result = burn_subtitles_to_mp4(
                        video,
                        subtitle_a,
                        output,
                        log_callback=lambda message: self.events.put(("log", message)),
                    )
                else:
                    result = run_two_pass_transcription(
                        video,
                        output,
                        model_name=model_name,
                        merge_gap=merge_gap,
                        duplicate_threshold=duplicate_threshold,
                        first_whisper_values=first_whisper_values,
                        second_whisper_values=second_whisper_values,
                        log_callback=lambda message: self.events.put(("log", message)),
                    )
            self.events.put(("success", (mode, result)))
        except Exception as exc:  # Display full details in log, a concise dialog to the user.
            self.events.put(("error", str(exc)))

    def _consume_events(self) -> None:
        try:
            while True:
                event_type, payload = self.events.get_nowait()
                if event_type == "log":
                    self._append_log(str(payload))
                elif event_type == "success":
                    self.running = False
                    self.start_button.configure(state="normal")
                    mode, result = payload
                    self.status.set("处理完成。")
                    self._append_log("全部完成。")
                    if mode == "second_only":
                        messagebox.showinfo(
                            "字幕 B 已生成", f"日语补全字幕 B 已保存到：\n{result.second_pass}"
                        )
                    elif mode == "first_only":
                        messagebox.showinfo(
                            "字幕 A 已生成", f"第一轮日语字幕 A 已保存到：\n{result.first_pass}"
                        )
                    elif mode == "split_chinese":
                        messagebox.showinfo(
                            "中文字幕已提取",
                            f"仅中文字幕已保存到：\n{result.chinese_only}",
                        )
                    elif mode == "burn_subtitles":
                        messagebox.showinfo(
                            "MP4 已生成",
                            f"字幕已永久烧录到画面：\n{result.burned_video}",
                        )
                    else:
                        messagebox.showinfo(
                            "字幕已生成", f"合并字幕已保存到：\n{result.merged}"
                        )
                elif event_type == "error":
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.status.set("处理失败，请查看运行日志。")
                    self._append_log(f"错误：{payload}")
                    messagebox.showerror("处理失败", str(payload))
        except Empty:
            pass
        self.root.after(120, self._consume_events)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _open_output_directory(self) -> None:
        destination = Path(self.output_dir.get() or Path.cwd())
        if not destination.exists():
            messagebox.showwarning("文件夹不存在", "请先选择一个有效的保存位置。")
            return
        if sys.platform.startswith("win"):
            os.startfile(destination)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", str(destination)], check=False)
        else:
            import subprocess
            subprocess.run(["xdg-open", str(destination)], check=False)


def main() -> None:
    enable_high_dpi_awareness()
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    SubtitleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
