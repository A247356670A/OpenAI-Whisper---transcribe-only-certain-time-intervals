"""Human annotations with an embedded, unchanged SRT for later precise editing."""

import hashlib
import json
from pathlib import Path
import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText


def _parse_cues(source):
    """Parse without the project's merge parser, which flattens bilingual lines."""
    normalized = source.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if not normalized.strip():
        raise ValueError("字幕文件为空，没有可以校对的字幕。")
    cues = []
    # Translation tools sometimes insert blank lines inside bilingual cues.
    # Only a timestamp starts a cue; preserve intervening text and blank lines.
    timestamp = r"\d{1,}:\d{2}:\d{2}[,.]\d{1,3}"
    timing_pattern = re.compile(
        rf"[^\S\n]*(?:(?P<number>\d+)[^\S\n]+)?"
        rf"(?P<timing>{timestamp}[^\S\n]*-->[^\S\n]*{timestamp})"
        r"(?P<tail>[^\n]*)"
    )
    lines = normalized.split("\n")
    headers = []

    def invalid(index):
        raise ValueError(
            f"字幕已成功解码，但第 {index + 1} 行附近格式无法解析（不是 UTF-8 编码问题）。\n"
            f"内容：{lines[index][:160]}\n"
            "请检查是否缺失或损坏时间轴，例如 00:00:01,000 --> 00:00:02,000。"
        )

    for index, line in enumerate(lines):
        match = timing_pattern.fullmatch(line)
        if match:
            # An immediately preceding integer is the explicit SRT cue number.
            inline_number = match["number"]
            has_number = not inline_number and index > 0 and re.fullmatch(r"\s*\d+\s*", lines[index - 1])
            start = index - 1 if has_number else index
            number = inline_number or (lines[index - 1].strip() if has_number else str(len(headers) + 1))
            timing, tail = match["timing"], match["tail"]
            inline_text = tail.lstrip()
            # SRT position metadata belongs to the timeline, not the dialogue.
            # Preserve it as before, but treat other trailing text as a first
            # dialogue line (some translators collapse number/time/text).
            if not inline_text or re.fullmatch(r"(?:\s*[XY][12]:\s*-?\d+)+\s*", tail):
                timing += tail
                inline_text = ""
            headers.append((start, index, number, timing, inline_text))
        elif "-->" in line:
            # Do not silently swallow a damaged timeline as subtitle text.
            invalid(index)
    if not headers:
        invalid(next(i for i, line in enumerate(lines) if line.strip()))
    for index in range(headers[0][0]):
        if lines[index].strip():
            invalid(index)
    for position, (_start, time_index, number, timing, inline_text) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        text_lines = lines[time_index + 1:end]
        if inline_text:
            text_lines.insert(0, inline_text)
        # Strip separating blank lines, never blank lines between dialogue lines.
        while text_lines and not text_lines[-1].strip():
            text_lines.pop()
        cues.append(dict(number=number, timing=timing, text="\n".join(text_lines)))
    return cues


def create_review(path):
    """Retain exact source text, cue numbers, line breaks and timestamp strings."""
    path = Path(path)
    raw = path.read_bytes()
    # UTF-16 is unambiguous only with a BOM. Never guess a legacy encoding
    # silently, since that can corrupt Chinese/Japanese names in the review.
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        source = raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"无法按 {encoding} 解码字幕：字节位置 {exc.start} 附近存在无效编码。"
            "请在文本编辑器中使用“另存为 UTF-8”，而不是仅修改文件扩展名。"
        ) from exc
    cues = _parse_cues(source)
    return dict(format="subtitle-proofreading", version=1, source_name=path.name,
                source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                source_srt=source, cues=cues, annotations=[])


