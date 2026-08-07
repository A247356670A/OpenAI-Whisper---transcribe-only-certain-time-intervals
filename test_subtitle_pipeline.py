"""Fast tests for the workflow that do not require a Whisper installation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import subtitle_pipeline


class _FakeModel:
    def transcribe(self, audio, **_options):
        if isinstance(audio, str):
            return {"segments": [{"start": 0.0, "end": 2.0, "text": "最初の字幕"}]}
        return {"segments": [{"start": 0.1, "end": 1.1, "text": "補完字幕"}]}


class _FakeWhisper:
    @staticmethod
    def load_model(_name, device):
        assert device == "cpu"
        return _FakeModel()


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


if __name__ == "__main__":
    unittest.main()
