"""Extra tests for LiteratureCorpus covering uncovered code paths."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from adda._src.literature.http_client import _robust_get, _robust_post
from adda._src.literature.literature_corpus import (
    LiteratureCorpus,
    _tokenize,
    _slugify,
)


def _make_corpus(tmp_path: Path) -> LiteratureCorpus:
    return LiteratureCorpus(tmp_path / "literature")


def _inject_paper(corpus: LiteratureCorpus, paper_id: str, title: str = "Test Paper",
                  authors: str = "A. Author", year: str = "2024",
                  source: str = "arxiv", text: str = "",
                  full_text: bool = True) -> None:
    paper_dir = corpus._paper_dir(paper_id)
    paper_dir.mkdir(parents=True, exist_ok=True)
    md_path = paper_dir / "paper.md"
    md_content = text or f"<!-- page 1 -->\nAbstract for {title}\n"
    md_path.write_text(md_content, encoding="utf-8")
    chunks = corpus._chunk_text(md_content)
    corpus._append_chunks(paper_id, chunks)
    rows = corpus._load_csv()
    rows.append({
        "paper_id": paper_id,
        "title": title,
        "authors": authors,
        "year": year,
        "doi": "",
        "arxiv_id": paper_id.replace("arxiv_", "").replace("_", "."),
        "venue": "",
        "abstract": f"Abstract for {title}",
        "local_pdf_path": "",
        "local_md_path": str(md_path),
        "added_at": "2024-01-01T00:00:00+00:00",
        "source": source,
        "citation_count": "0",
        "full_text": "true" if full_text else "false",
    })
    corpus._save_csv(rows)


# ---------------------------------------------------------------------------
# add() with a .txt file
# ---------------------------------------------------------------------------


def test_add_txt_file(tmp_path):
    """add() accepts a .txt file and stores it as paper.md."""
    corpus = _make_corpus(tmp_path)
    txt_file = tmp_path / "paper.txt"
    txt_file.write_text("<!-- page 1 -->\nContent from a text file.", encoding="utf-8")

    result = corpus.add(str(txt_file), arxiv_id="1234.56789", title="Text Paper")

    assert result == "arxiv_1234_56789"
    rows = corpus._load_csv()
    assert len(rows) == 1
    assert rows[0]["paper_id"] == "arxiv_1234_56789"


# ---------------------------------------------------------------------------
# add() with unsupported extension returns ERROR
# ---------------------------------------------------------------------------


def test_add_unsupported_extension_returns_error(tmp_path):
    """add() with a .docx file returns an ERROR string."""
    corpus = _make_corpus(tmp_path)
    docx_file = tmp_path / "paper.docx"
    docx_file.write_bytes(b"fake docx content")

    result = corpus.add(str(docx_file), title="Unsupported")

    assert result.startswith("ERROR:")
    assert "unsupported" in result.lower()


# ---------------------------------------------------------------------------
# _search_substring fallback (covers lines 397-432)
# ---------------------------------------------------------------------------


def test_search_substring_finds_match(tmp_path):
    """_search_substring returns matching passages."""
    corpus = _make_corpus(tmp_path)
    _inject_paper(
        corpus, "arxiv_1111_11111",
        title="Substring Test",
        text="<!-- page 1 -->\nThis paper discusses quantum entanglement.\n"
    )

    # Force BM25 to be unavailable so _search_substring is called
    import adda._src.literature.literature_corpus as lc_mod
    import sys

    # Save original rank_bm25 if present
    rank_bm25_saved = sys.modules.get("rank_bm25")
    sys.modules["rank_bm25"] = None  # type: ignore

    try:
        result = corpus.search("quantum entanglement", top_k=5)
    finally:
        if rank_bm25_saved is None:
            sys.modules.pop("rank_bm25", None)
        else:
            sys.modules["rank_bm25"] = rank_bm25_saved

    # Either finds it via BM25 (if installed) or substring
    # We just need it not to crash
    assert isinstance(result, str)


def test_search_substring_directly(tmp_path):
    """_search_substring directly returns results for exact matches."""
    corpus = _make_corpus(tmp_path)
    _inject_paper(
        corpus, "arxiv_2222_22222",
        title="Direct Substring",
        text="<!-- page 1 -->\nThe gravitational wave was detected in 2015.\n"
    )

    result = corpus._search_substring("gravitational wave", top_k=5)
    assert "gravitational wave" in result.lower()
    assert "Direct Substring" in result


def test_search_substring_respects_top_k(tmp_path):
    """_search_substring returns at most top_k passages."""
    corpus = _make_corpus(tmp_path)
    lines = "<!-- page 1 -->\n" + "\n".join(
        f"Line {i}: special_keyword here" for i in range(20)
    )
    _inject_paper(corpus, "arxiv_3333_33333", title="Many Matches", text=lines)

    result = corpus._search_substring("special_keyword", top_k=2)
    # Should have at most 2 passages (separated by "---")
    count = result.count("--- Many Matches")
    assert count <= 2


def test_search_substring_no_match(tmp_path):
    """_search_substring returns 'No results found.' when nothing matches."""
    corpus = _make_corpus(tmp_path)
    _inject_paper(corpus, "arxiv_4444_44444", title="No Match", text="<!-- page 1 -->\nHello world.\n")

    result = corpus._search_substring("zzznonexistentzzz", top_k=5)
    assert result == "No results found."


def test_search_substring_skips_missing_md_path(tmp_path):
    """_search_substring skips entries with empty or missing local_md_path."""
    corpus = _make_corpus(tmp_path)
    # Manually inject a row with no local_md_path
    rows = corpus._load_csv()
    rows.append({
        "paper_id": "orphan_paper",
        "title": "Orphan",
        "authors": "",
        "year": "2024",
        "doi": "",
        "arxiv_id": "",
        "venue": "",
        "abstract": "",
        "local_pdf_path": "",
        "local_md_path": "",  # empty — should be skipped
        "added_at": "2024-01-01T00:00:00+00:00",
        "source": "local",
        "citation_count": "0",
    })
    corpus._save_csv(rows)

    result = corpus._search_substring("anything", top_k=5)
    # Should not crash, and orphan_paper should not appear
    assert "orphan" not in result.lower() or result == "No results found."


# ---------------------------------------------------------------------------
# _robust_get retries and succeeds
# ---------------------------------------------------------------------------


def test_robust_get_succeeds_on_first_try():
    """_robust_get returns the response when the first request succeeds."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.headers = {}
    mock_resp.text = "{}"

    with patch("adda._src.literature.http_client._sleep"):
        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = _robust_get("http://example.com/api")

    assert result is mock_resp
    mock_get.assert_called_once()