def load_review(path):
    """Reject inconsistent annotation offsets or altered embedded source data."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != "subtitle-proofreading" or data.get("version") != 1:
        raise ValueError("不是支持的字幕校对文件。")
    if hashlib.sha256(data["source_srt"].encode("utf-8")).hexdigest() != data["source_sha256"]:
        raise ValueError("校对文件中的原字幕校验失败。")
    if data["cues"] != _parse_cues(data["source_srt"]):
        raise ValueError("字幕条目与内嵌原字幕不一致。")
    for note in data["annotations"]:
        if not 0 <= note["cue"] < len(data["cues"]):
            raise ValueError("校对标记的字幕序号无效。")
        cue = data["cues"][note["cue"]]
        start, end = note["start"], note["end"]
        if not 0 <= start <= end <= len(cue["text"]) or cue["text"][start:end] != note["quote"]:
            raise ValueError("校对标记与原字幕不一致。")
        if not all(isinstance(note[key], str) for key in ("language", "replacement", "comment")):
            raise ValueError("校对评论格式无效。")
    return data


def save_review(data, path):
    """Save the portable project atomically; it contains no local absolute paths."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def review_report(data):
    """Readable companion report containing annotated cues and adjacent context."""
    lines = ["# 字幕人工校对意见", "", f"原文件：{data['source_name']}",
             f"原字幕校验：{data['source_sha256']}", "",
             "仅标记问题与建议；请结合附带 JSON 的完整原字幕精校，保留时间轴。", ""]
    for number, note in enumerate(data["annotations"], 1):
        index = note["cue"]
        cue = data["cues"][index]
        lines += [f"## 标记 {number} · 字幕 {cue['number']} · {cue['timing']}", ""]
        for label, pos in (("前文", index - 1), ("原文", index), ("后文", index + 1)):
            if 0 <= pos < len(data["cues"]):
                lines += [label + "：", *["> " + s for s in data["cues"][pos]["text"].splitlines()], ""]
        lines += [f"问题文字：{note['quote']}", f"语言：{note['language']}",
                  f"建议改为：{note['replacement'] or '未填写'}", "评论：", note["comment"] or "未填写", ""]
    return "\n".join(lines)


