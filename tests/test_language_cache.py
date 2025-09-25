"""Tests ensuring LanguageAnalyzer memoization integrates with other modules."""

from __future__ import annotations

from auto_movie_edit.language import LanguageAnalyzer
from auto_movie_edit.proposals import ProposalModel
from auto_movie_edit.ymmp import ProjectBuilder
from auto_movie_edit.models import TimelineRow, WorkbookData


def test_extract_keywords_cache_hits() -> None:
    analyzer = LanguageAnalyzer()
    text = "テスト テスト 例 例 サンプル"

    initial_info = analyzer._keywords_cached.cache_info()  # type: ignore[attr-defined]
    first = analyzer.extract_keywords(text, limit=5)
    after_first = analyzer._keywords_cached.cache_info()  # type: ignore[attr-defined]
    second = analyzer.extract_keywords(text, limit=2)
    after_second = analyzer._keywords_cached.cache_info()  # type: ignore[attr-defined]

    assert first[:2] == second
    assert after_first.misses == initial_info.misses + 1
    assert after_second.misses == after_first.misses
    assert after_second.hits >= after_first.hits + 1


def test_project_builder_detect_tone_uses_cache() -> None:
    data = WorkbookData()
    builder = ProjectBuilder(data)
    row = TimelineRow(
        index=0,
        start=None,
        end=None,
        subtitle="これはテストですか？",
        telop=None,
        character="hero",
    )

    initial_info = builder.language_analyzer._tone_cached.cache_info()  # type: ignore[attr-defined]
    builder._apply_expression_presets(row)
    after_first = builder.language_analyzer._tone_cached.cache_info()  # type: ignore[attr-defined]
    builder._apply_expression_presets(row)
    after_second = builder.language_analyzer._tone_cached.cache_info()  # type: ignore[attr-defined]

    assert after_first.misses == initial_info.misses + 1
    assert after_second.misses == after_first.misses
    assert after_second.hits >= after_first.hits + 1


def test_proposal_model_tokenize_uses_language_cache() -> None:
    analyzer = LanguageAnalyzer()
    text = "キャッシュ テスト"

    initial_info = analyzer._tokenize_cached.cache_info()  # type: ignore[attr-defined]
    first = ProposalModel._tokenize(text, analyzer=analyzer)
    after_first = analyzer._tokenize_cached.cache_info()  # type: ignore[attr-defined]
    second = ProposalModel._tokenize(text, analyzer=analyzer)
    after_second = analyzer._tokenize_cached.cache_info()  # type: ignore[attr-defined]

    assert first == second
    assert after_first.misses == initial_info.misses + 1
    assert after_second.misses == after_first.misses
    assert after_second.hits >= after_first.hits + 1
