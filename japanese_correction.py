"""Conservative glossary-based correction for Japanese SRT subtitles.

The corrector deliberately separates candidate discovery from applying edits.
Exact glossary aliases may be selected by default, while fuzzy suggestions
always require review.  Source subtitles and glossary files are never changed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata

from SrtMerge import seconds_to_srt_time, srt_time_to_seconds, write_srt


SubtitleEntry = tuple[float, float, str]


@dataclass(frozen=True)
class GlossaryTerm:
    """One canonical Japanese spelling and its known surface aliases."""

    canonical: str
    chinese: str
    aliases: tuple[str, ...]
    canonical_confident: bool


@dataclass(frozen=True)
class TermChange:
    """One proposed replacement inside a subtitle entry."""

    source: str
    target: str
    chinese: str
    match_type: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class JapaneseCorrectionCandidate:
    """A complete proposed rewrite of one subtitle, with nearby context."""

    entry_index: int
    entry: SubtitleEntry
    proposed_text: str
    changes: tuple[TermChange, ...]
    previous_entry: SubtitleEntry | None
    next_entry: SubtitleEntry | None
    default_selected: bool


@dataclass(frozen=True)
class JapaneseCorrectionPaths:
    corrected_srt: Path
    json_report: Path
    markdown_report: Path


@dataclass(frozen=True)
class PreparedJapaneseCorrection:
    source_subtitle: Path
    glossary_path: Path
    paths: JapaneseCorrectionPaths
    entries: tuple[SubtitleEntry, ...]
    candidates: tuple[JapaneseCorrectionCandidate, ...]
    glossary_term_count: int


@dataclass(frozen=True)
class JapaneseCorrectionOutput:
    corrected_srt: Path
    json_report: Path
    markdown_report: Path
    candidate_count: int
    applied_count: int


_KATAKANA_TOKEN = re.compile(r"[\u30a1-\u30ff\u31f0-\u31ff\uff66-\uff9fー・･]{4,}")
_KATAKANA_CHAR = re.compile(r"[\u30a1-\u30ff\u31f0-\u31ff\uff66-\uff9fー]")
_GLOSSARY_HEADER_WORDS = frozenset(
    {"日语", "日文", "日語", "原文", "source", "ja", "japanese"}
)


def normalize_japanese(text: str) -> str:
    """Normalize width, punctuation and hiragana/katakana for comparison."""
    normalized = unicodedata.normalize("NFKC", str(text)).strip()
    normalized = (
        normalized.replace("･", "・")
        .replace("−", "ー")
        .replace("－", "ー")
        .replace("―", "ー")
        .replace("-", "ー")
    )
    converted: list[str] = []
    for character in normalized:
        codepoint = ord(character)
        converted.append(
            chr(codepoint + 0x60)
            if 0x3041 <= codepoint <= 0x3096
            else character
        )
    return "".join(converted)


def _comparison_key(text: str) -> str:
    return re.sub(r"[\s・･]", "", normalize_japanese(text))


def _katakana_to_hiragana(text: str) -> str:
    converted: list[str] = []
    for character in normalize_japanese(text):
        codepoint = ord(character)
        converted.append(
            chr(codepoint - 0x60)
            if 0x30A1 <= codepoint <= 0x30F6
            else character
        )
    return "".join(converted)


def _is_hiragana_only(text: str) -> bool:
    key = re.sub(r"[\s・･ー]", "", unicodedata.normalize("NFKC", text))
    return bool(key) and bool(re.fullmatch(r"[\u3041-\u3096]+", key))


def _canonical_choice(variants: list[str]) -> tuple[str, bool]:
    def rank(item: tuple[int, str]) -> tuple[int, int, int, int, int, int]:
        index, variant = item
        normalized = normalize_japanese(variant)
        reading_twin = _katakana_to_hiragana(normalized) in {
            unicodedata.normalize("NFKC", other) for other in variants if other != variant
        }
        visible = re.sub(r"[\s・･]", "", normalized)
        has_japanese_script = bool(
            re.search(r"[\u30a1-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", visible)
        )
        has_hiragana = bool(re.search(r"[\u3041-\u3096]", visible))
        return (
            1 if reading_twin else 0,
            1 if has_japanese_script and not has_hiragana else 0,
            1 if "・" in variant else 0,
            0 if "･" in variant else 1,
            -normalized.count("ーー"),
            -index,
        )

    _index, canonical = max(enumerate(variants), key=rank)
    canonical_normalized = normalize_japanese(canonical)
    has_reading_twin = _katakana_to_hiragana(canonical_normalized) in {
        unicodedata.normalize("NFKC", variant)
        for variant in variants
        if variant != canonical
    }
    has_han_reading = bool(
        re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", canonical)
    ) and any(_is_hiragana_only(variant) for variant in variants)
    formatting_only = len({_comparison_key(variant) for variant in variants}) == 1
    return canonical, bool(has_reading_twin or has_han_reading or formatting_only)


def build_japanese_correction_paths(
    subtitle_path: str | Path, output_dir: str | Path
) -> JapaneseCorrectionPaths:
    source = Path(subtitle_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    stem = source.stem
    return JapaneseCorrectionPaths(
        corrected_srt=destination / f"{stem}_ja_corrected.srt",
        json_report=destination / f"{stem}_ja_corrections.json",
        markdown_report=destination / f"{stem}_ja_corrections.md",
    )


def _read_srt_preserving_lines(path: Path) -> tuple[SubtitleEntry, ...]:
    """Parse SRT while preserving bilingual and other multi-line text."""
    content = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\r?\n[ \t]*\r?\n", content.strip()) if content.strip() else []
    entries: list[SubtitleEntry] = []
    time_pattern = re.compile(
        r"^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*"
        r"(\d{2}:\d{2}:\d{2},\d{3})(?:\s+.*)?$"
    )
    for block_number, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        time_index = next(
            (index for index, line in enumerate(lines) if time_pattern.match(line.strip())),
            None,
        )
        if time_index is None:
            raise ValueError(f"字幕第 {block_number} 个区块缺少有效的 SRT 时间轴。")
        match = time_pattern.match(lines[time_index].strip())
        assert match is not None
        text = "\n".join(lines[time_index + 1 :]).strip()
        if not text:
            continue
        entries.append(
            (
                srt_time_to_seconds(match.group(1)),
                srt_time_to_seconds(match.group(2)),
                text,
            )
        )
    return tuple(entries)


def load_glossary(path: str | Path) -> tuple[GlossaryTerm, ...]:
    """Load a UTF-8 TSV and group repeated Chinese translations as aliases.

    The first Japanese spelling for a Chinese value is treated as canonical.
    This remains compatible with the project's existing two-column glossary.
    """
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到术语表文件：{source}")
    if source.suffix.lower() not in {".tsv", ".txt"}:
        raise ValueError("术语表必须是以制表符分隔的 .tsv 或 .txt 文件。")

    grouped: dict[str, list[str]] = {}
    for line_number, raw_line in enumerate(
        source.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        columns = [column.strip() for column in raw_line.split("\t")]
        if len(columns) < 2 or not columns[0] or not columns[1]:
            raise ValueError(f"术语表第 {line_number} 行必须至少包含日文和中文两列。")
        japanese, chinese = columns[:2]
        if line_number == 1 and japanese.casefold() in _GLOSSARY_HEADER_WORDS:
            continue
        variants = grouped.setdefault(chinese, [])
        if japanese not in variants:
            variants.append(japanese)

    terms_list: list[GlossaryTerm] = []
    for chinese, variants in grouped.items():
        if not variants:
            continue
        canonical, canonical_confident = _canonical_choice(variants)
        terms_list.append(
            GlossaryTerm(
                canonical=canonical,
                chinese=chinese,
                aliases=tuple(variant for variant in variants if variant != canonical),
                canonical_confident=canonical_confident,
            )
        )
    terms = tuple(terms_list)
    if not terms:
        raise ValueError("术语表中没有可用的日中术语。")
    return terms


def _build_exact_alias_index(
    terms: tuple[GlossaryTerm, ...]
) -> tuple[tuple[str, GlossaryTerm], ...]:
    canonicals = {term.canonical for term in terms}
    aliases = [
        (alias, term)
        for term in terms
        for alias in term.aliases
        if alias != term.canonical
        and alias not in canonicals
    ]
    aliases.sort(key=lambda item: len(item[0]), reverse=True)
    return tuple(aliases)


def _build_fuzzy_index(
    terms: tuple[GlossaryTerm, ...]
) -> tuple[tuple[GlossaryTerm, str], ...]:
    variants: list[tuple[GlossaryTerm, str]] = []
    for term in terms:
        canonical_key = _comparison_key(term.canonical)
        if len(canonical_key) < 4:
            continue
        for variant in (term.canonical, *term.aliases):
            key = _comparison_key(variant)
            if key and re.fullmatch(r"[\u30a1-\u30ffー]+", key):
                variants.append((term, key))
    return tuple(variants)


def _replace_exact_aliases(
    text: str, aliases: tuple[tuple[str, GlossaryTerm], ...]
) -> tuple[str, tuple[TermChange, ...]]:
    proposed_spans: list[tuple[int, int, str, GlossaryTerm]] = []
    for alias, term in aliases:
        search_from = 0
        while True:
            alias_start = text.find(alias, search_from)
            if alias_start < 0:
                break
            span = (alias_start, alias_start + len(alias))
            search_from = span[1]
            if len(_comparison_key(alias)) <= 3:
                before = text[span[0] - 1] if span[0] else ""
                after = text[span[1]] if span[1] < len(text) else ""
                if _KATAKANA_CHAR.fullmatch(before) or _KATAKANA_CHAR.fullmatch(after):
                    continue
            # An alias can be a prefix or suffix of its canonical form.  Do
            # not replace that substring when the surrounding source already
            # contains the complete canonical spelling.
            alias_offset = term.canonical.find(alias)
            if alias_offset >= 0:
                canonical_start = span[0] - alias_offset
                canonical_end = canonical_start + len(term.canonical)
                if (
                    canonical_start >= 0
                    and text[canonical_start:canonical_end] == term.canonical
                ):
                    continue
            proposed_spans.append((span[0], span[1], alias, term))

    proposed_spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    selected: list[tuple[int, int, str, GlossaryTerm]] = []
    for proposal in proposed_spans:
        start, end, _alias, _term = proposal
        if any(start < kept_end and kept_start < end for kept_start, kept_end, *_ in selected):
            continue
        selected.append(proposal)

    proposed = text
    for start, end, _alias, term in reversed(selected):
        proposed = proposed[:start] + term.canonical + proposed[end:]

    changes: list[TermChange] = []
    seen_changes: set[tuple[str, str, str]] = set()
    for _start, _end, alias, term in selected:
        identity = (alias, term.canonical, term.chinese)
        if identity in seen_changes:
            continue
        seen_changes.add(identity)
        changes.append(
            TermChange(
                source=alias,
                target=term.canonical,
                chinese=term.chinese,
                match_type="exact_alias",
                confidence=1.0,
                reason="术语表中同一中文译名下的明确日文别名",
            )
        )
    return proposed, tuple(changes)


def _fuzzy_change(
    text: str,
    term_variants: tuple[tuple[GlossaryTerm, str], ...],
    canonical_frequency: dict[str, int],
) -> TermChange | None:
    best_change: TermChange | None = None
    best_score = 0.0
    second_score = 0.0

    for match in _KATAKANA_TOKEN.finditer(text):
        surface = match.group(0)
        surface_key = _comparison_key(surface)
        if len(surface_key) < 4:
            continue
        if len(surface_key) % 2 == 0:
            midpoint = len(surface_key) // 2
            if surface_key[:midpoint] == surface_key[midpoint:]:
                continue
        ranked_by_target: dict[str, tuple[float, GlossaryTerm]] = {}
        for term, variant_key in term_variants:
            length_difference = abs(len(surface_key) - len(variant_key))
            if length_difference > max(2, round(len(variant_key) * 0.35)):
                continue
            if surface_key == variant_key:
                continue
            score = SequenceMatcher(None, surface_key, variant_key).ratio()
            frequency_bonus = 0.03 if canonical_frequency.get(term.canonical, 0) else 0.0
            score = min(1.0, score + frequency_bonus)
            previous = ranked_by_target.get(term.canonical)
            if previous is None or score > previous[0]:
                ranked_by_target[term.canonical] = (score, term)

        ranked = sorted(ranked_by_target.values(), key=lambda item: item[0], reverse=True)
        if not ranked:
            continue
        score, term = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        # Four-kana names with one wrong long vowel score 0.75.  They are
        # useful review candidates, but remain unchecked by default.
        recurrent = canonical_frequency.get(term.canonical, 0) > 0
        threshold = (0.74 if len(surface_key) <= 4 else 0.76) if recurrent else 0.84
        if score < threshold or score - runner_up < 0.08:
            continue
        if score > best_score:
            second_score = max(best_score, runner_up)
            best_score = score
            recurrence = "；标准写法已在本字幕中出现" if canonical_frequency.get(term.canonical, 0) else ""
            best_change = TermChange(
                source=surface,
                target=term.canonical,
                chinese=term.chinese,
                match_type="fuzzy_katakana",
                confidence=round(score, 4),
                reason=f"片假名写法相似度 {score:.1%}{recurrence}",
            )
        elif score > second_score:
            second_score = score

    if best_change is None or best_score - second_score < 0.08:
        return None
    return best_change


def prepare_japanese_correction(
    subtitle_path: str | Path,
    glossary_path: str | Path,
    output_dir: str | Path,
) -> PreparedJapaneseCorrection:
    """Discover conservative correction candidates without writing output."""
    subtitle = Path(subtitle_path).expanduser().resolve()
    glossary = Path(glossary_path).expanduser().resolve()
    if not subtitle.is_file() or subtitle.suffix.lower() != ".srt":
        raise ValueError("请选择有效的日语 .srt 字幕文件。")
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    terms = load_glossary(glossary)
    entries = _read_srt_preserving_lines(subtitle)
    all_text = "\n".join(entry[2] for entry in entries)
    canonical_frequency = {
        term.canonical: all_text.count(term.canonical) for term in terms
    }
    exact_aliases = _build_exact_alias_index(terms)
    fuzzy_index = _build_fuzzy_index(terms)

    candidates: list[JapaneseCorrectionCandidate] = []
    for entry_index, entry in enumerate(entries):
        original = entry[2]
        proposed, exact_changes = _replace_exact_aliases(original, exact_aliases)
        changes = list(exact_changes)
        default_selected = bool(exact_changes) and all(
            len(_comparison_key(change.target)) >= 4
            and len(_comparison_key(change.source)) >= 4
            and next(
                term.canonical_confident
                for term in terms
                if term.canonical == change.target and term.chinese == change.chinese
            )
            for change in exact_changes
        )
        if not changes:
            fuzzy = _fuzzy_change(original, fuzzy_index, canonical_frequency)
            if fuzzy is not None:
                proposed = original.replace(fuzzy.source, fuzzy.target, 1)
                changes.append(fuzzy)
                default_selected = False
        if proposed == original or not changes:
            continue
        candidates.append(
            JapaneseCorrectionCandidate(
                entry_index=entry_index,
                entry=entry,
                proposed_text=proposed,
                changes=tuple(changes),
                previous_entry=entries[entry_index - 1] if entry_index else None,
                next_entry=entries[entry_index + 1] if entry_index + 1 < len(entries) else None,
                default_selected=default_selected,
            )
        )

    return PreparedJapaneseCorrection(
        source_subtitle=subtitle,
        glossary_path=glossary,
        paths=build_japanese_correction_paths(subtitle, destination),
        entries=entries,
        candidates=tuple(candidates),
        glossary_term_count=len(terms),
    )


def _report_item(
    candidate: JapaneseCorrectionCandidate, applied: bool
) -> dict[str, object]:
    start, end, original = candidate.entry
    return {
        "subtitle_index": candidate.entry_index + 1,
        "start": start,
        "end": end,
        "start_srt": seconds_to_srt_time(start),
        "end_srt": seconds_to_srt_time(end),
        "original": original,
        "proposed": candidate.proposed_text,
        "applied": applied,
        "default_selected": candidate.default_selected,
        "changes": [asdict(change) for change in candidate.changes],
        "previous": candidate.previous_entry[2] if candidate.previous_entry else None,
        "next": candidate.next_entry[2] if candidate.next_entry else None,
    }


def complete_japanese_correction(
    prepared: PreparedJapaneseCorrection, accepted_indices: set[int]
) -> JapaneseCorrectionOutput:
    """Apply only reviewed entries and write SRT plus JSON/Markdown audit reports."""
    candidate_by_index = {
        candidate.entry_index: candidate for candidate in prepared.candidates
    }
    invalid = accepted_indices - set(candidate_by_index)
    if invalid:
        raise ValueError("只能接受审核窗口中列出的术语修改。")

    corrected_entries = list(prepared.entries)
    for entry_index in accepted_indices:
        candidate = candidate_by_index[entry_index]
        start, end, _text = corrected_entries[entry_index]
        corrected_entries[entry_index] = (start, end, candidate.proposed_text)

    write_srt(corrected_entries, str(prepared.paths.corrected_srt))
    report_items = [
        _report_item(candidate, candidate.entry_index in accepted_indices)
        for candidate in prepared.candidates
    ]
    report = {
        "source_subtitle": str(prepared.source_subtitle),
        "glossary": str(prepared.glossary_path),
        "glossary_term_count": prepared.glossary_term_count,
        "candidate_count": len(prepared.candidates),
        "applied_count": len(accepted_indices),
        "changes": report_items,
    }
    prepared.paths.json_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    markdown = [
        "# 日语字幕术语纠错报告",
        "",
        f"- 原字幕：`{prepared.source_subtitle}`",
        f"- 术语表：`{prepared.glossary_path}`",
        f"- 术语组数：{prepared.glossary_term_count}",
        f"- 候选数量：{len(prepared.candidates)}",
        f"- 已接受修改：{len(accepted_indices)}",
        "",
    ]
    if not report_items:
        markdown.append("未发现可可靠提示的术语写法差异。")
    for item in report_items:
        markdown.extend(
            [
                f"## 字幕 {item['subtitle_index']} · {item['start_srt']} → {item['end_srt']}",
                "",
                f"- 处理：{'已修改' if item['applied'] else '保持原文'}",
                f"- 原文：{item['original']}",
                f"- 建议：{item['proposed']}",
                f"- 前文：{item['previous'] or '无'}",
                f"- 后文：{item['next'] or '无'}",
            ]
        )
        for change in item["changes"]:
            markdown.append(
                f"- 依据：{change['source']} → {change['target']}"
                f"（{change['chinese']}；{change['reason']}）"
            )
        markdown.append("")
    prepared.paths.markdown_report.write_text(
        "\n".join(markdown).rstrip() + "\n", encoding="utf-8"
    )
    return JapaneseCorrectionOutput(
        corrected_srt=prepared.paths.corrected_srt,
        json_report=prepared.paths.json_report,
        markdown_report=prepared.paths.markdown_report,
        candidate_count=len(prepared.candidates),
        applied_count=len(accepted_indices),
    )
