"""Independent dual-ASR review window; network work never touches Tk widgets."""

import os
from pathlib import Path
from queue import Queue, Empty
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from dual_model_review import prepare_package, export_package, reconcile, call_api, endpoint_url


class DualModelReviewDialog:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title('Whisper + Qwen 双模型交叉精校（文本对照）')
        self.window.geometry('1000x650')
        self.window.minsize(760, 520)
        self.window.columnconfigure(1, weight=1)
        self.queue, self.cancel = Queue(), threading.Event()
        self.running = False
        self.destination = None
        self.fields = {}
        self.controls = []
        intro = ttk.Label(self.window, text='选择同一视频、同一起点的两份日语 SRT。以 Whisper 为底稿，参考 Qwen 局部纠错。\n'
                          '不重新识别音频、不删除 Whisper 对白；不能确定的保留原文并记录。两个模型都漏掉的内容无法靠文本恢复。',
                          wraplength=900)
        intro.grid(row=0, column=0, columnspan=3, sticky='ew', padx=14, pady=14)
        specs = [('whisper', 'Whisper 字幕', ''), ('qwen', 'Qwen 字幕', ''),
                 ('glossary', '术语表（可选）', ''), ('output', '输出文件夹', str(Path.cwd() / 'outputs')),
                 ('base', 'API 地址', 'https://api.openai.com/v1'),
                 ('model', '模型名称', ''), ('key', 'API Key（不保存）', '')]
        for row, (name, label, default) in enumerate(specs, 1):
            ttk.Label(self.window, text=label).grid(row=row, column=0, sticky='w', padx=14, pady=6)
            variable = tk.StringVar(value=default)
            self.fields[name] = variable
            entry = ttk.Entry(self.window, textvariable=variable, show='*' if name == 'key' else '')
            entry.grid(row=row, column=1, sticky='ew', pady=6)
            self.controls.append(entry)
            if row <= 4:
                button = ttk.Button(self.window, text='选择…', command=lambda n=name: self.choose(n))
                button.grid(row=row, column=2, padx=14)
                self.controls.append(button)
        ttk.Label(self.window, text='自动精校：需要支持 Chat Completions / JSON 模式的服务，按服务计费。\n'
                  '本地导出：不联网、不需要 API；将生成的 review_package.json 发给我即可继续精校。',
                  wraplength=900).grid(row=8, column=0, columnspan=3, sticky='ew', padx=14, pady=12)
        actions = ttk.Frame(self.window)
        actions.grid(row=9, column=0, columnspan=3, sticky='w', padx=14)
        for text, auto in [('导出 AI 校对包（本地）', False), ('开始自动精校…', True)]:
            button = ttk.Button(actions, text=text, command=lambda a=auto: self.start(a))
            button.pack(side='left', padx=(0, 10))
            self.controls.append(button)
        self.stop = ttk.Button(actions, text='取消', command=self.request_cancel, state='disabled')
        self.stop.pack(side='left')
        ttk.Button(actions, text='打开结果文件夹', command=self.open_output).pack(side='left', padx=10)
        self.bar = ttk.Progressbar(self.window, maximum=100)
        self.bar.grid(row=10, column=0, columnspan=3, sticky='ew', padx=14, pady=14)
        self.status = tk.StringVar(value='就绪。原字幕文件不会被覆盖。')
        ttk.Label(self.window, textvariable=self.status, wraplength=900).grid(
            row=11, column=0, columnspan=3, sticky='nw', padx=14, pady=8)
        self.window.rowconfigure(11, weight=1)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.poll_id = self.window.after(100, self.poll)
        self.window.bind('<Configure>', self.resize_text)

    def resize_text(self, event):
        if event.widget is self.window:
            for widget in self.window.winfo_children():
                if isinstance(widget, ttk.Label) and widget.grid_info().get('columnspan', 1) == 3:
                    widget.configure(wraplength=max(300, event.width-40))

    def choose(self, name):
        if name == 'output':
            path = filedialog.askdirectory(parent=self.window)
        else:
            types = [('术语表', '*.tsv *.txt')] if name == 'glossary' else [('字幕', '*.srt')]
            path = filedialog.askopenfilename(parent=self.window, filetypes=types)
        if path:
            self.fields[name].set(path)

    def start(self, auto):
        if self.running:
            return
        values = {k: v.get().strip() for k, v in self.fields.items()}
        if not all(values[k] for k in ('whisper', 'qwen', 'output')):
            messagebox.showerror('缺少输入', '请选择两份字幕和输出文件夹。', parent=self.window)
            return
        if auto:
            try:
                endpoint_url(values['base'])
                if not values['model']:
                    raise ValueError('请填写服务支持的模型名称。')
            except ValueError as exc:
                messagebox.showerror('设置错误', str(exc), parent=self.window)
                return
            if not messagebox.askyesno('确认发送字幕',
                f"将向以下地址发送两份字幕的差异片段、上下文及所选术语表：\n{values['base']}\n\n"
                '不会发送音视频或本地文件路径。可能产生 API 费用。\n'
                '这是文本自动校对，不能保证人名或对白正确。是否开始？', parent=self.window):
                return
        self.running = True
        self.cancel.clear()
        self.bar['value'] = 0
        self.status.set('读取字幕并按时间轴匹配…')
        for control in self.controls:
            control.configure(state='disabled')
        self.stop.configure(state='normal')

        def worker():
            try:
                package = prepare_package(values['whisper'], values['qwen'], values['glossary'])
                destination = export_package(package, values['output'])
                warning_note = (f"\n发现 {len(package['warnings'])} 条零时长字幕，已保留并记录到 时间轴提醒.txt。"
                                if package.get('warnings') else '')
                self.queue.put(('destination', destination))
                if auto:
                    status, target = reconcile(package, destination,
                        lambda batch: call_api(values['base'], values['key'], values['model'], batch),
                        self.cancel, lambda n, total: self.queue.put(('progress', (n, total))))
                    self.queue.put(('done', (status, str(target) + warning_note)))
                else:
                    self.queue.put(('done', ('exported', str(destination / 'review_package.json') + warning_note)))
            except Exception as exc:
                # No raw HTTP body or secret-bearing URL is included in UI errors.
                message = str(exc)
                if values['key']:
                    message = message.replace(values['key'], '[REDACTED]')
                self.queue.put(('error', message))
            finally:
                values['key'] = ''
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.queue.get_nowait()
                if kind == 'destination':
                    self.destination = value
                elif kind == 'progress':
                    n, total = value
                    self.bar['value'] = 100*n/max(1, total)
                    self.status.set(f'自动精校：{n}/{total} 批')
                else:
                    self.running = False
                    self.fields['key'].set('')
                    for control in self.controls:
                        control.configure(state='normal')
                    self.stop.configure(state='disabled')
                    if kind == 'error':
                        self.status.set('失败：' + value)
                        messagebox.showerror('精校失败', value, parent=self.window)
                    else:
                        status, path = value
                        labels = {'complete': '精校完成', 'exported': '本地校对包已导出',
                                  'failed': '未全部完成，请查看 report.json 错误记录',
                                  'cancelled': '已取消，保留已处理结果'}
                        text = labels[status] + '\n' + path
                        self.status.set(text)
                        if status in ('complete', 'exported'):
                            self.bar['value'] = 100
                            messagebox.showinfo('完成', text, parent=self.window)
                        else:
                            messagebox.showwarning('部分结果', text, parent=self.window)
        except Empty:
            pass
        self.poll_id = self.window.after(100, self.poll)

    def request_cancel(self):
        self.cancel.set()
        self.status.set('正在取消；等待当前请求结束（网络读写超时 90 秒），不再应用当前批次。')

    def open_output(self):
        if self.destination:
            os.startfile(str(self.destination))

    def close(self):
        if self.running:
            self.request_cancel()
            return
        self.window.after_cancel(self.poll_id)
        self.window.destroy()
