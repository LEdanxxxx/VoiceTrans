"""
VoiceTrans 核心引擎
- 音频/视频处理 (ffmpeg)
- ASR 语音识别 (MiMo API: mimo-v2.5)
- 翻译 (MiMo API: mimo-chat)
"""

import os
import sys
import json
import base64
import tempfile
import subprocess
import re
from dataclasses import dataclass, field

import requests


@dataclass
class Segment:
    """单个语音段落"""
    index: int
    start: float
    end: float
    text: str
    speaker: str = ""
    translation: str = ""
    translated: bool = False

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class TranscriptionResult:
    """完整转录结果"""
    segments: list = field(default_factory=list)
    language: str = ""
    total_duration: float = 0.0


class AudioProcessor:
    """使用 ffmpeg 处理音频/视频"""

    _ffmpeg_path = None
    _ffprobe_path = None

    @classmethod
    def _find_ffmpeg(cls) -> str:
        """智能查找 ffmpeg 可执行文件路径"""
        if cls._ffmpeg_path:
            return cls._ffmpeg_path

        import shutil
        # 0. PyInstaller 打包环境 (sys._MEIPASS)
        if getattr(sys, 'frozen', False):
            bundle_dir = sys._MEIPASS
            ffmpeg_candidate = os.path.join(bundle_dir, "ffmpeg.exe")
            if os.path.exists(ffmpeg_candidate):
                cls._ffmpeg_path = ffmpeg_candidate
                ffprobe_candidate = os.path.join(bundle_dir, "ffprobe.exe")
                cls._ffprobe_path = ffprobe_candidate if os.path.exists(ffprobe_candidate) \
                    else ffmpeg_candidate.replace("ffmpeg", "ffprobe")
                return ffmpeg_candidate

        # 1. 先尝试 PATH
        found = shutil.which("ffmpeg")
        if found:
            cls._ffmpeg_path = found
            cls._ffprobe_path = shutil.which("ffprobe") or found.replace("ffmpeg", "ffprobe")
            return found

        # 2. WinGet Links
        winget_root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links")
        for exe in ["ffmpeg.exe", "ffprobe.exe"]:
            p = os.path.join(winget_root, exe)
            if os.path.exists(p):
                if exe == "ffmpeg.exe":
                    cls._ffmpeg_path = p
                else:
                    cls._ffprobe_path = p

        if cls._ffmpeg_path:
            if not cls._ffprobe_path:
                cls._ffprobe_path = cls._ffmpeg_path.replace("ffmpeg", "ffprobe")
            return cls._ffmpeg_path

        # 3. 常见安装目录
        candidates = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]
        for p in candidates:
            if os.path.exists(p):
                cls._ffmpeg_path = p
                cls._ffprobe_path = p.replace("ffmpeg", "ffprobe")
                return p

        raise FileNotFoundError("未找到 ffmpeg，请运行: winget install ffmpeg")

    @classmethod
    def _get_ffmpeg(cls) -> str:
        return cls._find_ffmpeg()

    @classmethod
    def _get_ffprobe(cls) -> str:
        cls._find_ffmpeg()
        return cls._ffprobe_path or cls._ffmpeg_path.replace("ffmpeg", "ffprobe")

    @classmethod
    def _get_ffplay(cls) -> str:
        cls._find_ffmpeg()
        ffplay = cls._ffmpeg_path.replace("ffmpeg", "ffplay")
        if os.path.exists(ffplay):
            return ffplay
        raise FileNotFoundError("未找到 ffplay，请确保 ffmpeg 完整安装")

    @classmethod
    def has_audio_stream(cls, file_path: str) -> bool:
        """检测文件是否包含音频流"""
        try:
            ffprobe = cls._get_ffprobe()
            result = subprocess.run([
                ffprobe, "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                file_path
            ], capture_output=True, text=True)
            return "audio" in result.stdout
        except Exception:
            return False

    @classmethod
    def extract_audio(cls, file_path: str, output_dir: str = None,
                      sample_rate: int = 16000, fmt: str = "wav") -> str:
        if output_dir is None:
            output_dir = tempfile.gettempdir()
        base = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(output_dir, f"{base}_audio.{fmt}")
        # 前置检测：无音频流则直接报错
        if not cls.has_audio_stream(file_path):
            raise RuntimeError("该视频不含音频轨道，无法进行语音识别")
        ffmpeg = cls._get_ffmpeg()
        # 方案A：直接转 PCM
        cmd = [
            ffmpeg, "-y", "-i", file_path,
            "-vn", "-c:a", "pcm_s16le",
            "-ar", str(sample_rate), "-ac", "1",
            "-f", fmt, output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return output_path
        except subprocess.CalledProcessError:
            # 方案B：两步走——先提取原始音频流，再转 PCM（兼容更多编码）
            raw_path = os.path.join(output_dir, f"{base}_raw_audio.tmp")
            try:
                subprocess.run([
                    ffmpeg, "-y", "-i", file_path,
                    "-vn", "-c:a", "copy",
                    "-f", "nut", raw_path
                ], capture_output=True, check=True)
                subprocess.run([
                    ffmpeg, "-y", "-i", raw_path,
                    "-c:a", "pcm_s16le",
                    "-ar", str(sample_rate), "-ac", "1",
                    "-f", fmt, output_path
                ], capture_output=True, check=True)
                return output_path
            finally:
                if os.path.exists(raw_path):
                    os.remove(raw_path)

    @classmethod
    def get_audio_duration(cls, file_path: str) -> float:
        ffprobe = cls._get_ffprobe()
        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())

    @classmethod
    def check_ffmpeg(cls) -> bool:
        try:
            cls._find_ffmpeg()
            return True
        except Exception:
            return False


