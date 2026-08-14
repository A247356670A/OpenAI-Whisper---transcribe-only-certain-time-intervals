"""Fast tests for the workflow that do not require a Whisper installation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import subtitle_pipeline
from whisper_options import build_whisper_options, default_option_values
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
        return [0.0] * (sr * 5), sr


class SubtitlePipelineTests(unittest.TestCase):
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

    def test_empty_intervals_do_not_restore_full_audio_for_b(self):
        segments, intervals = split_audio_by_intervals([0.0] * 16_000, [], 16_000)
        self.assertEqual(segments, [])
        self.assertEqual(intervals, [])

    def test_none_intervals_request_one_full_audio_segment(self):
        segments, intervals = split_audio_by_intervals([0.0] * 16_000, None, 16_000)
        self.assertEqual(intervals, [[0, 1.0]])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0][:2], [0, 1.0])

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
                output = subtitle_pipeline.burn_subtitles_to_mp4(video, subtitle, folder)

            command = popen.call_args.args[0]
            self.assertEqual(output.burned_video, folder / "原视频_burned_subtitles.mp4")
            self.assertTrue(output.input_was_mp4)
            self.assertIn("libx264", command)
            self.assertIn("aac", command)
            self.assertTrue(any("subtitles=filename=" in part for part in command))

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

    def test_build_output_paths_preserves_unicode_filename(self):
        outputs = subtitle_pipeline.build_output_paths("動画 01.mp4", "字幕")
        self.assertEqual(outputs.first_pass, Path("字幕") / "動画 01_A.srt")
        self.assertEqual(outputs.second_pass, Path("字幕") / "動画 01_B.srt")
        self.assertEqual(outputs.merged, Path("字幕") / "動画 01_merged.srt")

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


if __name__ == "__main__":
    unittest.main()
