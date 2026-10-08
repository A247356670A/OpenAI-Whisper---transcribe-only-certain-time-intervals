"""Check portable review integrity and bilingual annotation offsets."""
import tempfile
from pathlib import Path
import unittest

from subtitle_proofreading import create_review, save_review, load_review, review_report, _parse_cues


class ProofreadingTests(unittest.TestCase):
    def test_inline_number_time_and_dialogue_from_error_screenshot(self):
        cues = _parse_cues("3\n00:00:13,000 --> 00:00:14,000\n上一句\n\n4 00:00:15,060 --> 00:00:16,460 ん\n嗯\n\n5\n00:00:17,000 --> 00:00:18,000\n下一句")
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[1], dict(number="4", timing="00:00:15,060 --> 00:00:16,460", text="ん\n嗯"))
        self.assertEqual(cues[0]["text"], "上一句")
        self.assertEqual(cues[2]["text"], "下一句")

    def test_inline_text_without_number_and_number_without_inline_text(self):
        cues = _parse_cues("00:00:01,000 --> 00:00:02,000 你好\n2 00:00:03,000 --> 00:00:04,000\n日本語")
        self.assertEqual([cue["text"] for cue in cues], ["你好", "日本語"])
        self.assertEqual([cue["number"] for cue in cues], ["1", "2"])

    def test_position_metadata_is_not_dialogue(self):
        timing = "00:00:01,000 --> 00:00:02,000 X1:10 X2:20 Y1:30 Y2:40"
        cue = _parse_cues("1\n" + timing + "\n正文")[0]
        self.assertEqual(cue["timing"], timing)
        self.assertEqual(cue["text"], "正文")

    def test_collapsed_cue_review_can_be_saved_and_resumed(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.srt"
            raw = "4 00:00:15,060 --> 00:00:16,460 ん\n"
            source.write_bytes(raw.encode("utf-8"))
            data = create_review(source)
            data["annotations"].append(dict(cue=0, start=0, end=1,
                quote="ん", language="日文", replacement="", comment="核对原音"))
            path = Path(folder) / "review.json"
            save_review(data, path)
            self.assertEqual(load_review(path), data)
            self.assertEqual(data["source_srt"], raw)
            self.assertEqual(source.read_bytes(), raw.encode("utf-8"))

    def test_blank_line_inside_bilingual_cue_keeps_both_languages(self):
        text = "1\n00:00:01,000 --> 00:00:03,000\n日本語\n\n弗林茨家族原党首及弗林茨家族\n\n2\n00:00:04,000 --> 00:00:05,000\n下一条\n"
        cues = _parse_cues(text)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["text"], "日本語\n\n弗林茨家族原党首及弗林茨家族")
        self.assertEqual(cues[1]["number"], "2")

    def test_missing_separator_does_not_merge_two_cues(self):
        cues = _parse_cues("1\n00:00:01,000 --> 00:00:02,000\n第一条\n2\n00:00:02,000 --> 00:00:03,000\n第二条")
        self.assertEqual([cue["text"] for cue in cues], ["第一条", "第二条"])

    def test_bad_timeline_inside_file_is_not_silently_absorbed(self):
        with self.assertRaisesRegex(ValueError, "第 5 行"):
            _parse_cues("1\n00:00:01,000 --> 00:00:02,000\n正文\n2\n00:bad --> 00:00:04,000\n正文")

    def test_extra_blank_lines_and_common_timestamp_variants(self):
        cues = _parse_cues(" 1 \n 0:00:01.12 --> 0:00:03.456\n中文\n日本語\n\n\n\u3000\n2\n00:00:04,000 --> 00:00:05,000\n第二句\n")
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["text"], "中文\n日本語")
        self.assertEqual(cues[1]["number"], "2")

    def test_unnumbered_and_empty_cues_are_preserved(self):
        cues = _parse_cues("00:00:01,000 --> 00:00:02,000\n你好\n\n2\n00:00:03,000 --> 00:00:04,000\n")
        self.assertEqual(cues[0]["number"], "1")
        self.assertEqual(cues[1]["text"], "")

    def test_format_error_is_not_reported_as_encoding_error(self):
        with self.assertRaisesRegex(ValueError, "第 1 行.*不是 UTF-8"):
            _parse_cues("1\n错误时间轴\n中文")

    def test_utf16_bom_and_real_decode_error(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.srt"
            raw = "1\n00:00:00,000 --> 00:00:01,000\n中文\n日本語\n"
            source.write_bytes(raw.encode("utf-16"))
            self.assertEqual(create_review(source)["source_srt"], raw)
            source.write_bytes(b"\x81\x81")
            with self.assertRaisesRegex(ValueError, "字节位置"):
                create_review(source)

    def test_roundtrip_preserves_source_and_annotations(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "双语.srt"
            raw = "7\r\n00:00:01,123 --> 00:00:03,456\r\n你好😀人名\r\nこんにちは\r\n"
            source.write_bytes(raw.encode("utf-8-sig"))
            data = create_review(source)
            text = data["cues"][0]["text"]
            start = text.index("人名")
            data["annotations"].append(dict(cue=0, start=start, end=start+2,
                quote="人名", language="中文", replacement="正确名称", comment="请核实"))
            path = Path(folder) / "review.json"
            save_review(data, path)
            restored = load_review(path)
            self.assertEqual(restored, data)
            self.assertEqual(restored["source_srt"], raw)
            self.assertEqual(source.read_bytes(), raw.encode("utf-8-sig"))
            self.assertIn("こんにちは", review_report(restored))
            self.assertIn("请核实", review_report(restored))
            self.assertNotIn(folder, path.read_text(encoding="utf-8"))
            data["annotations"][0]["start"] = 0
            save_review(data, path)
            with self.assertRaises(ValueError):
                load_review(path)

    def test_modified_cue_cannot_silently_replace_original(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.srt"
            source.write_text("1\n00:00:00,000 --> 00:00:01,000\n原文\n", encoding="utf-8")
            data = create_review(source)
            data["cues"][0]["text"] = "篡改"
            path = Path(folder) / "review.json"
            save_review(data, path)
            with self.assertRaises(ValueError):
                load_review(path)