class ASREngine:
    """ASR via local faster-whisper (GPU-accelerated, ~3GB VRAM for medium)"""

    def __init__(self, model_size: str = "medium",
                 device: str = "auto",
                 compute_type: str = "auto"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load_whisper(self):
        if self._model is not None:
            return
        from faster_whisper import WhisperModel
        import torch
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.compute_type == "auto":
            self.compute_type = "float16" if self.device == "cuda" else "int8"
        print(f"[ASR] faster-whisper {self.model_size} device={self.device}")
        self._model = WhisperModel(
            self.model_size, device=self.device,
            compute_type=self.compute_type,
            download_root=os.path.join(os.path.expanduser("~"), ".cache", "whisper")
        )

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        self._load_whisper()
        segments_result, info = self._model.transcribe(
            audio_path, beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500, threshold=0.5),
            word_timestamps=True,
        )
        segments = []
        for i, seg in enumerate(segments_result):
            segments.append(Segment(
                index=i, start=round(seg.start, 3),
                end=round(seg.end, 3), text=seg.text.strip(),
            ))
        return TranscriptionResult(
            segments=segments, language=info.language,
            total_duration=info.duration,
        )


class Translator:
    API_BASE = "https://api.xiaomimimo.com/v1"

    def __init__(self, api_key: str, target_lang: str = "中文",
                 model: str = "mimo-v2-pro"):
        self.api_key = api_key
        self.target_lang = target_lang
        self.model = model
        self.fallback_model = "mimo-v2-flash"

    def translate(self, text: str, source_text: str = "",
                 fallback: bool = False, model_override: str = None) -> str:
        if not text.strip():
            return ""
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        if fallback:
            system_prompt = (
                f"你是翻译引擎。将以下内容翻译为{self.target_lang}。"
                "只输出译文。"
            )
            max_tokens_val = 4096
        else:
            system_prompt = (
                f"你是专业翻译引擎。将用户输入翻译为{self.target_lang}。\n\n"
                "要求：\n"
                "- 只输出译文，不要有任何其他内容\n"
                "- 译文长度与原文相近"
            )
            max_tokens_val = 2048
        model = model_override or self.model
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            "temperature": 0.0, "max_tokens": max_tokens_val,
        }
        try:
            resp = requests.post(
                f"{self.API_BASE}/chat/completions",
                headers=headers, json=payload, timeout=30
            )
            resp.raise_for_status()
        except requests.Timeout:
            raise RuntimeError("网络超时，请检查网络连接后重试")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                import time
                time.sleep(2)
            raise

        data = resp.json()
        if "choices" not in data or len(data["choices"]) == 0:
            raise RuntimeError("模型返回空白内容")
        message = data["choices"][0].get("message", {})
        content = message.get("content", "")
        if content is None or not str(content).strip():
            raise RuntimeError("模型返回空白内容")
        raw = content.strip()
        return self._clean_translation(raw)

    def translate_segments(self, segments: list, progress_callback=None,
                          target_indices: list = None) -> list:
        import time
        total = len(segments)
        target_set = set(target_indices) if target_indices else None
        for i, seg in enumerate(segments):
            if target_set is not None and i not in target_set:
                if progress_callback:
                    progress_callback(i + 1, total)
                continue
            if not seg.text.strip():
                seg.translation = ""
                seg.translated = True
            else:
                translated = False
                last_error = ""
                for attempt in range(2):
                    try:
                        use_fallback = (attempt == 1)
                        use_model = self.fallback_model if attempt == 1 else None
                        result = self.translate(
                            seg.text, source_text=seg.text,
                            fallback=use_fallback,
                            model_override=use_model
                        )
                        if result and result.strip():
                            seg.translation = result.strip()
                            seg.translated = True
                            translated = True
                            break
                        else:
                            last_error = "API 返回空白翻译"
                    except Exception as e:
                        last_error = str(e)
                        print(f"[Translate] seg {seg.index} attempt {attempt+1}: {e}")
                if not translated:
                    seg.translation = f"[翻译失败: {last_error}]"
                    seg.translated = False
            if progress_callback:
                progress_callback(i + 1, total)
            # 每 50 段休眠避免 API 限流
            if (i + 1) % 50 == 0:
                time.sleep(0.3)
        return segments

    def set_target_lang(self, lang: str):
        self.target_lang = lang

    @staticmethod
    def _clean_translation(raw: str) -> str:
        """清理模型输出的非译文噪声"""
        import re
        text = raw.strip()
        # JSON 包装提取
        if text.startswith("{") and text.endswith("}"):
            try:
                obj = json.loads(text)
                for k in ("translation", "translated_text", "result", "output", "text", "content"):
                    if k in obj and isinstance(obj[k], str):
                        text = obj[k]
                        break
            except Exception:
                pass
        # 去除常见前缀
        for prefix in ("翻译：", "译文：", "翻译结果：", "Translation:", "翻译:", "译文:", "translation:"):
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
        # 去除首尾成对引号/括号
        for left, right in (('"', '"'), ("'", "'"), ("「", "」"), ("『", "』"), ("（", "）"), ("(", ")")):
            if text.startswith(left) and text.endswith(right) and len(text) > 2:
                text = text[1:-1].strip()
        # 去除 markdown 代码块包装
        text = re.sub(r'^```[\w]*\s*\n', '', text)
        text = re.sub(r'\n```\s*$', '', text)
        return text.strip()


