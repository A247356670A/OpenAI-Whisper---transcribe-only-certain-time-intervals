"""Fast tests for the workflow that do not require a Whisper installation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

import subtitle_pipeline
import subtitle_gui
import resumable_transcription
from whisper_options import (
    WHISPER_OPTION_HELP,
    WHISPER_OPTION_SPECS,
    build_whisper_options,
    default_option_values,
)
from split_audio_by_intervals import split_audio_by_intervals


class _FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **_options):
        self.calls.append((audio, _options.copy()))
        if isinstance(audio, str):
            return {"segments": [{"start": 0.0, "end": 2.0, "text": "最初の字幕"}]}
        return {"segments": [{"start": 0.1, "end": 1.1, "text": "補完字幕"}]}


class _FakeWhisper:
    last_model = None

    @staticmethod
    def load_model(_name, device):
        assert device == "cpu"
        _FakeWhisper.last_model = _FakeModel()
        return _FakeWhisper.last_model


class _FakeTorch:
    class cuda:
        @staticmethod
        def is_available():
            return False


class _FakeLibrosa:
    @staticmethod
    def load(_source, sr, mono):
        assert sr == 16_000 and mono is True
        return [0.02] * (sr * 5), sr


class SubtitlePipelineTests(unittest.TestCase):
    def test_window_geometry_is_capped_to_available_screen_space(self):
        class _FakeWindow:
            geometry_value = ""
            minimum_value = (0, 0)

            @staticmethod
            def winfo_screenwidth():
                return 1000

            @staticmethod
            def winfo_screenheight():
                return 700

            @classmethod
            def geometry(cls, value):
                cls.geometry_value = value

            @classmethod
            def minsize(cls, width, height):
                cls.minimum_value = (width, height)

        subtitle_gui.fit_window_to_screen(_FakeWindow(), 1600, 900, 980, 700)

        self.assertTrue(_FakeWindow.geometry_value.startswith("940x600+"))
        self.assertEqual(_FakeWindow.minimum_value, (940, 600))

    def test_app_settings_round_trip_and_reject_invalid_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "settings.json"
            subtitle_gui.save_app_settings(
                {
                    "notification_enabled": False,
                    "notification_sound": "自定义音频",
                    "notification_sound_path": "/tmp/done.wav",
                    "ui_font_size": 18,
                    "ui_theme": "深色",
                    "accent_color": "紫色",
                    "cpu_thread_profile": "performance",
                    "unknown_future_setting": "ignored",
                },
                settings_path,
            )
            settings = subtitle_gui.load_app_settings(settings_path)

            self.assertFalse(settings["notification_enabled"])
            self.assertEqual(settings["ui_font_size"], 18)
            self.assertEqual(settings["ui_theme"], "深色")
            self.assertEqual(settings["accent_color"], "紫色")
            self.assertEqual(settings["cpu_thread_profile"], "performance")

            settings_path.write_text('{"ui_font_size": 100, "ui_theme": "无效"}', encoding="utf-8")
            recovered = subtitle_gui.load_app_settings(settings_path)
            self.assertEqual(recovered["ui_font_size"], 12)
            self.assertEqual(recovered["ui_theme"], "浅色")

            settings_path.write_text('{"ui_font_size": 14}', encoding="utf-8")
            migrated = subtitle_gui.load_app_settings(settings_path)
            self.assertEqual(migrated["ui_font_size"], 12)
            self.assertEqual(
                migrated["settings_version"], subtitle_gui.APP_SETTINGS_VERSION
            )

            settings_path.write_text('{"ui_font_size": 24}', encoding="utf-8")
            oversized_legacy = subtitle_gui.load_app_settings(settings_path)
            self.assertEqual(oversized_legacy["ui_font_size"], 18)

            settings_path.write_text(
                '{"settings_version": 2, "ui_font_size": 12, '
                '"notification_sound": "系统提示音"}',
                encoding="utf-8",
            )
            sound_migrated = subtitle_gui.load_app_settings(settings_path)
            self.assertEqual(sound_migrated["ui_font_size"], 12)
            self.assertEqual(sound_migrated["notification_sound"], "内置提示音")

    def test_bundled_completion_sound_is_available(self):
        self.assertEqual(
            subtitle_gui.DEFAULT_APP_SETTINGS["notification_sound"], "内置提示音"
        )
        self.assertTrue(subtitle_gui.BUILTIN_NOTIFICATION_PATH.is_file())

    def test_cpu_thread_reservation_keeps_extra_macos_headroom(self):
        class _FakeTorch:
            def __init__(self):
                self.thread_count = None

            def set_num_threads(self, count):
                self.thread_count = count

        mac_torch = _FakeTorch()
        mac_performance_torch = _FakeTorch()
        windows_torch = _FakeTorch()
        with patch("subtitle_pipeline.os.cpu_count", return_value=10):
            with patch("subtitle_pipeline.sys.platform", "darwin"):
                subtitle_pipeline._reserve_cpu_for_gui(mac_torch)
                subtitle_pipeline._reserve_cpu_for_gui(
                    mac_performance_torch, "performance"
                )
            with patch("subtitle_pipeline.sys.platform", "win32"):
                subtitle_pipeline._reserve_cpu_for_gui(windows_torch)

        self.assertEqual(mac_torch.thread_count, 6)
        self.assertEqual(mac_performance_torch.thread_count, 9)
        self.assertEqual(windows_torch.thread_count, 9)

    def test_gpu_high_performance_mode_requires_cuda(self):
        logs = []
        with self.assertRaisesRegex(RuntimeError, "NVIDIA CUDA"):
            subtitle_pipeline._configure_whisper_device(
                _FakeTorch,
                gpu_acceleration=True,
                log_callback=logs.append,
            )
        self.assertEqual(logs, [])

    def test_gpu_high_performance_mode_enables_fast_paths(self):
        class _Flag:
            pass

        class _Cuda:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def get_device_name(_index):
                return "Test GPU"

        class _Torch:
            cuda = _Cuda()
            backends = _Flag()
            backends.cuda = _Flag()
            backends.cuda.matmul = _Flag()
            backends.cudnn = _Flag()
            precision = None

            @classmethod
            def set_float32_matmul_precision(cls, value):
                cls.precision = value

        logs = []
        device = subtitle_pipeline._configure_whisper_device(
            _Torch,
            gpu_acceleration=True,
            log_callback=logs.append,
        )

        self.assertEqual(device, "cuda")
        self.assertTrue(_Torch.backends.cuda.matmul.allow_tf32)
        self.assertTrue(_Torch.backends.cudnn.allow_tf32)
        self.assertTrue(_Torch.backends.cudnn.benchmark)
        self.assertEqual(_Torch.precision, "high")
        self.assertIn("Test GPU", logs[0])

    def test_whisper_options_are_converted_from_gui_values(self):
        values = default_option_values("second")
        values.update(
            {
                "temperature": "0, 0.3, 0.6",
                "condition_on_previous_text": "True",
                "initial_prompt": "固有名詞：ホロライブ",
                "suppress_tokens": "-1, 50363",
                "fp16": "False",
            }
        )
        options = build_whisper_options("second", values, device="cuda")

        self.assertEqual(options["temperature"], (0.0, 0.3, 0.6))
        self.assertTrue(options["condition_on_previous_text"])
        self.assertEqual(options["initial_prompt"], "固有名詞：ホロライブ")
        self.assertEqual(options["suppress_tokens"], [-1, 50363])
        self.assertFalse(options["fp16"])

    def test_every_whisper_option_has_detailed_example_help(self):
        option_keys = {spec.key for spec in WHISPER_OPTION_SPECS}

        self.assertEqual(set(WHISPER_OPTION_HELP), option_keys)
        for help_text in WHISPER_OPTION_HELP.values():
            self.assertIn("作用：", help_text)
            self.assertIn("例子：", help_text)

    def test_empty_intervals_do_not_restore_full_audio_for_b(self):
        segments, intervals = split_audio_by_intervals([0.0] * 16_000, [], 16_000)
        self.assertEqual(segments, [])
        self.assertEqual(intervals, [])

    def test_none_intervals_request_one_full_audio_segment(self):
        segments, intervals = split_audio_by_intervals([0.0] * 16_000, None, 16_000)
        self.assertEqual(intervals, [[0, 1.0]])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0][:2], [0, 1.0])

    def test_silero_b_filter_keeps_only_segments_with_enough_speech(self):
        class _Tensor(list):
            def flatten(self):
                return self

            def cpu(self):
                return self

        class _FilterTorch:
            float32 = object()

            @staticmethod
            def as_tensor(samples, dtype):
                assert dtype is _FilterTorch.float32
                return _Tensor(samples)

        model = object()

        def get_speech_timestamps(audio, loaded_model, **options):
            self.assertIs(loaded_model, model)
            self.assertEqual(options["threshold"], 0.4)
            if max(abs(sample) for sample in audio) == 0:
                return []
            return [{"start": 0.1, "end": 0.6}]

        fake_silero = types.SimpleNamespace(
            load_silero_vad=lambda: model,
            get_speech_timestamps=get_speech_timestamps,
        )
        logs = []
        with patch.dict("sys.modules", {"silero_vad": fake_silero}):
            kept, skipped = subtitle_pipeline.filter_b_segments_with_silero(
                [
                    [0.0, 1.0, [0.0] * 16_000],
                    [1.0, 2.0, [0.02] * 16_000],
                ],
                16_000,
                _FilterTorch,
                threshold=0.4,
                min_speech_seconds=0.1,
                min_speech_ratio=0.2,
                log_callback=logs.append,
            )
        self.assertEqual([segment[:2] for segment in kept], [[1.0, 2.0]])
        self.assertEqual(skipped, [(0.0, 1.0)])
        self.assertTrue(any("人声 0.50s" in message for message in logs))

    def test_burn_subtitles_builds_h264_mp4_command(self):
        class _FakeProcess:
            stdout = ["ffmpeg progress\n"]

            @staticmethod
            def wait():
                return 0

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            video = folder / "原视频.mp4"
            subtitle = folder / "中文字幕.srt"
            video.touch()
            subtitle.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n测试\n", encoding="utf-8"
            )
            with (
                patch("subtitle_pipeline.shutil.which", return_value="ffmpeg"),
                patch("subtitle_pipeline.subprocess.Popen", return_value=_FakeProcess()) as popen,
            ):
                output = subtitle_pipeline.burn_subtitles_to_mp4(
                    video,
                    subtitle,
                    folder,
                    font_name="Meiryo",
                    font_size=52,
                    font_color="黄色",
                    outline_size=3,
                    margin_v=72,
                )

            command = popen.call_args.args[0]
            subtitle_filter = command[command.index("-vf") + 1]
            self.assertEqual(output.burned_video, folder / "原视频_burned_subtitles.mp4")
            self.assertTrue(output.input_was_mp4)
            self.assertIn("libx264", command)
            self.assertIn("aac", command)
            self.assertIn("subtitles=filename=", subtitle_filter)
            self.assertIn("FontName=Meiryo", subtitle_filter)
            self.assertIn("FontSize=52", subtitle_filter)
            self.assertIn("PrimaryColour=&H0000FFFF", subtitle_filter)
            self.assertIn("Outline=3", subtitle_filter)
            self.assertIn("MarginV=72", subtitle_filter)

    def test_subtitle_style_preview_uses_selected_style(self):
        class _FakeProcess:
            stdout = []

            @staticmethod
            def wait():
                return 0

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            video = folder / "原视频.mp4"
            subtitle = folder / "中文字幕.srt"
            video.touch()
            subtitle.write_text(
                "1\n00:00:02,000 --> 00:00:03,000\n测试\n", encoding="utf-8"
            )

            def fake_popen(command, **_kwargs):
                Path(command[-1]).touch()
                return _FakeProcess()

            with (
                patch("subtitle_pipeline.shutil.which", return_value="ffmpeg"),
                patch("subtitle_pipeline.subprocess.Popen", side_effect=fake_popen) as popen,
            ):
                preview = subtitle_pipeline.generate_subtitle_preview(
                    video,
                    subtitle,
                    folder,
                    font_name="SimHei",
                    font_size=50,
                    font_color="青色",
                    outline_size=2,
                    margin_v=64,
                )

            command = popen.call_args.args[0]
            subtitle_filter = command[command.index("-vf") + 1]
            self.assertEqual(preview.preview_time, 2.05)
            self.assertEqual(preview.preview_index, 0)
            self.assertEqual(preview.subtitle_count, 1)
            self.assertTrue(preview.preview_image.is_file())
            self.assertIn("-frames:v", command)
            self.assertIn("FontName=SimHei", subtitle_filter)
            self.assertIn("FontSize=50", subtitle_filter)
            self.assertIn("PrimaryColour=&H00FFFF00", subtitle_filter)
            self.assertIn("MarginV=64", subtitle_filter)

    def test_burn_subtitles_marks_non_mp4_as_conversion_input(self):
        class _FakeProcess:
            stdout = []

            @staticmethod
            def wait():
                return 0

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            video = folder / "原视频.mkv"
            subtitle = folder / "中文字幕.srt"
            video.touch()
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试\n", encoding="utf-8")
            with (
                patch("subtitle_pipeline.shutil.which", return_value="ffmpeg"),
                patch("subtitle_pipeline.subprocess.Popen", return_value=_FakeProcess()),
            ):
                output = subtitle_pipeline.burn_subtitles_to_mp4(video, subtitle, folder)

            self.assertFalse(output.input_was_mp4)
            self.assertEqual(output.burned_video.suffix, ".mp4")

    def test_download_video_as_mp4_uses_requested_yt_dlp_command(self):
        class _FakeProcess:
            stdout = []

            @staticmethod
            def wait():
                return 0

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            with (
                patch.dict("sys.modules", {"yt_dlp": object()}),
                patch("subtitle_pipeline.shutil.which", return_value=None),
                patch("subtitle_pipeline.subprocess.Popen", return_value=_FakeProcess()) as popen,
            ):
                output = subtitle_pipeline.download_video_as_mp4(
                    "https://example.test/watch?v=123", folder
                )

            command = popen.call_args.args[0]
            self.assertEqual(output.output_dir, folder)
            self.assertEqual(output.source_url, "https://example.test/watch?v=123")
            self.assertEqual(popen.call_args.kwargs["cwd"], str(folder))
            self.assertEqual(command[command.index("-R") + 1], "10")
            self.assertEqual(command[command.index("--retry-sleep") + 1], "5")
            self.assertEqual(command[command.index("--http-chunk-size") + 1], "1M")
            self.assertEqual(command[command.index("--merge-output-format") + 1], "mp4")
            self.assertIn("--write-thumbnail", command)
            self.assertEqual(command[command.index("--convert-thumbnails") + 1], "jpg")
            self.assertEqual(command[-1], "https://example.test/watch?v=123")
            self.assertNotIn("--cookies-from-browser", command)
            self.assertNotIn("--js-runtimes", command)

    def test_download_video_as_mp4_passes_browser_cookie_and_node_runtime(self):
        class _FakeProcess:
            stdout = []

            @staticmethod
            def wait():
                return 0

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            with (
                patch.dict("sys.modules", {"yt_dlp": object()}),
                patch(
                    "subtitle_pipeline.shutil.which",
                    side_effect=lambda executable: "/mock/node"
                    if executable == "node"
                    else None,
                ),
                patch("subtitle_pipeline.subprocess.Popen", return_value=_FakeProcess()) as popen,
            ):
                subtitle_pipeline.download_video_as_mp4(
                    "https://example.test/watch?v=123",
                    folder,
                    cookie_browser="chrome",
                )

            command = popen.call_args.args[0]
            self.assertEqual(
                command[command.index("--cookies-from-browser") + 1], "chrome"
            )
            self.assertEqual(command[command.index("--js-runtimes") + 1], "node")

    def test_download_video_as_mp4_explains_youtube_bot_check(self):
        class _FakeProcess:
            stdout = [
                "ERROR: Sign in to confirm you're not a bot. Use --cookies-from-browser"
            ]

            @staticmethod
            def wait():
                return 1

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            with (
                patch.dict("sys.modules", {"yt_dlp": object()}),
                patch("subtitle_pipeline.shutil.which", return_value=None),
                patch("subtitle_pipeline.subprocess.Popen", return_value=_FakeProcess()),
            ):
                with self.assertRaisesRegex(RuntimeError, "真人验证"):
                    subtitle_pipeline.download_video_as_mp4(
                        "https://example.test/watch?v=123", folder
                    )

    def test_manual_subtitle_merge_groups_overlaps_and_uses_selected_side(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            subtitle_a = folder / "A.srt"
            subtitle_b = folder / "B.srt"
            subtitle_a.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nA 冲突\n\n"
                "2\n00:00:04,000 --> 00:00:05,000\nA 独立\n",
                encoding="utf-8",
            )
            subtitle_b.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nB 冲突\n\n"
                "2\n00:00:06,000 --> 00:00:07,000\nB 独立\n",
                encoding="utf-8",
            )

            prepared = subtitle_pipeline.prepare_manual_subtitle_merge(
                subtitle_a, subtitle_b, folder
            )
            self.assertEqual(len(prepared.conflicts), 1)
            self.assertEqual(prepared.conflicts[0].a_entries[0][2], "A 冲突")
            self.assertEqual(prepared.conflicts[0].b_entries[0][2], "B 冲突")
            self.assertEqual(len(prepared.non_conflicting_entries), 2)

            output = subtitle_pipeline.complete_manual_subtitle_merge(
                prepared, [list(prepared.conflicts[0].b_entries)]
            )
            merged = output.output_path.read_text(encoding="utf-8")
            self.assertIn("B 冲突", merged)
            self.assertIn("A 独立", merged)
            self.assertIn("B 独立", merged)
            self.assertNotIn("A 冲突", merged)

    def test_manual_merge_path_does_not_duplicate_a_long_shared_video_name(self):
        title = (
            "20260821_【ゼンレスゾーンゼロ】どいつもこいつも愛でまくろう！！"
            "「パシャリ！フォーカスの陣！」キュート編【Vtuber】"
        )
        output = subtitle_pipeline.build_manual_merge_path(
            f"{title} _A.srt",
            f"{title} _A_B.srt",
            Path("字幕"),
        )

        self.assertEqual(output.name, f"{title}_merged.srt")
        self.assertEqual(output.name.count(title), 1)

    def test_manual_merge_path_truncates_extreme_names_with_stable_hash(self):
        title = "非常长的日语直播标题" * 40
        first = subtitle_pipeline.build_manual_merge_path(
            f"{title}_A.srt", f"{title}_A_B.srt", Path("字幕")
        )
        second = subtitle_pipeline.build_manual_merge_path(
            f"{title}_A.srt", f"{title}_A_B.srt", Path("字幕")
        )

        self.assertEqual(first, second)
        self.assertLessEqual(
            len(first.name.encode("utf-16-le")) // 2,
            220,
        )
        self.assertRegex(first.name, r"_[0-9a-f]{8}_merged\.srt$")

    def test_parse_editable_srt_text_accepts_edited_srt(self):
        entries = subtitle_pipeline.parse_editable_srt_text(
            "1\n00:00:01,000 --> 00:00:02,500\n修改后的字幕\n"
        )
        self.assertEqual(entries, [(1.0, 2.5, "修改后的字幕")])

    def test_hallucination_cleanup_lists_context_and_removes_only_confirmed_entries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "字幕.srt"
            source.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n正常开场\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\n(♪ BGM)\n\n"
                "3\n00:00:02,000 --> 00:00:03,000\n正常内容\n\n"
                "4\n00:00:03,000 --> 00:00:04,000\nご視聴ありがとうございました。\n\n"
                "5\n00:00:04,000 --> 00:00:05,000\n(エンディング)\n",
                encoding="utf-8",
            )

            prepared = subtitle_pipeline.prepare_hallucination_cleanup(source, folder)
            self.assertEqual(len(prepared.candidates), 3)
            bgm = prepared.candidates[0]
            self.assertEqual(bgm.entry[2], "(♪ BGM)")
            self.assertEqual(bgm.previous_entry[2], "正常开场")
            self.assertEqual(bgm.next_entry[2], "正常内容")

            output = subtitle_pipeline.complete_hallucination_cleanup(
                prepared, {prepared.candidates[0].entry_index, prepared.candidates[2].entry_index}
            )
            cleaned = output.output_path.read_text(encoding="utf-8")
            self.assertEqual(output.removed_count, 2)
            self.assertNotIn("(♪ BGM)", cleaned)
            self.assertNotIn("(エンディング)", cleaned)
            self.assertIn("ご視聴ありがとうございました。", cleaned)

    def test_hallucination_cleanup_rejects_unlisted_deletion(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "字幕.srt"
            source.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n正常内容\n", encoding="utf-8"
            )
            prepared = subtitle_pipeline.prepare_hallucination_cleanup(source, folder)
            with self.assertRaises(ValueError):
                subtitle_pipeline.complete_hallucination_cleanup(prepared, {0})

    def test_build_output_paths_preserves_unicode_filename(self):
        outputs = subtitle_pipeline.build_output_paths("動画 01.mp4", "字幕")
        self.assertEqual(outputs.first_pass, Path("字幕") / "動画 01_A.srt")
        self.assertEqual(outputs.second_pass, Path("字幕") / "動画 01_B.srt")
        self.assertEqual(outputs.merged, Path("字幕") / "動画 01_merged.srt")

    def test_audio_loader_falls_back_to_ffmpeg_for_unreadable_mp4(self):
        class _ContainerRejectingLibrosa:
            calls = []

            @classmethod
            def load(cls, source, sr, mono):
                cls.calls.append(source)
                assert sr == 16_000 and mono is True
                if str(source).lower().endswith(".mp4"):
                    raise RuntimeError("Format not recognised")
                return [0.1, 0.2], sr

        class _Completed:
            returncode = 0
            stderr = ""

        commands = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            Path(command[-1]).touch()
            return _Completed()

        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "网络视频.mp4"
            source.touch()
            logs = []
            with (
                patch("subtitle_pipeline.shutil.which", return_value="ffmpeg"),
                patch("subtitle_pipeline.subprocess.run", side_effect=fake_run),
            ):
                audio, sample_rate = subtitle_pipeline._load_audio_mono_16k(
                    source, _ContainerRejectingLibrosa, logs.append
                )

        self.assertEqual(audio, [0.1, 0.2])
        self.assertEqual(sample_rate, 16_000)
        self.assertEqual(commands[0][commands[0].index("-i") + 1], str(source))
        self.assertIn("pcm_s16le", commands[0])
        self.assertTrue(any("FFmpeg 兼容解码" in message for message in logs))

    def test_two_pass_workflow_writes_all_subtitles(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "動画.mp4"
            source.touch()
            with (
                patch("subtitle_pipeline.shutil.which", return_value="ffmpeg"),
                patch(
                    "subtitle_pipeline._import_dependencies",
                    return_value=(_FakeLibrosa, _FakeTorch, _FakeWhisper),
                ),
            ):
                outputs = subtitle_pipeline.run_two_pass_transcription(source, folder)

            self.assertTrue(outputs.first_pass.is_file())
            self.assertTrue(outputs.second_pass.is_file())
            self.assertTrue(outputs.merged.is_file())
            merged = outputs.merged.read_text(encoding="utf-8")
            self.assertIn("最初の字幕", merged)
            self.assertIn("補完字幕", merged)

    def test_first_pass_writes_only_a(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "動画.mp4"
            source.touch()
            with (
                patch("subtitle_pipeline.shutil.which", return_value="ffmpeg"),
                patch(
                    "subtitle_pipeline._import_dependencies",
                    return_value=(_FakeLibrosa, _FakeTorch, _FakeWhisper),
                ),
            ):
                output = subtitle_pipeline.run_first_pass_transcription(
                    source,
                    folder,
                    first_whisper_values={
                        "condition_on_previous_text": "False",
                        "temperature": "0.3",
                    },
                )

            self.assertEqual(output.first_pass, folder / "動画_A.srt")
            self.assertIn("最初の字幕", output.first_pass.read_text(encoding="utf-8"))
            self.assertFalse((folder / "動画_B.srt").exists())
            _audio, options = _FakeWhisper.last_model.calls[0]
            self.assertFalse(options["condition_on_previous_text"])
            self.assertEqual(options["temperature"], 0.3)
            self.assertEqual(options["task"], "transcribe")

    def test_second_pass_uses_existing_subtitle_and_writes_only_b(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "動画.mp4"
            source.touch()
            translated_a = folder / "動画_zh.srt"
            translated_a.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n翻译字幕\n\n",
                encoding="utf-8",
            )
            with (
                patch("subtitle_pipeline.shutil.which", return_value="ffmpeg"),
                patch(
                    "subtitle_pipeline._import_dependencies",
                    return_value=(_FakeLibrosa, _FakeTorch, _FakeWhisper),
                ),
            ):
                output = subtitle_pipeline.run_second_pass_from_subtitle(
                    source, translated_a, folder
                )

            self.assertEqual(output.second_pass, folder / "動画_zh_B.srt")
            self.assertTrue(output.second_pass.is_file())
            self.assertIn("補完字幕", output.second_pass.read_text(encoding="utf-8"))
            self.assertEqual(
                translated_a.read_text(encoding="utf-8"),
                "1\n00:00:00,000 --> 00:00:02,000\n翻译字幕\n\n",
            )

    def test_second_pass_reports_b_progress_by_segment_number(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "動画.mp4"
            source.touch()
            translated_a = folder / "A.srt"
            translated_a.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n字幕 A\n", encoding="utf-8"
            )
            progress = []
            with (
                patch("subtitle_pipeline.shutil.which", return_value="ffmpeg"),
                patch(
                    "subtitle_pipeline._import_dependencies",
                    return_value=(_FakeLibrosa, _FakeTorch, _FakeWhisper),
                ),
            ):
                subtitle_pipeline.run_second_pass_from_subtitle(
                    source,
                    translated_a,
                    folder,
                    progress_callback=lambda stage, current, total: progress.append(
                        (stage, current, total)
                    ),
                )

            self.assertIn(("subtitle_b", 0, 1), progress)
            self.assertIn(("subtitle_b", 1, 1), progress)

    def test_extract_chinese_subtitles_keeps_first_text_line(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            bilingual = folder / "bilingual.srt"
            bilingual.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n中文第一行\n日本語の二行目\n\n"
                "2\n00:00:03,000 --> 00:00:04,000\n第二句中文\n二つ目の日本語\n",
                encoding="utf-8",
            )

            output = subtitle_pipeline.extract_chinese_subtitles(bilingual, folder)

            self.assertEqual(output.chinese_only, folder / "bilingual_zh.srt")
            self.assertEqual(
                output.chinese_only.read_text(encoding="utf-8"),
                "1\n00:00:00,000 --> 00:00:02,000\n中文第一行\n\n"
                "2\n00:00:03,000 --> 00:00:04,000\n第二句中文\n",
            )

    def test_resumable_workflow_cancels_at_complete_chunk_and_resumes(self):
        class _ResumableLibrosa(_FakeLibrosa):
            @staticmethod
            def load(_source, sr, mono):
                assert sr == 16_000 and mono is True
                return [0.02] * (sr * 6), sr

        class _ResumableModel:
            def transcribe(self, _audio, **_options):
                return {
                    "segments": [
                        {"start": 0.2, "end": 0.8, "text": "分片字幕"},
                    ]
                }

        class _ResumableWhisper:
            @staticmethod
            def load_model(_name, device):
                assert device == "cpu"
                return _ResumableModel()

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "可续传视频.mp4"
            source.touch()
            cancel_event = threading.Event()

            def cancel_after_first_chunk(stage, current, _total):
                if stage == "resumable_a" and current >= 2:
                    cancel_event.set()

            with (
                patch("resumable_transcription.shutil.which", return_value="ffmpeg"),
                patch(
                    "resumable_transcription._import_dependencies",
                    return_value=(_ResumableLibrosa, _FakeTorch, _ResumableWhisper),
                ),
            ):
                cancelled = resumable_transcription.run_resumable_two_pass_transcription(
                    source,
                    folder,
                    resume=False,
                    cancel_check=cancel_event.is_set,
                    progress_callback=cancel_after_first_chunk,
                    merge_gap=0,
                    a_chunk_seconds=2,
                    a_overlap_seconds=0.5,
                )

            self.assertFalse(cancelled.completed)
            self.assertTrue(cancelled.checkpoint.is_file())
            self.assertTrue(cancelled.partial_first.is_file())

            cancel_event.clear()

            def cancel_after_first_b_segment(stage, current, _total):
                if stage == "resumable_b" and current >= 1:
                    cancel_event.set()

            with (
                patch("resumable_transcription.shutil.which", return_value="ffmpeg"),
                patch(
                    "resumable_transcription._import_dependencies",
                    return_value=(_ResumableLibrosa, _FakeTorch, _ResumableWhisper),
                ),
            ):
                completed = resumable_transcription.run_resumable_two_pass_transcription(
                    source,
                    folder,
                    resume=True,
                    cancel_check=cancel_event.is_set,
                    progress_callback=cancel_after_first_b_segment,
                    merge_gap=0,
                    a_chunk_seconds=2,
                    a_overlap_seconds=0.5,
                )

            self.assertFalse(completed.completed)
            self.assertTrue(completed.partial_second.is_file())
            cancel_event.clear()
            with (
                patch("resumable_transcription.shutil.which", return_value="ffmpeg"),
                patch(
                    "resumable_transcription._import_dependencies",
                    return_value=(_ResumableLibrosa, _FakeTorch, _ResumableWhisper),
                ),
            ):
                completed = resumable_transcription.run_resumable_two_pass_transcription(
                    source,
                    folder,
                    resume=True,
                    cancel_check=cancel_event.is_set,
                    merge_gap=0,
                    a_chunk_seconds=2,
                    a_overlap_seconds=0.5,
                )

            self.assertTrue(completed.completed)
            self.assertTrue(completed.first_pass.is_file())
            self.assertTrue(completed.second_pass.is_file())
            self.assertTrue(completed.merged.is_file())
            self.assertFalse(completed.checkpoint.exists())
            self.assertFalse(completed.partial_first.exists())
            self.assertFalse(completed.partial_second.exists())

    def test_resumable_checkpoint_rejects_changed_parameters(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "参数检查.mp4"
            source.touch()
            paths = resumable_transcription.build_resumable_output_paths(source, folder)
            settings = resumable_transcription._settings_identity(
                model_name="large-v2",
                merge_gap=1.0,
                duplicate_threshold=0.5,
                filter_b_speech=False,
                b_silero_threshold=subtitle_pipeline.B_SILERO_THRESHOLD,
                b_silero_min_speech_seconds=subtitle_pipeline.B_SILERO_MIN_SPEECH_SECONDS,
                b_silero_min_speech_ratio=subtitle_pipeline.B_SILERO_MIN_SPEECH_RATIO,
                cpu_thread_profile="balanced",
                gpu_acceleration=False,
                first_whisper_values=None,
                second_whisper_values=None,
                a_chunk_seconds=2,
                a_overlap_seconds=0.5,
            )
            state = resumable_transcription._fresh_checkpoint(source.resolve(), settings)
            resumable_transcription._write_json_atomic(paths.checkpoint, state)

            with (
                patch("resumable_transcription.shutil.which", return_value="ffmpeg"),
                self.assertRaisesRegex(ValueError, "参数与断点不一致"),
            ):
                resumable_transcription.run_resumable_two_pass_transcription(
                    source,
                    folder,
                    resume=True,
                    model_name="small",
                    a_chunk_seconds=2,
                    a_overlap_seconds=0.5,
                )


if __name__ == "__main__":
    unittest.main()
