"""Desktop GUI for the two-pass Japanese Whisper subtitle workflow."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from queue import Empty, Queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from subtitle_pipeline import build_output_paths, run_two_pass_transcription

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # The rest of the GUI is still useful without drag/drop.
    DND_FILES = None
    TkinterDnD = None


VIDEO_FILE_TYPES = [
    ("视频或音频", "*.mp4 *.mkv *.avi *.mov *.webm *.m4v *.mp3 *.wav *.flac *.m4a"),
    ("所有文件", "*.*"),
]


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
        self.output_dir = tk.StringVar()
        self.model_name = tk.StringVar(value="large-v2")
        self.merge_gap = tk.StringVar(value="1.0")
        self.duplicate_threshold = tk.StringVar(value="0.5")
        self.output_preview = tk.StringVar(value="请先选择视频文件。")

        self._configure_style()
        self._build()
        self.root.after(120, self._consume_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Hint.TLabel", foreground="#5b6472")
        style.configure("Drop.TLabel", anchor="center", padding=22, relief="solid")

    def _build(self) -> None:
        ttk.Label(self.root, text="日语字幕提取器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.root,
            text="自动执行：完整识别 A → 补全未识别片段 B → 合并去重",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(3, 16))

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

        video_row = ttk.Frame(self.root)
        video_row.pack(fill="x", pady=(14, 7))
        ttk.Label(video_row, text="视频文件", width=10).pack(side="left")
        self.video_entry = ttk.Entry(video_row, textvariable=self.video_path)
        self.video_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.video_button = ttk.Button(video_row, text="选择视频", command=self._choose_video)
        self.video_button.pack(side="left")

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

    def _choose_video(self) -> None:
        path = filedialog.askopenfilename(title="选择视频或音频文件", filetypes=VIDEO_FILE_TYPES)
        if path:
            self._set_video(path)

    def _on_drop(self, event) -> None:
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self._set_video(paths[0])

    def _set_video(self, path: str) -> None:
        video = Path(path).expanduser()
        if not video.is_file():
            messagebox.showerror("无法读取文件", f"找不到文件：\n{video}")
            return
        self.video_path.set(str(video.resolve()))
        self.output_dir.set(str(video.parent.resolve()))
        self._update_preview()
        self.status.set("已选择视频，可以开始。")

    def _choose_output_dir(self) -> None:
        initial = self.output_dir.get() or str(Path.cwd())
        path = filedialog.askdirectory(title="选择字幕保存文件夹", initialdir=initial)
        if path:
            self.output_dir.set(path)
            self._update_preview()

    def _update_preview(self) -> None:
        if not self.video_path.get() or not self.output_dir.get():
            self.output_preview.set("请先选择视频文件。")
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
        output = self.output_dir.get().strip()
        if not video:
            messagebox.showwarning("请选择视频", "请拖入视频文件，或点击“选择视频”。")
            return
        if not output:
            messagebox.showwarning("请选择保存位置", "请选择字幕保存文件夹。")
            return
        try:
            merge_gap = float(self.merge_gap.get())
            duplicate_threshold = float(self.duplicate_threshold.get())
            if merge_gap < 0 or duplicate_threshold < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("设置不正确", "合并间隔和去重阈值必须是大于或等于 0 的数字。")
            return

        outputs = build_output_paths(video, output)
        existing = [path.name for path in (outputs.first_pass, outputs.second_pass, outputs.merged) if path.exists()]
        if existing and not messagebox.askyesno(
            "确认覆盖", "以下文件已存在，继续会覆盖它们：\n\n" + "\n".join(existing)
        ):
            return

        self.running = True
        self.start_button.configure(state="disabled")
        self.status.set("正在识别，请保持此窗口打开…")
        self._append_log("=" * 54)
        self._append_log(f"开始处理：{video}")
        worker = threading.Thread(
            target=self._run_worker,
            args=(video, output, self.model_name.get(), merge_gap, duplicate_threshold),
            daemon=True,
        )
        worker.start()

    def _run_worker(
        self,
        video: str,
        output: str,
        model_name: str,
        merge_gap: float,
        duplicate_threshold: float,
    ) -> None:
        writer = _QueueWriter(self.events)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                outputs = run_two_pass_transcription(
                    video,
                    output,
                    model_name=model_name,
                    merge_gap=merge_gap,
                    duplicate_threshold=duplicate_threshold,
                    log_callback=lambda message: self.events.put(("log", message)),
                )
            self.events.put(("success", outputs))
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
                    outputs = payload
                    self.status.set("处理完成。")
                    self._append_log("全部完成。")
                    messagebox.showinfo("字幕已生成", f"合并字幕已保存到：\n{outputs.merged}")
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
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    SubtitleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