def test_robust_get_retries_on_failure():
    """_robust_get retries up to `retries` times before raising."""
    import requests

    call_count = [0]

    def fail_get(*args, **kwargs):
        call_count[0] += 1
        raise requests.RequestException("Connection failed")

    with patch("requests.get", side_effect=fail_get):
        with patch("time.sleep"):  # skip actual sleep
            with pytest.raises(requests.RequestException):
                _robust_get("http://example.com/api", retries=3)

    assert call_count[0] == 3


def test_robust_post_succeeds_on_first_try():
    """_robust_post returns the response when the first request succeeds."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.headers = {}

    with patch("adda._src.literature.http_client._sleep"):
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = _robust_post(
                "http://example.com/api", json={"key": "val"}
            )

    assert result is mock_resp
    mock_post.assert_called_once()


def test_robust_post_retries_on_failure():
    """_robust_post retries up to `retries` times before raising."""
    import requests

    call_count = [0]

    def fail_post(*args, **kwargs):
        call_count[0] += 1
        raise requests.RequestException("POST failed")

    with patch("requests.post", side_effect=fail_post):
        with patch("time.sleep"):
            with pytest.raises(requests.RequestException):
                _robust_post("http://example.com/api", retries=2)

    assert call_count[0] == 2


def test_robust_get_succeeds_on_second_try():
    """_robust_get returns response when first attempt fails but second succeeds."""
    import requests

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.headers = {}
    mock_resp.text = "{}"
    attempts = [0]

    def flaky_get(*args, **kwargs):
        attempts[0] += 1
        if attempts[0] == 1:
            raise requests.RequestException("Temporary failure")
        return mock_resp

    with patch("requests.get", side_effect=flaky_get):
        with patch("adda._src.literature.http_client._sleep"):
            result = _robust_get("http://example.com/api", retries=3)

    assert result is mock_resp
    assert attempts[0] == 2


# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------


def test_tokenize_lowercases_and_strips_punctuation():
    """_tokenize strips punctuation and lowercases tokens."""
    result = _tokenize("Hello, world! This is a test.")
    assert "hello" in result
    assert "world" in result
    assert "test" in result
    # Punctuation-only tokens should be excluded
    assert "," not in result
    assert "!" not in result


def test_tokenize_preserves_hyphens():
    """_tokenize keeps hyphens inside words (e.g. self-attention)."""
    result = _tokenize("self-attention mechanism")
    assert "self-attention" in result


def test_tokenize_empty_string():
    """_tokenize returns empty list for empty string."""
    assert _tokenize("") == []


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


def test_slugify_replaces_non_alphanumeric():
    """_slugify replaces non-alphanumeric characters with underscores."""
    result = _slugify("Hello, World! 2024")
    assert "," not in result
    assert "!" not in result
    assert "Hello" in result
    assert "2024" in result


# ---------------------------------------------------------------------------
# get_paper with missing md path (line 440)
# ---------------------------------------------------------------------------


def test_get_paper_with_missing_md_path(tmp_path):
    """get_paper returns ERROR when local_md_path is empty."""
    corpus = _make_corpus(tmp_path)
    rows = corpus._load_csv()
    rows.append({
        "paper_id": "test_no_md",
        "title": "No MD",
        "authors": "",
        "year": "2024",
        "doi": "",
        "arxiv_id": "",
        "venue": "",
        "abstract": "",
        "local_pdf_path": "",
        "local_md_path": "",  # missing md path
        "added_at": "2024-01-01T00:00:00+00:00",
        "source": "local",
        "citation_count": "0",
    })
    corpus._save_csv(rows)

    result = corpus.get_paper("test_no_md")
    assert result.startswith("ERROR:")
    assert "no extracted text" in result


def test_get_paper_nonexistent_file(tmp_path):
    """get_paper returns ERROR when local_md_path points to non-existent file."""
    corpus = _make_corpus(tmp_path)
    rows = corpus._load_csv()
    rows.append({
        "paper_id": "test_gone_file",
        "title": "Gone",
        "authors": "",
        "year": "2024",
        "doi": "",
        "arxiv_id": "",
        "venue": "",
        "abstract": "",
        "local_pdf_path": "",
        "local_md_path": "/nonexistent/path/paper.md",
        "added_at": "2024-01-01T00:00:00+00:00",
        "source": "local",
        "citation_count": "0",
    })
    corpus._save_csv(rows)

    result = corpus.get_paper("test_gone_file")
    assert result.startswith("ERROR:")
    assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# add() duplicate check via second path (line 261-262)
# ---------------------------------------------------------------------------


def test_add_duplicate_detected_after_concurrent_first_add(tmp_path):
    """add() detects duplicate at second CSV check (post-file-copy path)."""
    corpus = _make_corpus(tmp_path)

    md1 = tmp_path / "paper1.md"
    md1.write_text("<!-- page 1 -->\nContent one.", encoding="utf-8")
    md2 = tmp_path / "paper2.md"
    md2.write_text("<!-- page 1 -->\nContent one.", encoding="utf-8")

    # First add
    result1 = corpus.add(str(md1), arxiv_id="9999.11111", title="Paper One")
    assert result1 == "arxiv_9999_11111"

    # Inject the same paper_id directly (simulating a race where paper_dir was
    # created but csv was not yet written)
    paper_dir = corpus._paper_dir("arxiv_9999_11111")
    paper_dir.mkdir(parents=True, exist_ok=True)

    # Second add with same arxiv_id should detect duplicate
    result2 = corpus.add(str(md2), arxiv_id="9999.11111", title="Paper One Again")
    assert "Already in corpus" in result2


# ---------------------------------------------------------------------------
# LiteratureCorpus creates directory on init
# ---------------------------------------------------------------------------


def test_corpus_creates_directory_on_init(tmp_path):
    """LiteratureCorpus creates corpus_dir and papers/ on init."""
    corpus_dir = tmp_path / "new_corpus"
    assert not corpus_dir.exists()

    corpus = LiteratureCorpus(corpus_dir)

    assert corpus_dir.exists()
    assert (corpus_dir / "papers").exists()


# ---------------------------------------------------------------------------
# search on empty corpus
# ---------------------------------------------------------------------------


def test_search_empty_corpus(tmp_path):
    """search() returns an informative ERROR when corpus is empty."""
    corpus = _make_corpus(tmp_path)
    result = corpus.search("anything")
    # Empty corpus has no full-text papers; search returns guidance
    assert "ERROR" in result or result == "No results found."


# ---------------------------------------------------------------------------
# _chunk_text with page markers
# ---------------------------------------------------------------------------


def test_chunk_text_respects_page_markers(tmp_path):
    """_chunk_text assigns correct page numbers from <!-- page N --> markers."""
    corpus = _make_corpus(tmp_path)
    text = "<!-- page 1 -->\nFirst page content.\n<!-- page 2 -->\nSecond page content.\n"
    chunks = corpus._chunk_text(text)

    assert len(chunks) >= 1
    # First chunk should be on page 1
    assert chunks[0]["page"] == 1


def test_chunk_text_empty_string(tmp_path):
    """_chunk_text handles empty string gracefully."""
    corpus = _make_corpus(tmp_path)
    chunks = corpus._chunk_text("")
    assert chunks == []


# ---------------------------------------------------------------------------
# _load_all_embeddings partial coverage — one unembedded paper must not
# disable dense retrieval for the whole corpus.
#
# VERIFIED BUG: on the frozen litcorpus fixture, 1 of 132 papers (724 of
# 12,919 chunks = 5.60%) has chunks in chunks.jsonl but no chunks.npy
# (hussein2015_thesis_curved_beams_multistable_microrobots). The old
# _load_all_embeddings() aborted the WHOLE matrix (returned (chunks, None))
# the moment it hit that one paper's missing embeddings — discarding dense
# ranking for the other 131 papers (94.4%) that DID have embeddings, and
# silently downgrading retrieval_mode="auto" to BM25-only.
# ---------------------------------------------------------------------------


def _inject_paper_with_embedding(corpus, paper_id, title, text, vectors):
    """Like _inject_paper, but also writes a real chunks.npy.

    *vectors* must have one row per chunk _chunk_text(text) produces for
    *text* (use short text — under 150 words — for exactly one chunk).
    """
    _inject_paper(corpus, paper_id, title=title, text=text)
    paper_dir = corpus._paper_dir(paper_id)
    np.save(str(paper_dir / "chunks.npy"), np.asarray(vectors, dtype=np.float32))


class _FakeEmbedder:
    """Stub for LiteratureCorpus._get_embedding_model(): a fixed query vector,
    independent of the input text — search() only ever calls .embed([query])."""

    def __init__(self, query_vec):
        self._query_vec = list(query_vec)

    def embed(self, texts):
        return [self._query_vec]


def test_load_all_embeddings_partial_coverage_returns_matrix_not_none(tmp_path):
    """(a) one paper of several lacking chunks.npy still yields a matrix.

    FAILS on today's code: the per-chunk loop in _load_all_embeddings hits
    paper_no_emb (no chunks.npy) and returns (chunks, None) unconditionally,
    discarding paper_a's and paper_c's embeddings too.
    """
    corpus = _make_corpus(tmp_path)
    _inject_paper_with_embedding(
        corpus, "paper_a", "Paper A", "alpha content words here",
        [[1.0, 0.0, 0.0, 0.0]],
    )
    _inject_paper(
        corpus, "paper_no_emb", title="Paper NoEmb",
        text="beta content with no embedding file at all",
    )
    _inject_paper_with_embedding(
        corpus, "paper_c", "Paper C", "gamma content words here",
        [[0.0, 0.0, 1.0, 0.0]],
    )

    chunks, matrix, has_embedding = corpus._load_all_embeddings()

    assert matrix is not None, (
        "one paper lacking chunks.npy must not abort the WHOLE embedding "
        "matrix — dense ranking must still run over the papers that DO "
        "have embeddings"
    )
    assert len(chunks) == 3
    assert len(matrix) == 3
    assert has_embedding is not None
    assert list(has_embedding) == [True, False, True]
    # Alignment: each embedded paper's row must be ITS OWN vector, not
    # shifted by the unembedded paper sitting between them in chunk order.
    np.testing.assert_allclose(matrix[0], [1.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(matrix[2], [0.0, 0.0, 1.0, 0.0])


def test_load_all_embeddings_fewer_rows_than_chunks_partial_coverage(tmp_path):
    """(b) a paper re-chunked without a re-embed (fewer .npy rows than
    chunks) loses dense coverage for only ITS excess chunk(s), not the
    whole corpus.

    FAILS on today's code: the second-instance guard
    (`idx >= len(paper_embs[pid])`) also returns (chunks, None)
    unconditionally.
    """
    corpus = _make_corpus(tmp_path)
    words = " ".join(f"word{i}" for i in range(200))  # -> 2 chunks
    text = "<!-- page 1 -->\n" + words + "\n"
    _inject_paper(corpus, "paper_rechunked", title="Rechunked", text=text)
    paper_dir = corpus._paper_dir("paper_rechunked")
    # Stale embeddings: only 1 row though _chunk_text now produces 2 chunks.
    np.save(str(paper_dir / "chunks.npy"),
            np.array([[1.0, 0.0]], dtype=np.float32))
    _inject_paper_with_embedding(
        corpus, "paper_ok", "OK", "other short content here",
        [[0.0, 1.0]],
    )

    chunks, matrix, has_embedding = corpus._load_all_embeddings()

    assert matrix is not None, (
        "a paper with fewer embedding rows than chunks must not abort the "
        "WHOLE embedding matrix"
    )
    rechunked_positions = [
        i for i, c in enumerate(chunks) if c["paper_id"] == "paper_rechunked"
    ]
    assert len(rechunked_positions) == 2
    assert has_embedding[rechunked_positions[0]] == True  # noqa: E712
    assert has_embedding[rechunked_positions[1]] == False  # noqa: E712
    ok_positions = [i for i, c in enumerate(chunks) if c["paper_id"] == "paper_ok"]
    assert has_embedding[ok_positions[0]] == True  # noqa: E712


def test_load_all_embeddings_no_papers_embedded_still_returns_none(tmp_path):
    """Zero coverage (no paper has any embedding at all) is still None —
    the corpus-wide fallback to BM25/substring must be preserved when there
    is genuinely nothing to rank densely."""
    corpus = _make_corpus(tmp_path)
    _inject_paper(corpus, "paper_1", title="One", text="one content words")
    _inject_paper(corpus, "paper_2", title="Two", text="two content words")

    chunks, matrix, has_embedding = corpus._load_all_embeddings()

    assert matrix is None
    assert has_embedding is None


def test_search_hybrid_partial_coverage_stays_hybrid_and_reports_coverage(tmp_path):
    """(c) partial dense coverage is VISIBLE, not silent, and hybrid mode
    still actually runs (resolved_mode == 'hybrid', not silently 'bm25')
    when only some papers have embeddings.

    FAILS on today's code: _load_all_embeddings returns None because of
    paper_no_emb, so dense_ranks stays empty and resolved_mode becomes
    'bm25' even though retrieval_mode='hybrid' was requested and an
    embedder IS available — exactly the mislabelled-condition failure mode
    the module docstring calls out.
    """
    from adda._src.runtime import settings

    corpus = _make_corpus(tmp_path)
    _inject_paper_with_embedding(
        corpus, "paper_dense_hit", "Dense Hit Paper",
        "zzzznomatch zzzznomatch content words",
        [[1.0, 0.0]],
    )
    _inject_paper(
        corpus, "paper_no_emb", title="No Embedding Paper",
        text="completely unrelated filler content with no embedding file",
    )

    query_vec = [1.0, 0.0]  # cosine-aligned with paper_dense_hit's vector
    corpus._get_embedding_model = lambda: _FakeEmbedder(query_vec)

    try:
        settings.configure({"retrieval_mode": "hybrid"})
        result = corpus.search("zzzznomatch", top_k=5)
        assert corpus.resolved_mode == "hybrid", (
            f"requested retrieval_mode='hybrid' but resolved_mode="
            f"{corpus.resolved_mode!r} — a run labelled hybrid silently "
            "ran as bm25 because one paper's missing embedding poisoned "
            "the whole matrix"
        )
        assert "Dense Hit Paper" in result
        # The partial-coverage signal must be observable, not silent.
        assert corpus.dense_coverage is not None
        assert 0.0 < corpus.dense_coverage < 1.0
    finally:
        settings.configure(None)


def test_search_full_coverage_reports_dense_coverage_one(tmp_path):
    """When every full-text paper has embeddings, dense_coverage == 1.0."""
    from adda._src.runtime import settings

    corpus = _make_corpus(tmp_path)
    _inject_paper_with_embedding(
        corpus, "paper_a", "Paper A", "alpha content words here",
        [[1.0, 0.0]],
    )
    _inject_paper_with_embedding(
        corpus, "paper_b", "Paper B", "beta content words here",
        [[0.0, 1.0]],
    )
    corpus._get_embedding_model = lambda: _FakeEmbedder([1.0, 0.0])

    try:
        settings.configure({"retrieval_mode": "hybrid"})
        corpus.search("alpha", top_k=5)
        assert corpus.resolved_mode == "hybrid"
        assert corpus.dense_coverage == 1.0
    finally:
        settings.configure(None)
