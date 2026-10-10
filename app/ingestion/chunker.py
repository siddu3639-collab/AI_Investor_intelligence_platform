import re

MIN_CHUNK_CHARS = 40  # skip scraps like a lone page header


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\x00", "")

    # Drop lines that are *only* a page marker ("Page 12", "page 3 of 80").
    text = re.sub(
        r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", "", text, flags=re.IGNORECASE | re.MULTILINE
    )

    text = re.sub(r"[ \t]+", " ", text)      # runs of spaces/tabs -> one space
    text = re.sub(r"\n{3,}", "\n\n", text)   # many blank lines -> one
    return text.strip()


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    current = ""

    for sentence in sentences:
        # A "sentence" longer than the limit (a table dump, say): cut on words.
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()

        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = sentence

    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def _split_into_units(text: str, max_chars: int) -> list[str]:
    units: list[str] = []

    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip() 
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            units.append(paragraph)
        else:
            units.extend(_split_long(paragraph, max_chars))

    return units


def _overlap_tail(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return ""
    tail = text[-overlap_chars:]
    first_space = tail.find(" ")
    return tail[first_space + 1:] if first_space != -1 else tail


def semantic_chunk(
    pages: list[dict],
    max_chars: int = 1800,
    overlap_chars: int = 300,
) -> list[dict]:
    chunks: list[dict] = []

    for page in pages:
        text = clean_text(page["text"])
        if not text:
            continue

        current = ""

        for unit in _split_into_units(text, max_chars):
            candidate = f"{current} {unit}".strip()

            if len(candidate) <= max_chars:
                current = candidate
                continue

            # Chunk is full: save it and start the next one with some overlap.
            if len(current) >= MIN_CHUNK_CHARS:
                chunks.append({"page": page["page"], "content": current})

            seeded = f"{_overlap_tail(current, overlap_chars)} {unit}".strip()
            current = seeded if len(seeded) <= max_chars else unit

        if len(current) >= MIN_CHUNK_CHARS:
            chunks.append({"page": page["page"], "content": current})

    return chunks
