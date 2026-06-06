"""
VoiceTrans - 视频音频翻译工具
剪映风格深色主题 · 三面板布局
"""

import os
import sys
import json
import time
import subprocess
import re
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (
    AudioProcessor, ASREngine, Translator,
    Exporter, TranscriptionResult, Segment,
    AudioSplitter, TTSEngine,
)

THEME = {
    "bg_dark": "#1a1a2e", "bg_mid": "#16213e", "bg_panel": "#1e1e3a",
    "bg_input": "#252545", "bg_table": "#1a1a30", "bg_row_alt": "#222244",
    "bg_row_sel": "#3a3a6a", "bg_progress": "#2a2a4a",
    "fg_primary": "#e0e0f0", "fg_secondary": "#a0a0c0", "fg_dim": "#6a6a8a",
    "accent": "#6c63ff", "accent_hover": "#8b83ff", "accent_dim": "#4a44cc",
    "success": "#4caf50", "warning": "#ff9800", "error": "#f44336",
    "border": "#333355", "border_focus": "#6c63ff",
    "scrollbar_bg": "#2a2a4a", "scrollbar_fg": "#4a4a7a",
}


def apply_theme(root: tk.Tk):
    style = ttk.Style(root)
    root.configure(bg=THEME["bg_dark"])
    df = ("Microsoft YaHei UI", 10)
    style.theme_use("clam")
    style.configure("TFrame", background=THEME["bg_dark"])
    style.configure("Panel.TFrame", background=THEME["bg_panel"])
    style.configure("Card.TFrame", background=THEME["bg_mid"])
    style.configure("TLabel", background=THEME["bg_dark"], foreground=THEME["fg_primary"], font=df)
    style.configure("Title.TLabel", background=THEME["bg_panel"], foreground=THEME["fg_primary"], font=("Microsoft YaHei UI", 12, "bold"))
    style.configure("Subtitle.TLabel", background=THEME["bg_panel"], foreground=THEME["fg_secondary"], font=("Microsoft YaHei UI", 9))
    style.configure("Dim.TLabel", background=THEME["bg_dark"], foreground=THEME["fg_dim"])
    style.configure("TButton", background=THEME["accent"], foreground="#ffffff", borderwidth=0, focusthickness=0, font=df, padding=(16, 6))
    style.map("TButton", background=[("active", THEME["accent_hover"]), ("disabled", THEME["bg_input"])], foreground=[("disabled", THEME["fg_dim"])])
    style.configure("Secondary.TButton", background=THEME["bg_input"], foreground=THEME["fg_primary"])
    style.map("Secondary.TButton", background=[("active", THEME["bg_row_sel"])])
    style.configure("TEntry", fieldbackground=THEME["bg_input"], foreground=THEME["fg_primary"], borderwidth=1, font=df)
    style.map("TEntry", fieldbackground=[("focus", THEME["bg_input"])])
    style.configure("TCombobox", fieldbackground=THEME["bg_input"], background=THEME["bg_input"], foreground=THEME["fg_primary"], arrowcolor=THEME["fg_primary"], font=df)
    style.map("TCombobox", fieldbackground=[("readonly", THEME["bg_input"])], selectbackground=[("readonly", THEME["bg_row_sel"])])
    root.option_add("*TCombobox*Listbox.background", THEME["bg_input"])
    root.option_add("*TCombobox*Listbox.foreground", THEME["fg_primary"])
    root.option_add("*TCombobox*Listbox.selectBackground", THEME["bg_row_sel"])
    root.option_add("*TCombobox*Listbox.font", df)
    style.configure("TProgressbar", background=THEME["accent"], troughcolor=THEME["bg_progress"], borderwidth=0, thickness=8)
    style.configure("Treeview", background=THEME["bg_table"], foreground=THEME["fg_primary"], fieldbackground=THEME["bg_table"], borderwidth=0, font=df, rowheight=32)
    style.configure("Treeview.Heading", background=THEME["bg_panel"], foreground=THEME["fg_secondary"], font=("Microsoft YaHei UI", 9, "bold"), borderwidth=1, relief="flat")
    style.map("Treeview.Heading", background=[("active", THEME["bg_row_sel"])])
    style.map("Treeview", background=[("selected", THEME["bg_row_sel"])], foreground=[("selected", THEME["fg_primary"])])
    style.configure("TScrollbar", background=THEME["scrollbar_bg"], troughcolor=THEME["bg_dark"], borderwidth=0, arrowsize=14)
    style.map("TScrollbar", background=[("active", THEME["scrollbar_fg"])])
    style.configure("TNotebook", background=THEME["bg_dark"], borderwidth=0)
    style.configure("TNotebook.Tab", background=THEME["bg_mid"], foreground=THEME["fg_secondary"], padding=(16, 8), font=df)
    style.map("TNotebook.Tab", background=[("selected", THEME["bg_panel"])], foreground=[("selected", THEME["fg_primary"])])
    style.configure("TPanedwindow", background=THEME["border"])
    style.configure("TScale", background=THEME["bg_dark"], troughcolor=THEME["bg_progress"])
    return style


class VoiceTransApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("VoiceTrans - 视频音频翻译工具")
        self.root.geometry("1400x850")
        self.root.minsize(1100, 650)
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"1400x850+{(sw-1400)//2}+{(sh-850)//2}")
        apply_theme(root)
        self.audio_file = ""
        self.original_file = ""
        self.segments: list = []
        self.result: TranscriptionResult = None
        self.processing = False
        self.asr_engine: ASREngine = None
        self.translator: Translator = None
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        self.config = self._load_config()
        self._build_ui()
        self._load_config_to_ui()
        self.root.after(500, self._check_ffmpeg)

    def _load_config(self) -> dict:
        defaults = {"api_key": "", "target_lang": "中文", "asr_model": "medium"}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    defaults.update(json.load(f))
            except Exception:
                pass
        return defaults

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_config_to_ui(self):
        self.api_key_var.set(self.config.get("api_key", ""))
        self.target_lang_var.set(self.config.get("target_lang", "中文"))
        self.asr_model_var.set(self.config.get("asr_model", "medium"))

    # ---- UI ----
    def _build_ui(self):
        main_pw = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pw.pack(fill=tk.BOTH, expand=True)
        self._build_left_panel(main_pw)
        right_frame = ttk.Frame(main_pw, style="Panel.TFrame")
        main_pw.add(right_frame, weight=3)
        right_pw = ttk.PanedWindow(right_frame, orient=tk.VERTICAL)
        right_pw.pack(fill=tk.BOTH, expand=True)
        self._build_player_panel(right_pw)
        self._build_video_panel(right_pw)
        self._build_result_panel(right_pw)
        self.root.update_idletasks()
        # 预分配 sash 位置: 播放器 180px, 视频 220px, 剩余给结果
        try:
            right_pw.sashpos(0, 180)
            right_pw.sashpos(1, 400)
        except Exception:
            pass

    def _build_left_panel(self, parent):
        left = ttk.Frame(parent, style="Panel.TFrame", width=320)
        parent.add(left, weight=1)
        # 标题
        tf = ttk.Frame(left, style="Panel.TFrame")
        tf.pack(fill=tk.X, padx=16, pady=(12, 8))
        ttk.Label(tf, text="素材管理", style="Title.TLabel").pack(side=tk.LEFT)
        # 上传
        uf = ttk.Frame(left, style="Card.TFrame")
        uf.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(uf, text="+ 上传音频/视频", command=self._on_upload, style="TButton").pack(fill=tk.X, padx=16, pady=16)
        self.file_label_var = tk.StringVar(value="未选择文件")
        ttk.Label(uf, textvariable=self.file_label_var, style="Dim.TLabel", wraplength=260).pack(padx=16, pady=(0, 12))
        self.file_info_var = tk.StringVar(value="")
        ttk.Label(uf, textvariable=self.file_info_var, style="Subtitle.TLabel").pack(padx=16, pady=(0, 12))
        # API Key
        af = ttk.Frame(left, style="Card.TFrame")
        af.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Label(af, text="MiMo API Key", style="Subtitle.TLabel").pack(anchor=tk.W, padx=16, pady=(12, 2))
        self.api_key_var = tk.StringVar()
        self.api_key_var.trace_add("write", self._on_api_key_change)
        ttk.Entry(af, textvariable=self.api_key_var, show="*").pack(fill=tk.X, padx=16, pady=(0, 4))
        ttk.Label(af, text="获取: platform.xiaomimimo.com", style="Dim.TLabel", font=("Microsoft YaHei UI", 8)).pack(anchor=tk.W, padx=16, pady=(0, 12))
        # 翻译设置
        tf2 = ttk.Frame(left, style="Card.TFrame")
        tf2.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Label(tf2, text="翻译设置", style="Subtitle.TLabel").pack(anchor=tk.W, padx=16, pady=(12, 4))
        row = ttk.Frame(tf2, style="Card.TFrame")
        row.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(row, text="目标语言", style="Dim.TLabel").pack(side=tk.LEFT)
        self.target_lang_var = tk.StringVar(value="中文")
        self.target_lang_var.trace_add("write", self._on_target_lang_change)
        ttk.Combobox(row, textvariable=self.target_lang_var,
                     values=["中文","English","日本語","한국어","Français","Deutsch","Español","Русский","العربية","Português","Italiano"],
                     state="readonly", width=12).pack(side=tk.RIGHT)
        # ASR 设置
        aaf = ttk.Frame(left, style="Card.TFrame")
        aaf.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Label(aaf, text="语音识别 (whisper)", style="Subtitle.TLabel").pack(anchor=tk.W, padx=16, pady=(12, 4))
        r1 = ttk.Frame(aaf, style="Card.TFrame"); r1.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(r1, text="模型", style="Dim.TLabel").pack(side=tk.LEFT)
        self.asr_model_var = tk.StringVar(value="medium")
        self.asr_model_var.trace_add("write", self._on_asr_model_change)
        ttk.Combobox(r1, textvariable=self.asr_model_var, values=["tiny","base","small","medium","large-v3"], state="readonly", width=12).pack(side=tk.RIGHT)
        # 处理按钮
        pf = ttk.Frame(left, style="Card.TFrame")
        pf.pack(fill=tk.X, padx=12, pady=(0, 12))
        self.process_btn = ttk.Button(pf, text="开始处理", command=self._on_process, style="TButton")
        self.process_btn.pack(fill=tk.X, padx=16, pady=(16, 4))
        self.cancel_btn = ttk.Button(pf, text="取消", command=self._on_cancel, style="Secondary.TButton", state="disabled")
        self.cancel_btn.pack(fill=tk.X, padx=16, pady=(0, 12))
        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(pf, variable=self.progress_var, mode="determinate", style="TProgressbar").pack(fill=tk.X, padx=16, pady=(0, 4))
        self.progress_label_var = tk.StringVar(value="就绪")
        ttk.Label(pf, textvariable=self.progress_label_var, style="Dim.TLabel").pack(padx=16, pady=(0, 16))

    def _build_player_panel(self, parent):
        player = ttk.Frame(parent, style="Panel.TFrame", height=200)
        parent.add(player, weight=1)
        ttk.Label(player, text="音频预览", style="Title.TLabel").pack(anchor=tk.W, padx=16, pady=(12, 8))
        self.wave_canvas = tk.Canvas(player, bg=THEME["bg_mid"], height=100, highlightthickness=0, bd=0)
        self.wave_canvas.pack(fill=tk.X, padx=16, pady=(0, 8))
        cf = ttk.Frame(player, style="Panel.TFrame"); cf.pack(fill=tk.X, padx=16, pady=(0, 12))
        self.play_btn = ttk.Button(cf, text="▶ 播放", command=self._on_play, style="Secondary.TButton", state="disabled")
        self.play_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_btn = ttk.Button(cf, text="■ 停止", command=self._on_stop, style="Secondary.TButton", state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 16))
        self.seek_var = tk.DoubleVar(value=0)
        self.seek_scale = ttk.Scale(cf, from_=0, to=100, variable=self.seek_var, orient=tk.HORIZONTAL, state="disabled")
        self.seek_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.time_var = tk.StringVar(value="00:00 / 00:00")
        ttk.Label(cf, textvariable=self.time_var, style="Dim.TLabel", width=14).pack(side=tk.RIGHT)
        ttk.Label(cf, text="🔊", style="Dim.TLabel").pack(side=tk.RIGHT, padx=(8, 0))
        self.volume_var = tk.DoubleVar(value=80)
        ttk.Scale(cf, from_=0, to=100, variable=self.volume_var, orient=tk.HORIZONTAL).pack(side=tk.RIGHT, padx=(4, 0))
        ef = ttk.Frame(player, style="Panel.TFrame"); ef.pack(fill=tk.X, padx=16, pady=(0, 12))
        ttk.Label(ef, text="导入字幕：", style="Subtitle.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.import_srt_btn = ttk.Button(ef, text="导入SRT",
                                         command=self._on_import_srt,
                                         style="Secondary.TButton")
        self.import_srt_btn.pack(side=tk.LEFT, padx=2)
        ttk.Separator(ef, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(ef, text="导出字幕：", style="Subtitle.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.export_srt_btn = ttk.Button(ef, text="SRT", command=lambda: self._on_export("srt"), style="Secondary.TButton", state="disabled")
        self.export_srt_btn.pack(side=tk.LEFT, padx=2)
        self.export_ass_btn = ttk.Button(ef, text="ASS", command=lambda: self._on_export("ass"), style="Secondary.TButton", state="disabled")
        self.export_ass_btn.pack(side=tk.LEFT, padx=2)
        self.export_json_btn = ttk.Button(ef, text="JSON", command=lambda: self._on_export("json"), style="Secondary.TButton", state="disabled")
        self.export_json_btn.pack(side=tk.LEFT, padx=2)
        self.bilingual_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ef, text="双语", variable=self.bilingual_var).pack(side=tk.RIGHT, padx=(8, 0))

    def _build_video_panel(self, parent):
        self.video_frame = ttk.Frame(parent, style="Panel.TFrame")
        parent.add(self.video_frame, weight=1)
        vhf = ttk.Frame(self.video_frame, style="Panel.TFrame")
        vhf.pack(fill=tk.X, padx=16, pady=(12, 4))
        ttk.Label(vhf, text="视频预览", style="Title.TLabel").pack(side=tk.LEFT)
        self.video_status_var = tk.StringVar(value="未加载视频")
        ttk.Label(vhf, textvariable=self.video_status_var,
                  style="Dim.TLabel").pack(side=tk.RIGHT)
        self.video_canvas = tk.Canvas(
            self.video_frame, bg=THEME["bg_mid"],
            height=200, highlightthickness=0, bd=0
        )
        self.video_canvas.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        # 速度控制栏
        vsf = ttk.Frame(self.video_frame, style="Panel.TFrame")
        vsf.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._video_speed_var = tk.DoubleVar(value=1.0)
        speeds = [("0.5x", 0.5), ("1x", 1.0), ("1.5x", 1.5), ("2x", 2.0)]
        for label, val in speeds:
            ttk.Button(vsf, text=label, width=5,
                       command=lambda v=val: self._set_video_speed(v),
                       style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 4))
        self.video_canvas.create_text(
            200, 100, text="上传视频文件以预览",
            fill=THEME["fg_dim"], font=("Microsoft YaHei UI", 12),
            tags=("placeholder",)
        )
        self._video_cap = None
        self._video_seek_time = 0.0
        self._video_playing = False
        self._video_duration = 0.0
        self._video_speed = 1.0
        # 单击画布跳转播放
        self.video_canvas.bind("<Button-1>", self._on_video_click)

    def _build_result_panel(self, parent):
        result = ttk.Frame(parent, style="Panel.TFrame")
        parent.add(result, weight=4)
        hf = ttk.Frame(result, style="Panel.TFrame"); hf.pack(fill=tk.X, padx=16, pady=(12, 8))
        ttk.Label(hf, text="分段结果", style="Title.TLabel").pack(side=tk.LEFT)
        self.segment_count_var = tk.StringVar(value="0 段")
        ttk.Label(hf, textvariable=self.segment_count_var, style="Subtitle.TLabel").pack(side=tk.RIGHT)
        tf = ttk.Frame(result, style="Panel.TFrame"); tf.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 4))
        cols = ("index", "time", "speaker", "text", "translation", "play")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("index", text="#", anchor=tk.CENTER)
        self.tree.heading("time", text="时间范围", anchor=tk.CENTER)
        self.tree.heading("speaker", text="说话人", anchor=tk.CENTER)
        self.tree.heading("text", text="原文", anchor=tk.W)
        self.tree.heading("translation", text="译文", anchor=tk.W)
        self.tree.heading("play", text="试听", anchor=tk.CENTER)
        self.tree.column("index", width=40, anchor=tk.CENTER, stretch=False)
        self.tree.column("time", width=140, anchor=tk.CENTER, stretch=False)
        self.tree.column("speaker", width=80, anchor=tk.CENTER, stretch=False)
        self.tree.column("text", width=320, anchor=tk.W)
        self.tree.column("translation", width=320, anchor=tk.W)
        self.tree.column("play", width=60, anchor=tk.CENTER, stretch=False)
        vsb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1); tf.columnconfigure(0, weight=1)
        # 绑定: 单击播放, 右键菜单, 试听列点击
        self.tree.bind("<<TreeviewSelect>>", self._on_segment_select)
        self.tree.bind("<Button-3>", self._on_segment_right_click)
        self.tree.bind("<Button-1>", self._on_tree_click)
        # 右键菜单
        self._ctx_menu = tk.Menu(self.root, tearoff=0, bg=THEME["bg_mid"],
                                 fg=THEME["fg_primary"],
                                 activebackground=THEME["bg_row_sel"],
                                 activeforeground=THEME["fg_primary"])
        # 翻译 / TTS 控制栏
        ttsf = ttk.Frame(result, style="Panel.TFrame")
        ttsf.pack(fill=tk.X, padx=16, pady=(4, 12))
        self.translate_all_btn = ttk.Button(ttsf, text="一键翻译",
                                            command=self._on_translate_all,
                                            style="Secondary.TButton",
                                            state="disabled")
        self.translate_all_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.retry_translate_btn = ttk.Button(ttsf, text="重试失败",
                                               command=self._on_retry_failed,
                                               style="Secondary.TButton",
                                               state="disabled")
        self.retry_translate_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.synth_all_btn = ttk.Button(ttsf, text="一键合成配音",
                                        command=self._on_synthesize_all,
                                        style="Secondary.TButton",
                                        state="disabled")
        self.synth_all_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.export_dub_btn = ttk.Button(ttsf, text="一键导出配音",
                                         command=self._on_export_dub,
                                         style="Secondary.TButton",
                                         state="disabled")
        self.export_dub_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.tts_progress_var = tk.StringVar(value="")
        ttk.Label(ttsf, textvariable=self.tts_progress_var,
                  style="Dim.TLabel").pack(side=tk.LEFT, padx=(8, 0))

    # ---- Events ----
    def _on_api_key_change(self, *args):
        self.config["api_key"] = self.api_key_var.get(); self._save_config()

    def _on_target_lang_change(self, *args):
        self.config["target_lang"] = self.target_lang_var.get(); self._save_config()
        if self.translator:
            self.translator.set_target_lang(self.target_lang_var.get())

    def _on_asr_model_change(self, *args):
        self.config["asr_model"] = self.asr_model_var.get(); self._save_config()

    def _check_ffmpeg(self):
        if not AudioProcessor.check_ffmpeg():
            messagebox.showwarning("缺少 ffmpeg", "未检测到 ffmpeg。\n请安装: winget install ffmpeg")

    def _on_upload(self):
        fp = filedialog.askopenfilename(
            title="选择音频或视频文件",
            filetypes=[("音频/视频", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.mp4 *.mkv *.avi *.mov *.flv *.webm"), ("所有文件", "*.*")]
        )
        if not fp:
            return
        self.original_file = fp
        self.file_label_var.set(os.path.basename(fp))
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        ext = os.path.splitext(fp)[1].upper()
        parts = [f"{ext} | {size_mb:.1f} MB"]
        try:
            dur = AudioProcessor.get_audio_duration(fp)
            parts.append(f"{dur:.1f} 秒")
        except Exception:
            dur = 0
        self.file_info_var.set(" | ".join(parts))
        self._draw_empty_waveform(dur)
        self.play_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.seek_scale.configure(state="normal")

    def _on_process(self):
        if not self.original_file:
            messagebox.showinfo("提示", "请先上传文件"); return
        if not self.api_key_var.get().strip():
            messagebox.showinfo("提示", "请填写 MiMo API Key"); return
        self.processing = True
        self.process_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_var.set(0)
        self.progress_label_var.set("准备中...")
        self.tree.delete(*self.tree.get_children())
        self.segment_count_var.set("0 段")
        threading.Thread(target=self._process_pipeline, daemon=True).start()

    def _process_pipeline(self):
        try:
            self._update_progress(5, "提取音频...")
            ext = os.path.splitext(self.original_file)[1].lower()
            if ext in ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm'):
                self.audio_file = AudioProcessor.extract_audio(self.original_file, output_dir=tempfile.gettempdir())
            else:
                self.audio_file = self.original_file

            self._update_progress(15, "语音识别中...")
            self.asr_engine = ASREngine(model_size=self.asr_model_var.get())
            self.result = self.asr_engine.transcribe(self.audio_file)
            self.segments = self.result.segments
            self._update_progress(40, f"识别完成: {len(self.segments)} 段")
            # 初始化翻译器但不自动翻译
            self.translator = Translator(api_key=self.api_key_var.get(), target_lang=self.target_lang_var.get())
            self._update_progress(98, "更新界面...")
            self.root.after(0, self._display_results)
            self._update_progress(100, "完成")
        except Exception as e:
            import traceback
            err_msg = str(e)
            tb = traceback.format_exc()
            # Log to file for diagnosis
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(tb)
            print(f"[ERROR] {tb}")
            self._update_progress(0, f"错误: {err_msg}")
            _err = err_msg  # capture for lambda
            self.root.after(0, lambda m=_err: messagebox.showerror("处理失败", m))
        finally:
            self.processing = False
            self.root.after(0, lambda: self.process_btn.configure(state="normal"))
            self.root.after(0, lambda: self.cancel_btn.configure(state="disabled"))

    def _display_results(self):
        self.tree.delete(*self.tree.get_children())
        failed_indices = getattr(self, "_tts_failed_indices", set())
        for seg in self.segments:
            ts = f"{self._fmt_time(seg.start)} → {self._fmt_time(seg.end)}"
            if seg.index in failed_indices:
                ts += "  [合成失败]"
            trans_display = seg.translation if seg.translation else "未翻译"
            tts_map = getattr(self, "_tts_map", {}) or {}
            has_tts = seg.index in tts_map
            play_display = "▶" if has_tts else "—"
            vals = (seg.index+1, ts, seg.speaker or "-", seg.text, trans_display, play_display)
            tag = "failed" if seg.index in failed_indices else (
                "even" if seg.index % 2 == 0 else "odd")
            self.tree.insert("", tk.END, values=vals, tags=(tag,))
        self.tree.tag_configure("odd", background=THEME["bg_row_alt"])
        self.tree.tag_configure("even", background=THEME["bg_table"])
        self.tree.tag_configure("failed", background="#4a2020",
                                 foreground="#ff6b6b")
        self.segment_count_var.set(f"{len(self.segments)} 段")
        self.export_srt_btn.configure(state="normal")
        self.export_ass_btn.configure(state="normal")
        self.export_json_btn.configure(state="normal")
        self.translate_all_btn.configure(state="normal")
        self.synth_all_btn.configure(state="normal")
        self.export_dub_btn.configure(state="normal")
        has_failed = any(
            not s.translated or (s.text.strip() and s.translation.startswith("[翻译失败:"))
            for s in self.segments
        )
        self.retry_translate_btn.configure(state="normal" if has_failed else "disabled")
        self._draw_result_waveform()
        # 如果是视频文件，初始化视频预览
        if self.original_file:
            ext = os.path.splitext(self.original_file)[1].lower()
            if ext in ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm'):
                self._init_video_preview()

    def _on_cancel(self):
        self.processing = False
        self.progress_label_var.set("已取消")
        self.process_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    def _on_play(self):
        fp = self.audio_file or self.original_file
        if not fp or not os.path.exists(fp):
            return
        self._on_stop()
        try:
            ffplay = AudioProcessor._get_ffplay()
            start = 0.0
            sel = self.tree.selection()
            if sel and self.segments:
                idx = int(self.tree.item(sel[0])["values"][0]) - 1
                if 0 <= idx < len(self.segments):
                    start = self.segments[idx].start
            vol = max(0, min(100, int(self.volume_var.get())))
            cmd = [ffplay, "-nodisp", "-autoexit", "-volume", str(vol)]
            if start > 0:
                cmd += ["-ss", str(start)]
            cmd.append(fp)
            self._ffplay_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self._play_start_time = time.time() - start
            self._check_ffplay_done()
            self._update_playback_progress()
        except Exception as e:
            messagebox.showerror("播放失败", str(e))

    def _on_stop(self):
        if hasattr(self, "_ffplay_process") and self._ffplay_process:
            try:
                self._ffplay_process.terminate()
            except Exception:
                pass
            self._ffplay_process = None
        if hasattr(self, "_ffmpeg_proc") and self._ffmpeg_proc:
            try:
                self._ffmpeg_proc.terminate()
            except Exception:
                pass
            self._ffmpeg_proc = None
        self._stop_video_playback()
        self.seek_var.set(0)
        if hasattr(self, "_play_start_time"):
            del self._play_start_time

    def _check_ffplay_done(self):
        if not hasattr(self, "_ffplay_process") or not self._ffplay_process:
            return
        if self._ffplay_process.poll() is not None:
            self._ffplay_process = None
            self.seek_var.set(0)
            self.time_var.set("00:00 / 00:00")
            return
        self.root.after(500, self._check_ffplay_done)

    def _update_playback_progress(self):
        if not hasattr(self, "_ffplay_process") or not self._ffplay_process:
            return
        if not hasattr(self, "_play_start_time"):
            return
        total = self.result.total_duration if self.result else 100
        if total <= 0:
            return
        elapsed = time.time() - self._play_start_time
        pos = min(elapsed, total)
        self.seek_var.set(min(pos / total * 100, 100))
        self.time_var.set(f"{self._fmt_time(pos)} / {self._fmt_time(total)}")
        self.root.after(200, self._update_playback_progress)

    def _on_segment_select(self, event):
        """单击分段：播放该段音频。视频文件用 ffplay 播放含声音的视频"""
        if getattr(self, "_skip_select", False):
            self._skip_select = False
            return
        sel = self.tree.selection()
        if not sel or not self.segments:
            return
        idx = int(self.tree.item(sel[0])["values"][0]) - 1
        if not (0 <= idx < len(self.segments)):
            return
        seg = self.segments[idx]
        self._on_stop()
        # 视频文件：ffplay 播放（含声音 + 视频窗口），纯音频：ffplay -nodisp
        if self._video_cap is not None:
            self._start_video_playback(seg.start, seg.end)
        else:
            self._play_segment_range(seg)

    def _play_segment_range(self, seg: Segment):
        """播放指定分段的时间范围。ffmpeg 精准 seek → 管道 → ffplay"""
        fp = self.audio_file or self.original_file
        if not fp or not os.path.exists(fp):
            return
        self._on_stop()
        try:
            ffplay = AudioProcessor._get_ffplay()
            ffmpeg = AudioProcessor._get_ffmpeg()
            duration = seg.end - seg.start
            if duration <= 0:
                return
            vol = max(0, min(100, int(self.volume_var.get())))
            # ffmpeg 按采样精度 seek，通过管道输出 WAV 给 ffplay
            self._ffmpeg_proc = subprocess.Popen([
                ffmpeg, "-ss", f"{seg.start:.3f}",
                "-t", f"{duration:.3f}",
                "-i", fp,
                "-f", "wav", "pipe:1"
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
               creationflags=subprocess.CREATE_NO_WINDOW)
            self._ffplay_process = subprocess.Popen([
                ffplay, "-nodisp", "-autoexit",
                "-volume", str(vol), "pipe:0"
            ], stdin=self._ffmpeg_proc.stdout,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               creationflags=subprocess.CREATE_NO_WINDOW)
            self._ffmpeg_proc.stdout.close()
            self._play_start_time = time.time()
            self._play_seg_start = seg.start
            self._play_seg_end = seg.end
            self._check_ffplay_done()
            self._update_seg_playback_progress()
        except Exception as e:
            print(f"[Playback] {e}")

    def _on_export(self, fmt: str):
        if not self.segments:
            return
        ext_map = {"srt": "SRT 字幕", "ass": "ASS 字幕", "json": "JSON"}
        fp = filedialog.asksaveasfilename(title=f"导出{ext_map[fmt]}", defaultextension=f".{fmt}", filetypes=[(ext_map[fmt], f"*.{fmt}")])
        if not fp:
            return
        try:
            bil = self.bilingual_var.get()
            if fmt == "srt":
                Exporter.to_srt(self.segments, fp, bil)
            elif fmt == "ass":
                Exporter.to_ass(self.segments, fp, bil)
            else:
                Exporter.to_json(self.segments, fp)
            messagebox.showinfo("导出成功", f"已导出到:\n{fp}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ---- SRT Import ----
    def _on_import_srt(self):
        """导入 SRT 字幕文件，匹配时间到已有分段，替换原文或译文"""
        fp = filedialog.askopenfilename(
            title="导入 SRT 字幕",
            filetypes=[("SRT 字幕", "*.srt"), ("所有文件", "*.*")]
        )
        if not fp:
            return
        try:
            entries = self._parse_srt(fp)
        except Exception as e:
            messagebox.showerror("解析失败", f"SRT 文件格式错误:\n{e}")
            return
        if not entries:
            messagebox.showinfo("提示", "SRT 文件中没有有效条目")
            return

        # 询问替换模式
        mode_dlg = tk.Toplevel(self.root)
        mode_dlg.title("导入模式")
        mode_dlg.geometry("360x150")
        mode_dlg.configure(bg=THEME["bg_mid"])
        mode_dlg.transient(self.root)
        mode_dlg.grab_set()
        mode_dlg.update_idletasks()
        mx = self.root.winfo_x() + (self.root.winfo_width() - 360) // 2
        my = self.root.winfo_y() + (self.root.winfo_height() - 150) // 2
        mode_dlg.geometry(f"+{mx}+{my}")

        ttk.Label(mode_dlg, text=f"检测到 {len(entries)} 条字幕\n"
                  "按时间范围匹配已有分段，替换哪一列？",
                  style="Subtitle.TLabel").pack(pady=(20, 10), padx=20)
        bf = ttk.Frame(mode_dlg, style="Panel.TFrame")
        bf.pack()

        def do_import(target: str):
            mode_dlg.destroy()
            self._apply_srt_import(entries, target)

        ttk.Button(bf, text="替换原文",
                   command=lambda: do_import("text"),
                   style="Primary.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="替换译文",
                   command=lambda: do_import("translation"),
                   style="Primary.TButton").pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="取消",
                   command=mode_dlg.destroy,
                   style="Secondary.TButton").pack(side=tk.LEFT, padx=4)

    def _parse_srt(self, filepath: str) -> list:
        """解析 SRT 文件，返回 [(start_sec, end_sec, text), ...]"""
        entries = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            content = f.read().strip()
        blocks = [b.strip() for b in re.split(r'\n\s*\n', content) if b.strip()]
        for block in blocks:
            lines = block.splitlines()
            if len(lines) < 3:
                # 跳过序号行，找时间行
                time_line = None
                text_lines = []
                for line in lines:
                    if '-->' in line and time_line is None:
                        time_line = line
                    elif time_line is not None:
                        text_lines.append(line)
                if time_line is None:
                    continue
                text = "\n".join(text_lines).strip()
            else:
                # 标准格式：序号 / 时间 / 文本
                time_line = lines[1] if len(lines) > 1 else lines[0]
                text = "\n".join(lines[2:]).strip()
            if not time_line or not text:
                continue
            # 解析时间
            m = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*'
                         r'(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})', time_line)
            if not m:
                continue
            start = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                     + int(m.group(3)) + int(m.group(4)) / 1000)
            end = (int(m.group(5)) * 3600 + int(m.group(6)) * 60
                   + int(m.group(7)) + int(m.group(8)) / 1000)
            if end > start:
                entries.append((start, end, text))
        return entries

    def _apply_srt_import(self, entries: list, target: str):
        """将 SRT 条目按时间匹配到已有分段，或追加新分段"""
        if not self.segments:
            # 没有已有分段，直接创建
            self.segments = []
            for i, (start, end, text) in enumerate(entries):
                seg = Segment(index=i, start=start, end=end,
                              text=text if target == "text" else "",
                              speaker="SPEAKER_00")
                if target == "translation":
                    seg.translated = True
                    seg.translation = text
                self.segments.append(seg)
            self.result = ASRResult(audio_file=self.original_file,
                                     segments=self.segments,
                                     total_duration=self.segments[-1].end)
            self._display_results()
            return

        matched = 0
        used_seg_indices = set()
        unmatched_entries = []

        # 第一阶段：精确匹配（0.5 秒容差）
        for entry_idx, (start, end, text) in enumerate(entries):
            found = False
            for seg in self.segments:
                if (abs(seg.start - start) < 0.5
                        and abs(seg.end - end) < 0.5):
                    if target == "text":
                        seg.text = text
                    else:
                        seg.translated = True
                        seg.translation = text
                    found = True
                    matched += 1
                    used_seg_indices.add(seg.index)
                    break
            if not found:
                unmatched_entries.append((start, end, text))

        # 第二阶段：未匹配的 SRT 条目 → 未匹配的空白分段（按时间顺序配对）
        unmatched_segs = [seg for seg in self.segments
                          if seg.index not in used_seg_indices and not seg.text.strip()]
        for i, (start, end, text) in enumerate(unmatched_entries):
            if i < len(unmatched_segs):
                seg = unmatched_segs[i]
                if target == "text":
                    seg.text = text
                else:
                    seg.translated = True
                    seg.translation = text
                matched += 1
                used_seg_indices.add(seg.index)
            else:
                # 第三阶段：剩余未匹配的追加到末尾
                new_idx = len(self.segments)
                seg = Segment(index=new_idx, start=start, end=end,
                              text=text if target == "text" else "",
                              speaker="SPEAKER_00")
                if target == "translation":
                    seg.translated = True
                    seg.translation = text
                self.segments.append(seg)
        # 重新编号
        for i, seg in enumerate(self.segments):
            seg.index = i
        self.result.total_duration = self.segments[-1].end
        self._display_results()
        messagebox.showinfo(
            "导入完成",
            f"匹配 {matched} 段，追加 {len(entries) - matched} 段")

    # ---- Waveform ----
    def _draw_empty_waveform(self, dur: float):
        self.wave_canvas.delete("all")
        w = max(self.wave_canvas.winfo_width(), 600)
        h = max(self.wave_canvas.winfo_height(), 100)
        self.wave_canvas.create_rectangle(0, 0, w, h, fill=THEME["bg_mid"], outline="")
        self.wave_canvas.create_line(0, h//2, w, h//2, fill=THEME["border"], dash=(4,4))
        text = f"音频时长: {self._fmt_time(dur)}" if dur > 0 else "上传音频文件以查看波形"
        self.wave_canvas.create_text(w//2, h//2, text=text, fill=THEME["fg_dim"], font=("Microsoft YaHei UI", 12))

    def _draw_result_waveform(self):
        self.wave_canvas.delete("all")
        w = max(self.wave_canvas.winfo_width(), 600)
        h = max(self.wave_canvas.winfo_height(), 100)
        self.wave_canvas.create_rectangle(0, 0, w, h, fill=THEME["bg_mid"], outline="")
        if not self.segments:
            return
        total = self.segments[-1].end
        if total <= 0:
            return
        colors = {"SPEAKER_00": "#6c63ff","SPEAKER_01": "#4caf50","SPEAKER_02": "#ff9800","SPEAKER_03": "#f44336"}
        sh = max(h - 20, 10)
        for seg in self.segments:
            x1, x2 = int(seg.start/total*w), int(seg.end/total*w)
            color = colors.get(seg.speaker, THEME["success"]) if seg.translated else THEME["fg_dim"]
            self.wave_canvas.create_rectangle(x1, 10, max(x2, x1+2), 10+sh, fill=color, outline="")
        mid_y = 10 + sh//2
        for i in range(6):
            t = total * i / 5
            x = int(w * i / 5)
            self.wave_canvas.create_line(x, mid_y-8, x, mid_y+8, fill=THEME["border"])
            self.wave_canvas.create_text(x, mid_y+18, text=self._fmt_time(t), fill=THEME["fg_dim"], font=("Microsoft YaHei UI", 8), anchor=tk.N)

    def _update_progress(self, v: int, label: str):
        self.root.after(0, lambda: self.progress_var.set(v))
        self.root.after(0, lambda: self.progress_label_var.set(label))

    def _update_seg_playback_progress(self):
        """更新分段播放进度"""
        if not hasattr(self, "_ffplay_process") or not self._ffplay_process:
            return
        if not hasattr(self, "_play_seg_start"):
            return
        if self._ffplay_process.poll() is not None:
            self._ffplay_process = None
            return
        elapsed = time.time() - self._play_start_time
        pos = self._play_seg_start + elapsed
        dur = self._play_seg_end
        total = self.result.total_duration if self.result else dur
        if total > 0:
            self.seek_var.set(min(pos / total * 100, 100))
        self.time_var.set(f"{self._fmt_time(pos)} / {self._fmt_time(dur)}")
        self.root.after(100, self._update_seg_playback_progress)

    # ---- Segment Editing ----
    def _open_edit_dialog(self, idx: int):
        """打开分段编辑对话框"""
        seg = self.segments[idx]
        dlg = tk.Toplevel(self.root)
        dlg.title(f"编辑分段 #{seg.index + 1}")
        dlg.geometry("600x420")
        dlg.configure(bg=THEME["bg_mid"])
        dlg.transient(self.root)
        dlg.grab_set()
        # 居中
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 420) // 2
        dlg.geometry(f"+{x}+{y}")

        pad = {"padx": 16, "pady": (8, 2)}
        # 时间范围
        tf = ttk.Frame(dlg, style="Card.TFrame")
        tf.pack(fill=tk.X, padx=16, pady=(16, 0))
        ttk.Label(tf, text="时间范围（秒，精确到毫秒）",
                  style="Subtitle.TLabel").pack(anchor=tk.W, **pad)
        tr = ttk.Frame(tf, style="Card.TFrame"); tr.pack(fill=tk.X, padx=16)
        ttk.Label(tr, text="开始:", style="Dim.TLabel").pack(side=tk.LEFT)
        start_var = tk.StringVar(value=f"{seg.start:.3f}")
        ttk.Entry(tr, textvariable=start_var, width=12).pack(side=tk.LEFT, padx=(4, 16))
        ttk.Label(tr, text="结束:", style="Dim.TLabel").pack(side=tk.LEFT)
        end_var = tk.StringVar(value=f"{seg.end:.3f}")
        ttk.Entry(tr, textvariable=end_var, width=12).pack(side=tk.LEFT, padx=(4, 0))

        # 说话人
        spf = ttk.Frame(dlg, style="Card.TFrame")
        spf.pack(fill=tk.X, padx=16, pady=(8, 0))
        ttk.Label(spf, text="说话人", style="Subtitle.TLabel").pack(anchor=tk.W, **pad)
        speaker_var = tk.StringVar(value=seg.speaker or "")
        ttk.Entry(spf, textvariable=speaker_var).pack(fill=tk.X, padx=16, pady=(0, 4))

        # 原文
        of = ttk.Frame(dlg, style="Card.TFrame")
        of.pack(fill=tk.X, padx=16, pady=(8, 0))
        ttk.Label(of, text="原文", style="Subtitle.TLabel").pack(anchor=tk.W, **pad)
        text_var = tk.StringVar(value=seg.text)
        ttk.Entry(of, textvariable=text_var).pack(fill=tk.X, padx=16, pady=(0, 4))

        # 译文
        tf2 = ttk.Frame(dlg, style="Card.TFrame")
        tf2.pack(fill=tk.X, padx=16, pady=(8, 0))
        ttk.Label(tf2, text="译文", style="Subtitle.TLabel").pack(anchor=tk.W, **pad)
        trans_var = tk.StringVar(value=seg.translation if seg.translated else "")
        ttk.Entry(tf2, textvariable=trans_var).pack(fill=tk.X, padx=16, pady=(0, 4))

        # 按钮
        bf = ttk.Frame(dlg, style="Card.TFrame")
        bf.pack(fill=tk.X, padx=16, pady=(16, 16))

        def on_save():
            old_start, old_end = seg.start, seg.end
            try:
                seg.start = float(start_var.get())
                seg.end = float(end_var.get())
            except ValueError:
                messagebox.showwarning("格式错误", "时间必须是数字（如 12.345）", parent=dlg)
                return
            time_changed = (abs(seg.start - old_start) > 0.001
                            or abs(seg.end - old_end) > 0.001)
            seg.speaker = speaker_var.get()
            seg.text = text_var.get()
            trans = trans_var.get()
            if trans:
                seg.translation = trans
                seg.translated = True
            # 时间变更 → 清理旧的 TTS 缓存
            if time_changed:
                tts_map = getattr(self, "_tts_map", {}) or {}
                tts_map.pop(seg.index, None)
                tts_raw_map = getattr(self, "_tts_raw_map", {}) or {}
                tts_raw_map.pop(seg.index, None)
                failed = getattr(self, "_tts_failed_indices", set())
                failed.discard(seg.index)
            # 刷新 Treeview
            item = self.tree.get_children()[idx]
            ts = f"{self._fmt_time(seg.start)} → {self._fmt_time(seg.end)}"
            trans_display = seg.translation if seg.translation else ("⏳" if not seg.translated else "")
            tts_map = getattr(self, "_tts_map", {}) or {}
            play_display = "▶" if seg.index in tts_map else "—"
            self.tree.item(item, values=(
                seg.index + 1, ts, seg.speaker or "-",
                seg.text, trans_display, play_display
            ))
            # 时间变更 → 刷新波形并跳转视频预览
            if time_changed:
                self._draw_result_waveform()
                if self._video_cap is not None:
                    self._video_seek_time = seg.start
                    self._show_video_frame_at(seg.start)
            dlg.destroy()

        ttk.Button(bf, text="保存", command=on_save,
                   style="TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bf, text="取消", command=dlg.destroy,
                   style="Secondary.TButton").pack(side=tk.RIGHT)

    def _on_segment_right_click(self, event):
        """右键菜单"""
        sel = self.tree.selection()
        self._ctx_menu.delete(0, tk.END)
        if sel and self.segments:
            idx = int(self.tree.item(sel[0])["values"][0]) - 1
            self._ctx_menu.add_command(
                label="编辑此段", command=lambda i=idx: self._open_edit_dialog(i))
            self._ctx_menu.add_command(
                label="翻译此段",
                command=lambda i=idx: self._on_translate_segment(i))
            self._ctx_menu.add_command(
                label="合成此段配音",
                command=lambda i=idx: self._on_synthesize_segment(i))
            self._ctx_menu.add_command(
                label="试听原音频",
                command=lambda i=idx: self._on_preview_segment(i))
            self._ctx_menu.add_separator()
            self._ctx_menu.add_command(
                label="在此位置新增分段",
                command=lambda i=idx: self._on_add_segment(i))
            self._ctx_menu.add_command(
                label="删除此段",
                command=lambda i=idx: self._on_delete_segment(i))
            self._ctx_menu.add_command(
                label="替换参考音频",
                command=lambda i=idx: self._on_replace_ref_audio(i))
        else:
            self._ctx_menu.add_command(
                label="在末尾新增分段",
                command=lambda: self._on_add_segment(len(self.segments) - 1))
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _on_add_segment(self, after_idx: int):
        """在指定位置后新增分段"""
        if not self.segments:
            return
        ref = self.segments[after_idx]
        new_seg = Segment(
            index=len(self.segments),
            start=ref.end, end=ref.end + 2.000,
            text="", speaker=ref.speaker,
        )
        self.segments.insert(after_idx + 1, new_seg)
        # 重新编号
        for i, seg in enumerate(self.segments):
            seg.index = i
        # 清空 TTS 缓存（索引已变，旧音频不再匹配）
        self._tts_map = {}
        self._tts_raw_map = {}
        self._tts_failed_indices = set()
        self._display_results()

    def _on_delete_segment(self, idx: int):
        """删除指定分段"""
        if not self.segments or idx < 0 or idx >= len(self.segments):
            return
        del self.segments[idx]
        for i, seg in enumerate(self.segments):
            seg.index = i
        # 清空 TTS 缓存（索引已变，旧音频不再匹配）
        self._tts_map = {}
        self._tts_raw_map = {}
        self._tts_failed_indices = set()
        self._display_results()

    def _on_replace_ref_audio(self, idx: int):
        """替换参考音频（用于 TTS 参考）"""
        fp = filedialog.askopenfilename(
            title="选择参考音频",
            filetypes=[("音频", "*.wav *.mp3 *.flac *.ogg *.m4a"), ("所有", "*.*")]
        )
        if not fp:
            return
        if not hasattr(self, "_ref_audio_map"):
            self._ref_audio_map = {}
        self._ref_audio_map[idx] = fp
        messagebox.showinfo("已设置", f"分段 #{idx+1} 的参考音频已替换")

    # ---- Translation ----
    def _on_translate_all(self):
        if not self.translator:
            messagebox.showinfo("提示", "请先处理音频"); return
        if not self.api_key_var.get().strip():
            messagebox.showinfo("提示", "请填写 MiMo API Key"); return
        self.translate_all_btn.configure(state="disabled")
        self.tts_progress_var.set("翻译中... 0/{}".format(len(self.segments)))
        threading.Thread(target=self._translate_all_thread, daemon=True).start()

    def _translate_all_thread(self):
        try:
            def cb(cur, tot):
                self.root.after(0, lambda c=cur, t=tot: self.tts_progress_var.set(
                    f"翻译中... {c}/{t}"))
            self.segments = self.translator.translate_segments(
                self.segments, progress_callback=cb)
            done = sum(1 for s in self.segments if s.translated)
            self.root.after(0, lambda: self.tts_progress_var.set(
                f"翻译完成: {done}/{len(self.segments)} 段"))
            self.root.after(0, self._display_results)
        except Exception as e:
            self.root.after(0, lambda: self.tts_progress_var.set(f"翻译失败: {e}"))
            self.root.after(0, lambda: messagebox.showerror("翻译失败", str(e)))
        finally:
            self.root.after(0, lambda: self.translate_all_btn.configure(state="normal"))

    def _on_retry_failed(self):
        """重试所有翻译失败的分段"""
        if not self.translator or not self.api_key_var.get().strip():
            return
        # 筛选失败分段
        failed_indices = [
            i for i, seg in enumerate(self.segments)
            if not seg.translated or (seg.text.strip() and seg.translation.startswith("[翻译失败:"))
        ]
        if not failed_indices:
            messagebox.showinfo("提示", "没有翻译失败的分段")
            return
        self.retry_translate_btn.configure(state="disabled")
        self.translate_all_btn.configure(state="disabled")
        self.tts_progress_var.set(f"重试翻译中... 0/{len(failed_indices)}")
        threading.Thread(target=self._retry_failed_thread,
                         args=(failed_indices,), daemon=True).start()

    def _retry_failed_thread(self, failed_indices):
        try:
            def cb(cur, tot):
                self.root.after(0, lambda c=cur, t=tot: self.tts_progress_var.set(
                    f"重试翻译中... {c}/{t}"))
            self.segments = self.translator.translate_segments(
                self.segments, progress_callback=cb,
                target_indices=failed_indices)
            done = sum(1 for i in failed_indices if self.segments[i].translated)
            self.root.after(0, lambda: self.tts_progress_var.set(
                f"重试完成: {done}/{len(failed_indices)} 段"))
            self.root.after(0, self._display_results)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("重试失败", str(e)))
        finally:
            self.root.after(0, lambda: self.retry_translate_btn.configure(state="normal"))
            self.root.after(0, lambda: self.translate_all_btn.configure(state="normal"))

    def _on_translate_segment(self, idx: int):
        if idx < 0 or idx >= len(self.segments):
            return
        if not self.translator:
            messagebox.showinfo("提示", "请先处理音频"); return
        if not self.api_key_var.get().strip():
            messagebox.showinfo("提示", "请填写 MiMo API Key"); return
        seg = self.segments[idx]
        if not seg.text.strip():
            messagebox.showinfo("提示", "该段无原文，无法翻译"); return
        self.tts_progress_var.set(f"翻译 #{idx+1}...")
        threading.Thread(target=self._translate_single_thread,
                         args=(idx,), daemon=True).start()

    def _translate_single_thread(self, idx: int):
        try:
            self.segments = self.translator.translate_segments(
                self.segments, progress_callback=None,
                target_indices=[idx])
            seg = self.segments[idx]
            status = "完成" if seg.translated else "失败"
            self.root.after(0, lambda: self.tts_progress_var.set(
                f"#{idx+1} 翻译{status}"))
            self.root.after(0, self._display_results)
        except Exception as e:
            self.root.after(0, lambda: self.tts_progress_var.set(f"#{idx+1} 翻译失败: {e}"))

    # ---- TTS ----
    def _on_synthesize_all(self):
        """一键合成所有分段配音"""
        if not self.segments:
            return
        if not self.api_key_var.get().strip():
            messagebox.showinfo("提示", "请先填写 MiMo API Key")
            return
        self.synth_all_btn.configure(state="disabled")
        self.tts_progress_var.set("合成中...")
        self.export_dub_btn.configure(state="disabled")
        threading.Thread(target=self._synthesize_all_thread, daemon=True).start()

    def _synthesize_all_thread(self):
        try:
            tts = TTSEngine(api_key=self.api_key_var.get())
            out_dir = os.path.join(tempfile.gettempdir(), "voicetrans_tts")
            os.makedirs(out_dir, exist_ok=True)
            # 预检查：验证 API Key 有效性
            try:
                import requests as _req
                _resp = _req.get("https://api.xiaomimimo.com/v1/models",
                                 headers={"api-key": self.api_key_var.get()},
                                 timeout=10)
                if _resp.status_code == 401:
                    self.root.after(0, lambda: (
                        self.tts_progress_var.set("失败: API Key 无效"),
                        self.synth_all_btn.configure(state="normal"),
                        messagebox.showerror("API 错误", "MiMo API Key 无效 (401)，请重新获取有效的 API Key")
                    ))
                    return
            except Exception:
                pass  # 网络不通则跳过预检查，让后续合成自然报错
            # 切割原始音频作为参考音色素材
            ref_audio_map = {}
            fp = self.audio_file if (self.audio_file and os.path.exists(self.audio_file)) else self.original_file
            if not fp or not os.path.exists(fp):
                self.root.after(0, lambda: (
                    self.tts_progress_var.set("失败: 无原始音频"),
                    self.synth_all_btn.configure(state="normal")
                ))
                return
            try:
                ref_dir = os.path.join(out_dir, "_ref")
                AudioSplitter.split_by_segments(fp, self.segments, ref_dir)
                for seg in self.segments:
                    ref_path = os.path.join(
                        ref_dir, f"seg_{seg.index:04d}.wav")
                    if os.path.exists(ref_path):
                        ref_audio_map[seg.index] = ref_path
            except Exception as e:
                print(f"[TTS] 参考音频切割失败: {e}")
                self.root.after(0, lambda: (
                    self.tts_progress_var.set(f"失败: {e}"),
                    self.synth_all_btn.configure(state="normal")
                ))
                return
            # 并行合成：每个任务独立创建 TTSEngine 实例，避免跨线程共享状态
            progress_lock = threading.Lock()
            error_lock = threading.Lock()
            cur = [0]
            tot = len(self.segments)
            tts_map = {}
            tts_errors = []

            def _sync_progress():
                with progress_lock:
                    cur[0] += 1
                self.root.after(0, lambda c=cur[0], t=tot: self.tts_progress_var.set(
                    f"合成中... {c}/{t}"))

            def _synth_one(seg, api_key, ref_map, odir):
                if not (seg.translated and seg.translation):
                    return seg.index, None, None
                try:
                    tts_local = TTSEngine(api_key=api_key)
                    out = os.path.join(odir, f"tts_{seg.index:04d}.wav")
                    ref_path = ref_map.get(seg.index, "")
                    if not ref_path:
                        raise RuntimeError("缺少参考音频")
                    tts_local.synthesize(seg.translation, out, reference_audio_path=ref_path)
                    _sync_progress()
                    return seg.index, out, None
                except Exception as e:
                    _sync_progress()
                    return seg.index, None, f"#{seg.index+1}: {e}"

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(
                    _synth_one, seg, self.api_key_var.get(),
                    ref_audio_map, out_dir) for seg in self.segments]
                for future in as_completed(futures):
                    idx, path, err = future.result()
                    if path:
                        tts_map[idx] = path
                    if err:
                        with error_lock:
                            tts_errors.append(err)
            self._tts_map = tts_map
            # 逐段变速对齐原分段时长
            self._tts_raw_map = {}
            aligned_map = {}
            for seg_idx, tts_path in self._tts_map.items():
                seg = self.segments[seg_idx]
                aligned = os.path.join(out_dir,
                                       f"tts_{seg_idx:04d}_aligned.wav")
                seg_duration = seg.end - seg.start
                try:
                    AudioSplitter.speed_adjust(tts_path, aligned,
                                               seg_duration)
                    aligned_map[seg_idx] = aligned
                    self._tts_raw_map[seg_idx] = tts_path
                except Exception as ae:
                    print(f"[TTS] 变速对齐 #{seg_idx+1} 失败: {ae}")
                    aligned_map[seg_idx] = tts_path
            self._tts_map = aligned_map
            total = len(self.segments)
            done = len(self._tts_map)
            # 收集合成失败的索引
            self._tts_failed_indices = set()
            if tts_errors:
                import re
                for err in tts_errors:
                    m = re.match(r'#(\d+):', err)
                    if m:
                        self._tts_failed_indices.add(int(m.group(1)))
                err_summary = "; ".join(tts_errors[:3])
                if len(tts_errors) > 3:
                    err_summary += f" ...等 {len(tts_errors)} 段失败"
                self.root.after(0, lambda: self.tts_progress_var.set(
                    f"完成: {done}/{total}, 失败: {len(tts_errors)}"))
                self.root.after(0, lambda: messagebox.showwarning(
                    "合成完成（有错误）",
                    f"{done}/{total} 段成功\n{len(tts_errors)} 段失败\n\n{err_summary}"))
            else:
                self.root.after(0, lambda: self.tts_progress_var.set(
                    f"完成: {done}/{total} 段"))
            self.root.after(0, lambda: self.export_dub_btn.configure(
                state="normal"))
            self.root.after(0, self._refresh_play_column)
        except Exception as e:
            self.root.after(0, lambda: self.tts_progress_var.set(f"失败: {e}"))
            self.root.after(0, lambda: messagebox.showerror("合成失败", str(e)))
        finally:
            self.root.after(0, lambda: self.synth_all_btn.configure(
                state="normal"))

    def _on_synthesize_segment(self, idx: int):
        """右键菜单：单独合成某一分段"""
        if idx < 0 or idx >= len(self.segments):
            return
        seg = self.segments[idx]
        if not (seg.translated and seg.translation):
            messagebox.showinfo("提示", "该段没有译文，无法合成")
            return
        if not self.api_key_var.get().strip():
            messagebox.showinfo("提示", "请先填写 MiMo API Key")
            return
        self.tts_progress_var.set(f"合成 #{idx+1}...")
        threading.Thread(target=self._synth_single_thread,
                         args=(idx,), daemon=True).start()

    def _on_preview_segment(self, idx: int):
        """试听：播放该分段对应的原始音频片段"""
        if idx < 0 or idx >= len(self.segments):
            return
        seg = self.segments[idx]
        fp = self.audio_file if (self.audio_file and os.path.exists(self.audio_file)) else self.original_file
        if not fp or not os.path.exists(fp):
            messagebox.showinfo("提示", "没有原始音频，无法试听")
            return
        preview_path = os.path.join(
            tempfile.gettempdir(), "voicetrans_preview",
            f"preview_{seg.index:04d}.wav")
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)
        try:
            AudioSplitter.split_single(fp, seg, preview_path)
        except Exception as e:
            messagebox.showerror("试听失败", f"音频切割失败:\n{e}")
            return
        ffplay = AudioProcessor._get_ffmpeg().replace(
            "ffmpeg.exe", "ffplay.exe").replace("ffmpeg", "ffplay")
        subprocess.Popen([ffplay, "-nodisp", "-autoexit", preview_path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW)

    def _synth_single_thread(self, idx: int):
        try:
            tts = TTSEngine(api_key=self.api_key_var.get())
            out_dir = os.path.join(tempfile.gettempdir(), "voicetrans_tts")
            os.makedirs(out_dir, exist_ok=True)
            seg = self.segments[idx]
            out = os.path.join(out_dir, f"tts_{seg.index:04d}.wav")
            # 切割对应时间段原始音频作为参考音色
            ref_path = ""
            fp = self.audio_file if (self.audio_file and os.path.exists(self.audio_file)) else self.original_file
            if fp and os.path.exists(fp):
                try:
                    ref_dir = os.path.join(out_dir, "_ref_single")
                    AudioSplitter.split_by_segments(fp, [seg], ref_dir)
                    ref_path = os.path.join(ref_dir, f"seg_{seg.index:04d}.wav")
                    if not os.path.exists(ref_path):
                        ref_path = ""
                except Exception as re:
                    print(f"[TTS] 参考音频切割失败: {re}")
            if not ref_path:
                raise RuntimeError("没有原始音频，无法进行音色克隆合成。请先导入音频文件。")
            tts.synthesize(seg.translation, out, reference_audio_path=ref_path)
            # 变速对齐原分段时长
            aligned = os.path.join(out_dir, f"tts_{seg.index:04d}_aligned.wav")
            seg_duration = seg.end - seg.start
            AudioSplitter.speed_adjust(out, aligned, seg_duration)
            if not hasattr(self, "_tts_map"):
                self._tts_map = {}
            self._tts_map[seg.index] = aligned
            self._tts_raw_map = getattr(self, "_tts_raw_map", {})
            self._tts_raw_map[seg.index] = out
            self.root.after(0, lambda: self.tts_progress_var.set(
                f"#{idx+1} 合成完成"))
            self.root.after(0, self._refresh_play_column)
        except Exception as e:
            if not hasattr(self, "_tts_failed_indices"):
                self._tts_failed_indices = set()
            self._tts_failed_indices.add(idx)
            self.root.after(0, lambda: self.tts_progress_var.set(f"#{idx+1} 失败: {e}"))

    def _refresh_play_column(self):
        """刷新所有行的试听列显示"""
        tts_map = getattr(self, "_tts_map", {}) or {}
        for item in self.tree.get_children():
            vals = list(self.tree.item(item)["values"])
            if len(vals) != 6:
                continue
            idx = int(vals[0]) - 1
            vals[5] = "▶" if idx in tts_map else "—"
            self.tree.item(item, values=vals)

    def _on_tree_click(self, event):
        """检测点击是否在试听列上"""
        col = self.tree.identify_column(event.x)
        if col == "#6":  # play 列
            item = self.tree.identify_row(event.y)
            if not item:
                return
            vals = self.tree.item(item)["values"]
            if len(vals) < 6:
                return
            seg_idx = int(vals[0]) - 1
            if seg_idx < 0 or seg_idx >= len(self.segments):
                return
            tts_map = getattr(self, "_tts_map", {}) or {}
            if seg_idx not in tts_map:
                return
            self._skip_select = True
            self._play_tts_for_segment(self.segments[seg_idx], tts_map[seg_idx])

    def _play_tts_for_segment(self, seg, tts_path):
        """播放指定分段的合成 TTS 音频"""
        if not os.path.exists(tts_path):
            messagebox.showinfo("提示", "合成音频文件不存在")
            return
        self._on_stop()
        try:
            ffplay = AudioProcessor._get_ffplay()
            vol = max(0, min(100, int(self.volume_var.get())))
            self._ffplay_process = subprocess.Popen([
                ffplay, "-nodisp", "-autoexit",
                "-volume", str(vol), tts_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               creationflags=subprocess.CREATE_NO_WINDOW)
            self._play_start_time = time.time()
            self._play_seg_start = seg.start
            self._play_seg_end = seg.end
            self._check_ffplay_done()
            self._update_seg_playback_progress()
        except Exception as e:
            print(f"[TTS Playback] {e}")

    def _on_export_dub(self):
        """一键导出：将所有合成音频按分段时间轴拼接为完整音频"""
        if not self.segments:
            return
        if not hasattr(self, "_tts_map") or not self._tts_map:
            messagebox.showinfo("提示", "请先合成配音")
            return
        fp = filedialog.asksaveasfilename(
            title="导出配音音频",
            defaultextension=".wav",
            filetypes=[("WAV 音频", "*.wav"), ("MP3 音频", "*.mp3")]
        )
        if not fp:
            return
        self.tts_progress_var.set("导出中...")
        threading.Thread(target=self._export_dub_thread,
                         args=(fp,), daemon=True).start()

    def _export_dub_thread(self, output_path: str):
        try:
            fp = self.audio_file or self.original_file
            AudioSplitter.concat_with_silence(
                self.segments, self._tts_map, output_path, fp)
            self.root.after(0, lambda: self.tts_progress_var.set("导出完成"))
            self.root.after(0, lambda: messagebox.showinfo(
                "导出成功", f"配音已导出到:\n{output_path}"))
        except Exception as e:
            self.root.after(0, lambda: self.tts_progress_var.set(f"导出失败: {e}"))
            self.root.after(0, lambda: messagebox.showerror("导出失败", str(e)))

    # ---- Video Preview ----
    def _init_video_preview(self):
        """初始化视频预览（使用 OpenCV）"""
        if not self.original_file:
            return
        ext = os.path.splitext(self.original_file)[1].lower()
        if ext not in ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm'):
            return
        self._release_video()
        try:
            import cv2
            self._video_cap = cv2.VideoCapture(self.original_file)
            if not self._video_cap.isOpened():
                self._release_video()
                return
            self._video_duration = (
                self._video_cap.get(cv2.CAP_PROP_FRAME_COUNT) /
                max(self._video_cap.get(cv2.CAP_PROP_FPS), 1)
            )
            self.video_canvas.delete("placeholder")
            self.video_status_var.set(
                f"视频 {os.path.basename(self.original_file)}")
            self._show_video_frame()
        except ImportError:
            self.video_status_var.set("需安装 opencv-python")
        except Exception as e:
            self.video_status_var.set(f"加载失败: {e}")
            self._release_video()

    def _show_video_frame(self):
        """显示视频当前帧到 Canvas（毫秒级寻址）"""
        if self._video_cap is None:
            return
        try:
            import cv2
            from PIL import Image, ImageTk
            # 毫秒级精确定位
            self._video_cap.set(cv2.CAP_PROP_POS_MSEC, self._video_seek_time * 1000)
            ret, frame = self._video_cap.read()
            if not ret:
                fps = self._video_cap.get(cv2.CAP_PROP_FPS) or 30
                self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, int(self._video_seek_time * fps))
                ret, frame = self._video_cap.read()
                if not ret:
                    return
            cw = self.video_canvas.winfo_width()
            ch = self.video_canvas.winfo_height()
            if cw < 10:
                cw = 400
            if ch < 10:
                ch = 200
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame.shape[:2]
            scale = min(cw / w, ch / h)
            nw, nh = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (nw, nh))
            img = Image.fromarray(frame)
            self._video_tk_img = ImageTk.PhotoImage(img)
            self.video_canvas.delete("all")
            self.video_canvas.create_image(
                cw // 2, ch // 2, image=self._video_tk_img, anchor=tk.CENTER)
            # 时间戳在状态栏显示，不叠加到画面
            self.video_status_var.set(
                f"视频 {os.path.basename(self.original_file)} | {self._fmt_time(self._video_seek_time)}")
        except Exception as e:
            self.video_status_var.set(f"帧错误: {e}")

    def _show_video_frame_at(self, t: float):
        """定位到指定时间并渲染帧到 Canvas（使用毫秒级寻址）"""
        if self._video_cap is None:
            return
        try:
            import cv2
            from PIL import Image, ImageTk
            # 毫秒级精确定位，比 frame_no 更准确（尤其对可变帧率视频）
            self._video_cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ret, frame = self._video_cap.read()
            if not ret:
                # 回退到帧号定位
                fps = self._video_cap.get(cv2.CAP_PROP_FPS) or 30
                self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
                ret, frame = self._video_cap.read()
                if not ret:
                    return
            cw = self.video_canvas.winfo_width()
            ch = self.video_canvas.winfo_height()
            if cw < 10:
                cw = 400
            if ch < 10:
                ch = 200
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame.shape[:2]
            scale = min(cw / w, ch / h)
            nw, nh = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (nw, nh))
            img = Image.fromarray(frame)
            self._video_tk_img = ImageTk.PhotoImage(img)
            self.video_canvas.delete("all")
            self.video_canvas.create_image(
                cw // 2, ch // 2, image=self._video_tk_img, anchor=tk.CENTER)
        except Exception as e:
            pass  # 帧渲染失败不影响播放流程

    def _start_video_playback(self, start_time: float, end_time: float):
        """在现有视频预览窗口内播放指定时间范围。
        视频帧由后台线程解码，主线程只渲染；音频用 ffplay -nodisp 后台播放。"""
        self._stop_video_playback()
        if self._video_cap is None:
            return
        duration = end_time - start_time
        if duration <= 0:
            return
        try:
            import cv2, queue, random
            ffplay = AudioProcessor._get_ffplay()
            ffmpeg = AudioProcessor._get_ffmpeg()
            vol = max(0, min(100, int(self.volume_var.get())))
            # 后台播放音频：ffmpeg 精准 seek → 管道 → ffplay
            self._video_ffmpeg_proc = subprocess.Popen([
                ffmpeg, "-ss", f"{start_time:.3f}",
                "-t", f"{duration:.3f}",
                "-i", self.original_file,
                "-f", "wav", "pipe:1"
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
               creationflags=subprocess.CREATE_NO_WINDOW)
            self._video_audio_proc = subprocess.Popen([
                ffplay, "-nodisp", "-autoexit",
                "-volume", str(vol), "pipe:0"
            ], stdin=self._video_ffmpeg_proc.stdout,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               creationflags=subprocess.CREATE_NO_WINDOW)
            self._video_ffmpeg_proc.stdout.close()
            fps = self._video_cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30
            # 在 ffplay 启动后再记录 wall time，确保音视频时间基准一致
            self._video_play_start_wall = time.time()
            self._video_play_start = start_time
            self._video_play_end = end_time
            self._video_play_fps = fps
            self.video_status_var.set(
                f"播放中 [{self._fmt_time_short(start_time)} → {self._fmt_time_short(end_time)}]")
            # 后台线程解码帧，使用代际计数器防止旧线程污染新播放
            self._video_play_gen = random.randint(0, 2**31 - 1)
            self._video_frame_queue = queue.Queue(maxsize=2)
            self._video_decode_running = True
            self._video_decode_lock = threading.Lock()
            self._video_decode_thread = threading.Thread(
                target=self._video_decode_loop,
                args=(self._video_play_gen,), daemon=True)
            self._video_decode_thread.start()
            # 主线程渲染循环
            self._video_canvas_playback_loop()
        except Exception as e:
            self.video_status_var.set(f"播放失败: {e}")

    def _video_decode_loop(self, my_gen: int):
        """后台线程：持续解码视频帧，放入队列供主线程渲染。
        my_gen 是代际 ID，与 _video_play_gen 比对，不匹配则立即退出。"""
        import cv2, queue
        while self._video_decode_running and getattr(self, "_video_play_gen", -1) == my_gen:
            elapsed = (time.time() - self._video_play_start_wall) * self._video_speed
            current_time = self._video_play_start + elapsed
            if current_time >= self._video_play_end:
                break
            with self._video_decode_lock:
                self._video_cap.set(cv2.CAP_PROP_POS_MSEC, current_time * 1000)
                ret, frame = self._video_cap.read()
            if ret and getattr(self, "_video_play_gen", -1) == my_gen:
                try:
                    self._video_frame_queue.put_nowait(frame)
                except queue.Full:
                    try:
                        self._video_frame_queue.get_nowait()
                        self._video_frame_queue.put_nowait(frame)
                    except queue.Empty:
                        pass
            time.sleep(0.03)

    def _video_canvas_playback_loop(self):
        """主线程渲染循环：从队列取最新帧并显示到 Canvas"""
        import queue
        if not hasattr(self, "_video_play_start") or self._video_cap is None:
            return
        elapsed = (time.time() - self._video_play_start_wall) * self._video_speed
        current_time = self._video_play_start + elapsed
        if current_time >= self._video_play_end:
            # 尝试取最后一帧
            try:
                frame = self._video_frame_queue.get_nowait()
                self._render_frame_to_canvas(frame, current_time)
            except queue.Empty:
                pass
            # 自然结束：不终止 ffplay，让其通过 -autoexit 自然退出
            self._video_decode_running = False
            if hasattr(self, "_video_play_timer") and self._video_play_timer:
                self.root.after_cancel(self._video_play_timer)
                self._video_play_timer = None
            return
        # 取队列中最新帧
        latest_frame = None
        while True:
            try:
                latest_frame = self._video_frame_queue.get_nowait()
            except queue.Empty:
                break
        if latest_frame is not None:
            self._render_frame_to_canvas(latest_frame, current_time)
        self._video_play_timer = self.root.after(
            30, self._video_canvas_playback_loop)

    def _render_frame_to_canvas(self, frame, timestamp):
        """将已解码帧渲染到 Canvas（必须在主线程调用）"""
        try:
            import cv2
            from PIL import Image, ImageTk
            cw = self.video_canvas.winfo_width()
            ch = self.video_canvas.winfo_height()
            if cw < 10:
                cw = 400
            if ch < 10:
                ch = 200
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame.shape[:2]
            scale = min(cw / w, ch / h)
            nw, nh = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (nw, nh))
            img = Image.fromarray(frame)
            self._video_tk_img = ImageTk.PhotoImage(img)
            self.video_canvas.delete("all")
            self.video_canvas.create_image(
                cw // 2, ch // 2, image=self._video_tk_img, anchor=tk.CENTER)
            # 叠加时间戳（Canvas 左下方）
            ts_text = self._fmt_time(timestamp)
            self.video_canvas.create_text(
                10, ch - 8, text=ts_text,
                fill="#ffffff", font=("Microsoft YaHei UI", 11, "bold"),
                anchor=tk.SW, tags=("timestamp",)
            )
            self.video_status_var.set(
                f"视频 {os.path.basename(self.original_file)} | {self._fmt_time(timestamp)}")
        except Exception as e:
            self.video_status_var.set(f"帧错误: {e}")

    def _stop_video_playback(self):
        """停止视频播放"""
        # 停止后台解码线程
        if hasattr(self, "_video_decode_running"):
            self._video_decode_running = False
        if hasattr(self, "_video_decode_thread") and self._video_decode_thread:
            self._video_decode_thread.join(timeout=0.5)
            self._video_decode_thread = None
        if hasattr(self, "_video_play_timer") and self._video_play_timer:
            self.root.after_cancel(self._video_play_timer)
            self._video_play_timer = None
        if hasattr(self, "_video_audio_proc") and self._video_audio_proc:
            try:
                self._video_audio_proc.terminate()
            except Exception:
                pass
            self._video_audio_proc = None
        if hasattr(self, "_video_ffmpeg_proc") and self._video_ffmpeg_proc:
            try:
                self._video_ffmpeg_proc.terminate()
            except Exception:
                pass
            self._video_ffmpeg_proc = None
        # 保留旧的 ffplay 进程清理（兼容旧代码）
        if hasattr(self, "_video_ffplay_process") and self._video_ffplay_process:
            try:
                self._video_ffplay_process.terminate()
            except Exception:
                pass
            self._video_ffplay_process = None
        for attr in ("_video_play_start", "_video_play_end",
                     "_video_play_start_wall", "_video_play_fps"):
            if hasattr(self, attr):
                delattr(self, attr)
        # 恢复状态栏
        if self._video_cap is not None:
            self.video_status_var.set(
                f"视频 {os.path.basename(self.original_file)}")

    def _set_video_speed(self, speed: float):
        """设置视频播放速度倍率"""
        self._video_speed = speed
        self._video_speed_var.set(speed)

    def _on_video_click(self, event):
        """单击视频画布：跳转到对应时间"""
        if self._video_cap is None or self._video_duration <= 0:
            return
        cw = self.video_canvas.winfo_width()
        if cw <= 0:
            return
        ratio = event.x / cw
        self._video_seek_time = ratio * self._video_duration
        self._show_video_frame()
        # 同时跳转音频播放
        self._seek_and_play(self._video_seek_time)

    def _seek_and_play(self, t: float):
        """跳转到指定时间并播放"""
        fp = self.audio_file or self.original_file
        if not fp or not os.path.exists(fp):
            return
        self._on_stop()
        try:
            ffplay = AudioProcessor._get_ffplay()
            vol = max(0, min(100, int(self.volume_var.get())))
            cmd = [
                ffplay, "-nodisp", "-autoexit",
                "-volume", str(vol),
                "-ss", f"{t:.3f}", fp
            ]
            self._ffplay_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            self._play_start_time = time.time()
            self._play_seg_start = t
            self._play_seg_end = self._video_duration
            self._check_ffplay_done()
            self._update_seg_playback_progress()
        except Exception as e:
            print(f"[Seek] {e}")

    def _release_video(self):
        self._stop_video_playback()
        if self._video_cap is not None:
            try:
                self._video_cap.release()
            except Exception:
                pass
            self._video_cap = None

    @staticmethod
    def _fmt_time(t: float) -> str:
        """格式化时间为 HH:MM:SS.mmm"""
        h, t = divmod(t, 3600)
        m, s = divmod(t, 60)
        ms = int(round((s - int(s)) * 1000))
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{ms:03d}"

    @staticmethod
    def _fmt_time_short(t: float) -> str:
        """格式化时间为 MM:SS.mmm（小于1小时时）"""
        m, s = divmod(t, 60)
        if m >= 60:
            return VoiceTransApp._fmt_time(t)
        ms = int(round((s - int(s)) * 1000))
        return f"{int(m):02d}:{int(s):02d}.{ms:03d}"


def main():
    root = tk.Tk()
    VoiceTransApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
