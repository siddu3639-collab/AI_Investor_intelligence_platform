from app.ingestion.chunker import clean_text, semantic_chunk


def test_page_markers_removed_but_paragraphs_kept():
    text = "Revenue grew.\n\nPage 12\n\nCosts fell."
    cleaned = clean_text(text)
    assert "Page 12" not in cleaned
    assert "Revenue grew." in cleaned and "Costs fell." in cleaned


def test_text_mentioning_a_page_is_not_destroyed():
    assert "see Page 4 for details" in clean_text("Revenue grew, see Page 4 for details.")


def test_small_page_becomes_one_chunk_with_page_number():
    pages = [{"page": 7, "text": "Revenue increased by twelve percent because demand was strong."}]
    chunks = semantic_chunk(pages)
    assert len(chunks) == 1
    assert chunks[0]["page"] == 7


def test_long_text_is_split_within_limit_and_overlaps():
    sentence = "The company reported higher revenue due to strong demand in several markets. "
    pages = [{"page": 1, "text": sentence * 80}]
    chunks = semantic_chunk(pages, max_chars=600, overlap_chars=120)

    assert len(chunks) > 1
    assert all(len(c["content"]) <= 600 for c in chunks)
    tail_words = chunks[0]["content"].split()[-4:]
    assert " ".join(tail_words) in chunks[1]["content"]


def test_paragraph_breaks_are_respected():
    pages = [{"page": 1, "text": ("A" * 50 + ".\n\n") * 5}]
    chunks = semantic_chunk(pages, max_chars=120, overlap_chars=0)
    assert len(chunks) >= 2


def test_giant_unbroken_string_is_still_cut():
    pages = [{"page": 1, "text": "word " * 2000}]
    chunks = semantic_chunk(pages, max_chars=500, overlap_chars=50)
    assert all(len(c["content"]) <= 500 for c in chunks)


def test_empty_and_tiny_pages_produce_nothing():
    assert semantic_chunk([{"page": 1, "text": "   "}, {"page": 2, "text": "Hi"}]) == []