class Exporter:
    @staticmethod
    def to_srt(segments: list, output_path: str, bilingual: bool = True):
        with open(output_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                f.write(f"{i}\n{Exporter._fmt_srt(seg.start)} --> {Exporter._fmt_srt(seg.end)}\n")
                if bilingual and seg.translation:
                    f.write(f"{seg.text}\n{seg.translation}\n\n")
                else:
                    f.write(f"{seg.translation or seg.text}\n\n")

    @staticmethod
    def to_ass(segments: list, output_path: str, bilingual: bool = True):
        header = (
            "[Script Info]\nTitle: VoiceTrans\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
            "Style: Trans,Microsoft YaHei,40,&H00FFFF00,&H000000FF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,2,2,2,10,10,30,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header)
            for seg in segments:
                s, e = Exporter._fmt_ass(seg.start), Exporter._fmt_ass(seg.end)
                f.write(f"Dialogue: 0,{s},{e},Default,,0,0,0,,{seg.text}\n")
                if bilingual and seg.translation:
                    f.write(f"Dialogue: 0,{s},{e},Trans,,0,0,0,,{seg.translation}\n")

    @staticmethod
    def to_json(segments: list, output_path: str):
        data = {"segments": [{
            "index": s.index, "start": s.start, "end": s.end,
            "duration": s.duration, "speaker": s.speaker,
            "text": s.text, "translation": s.translation,
        } for s in segments]}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _fmt_srt(t: float) -> str:
        h, t = divmod(t, 3600); m, s = divmod(t, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s%1)*1000):03d}"

    @staticmethod
    def _fmt_ass(t: float) -> str:
        h, t = divmod(t, 3600); m, s = divmod(t, 60)
        return f"{int(h)}:{int(m):02d}:{int(s):02d}.{int((s%1)*100):02d}"


