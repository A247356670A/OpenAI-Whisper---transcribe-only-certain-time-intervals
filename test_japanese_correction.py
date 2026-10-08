"""Tests for conservative Japanese glossary correction."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from japanese_correction import (
    complete_japanese_correction,
    load_glossary,
    normalize_japanese,
    prepare_japanese_correction,
)


class JapaneseCorrectionTests(unittest.TestCase):
    def _write_srt(self, path: Path, texts: list[str]) -> None:
        blocks = []
        for index, text in enumerate(texts, start=1):
            blocks.append(
                f"{index}\n00:00:{index:02},000 --> 00:00:{index + 1:02},000\n{text}"
            )
        path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

    def test_normalize_japanese_unifies_width_kana_and_long_dash(self):
        self.assertEqual(normalize_japanese("ろくしー･－"), "ロクシー・ー")

    def test_glossary_groups_later_spellings_as_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            glossary = Path(directory) / "terms.tsv"
            glossary.write_text(
                "ロクシー・イフリータ・プライス\t洛克茜·伊芙莉塔·普莱斯\n"
                "ロクシーイフリータプライス\t洛克茜·伊芙莉塔·普莱斯\n"
                "ホロウ\t空洞\n",
                encoding="utf-8",
            )
            terms = load_glossary(glossary)

            self.assertEqual(terms[0].canonical, "ロクシー・イフリータ・プライス")
            self.assertEqual(terms[0].aliases, ("ロクシーイフリータプライス",))

    def test_reading_pair_selects_official_spelling_even_when_it_appears_later(self):
        with tempfile.TemporaryDirectory() as directory:
            glossary = Path(directory) / "terms.tsv"
            glossary.write_text(
                "シグリット\t希格莉德\n"
                "ホロウ\t空洞\n"
                "シグリッド\t希格莉德\n"
                "しぐりっど\t希格莉德\n",
                encoding="utf-8",
            )

            terms = load_glossary(glossary)
            sigrit = next(term for term in terms if term.chinese == "希格莉德")

            self.assertEqual(sigrit.canonical, "シグリッド")
            self.assertTrue(sigrit.canonical_confident)
            self.assertIn("シグリット", sigrit.aliases)

    def test_exact_alias_is_selected_by_default_and_source_is_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            glossary = root / "terms.tsv"
            self._write_srt(source, ["ロクシーイフリータプライスが来た"])
            glossary.write_text(
                "ロクシー・イフリータ・プライス\t洛克茜·伊芙莉塔·普莱斯\n"
                "ロクシーイフリータプライス\t洛克茜·伊芙莉塔·普莱斯\n",
                encoding="utf-8",
            )

            prepared = prepare_japanese_correction(source, glossary, root)
            self.assertEqual(len(prepared.candidates), 1)
            self.assertTrue(prepared.candidates[0].default_selected)
            result = complete_japanese_correction(prepared, {0})

            corrected = result.corrected_srt.read_text(encoding="utf-8")
            self.assertIn("ロクシー・イフリータ・プライスが来た", corrected)
            self.assertIn("ロクシーイフリータプライスが来た", source.read_text(encoding="utf-8"))
            self.assertTrue(result.json_report.is_file())
            self.assertTrue(result.markdown_report.is_file())

    def test_fuzzy_katakana_candidate_requires_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            glossary = root / "terms.tsv"
            self._write_srt(source, ["ロクシイが来た", "ロクシーは強い"])
            glossary.write_text("ロクシー\t洛克茜\n", encoding="utf-8")

            prepared = prepare_japanese_correction(source, glossary, root)

            self.assertEqual(len(prepared.candidates), 1)
            self.assertFalse(prepared.candidates[0].default_selected)
            self.assertEqual(prepared.candidates[0].proposed_text, "ロクシーが来た")
            self.assertEqual(prepared.candidates[0].changes[0].match_type, "fuzzy_katakana")

    def test_short_terms_are_not_fuzzy_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            glossary = root / "terms.tsv"
            self._write_srt(source, ["リンと話した"])
            glossary.write_text("リナ\t丽娜\n", encoding="utf-8")

            prepared = prepare_japanese_correction(source, glossary, root)

            self.assertEqual(prepared.candidates, ())

    def test_alias_inside_canonical_spelling_is_not_replaced_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            glossary = root / "terms.tsv"
            self._write_srt(source, ["スターライトを見た"])
            glossary.write_text(
                "スターライト\t星徽\n"
                "すたーらいと\t星徽\n"
                "スター\t星徽\n",
                encoding="utf-8",
            )

            prepared = prepare_japanese_correction(source, glossary, root)

            self.assertEqual(prepared.candidates, ())

    def test_short_exact_alias_is_not_replaced_inside_a_longer_katakana_word(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            glossary = root / "terms.tsv"
            self._write_srt(source, ["電気がビリビリ来ている"])
            glossary.write_text(
                "ビリー\t比利\n"
                "びりー\t比利\n"
                "ビリ\t比利\n",
                encoding="utf-8",
            )

            prepared = prepare_japanese_correction(source, glossary, root)

            self.assertEqual(prepared.candidates, ())

    def test_declined_candidates_are_reported_but_not_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            glossary = root / "terms.tsv"
            self._write_srt(source, ["ロクシイが来た", "ロクシーは強い"])
            glossary.write_text("ロクシー\t洛克茜\n", encoding="utf-8")
            prepared = prepare_japanese_correction(source, glossary, root)

            result = complete_japanese_correction(prepared, set())

            self.assertIn("ロクシイが来た", result.corrected_srt.read_text(encoding="utf-8"))
            report = result.markdown_report.read_text(encoding="utf-8")
            self.assertIn("保持原文", report)
            self.assertIn("ロクシイ", report)

    def test_bilingual_line_breaks_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            glossary = root / "terms.tsv"
            source.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\n"
                "希格莉德来了\nシグリットが来た\n",
                encoding="utf-8",
            )
            glossary.write_text(
                "シグリッド\t希格莉德\n"
                "しぐりっど\t希格莉德\n"
                "シグリット\t希格莉德\n",
                encoding="utf-8",
            )
            prepared = prepare_japanese_correction(source, glossary, root)

            result = complete_japanese_correction(prepared, {0})
            corrected = result.corrected_srt.read_text(encoding="utf-8")

            self.assertIn("希格莉德来了\nシグリッドが来た", corrected)


if __name__ == "__main__":
    unittest.main()
