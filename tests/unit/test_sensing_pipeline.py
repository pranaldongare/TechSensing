"""Unit tests for core.sensing.pipeline — pipeline orchestration."""

from unittest.mock import AsyncMock, patch

import pytest

from core.sensing.ingest import RawArticle
from core.llm.output_schemas.sensing_outputs import (
    ClassifiedArticle,
    RadarItem,
    Recommendation,
    ReportSection,
    TechSensingReport,
    TrendItem,
)


def _make_raw_articles(n=5):
    return [
        RawArticle(
            title=f"Article {i}",
            url=f"https://example.com/{i}",
            source="TestSource",
            snippet=f"Snippet {i}",
        )
        for i in range(n)
    ]


def _make_classified_articles(n=3):
    return [
        ClassifiedArticle(
            title=f"Classified {i}",
            source="TestSource",
            url=f"https://example.com/{i}",
            published_date="2026-03-25T00:00:00",
            summary=f"Summary {i}",
            relevance_score=0.8,
            quadrant="Techniques",
            ring="Assess",
            technology_name=f"Tech{i}",
            reasoning=f"Reason {i}",
        )
        for i in range(n)
    ]


def _make_report():
    return TechSensingReport(
        report_title="Test Report",
        executive_summary="Test summary",
        domain="Generative AI",
        date_range="Mar 20 - Mar 27, 2026",
        total_articles_analyzed=5,
        key_trends=[
            TrendItem(
                trend_name="Test Trend",
                description="A test trend",
                evidence=["Article 1"],
                impact_level="High",
                time_horizon="Near-term (6-18mo)",
            )
        ],
        report_sections=[
            ReportSection(
                section_title="Section 1", content="Section content"
            )
        ],
        radar_items=[
            RadarItem(
                name="TestTech",
                quadrant="Techniques",
                ring="Assess",
                description="A test technology",
                is_new=True,
            )
        ],
        recommendations=[
            Recommendation(
                title="Test Rec",
                description="Do this",
                priority="High",
                related_trends=["Test Trend"],
            )
        ],
        notable_articles=_make_classified_articles(1),
    )


@pytest.mark.unit
class TestRunSensingPipeline:
    @pytest.mark.asyncio
    @patch("core.sensing.pipeline.fetch_youtube_videos")
    @patch("core.sensing.pipeline.generate_report")
    @patch("core.sensing.pipeline.classify_articles")
    @patch("core.sensing.pipeline.extract_full_text")
    @patch("core.sensing.pipeline.deduplicate_articles")
    @patch("core.sensing.pipeline.search_duckduckgo")
    @patch("core.sensing.pipeline.fetch_rss_feeds")
    async def test_full_pipeline(
        self,
        mock_rss,
        mock_ddg,
        mock_dedup,
        mock_extract,
        mock_classify,
        mock_report,
        mock_youtube,
    ):
        raw_articles = _make_raw_articles(5)
        classified = _make_classified_articles(3)
        report = _make_report()

        mock_rss.return_value = raw_articles[:3]
        mock_ddg.return_value = raw_articles[3:]
        mock_dedup.return_value = raw_articles
        mock_extract.side_effect = lambda a: a  # pass through
        mock_classify.return_value = classified
        mock_report.return_value = report
        mock_youtube.return_value = []

        from core.sensing.pipeline import run_sensing_pipeline

        result = await run_sensing_pipeline(domain="Generative AI")

        assert result.raw_article_count == 5
        assert result.deduped_article_count == 5
        assert result.classified_article_count == 3
        assert result.report.report_title == "Test Report"
        assert result.execution_time_seconds >= 0

        mock_rss.assert_called_once()
        mock_ddg.assert_called_once()
        mock_dedup.assert_called_once()
        mock_classify.assert_called_once()
        mock_report.assert_called_once()

    @pytest.mark.asyncio
    @patch("core.sensing.pipeline.fetch_youtube_videos")
    @patch("core.sensing.pipeline.generate_report")
    @patch("core.sensing.pipeline.classify_articles")
    @patch("core.sensing.pipeline.extract_full_text")
    @patch("core.sensing.pipeline.deduplicate_articles")
    @patch("core.sensing.pipeline.search_duckduckgo")
    @patch("core.sensing.pipeline.fetch_rss_feeds")
    async def test_progress_callback_called(
        self,
        mock_rss,
        mock_ddg,
        mock_dedup,
        mock_extract,
        mock_classify,
        mock_report,
        mock_youtube,
    ):
        mock_rss.return_value = []
        mock_ddg.return_value = []
        mock_dedup.return_value = []
        mock_extract.side_effect = lambda a: a
        mock_classify.return_value = []
        mock_report.return_value = _make_report()
        mock_youtube.return_value = []

        callback = AsyncMock()

        from core.sensing.pipeline import run_sensing_pipeline

        await run_sensing_pipeline(
            domain="AI", progress_callback=callback
        )

        # Should have called progress at each stage
        assert callback.call_count >= 5
        stages = [call.args[0] for call in callback.call_args_list]
        assert "ingest" in stages
        assert "dedup" in stages
        assert "extract" in stages
        assert "classify" in stages
        assert "videos" in stages
        assert "complete" in stages