class AudioSplitter:
    """使用 ffmpeg 将音频按分段时间范围切割"""

    @classmethod
    def split_by_segments(cls, audio_path: str, segments: list,
                          output_dir: str) -> list:
        """切割音频，返回每个分段对应的音频文件路径列表"""
        os.makedirs(output_dir, exist_ok=True)
        split_files = []
        ffmpeg = AudioProcessor._get_ffmpeg()
        for seg in segments:
            output = os.path.join(output_dir, f"seg_{seg.index:04d}.wav")
            cls.split_single(audio_path, seg, output)
            split_files.append(output)
        return split_files

    @classmethod
    def get_duration(cls, audio_path: str) -> float:
        """获取音频时长（秒）"""
        ffmpeg = AudioProcessor._get_ffmpeg()
        ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe") \
                         .replace("ffmpeg", "ffprobe")
        cmd = [ffprobe, "-v", "error", "-show_entries",
               "format=duration", "-of",
               "default=noprint_wrappers=1:nokey=1",
               audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())

    @classmethod
    def split_single(cls, audio_path: str, segment: 'Segment',
                     output_path: str):
        ffmpeg = AudioProcessor._get_ffmpeg()
        cmd = [
            ffmpeg, "-y", "-i", audio_path,
            "-ss", str(segment.start), "-to", str(segment.end),
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    @classmethod
    def concat_audio_files(cls, file_paths: list, output_path: str):
        """拼接多个音频文件为完整音频"""
        # 过滤空路径
        valid = [fp for fp in file_paths if fp and os.path.exists(fp)]
        if not valid:
            raise ValueError("没有可拼接的音频文件")
        ffmpeg = AudioProcessor._get_ffmpeg()
        list_path = os.path.join(os.path.dirname(output_path),
                                 "_concat_list.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for fp in valid:
                f.write(f"file '{fp}'\n")
        cmd = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0",
            "-i", list_path, "-c", "copy", output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        try:
            os.remove(list_path)
        except Exception:
            pass

    @classmethod
    def speed_adjust(cls, input_path: str, output_path: str,
                     target_duration: float):
        """将音频变速以对齐目标时长。用时 ratio = 原时长 / 目标时长。
        ratio > 1 加速（缩短），< 1 减速（拉长）。
        atempo 滤镜单级范围 0.5~2.0，超出则链式多级。"""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"音频不存在: {input_path}")
        actual_duration = AudioSplitter.get_duration(input_path)
        if actual_duration <= 0 or target_duration <= 0:
            raise ValueError(f"无效时长: actual={actual_duration}, "
                             f"target={target_duration}")
        ratio = actual_duration / target_duration
        if abs(ratio - 1.0) < 0.002:
            # 无需变速，直接复制
            import shutil
            shutil.copy2(input_path, output_path)
            return
        # 构建 atempo 链
        filters = []
        remaining = ratio
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        filters.append(f"atempo={remaining:.6f}")
        filter_chain = ",".join(filters)
        ffmpeg = AudioProcessor._get_ffmpeg()
        cmd = [
            ffmpeg, "-y", "-i", input_path,
            "-filter:a", filter_chain,
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    @classmethod
    def concat_with_silence(cls, segments: list, audio_map: dict,
                            output_path: str, original_audio: str):
        """按分段时间轴拼接音频（含静音填补间隙）。
        TTS 音频自动变速对齐原分段时长，确保拼接后时间轴一致。"""
        if not segments:
            return
        tmp_dir = tempfile.mkdtemp(prefix="vt_concat_")
        file_parts = []
        prev_end = 0.0
        ffmpeg = AudioProcessor._get_ffmpeg()
        for seg in segments:
            gap = seg.start - prev_end
            if gap > 0.001:
                silence_path = os.path.join(tmp_dir,
                                            f"_silence_{prev_end:.3f}.wav")
                subprocess.run([
                    ffmpeg, "-y", "-f", "lavfi",
                    "-i", f"anullsrc=r=16000:cl=mono",
                    "-t", f"{gap:.3f}",
                    "-acodec", "pcm_s16le", silence_path
                ], capture_output=True, check=True)
                file_parts.append(silence_path)
            tts_file = audio_map.get(seg.index)
            seg_duration = seg.end - seg.start
            if tts_file and os.path.exists(tts_file):
                # 变速对齐原分段时长
                aligned = os.path.join(
                    tmp_dir, f"_aligned_{seg.index:04d}.wav")
                AudioSplitter.speed_adjust(tts_file, aligned, seg_duration)
                file_parts.append(aligned)
            else:
                seg_audio = os.path.join(tmp_dir,
                                         f"_orig_{seg.index:04d}.wav")
                AudioSplitter.split_single(original_audio, seg, seg_audio)
                file_parts.append(seg_audio)
            prev_end = seg.end
        AudioSplitter.concat_audio_files(file_parts, output_path)
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


class TTSEngine:
    """MiMo TTS 语音合成（基于 chat/completions + mimo-v2.5-tts-voiceclone）"""

    API_BASE = "https://api.xiaomimimo.com/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def synthesize(self, text: str, output_path: str,
                   voice: str = "",
                   speed: float = 1.0,
                   reference_audio_path: str = "") -> str:
        """合成语音并保存到 WAV 文件。可传入参考音频路径以克隆音色。"""
        if not text.strip():
            raise ValueError("文本为空")

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "model": "mimo-v2.5-tts-voiceclone",
            "messages": [
                {"role": "user", "content": ""},
                {"role": "assistant", "content": text},
            ],
        }

        # 音色克隆：参考音频 base64 编码
        if reference_audio_path and os.path.exists(reference_audio_path):
            try:
                with open(reference_audio_path, "rb") as af:
                    audio_b64 = base64.b64encode(af.read()).decode("utf-8")
                payload["audio"] = {
                    "voice": f"data:audio/wav;base64,{audio_b64}"
                }
            except Exception as e:
                print(f"[TTS] 参考音频编码失败: {e}")

        resp = requests.post(
            f"{self.API_BASE}/chat/completions",
            headers=headers, json=payload, timeout=120
        )
        resp.raise_for_status()

        result = resp.json()
        audio_b64 = result["choices"][0]["message"]["audio"]["data"]
        audio_bytes = base64.b64decode(audio_b64)

        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        return output_path

    def synthesize_segments(self, segments: list, output_dir: str,
                            progress_callback=None,
                            reference_audio_map: dict = None) -> dict:
        """批量合成所有分段，返回 {seg_index: file_path}
        
        Args:
            segments: 分段列表
            output_dir: 输出目录
            progress_callback: 进度回调 (current, total)
            reference_audio_map: {seg_index: 参考音频路径}，用于音色克隆
        """
        os.makedirs(output_dir, exist_ok=True)
        synth_map = {}
        errors = []
        total = len(segments)
        if reference_audio_map is None:
            reference_audio_map = {}
        for i, seg in enumerate(segments):
            if not (seg.translated and seg.translation):
                if progress_callback:
                    progress_callback(i + 1, total)
                continue
            output = os.path.join(output_dir, f"tts_{seg.index:04d}.wav")
            ref_path = reference_audio_map.get(seg.index, "")
            try:
                self.synthesize(seg.translation, output,
                                reference_audio_path=ref_path)
                synth_map[seg.index] = output
            except Exception as e:
                err_msg = str(e)
                print(f"[TTS] segment {seg.index} failed: {err_msg}")
                errors.append(f"#{seg.index + 1}: {err_msg}")
            if progress_callback:
                progress_callback(i + 1, total)
        return synth_map, errors