class ProofreadingDialog:
    """Select exact text, attach multiple notes per cue, and resume saved reviews."""

    def __init__(self, parent, source, output_dir=None):
        self.data = create_review(source)
        self.path = None
        self.output_dir = output_dir or str(Path(source).parent)
        self.dirty = False
        self.current = 0
        self.window = tk.Toplevel(parent)
        self.window.title("字幕人工校对 — 标记与评论")
        self.window.geometry(f"{min(1200, parent.winfo_screenwidth()-80)}x{min(800, parent.winfo_screenheight()-100)}")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        # Treeview's default 20px rows do not grow with the app's font/DPI.
        # Use the same CJK font as the GUI and measure its actual pixel height.
        self.review_font = tkfont.nametofont("TkDefaultFont", root=self.window).copy()
        line_height = self.review_font.metrics("linespace")
        style = ttk.Style(self.window)
        self.tree_style = f"Proofreading{id(self)}.Treeview"
        style.configure(self.tree_style, font=self.review_font,
                        rowheight=line_height + max(10, line_height // 3))
        style.configure(self.tree_style + ".Heading", font=self.review_font)
        toolbar = ttk.Frame(self.window, padding=8)
        toolbar.pack(fill="x")
        for title, command in (("打开校对文件…", self.open), ("保存校对文件…", self.save),
                               ("导出可读报告…", self.export)):
            ttk.Button(toolbar, text=title, command=command).pack(side="left", padx=3)
        self.status = tk.StringVar(value="选择字幕，再选中错误文字添加标记；不选文字时标记整条字幕。")
        ttk.Label(self.window, textvariable=self.status, wraplength=1000).pack(fill="x", padx=10)
        pane = ttk.Panedwindow(self.window, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=8)
        left, right = ttk.Frame(pane), ttk.Frame(pane)
        pane.add(left, weight=2)
        pane.add(right, weight=3)
        # Explicitly set the starting split: Text's default 80-character width
        # otherwise determines pane allocation before the window is mapped.
        self.window.after_idle(lambda: pane.sashpos(0, int(pane.winfo_width() * 0.40))
                               if pane.winfo_exists() else None)
        search_row = ttk.Frame(left)
        search_row.pack(fill="x")
        self.query = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self.query)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self.populate())
        ttk.Button(search_row, text="搜索", command=self.populate).pack(side="left")
        self.tree = ttk.Treeview(left, columns=("number", "text"), show="headings", selectmode="browse", style=self.tree_style, height=12)
        self.tree.heading("number", text="编号 / 标记数")
        self.tree.heading("text", text="字幕内容")
        self.tree.column("number", width=self.review_font.measure("编号 / 标记数") + 24, stretch=False)
        self.tree.column("text", width=240)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        horizontal = ttk.Scrollbar(left, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=horizontal.set)
        horizontal.pack(side="bottom", fill="x")
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.context = tk.StringVar()
        self.context_text = ScrolledText(right, height=4, width=1, wrap="word",
                                        font=self.review_font, state="disabled")
        self.context_text.pack(fill="x", pady=(0, 6))
        ttk.Label(right, text="当前字幕：选中错误文字后填写评论").pack(anchor="w")
        self.text = ScrolledText(right, height=7, width=1, wrap="word", exportselection=False,
                                font=self.review_font, spacing1=3, spacing3=3)
        self.text.pack(fill="both", expand=True)
        self.text.tag_configure("marked", background="#ffe59a", foreground="#151515")
        fields = ttk.Frame(right)
        fields.pack(fill="x", pady=5)
        self.language = tk.StringVar(value="未指定")
        ttk.Label(fields, text="问题语言").pack(side="left")
        ttk.Combobox(fields, textvariable=self.language, values=("中文", "日文", "其他", "未指定"), state="readonly", width=9).pack(side="left", padx=5)
        ttk.Label(fields, text="建议改为（可空）").pack(side="left")
        self.replacement = tk.StringVar()
        ttk.Entry(fields, textvariable=self.replacement).pack(side="left", fill="x", expand=True)
        ttk.Label(right, text="评论 / 问题说明（例如：这里是人名，听起来像……）").pack(anchor="w")
        self.comment = ScrolledText(right, height=3, width=1, wrap="word", font=self.review_font)
        self.comment.pack(fill="x")
        ttk.Button(right, text="添加标记与评论", command=self.add).pack(anchor="e", pady=5)
        self.notes = tk.Listbox(right, height=4, width=1, exportselection=False, font=self.review_font)
        self.notes.pack(fill="x")
        notes_scroll = ttk.Scrollbar(right, orient="horizontal", command=self.notes.xview)
        self.notes.configure(xscrollcommand=notes_scroll.set)
        notes_scroll.pack(fill="x")
        ttk.Button(right, text="删除选中标记", command=self.delete).pack(anchor="e", pady=5)
        self.populate()
        self.display()

    def populate(self):
        self.tree.delete(*self.tree.get_children())
        counts = {}
        for note in self.data["annotations"]:
            counts[note["cue"]] = counts.get(note["cue"], 0) + 1
        for index, cue in enumerate(self.data["cues"]):
            if self.query.get().casefold() in (cue["text"] + cue["number"] + cue["timing"]).casefold():
                self.tree.insert("", "end", iid=str(index), values=(f"{cue['number']} / {counts.get(index, 0)}", cue["text"].replace("\n", " / ")))
        if self.tree.exists(str(self.current)):
            self.tree.selection_set(str(self.current))

    def select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        if int(selection[0]) != self.current and self.has_draft():
            self.add(refresh=False)
        self.current = int(selection[0])
        self.display()

    def display(self):
        cue = self.data["cues"][self.current]
        before = self.data["cues"][self.current-1]["text"] if self.current else "无"
        after = self.data["cues"][self.current+1]["text"] if self.current+1 < len(self.data["cues"]) else "无"
        self.context.set(f"字幕 {cue['number']} · {cue['timing']}\n前文：{before}\n后文：{after}")
        self.context_text.configure(state="normal")
        self.context_text.delete("1.0", "end")
        self.context_text.insert("1.0", self.context.get())
        self.context_text.configure(state="disabled")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", cue["text"])
        self.notes.delete(0, "end")
        self.note_ids = []
        for index, note in enumerate(self.data["annotations"]):
            if note["cue"] == self.current:
                # Derive Tk positions from prefixes: Python and Tk differ for emoji offsets.
                def pos(offset):
                    prefix = cue["text"][:offset]
                    line = prefix.count("\n") + 1
                    column = self.text.tk.call("string", "length", prefix.rsplit("\n", 1)[-1])
                    return f"{line}.{column}"
                self.text.tag_add("marked", pos(note["start"]), pos(note["end"]))
                self.notes.insert("end", f"[{note['language']}] {note['quote']} → {note['replacement']} | {note['comment']}")
                self.note_ids.append(index)
        self.text.configure(state="disabled")

    def add(self, refresh=True):
        cue = self.data["cues"][self.current]
        try:
            start = len(self.text.get("1.0", "sel.first"))
            end = min(len(cue["text"]), len(self.text.get("1.0", "sel.last")))
        except tk.TclError:
            start, end = 0, len(cue["text"])
        self.data["annotations"].append(dict(cue=self.current, start=start, end=end,
            quote=cue["text"][start:end], language=self.language.get(),
            replacement=self.replacement.get(), comment=self.comment.get("1.0", "end-1c")))
        self.dirty = True
        self.replacement.set("")
        self.comment.delete("1.0", "end")
        if refresh:
            self.populate()
            self.display()
        self.status.set(f"已添加标记，共 {len(self.data['annotations'])} 个。请保存校对文件。")

    def delete(self):
        selected = self.notes.curselection()
        if selected:
            del self.data["annotations"][self.note_ids[selected[0]]]
            self.dirty = True
            self.populate()
            self.display()

    def save(self):
        if self.has_draft():
            self.add()
        path = filedialog.asksaveasfilename(parent=self.window, initialdir=self.output_dir,
            initialfile=Path(self.path).name if self.path else Path(self.data["source_name"]).stem + "_review.json",
            defaultextension=".json", filetypes=[("字幕校对文件", "*.json")])
        if not path:
            return False
        try:
            save_review(self.data, path)
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.window)
            return False
        self.path, self.dirty = path, False
        self.status.set(f"已保存 {len(self.data['annotations'])} 个标记。此 JSON 已包含完整原字幕，可直接提供给精校人员。")
        return True

    def confirm(self):
        if not self.dirty and not self.has_draft():
            return True
        answer = messagebox.askyesnocancel("未保存的标记", "是否先保存校对标记？", parent=self.window)
        return self.save() if answer else answer is False

    def has_draft(self):
        """Keep typed comments when navigating away or saving before Add is pressed."""
        return bool(self.replacement.get().strip() or self.comment.get("1.0", "end-1c").strip())

    def open(self):
        if not self.confirm():
            return
        path = filedialog.askopenfilename(parent=self.window, filetypes=[("字幕校对文件", "*.json")])
        if not path:
            return
        try:
            data = load_review(path)
        except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            messagebox.showerror("无法打开", str(exc), parent=self.window)
            return
        self.data, self.path, self.current, self.dirty = data, path, 0, False
        self.replacement.set("")
        self.comment.delete("1.0", "end")
        self.query.set("")
        self.populate()
        self.display()

    def export(self):
        if self.has_draft():
            self.add()
        path = filedialog.asksaveasfilename(parent=self.window, initialdir=self.output_dir,
            initialfile=Path(self.data["source_name"]).stem + "_review.md",
            defaultextension=".md", filetypes=[("校对报告", "*.md")])
        if path:
            try:
                Path(path).write_text(review_report(self.data), encoding="utf-8")
                self.status.set("可读报告已导出；请同时保存 JSON，以便恢复标记和提供完整原字幕。")
            except OSError as exc:
                messagebox.showerror("导出失败", str(exc), parent=self.window)

    def close(self):
        if self.confirm():
            self.window.destroy()
