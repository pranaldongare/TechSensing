"""Unit tests for core.sensing.sources.epo_patent_search — EPO OPS patent search."""

from unittest.mock import AsyncMock, patch

import pytest

from core.sensing.ingest import RawArticle
from core.sensing.sources.epo_patent_search import (
    _build_cql_query,
    _parse_biblio_xml,
    search_epo_patents,
)

# Sample EPO OPS XML response (minimal but structurally valid)
SAMPLE_EPO_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
    xmlns="http://www.epo.org/exchange">
  <ops:biblio-search total-result-count="2">
    <ops:search-result>
      <ops:publication-reference>
        <document-id document-id-type="epodoc">
          <doc-number>EP4123456</doc-number>
        </document-id>
      </ops:publication-reference>
      <exchange-document system="ops.epo.org" family-id="99999"
          country="EP" doc-number="4123456" kind="A1">
        <bibliographic-data>
          <publication-reference>
            <document-id document-id-type="epodoc">
              <doc-number>EP4123456</doc-number>
              <date>20250315</date>
            </document-id>
          </publication-reference>
          <invention-title lang="en">Method for generative AI inference</invention-title>
          <invention-title lang="fr">Procede d inference IA generative</invention-title>
          <abstract lang="en"><p>A method for optimizing inference in large language models.</p></abstract>
          <parties>
            <applicants>
              <applicant>
                <applicant-name><name>ACME CORP</name></applicant-name>
              </applicant>
            </applicants>
          </parties>
        </bibliographic-data>
      </exchange-document>
    </ops:search-result>
    <ops:search-result>
      <ops:publication-reference>
        <document-id document-id-type="epodoc">
          <doc-number>WO2025001234</doc-number>
        </document-id>
      </ops:publication-reference>
      <exchange-document system="ops.epo.org" family-id="88888"
          country="WO" doc-number="2025001234" kind="A2">
        <bibliographic-data>
          <publication-reference>
            <document-id document-id-type="epodoc">
              <doc-number>WO2025001234</doc-number>
              <date>20250201</date>
            </document-id>
          </publication-reference>
          <invention-title lang="en">Neural network training system</invention-title>
          <abstract lang="en"><p>A distributed training system for deep neural networks.</p></abstract>
          <parties>
            <applicants>
              <applicant>
                <applicant-name><name>TECH LABS INC</name></applicant-name>
              </applicant>
              <applicant>
                <applicant-name><name>UNIVERSITY OF AI</name></applicant-name>
              </applicant>
            </applicants>
          </parties>
        </bibliographic-data>
      </exchange-document>
    </ops:search-result>
  </ops:biblio-search>
</ops:world-patent-data>
"""


@pytest.mark.unit
class TestBuildCqlQuery:
    def test_basic_query(self):
        q = _build_cql_query("Generative AI", lookback_days=365)
        assert 'ti="Generative AI"' in q
        assert 'ab="Generative AI"' in q
        assert "pd>=" in q

    def test_with_must_include(self):
        q = _build_cql_query("Robotics", lookback_days=30, must_include=["LLM", "NLP"])
        assert 'ti="Robotics"' in q
        assert 'ti="LLM"' in q
        assert 'ti="NLP"' in q

    def test_caps_must_include_at_3(self):
        q = _build_cql_query("AI", lookback_days=7, must_include=["a", "b", "c", "d", "e"])
        # domain + 3 must_include = 4 keyword groups
        assert q.count("ti=") == 4


@pytest.mark.unit
class TestParseBiblioXml:
    def test_parses_two_patents(self):
        results = _parse_biblio_xml(SAMPLE_EPO_XML)
        assert len(results) == 2

    def test_first_patent_fields(self):
        results = _parse_biblio_xml(SAMPLE_EPO_XML)
        p = results[0]
        assert p["title"] == "Method for generative AI inference"
        assert p["patent_ref"] == "EP4123456"
        assert p["pub_date"] == "2025-03-15"
        assert p["country"] == "EP"
        assert "ACME CORP" in p["applicants"]

    def test_second_patent_multiple_applicants(self):
        results = _parse_biblio_xml(SAMPLE_EPO_XML)
        p = results[1]
        assert p["title"] == "Neural network training system"
        assert p["country"] == "WO"
        assert len(p["applicants"]) == 2
        assert "TECH LABS INC" in p["applicants"]
        assert "UNIVERSITY OF AI" in p["applicants"]

    def test_prefers_english_title(self):
        results = _parse_biblio_xml(SAMPLE_EPO_XML)
        # Should pick English title, not French
        assert "generative AI" in results[0]["title"]
        assert "generative" not in results[0]["title"].lower() or "procede" not in results[0]["title"].lower()

    def test_handles_invalid_xml(self):
        results = _parse_biblio_xml("not xml at all")
        assert results == []

    def test_handles_empty_xml(self):
        xml = '<?xml version="1.0"?><root></root>'
        results = _parse_biblio_xml(xml)
        assert results == []


@pytest.mark.unit
class TestSearchEpoPatents:
    @pytest.mark.asyncio
    @patch.dict("os.environ", {"EPO_CONSUMER_KEY": "", "EPO_CONSUMER_SECRET": ""})
    async def test_skips_when_no_credentials(self):
        result = await search_epo_patents("AI")
        assert result == []

    @pytest.mark.asyncio
    @patch("core.sensing.sources.epo_patent_search._get_access_token")
    @patch("core.sensing.sources.epo_patent_search.httpx.AsyncClient")
    @patch.dict("os.environ", {"EPO_CONSUMER_KEY": "test_key", "EPO_CONSUMER_SECRET": "test_secret"})
    async def test_returns_articles_on_success(self, mock_client_cls, mock_get_token):
        mock_get_token.return_value = "fake_token"

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_EPO_XML
        mock_resp.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        articles = await search_epo_patents("Generative AI")
        assert len(articles) == 2
        assert all(isinstance(a, RawArticle) for a in articles)
        assert articles[0].source == "EPO Patent"
        assert "ACME CORP" in articles[0].snippet
        assert articles[0].title == "Method for generative AI inference"

    @pytest.mark.asyncio
    @patch("core.sensing.sources.epo_patent_search._get_access_token")
    @patch("core.sensing.sources.epo_patent_search.httpx.AsyncClient")
    @patch.dict("os.environ", {"EPO_CONSUMER_KEY": "key", "EPO_CONSUMER_SECRET": "secret"})
    async def test_handles_api_error_gracefully(self, mock_client_cls, mock_get_token):
        mock_get_token.return_value = "fake_token"

        mock_resp = AsyncMock()
        mock_resp.status_code = 500

        import httpx
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=AsyncMock(), response=mock_resp
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        articles = await search_epo_patents("AI")
        assert articles == []
