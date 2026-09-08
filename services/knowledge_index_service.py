from difflib import get_close_matches
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread

from services.database_service import (
    get_knowledge_documents,
    get_support_articles as get_saved_support_articles,
)
from services.macro_service import (
    get_macros,
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AI_INDEX_DIR = PROJECT_ROOT / "data" / "ai_index"
WORKSPACE_INDEX_PATH = AI_INDEX_DIR / "workspace_knowledge_index.json"
WORKSPACE_INDEX_SCHEMA_VERSION = 2
MAX_CHARS_PER_CHUNK = 900
MAX_SEARCH_RESULTS = 8
QUERY_TOKEN_ALIASES = {
    "macrous": "macros",
}
QUERY_TOKEN_SYNONYMS = {
    "apartment": {
        "flat",
        "home",
        "property",
        "residence",
        "unit",
        "units",
    },
    "commercial": {
        "office",
        "offices",
        "property",
        "retail",
        "showroom",
        "warehouse",
    },
    "handover": {
        "defect",
        "maintenance",
        "possession",
        "snag",
    },
    "plot": {
        "land",
        "parcel",
        "plot",
        "plots",
        "property",
        "site",
    },
    "price": {
        "cost",
        "pricing",
        "quotation",
        "quote",
        "rate",
    },
    "project": {
        "community",
        "development",
        "phase",
        "property",
        "tower",
    },
    "property": {
        "apartment",
        "commercial",
        "flat",
        "home",
        "plot",
        "project",
        "unit",
        "villa",
    },
    "unit": {
        "apartment",
        "flat",
        "home",
        "inventory",
        "property",
        "units",
    },
    "villa": {
        "bungalow",
        "home",
        "house",
        "property",
        "residence",
        "villa",
        "villas",
    },
}
LOW_SIGNAL_QUERY_TERMS = {
    "agent",
    "ai",
    "article",
    "bot",
    "chat",
    "contact",
    "count",
    "customer",
    "document",
    "help",
    "knowledge",
    "macros",
    "many",
    "acrobuild",
    "feature",
    "features",
    "number",
    "page",
    "policy",
    "support",
    "team",
    "workspace",
    "available",
    "website",
}
STOPWORD_TOKENS = {
    "a",
    "about",
    "after",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "before",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "more",
    "my",
    "of",
    "on",
    "or",
    "our",
    "please",
    "should",
    "so",
    "than",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "to",
    "up",
    "us",
    "want",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}
INDEX_LOCK = Lock()
INDEX_BUILD_LOCK = Lock()
WORKSPACE_INDEX_CACHE = None
WORKSPACE_INDEX_BUILDING = False
WORKSPACE_INDEX_DIRTY = False


def is_semantic_search_enabled():

    return False


def normalize_index_text(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def sanitize_macro_workspace_text(value):

    cleaned_text = re.sub(
        r"\{\{\s*[^}]+?\s*\}\}",
        " ",
        str(value or ""),
    )
    cleaned_lines = []

    for line in cleaned_text.splitlines():
        normalized_line = normalize_index_text(
            line
        )
        lowered_line = normalized_line.lower()

        if not normalized_line:
            continue

        if lowered_line.startswith(
            (
                "best regards",
                "hello ",
                "hi ",
                "kind regards",
                "thanks,",
                "warm regards",
            )
        ) or lowered_line in (
            "hello",
            "hi",
        ):
            continue

        cleaned_lines.append(
            normalized_line
        )

    cleaned_text = "\n".join(
        cleaned_lines
    )
    cleanup_patterns = (
        (
            r"\blinked to\s+\.",
            ".",
        ),
        (
            r"\bfor ticket\s+\.",
            ".",
        ),
        (
            r"\bfor order\s+\.",
            ".",
        ),
        (
            r"\bticket\s+\.",
            ".",
        ),
        (
            r"\border\s+\.",
            ".",
        ),
        (
            r"\blinked to\s*\.",
            ".",
        ),
        (
            r"\baffected in\s*\.",
            "affected.",
        ),
        (
            r"\s+([.,!?;:])",
            r"\1",
        ),
    )

    for pattern, replacement in cleanup_patterns:
        cleaned_text = re.sub(
            pattern,
            replacement,
            cleaned_text,
            flags=re.IGNORECASE,
        )

    return cleaned_text.strip()


def tokenize_index_text(value):

    return {
        token
        for token in re.findall(
            r"[a-z0-9]+",
            normalize_index_text(value).lower(),
        )
        if len(token) > 1
        and token not in STOPWORD_TOKENS
    }


def normalize_query_token(token):

    cleaned_token = normalize_index_text(
        token
    ).lower()

    return QUERY_TOKEN_ALIASES.get(
        cleaned_token,
        cleaned_token,
    )


def collect_workspace_vocabulary(
    workspace_index,
):

    vocabulary = set()

    for item in workspace_index.get(
        "items",
        [],
    ):
        vocabulary.update(
            item.get("title_terms", [])
        )
        vocabulary.update(
            item.get("tag_terms", [])
        )
        vocabulary.update(
            item.get("content_terms", [])
        )

    return vocabulary


def expand_query_tokens(
    query_tokens,
    workspace_vocabulary=None,
):

    expanded_tokens = set()
    workspace_vocabulary = (
        workspace_vocabulary or set()
    )

    for token in query_tokens:
        normalized_token = normalize_query_token(
            token
        )
        expanded_tokens.add(
            normalized_token
        )
        expanded_tokens.update(
            QUERY_TOKEN_SYNONYMS.get(
                normalized_token,
                set(),
            )
        )

        if (
            normalized_token
            and normalized_token
            not in workspace_vocabulary
            and len(normalized_token) >= 5
        ):
            close_matches = get_close_matches(
                normalized_token,
                list(workspace_vocabulary),
                n=1,
                cutoff=0.84,
            )

            if close_matches:
                corrected_token = close_matches[0]
                expanded_tokens.add(
                    corrected_token
                )
                expanded_tokens.update(
                    QUERY_TOKEN_SYNONYMS.get(
                        corrected_token,
                        set(),
                    )
                )

    return {
        token
        for token in expanded_tokens
        if token
    }


def get_chunk_overlap_details(
    chunk_entry,
    query_tokens,
):

    title_tokens = set(
        chunk_entry.get(
            "title_terms",
            [],
        )
    )
    tag_tokens = {
        normalize_index_text(tag).lower()
        for tag in chunk_entry.get(
            "tag_terms",
            [],
        )
    }
    content_tokens = set(
        chunk_entry.get(
            "content_terms",
            [],
        )
    )
    overlap_tokens = query_tokens & (
        title_tokens
        | tag_tokens
        | content_tokens
    )
    strong_overlap_tokens = {
        token
        for token in overlap_tokens
        if token not in LOW_SIGNAL_QUERY_TERMS
    }
    strong_title_overlap_tokens = (
        strong_overlap_tokens
        & title_tokens
    )
    strong_tag_overlap_tokens = (
        strong_overlap_tokens
        & tag_tokens
    )
    strong_content_overlap_tokens = (
        strong_overlap_tokens
        & content_tokens
    )

    return {
        "content_tokens": content_tokens,
        "overlap_tokens": overlap_tokens,
        "strong_overlap_tokens": strong_overlap_tokens,
        "strong_content_overlap_tokens": strong_content_overlap_tokens,
        "tag_tokens": tag_tokens,
        "title_tokens": title_tokens,
        "strong_tag_overlap_tokens": strong_tag_overlap_tokens,
        "strong_title_overlap_tokens": strong_title_overlap_tokens,
    }


def ensure_ai_index_dir():

    AI_INDEX_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def split_text_into_chunks(
    text,
    max_chars=MAX_CHARS_PER_CHUNK,
):

    cleaned_text = str(text or "").replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).strip()

    if not cleaned_text:
        return []

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(
            r"\n\s*\n",
            cleaned_text,
        )
        if paragraph.strip()
    ]

    if not paragraphs:
        paragraphs = [cleaned_text]

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        paragraph_sentences = re.split(
            r"(?<=[.!?])\s+",
            paragraph,
        )

        for sentence in paragraph_sentences:
            cleaned_sentence = normalize_index_text(
                sentence
            )

            if not cleaned_sentence:
                continue

            candidate_chunk = (
                f"{current_chunk} {cleaned_sentence}".strip()
                if current_chunk
                else cleaned_sentence
            )

            if current_chunk and len(candidate_chunk) > max_chars:
                chunks.append(current_chunk)
                current_chunk = cleaned_sentence
                continue

            if len(cleaned_sentence) > max_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                for index in range(
                    0,
                    len(cleaned_sentence),
                    max_chars,
                ):
                    chunks.append(
                        cleaned_sentence[
                            index:index + max_chars
                        ].strip()
                    )

                continue

            current_chunk = candidate_chunk

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def build_workspace_records():

    published_documents = [
        {
            **document,
            "record_kind": "knowledge",
            "source_key": f"knowledge:{int(document['id'])}",
        }
        for document in get_knowledge_documents()
        if normalize_index_text(
            document.get("status")
        ).lower() == "published"
    ]
    published_articles = [
        {
            **article,
            "record_kind": "article",
            "source_key": f"article:{int(article['id'])}",
        }
        for article in get_saved_support_articles()
        if normalize_index_text(
            article.get("status")
        ).lower() == "published"
    ]
    published_macros = []

    for macro in get_macros(
        include_archived=False
    ):
        macro_body = sanitize_macro_workspace_text(
            macro.get(
                "response_text",
                "",
            )
        )

        if not macro_body:
            continue

        macro_summary = normalize_index_text(
            macro.get(
                "description",
                "",
            )
        )
        published_macros.append(
            {
                "body": macro_body,
                "category": normalize_index_text(
                    macro.get(
                        "category",
                        "",
                    )
                )
                or "Macros",
                "id": int(macro["id"]),
                "record_kind": "knowledge",
                "source_key": f"macro:{int(macro['id'])}",
                "source_name": normalize_index_text(
                    macro.get(
                        "name",
                        "",
                    )
                )
                or "Macro",
                "source_type": "macro",
                "status": "Published",
                "summary": macro_summary,
                "tags": macro.get(
                    "tag_names",
                    [],
                ),
                "title": normalize_index_text(
                    macro.get(
                        "name",
                        "",
                    )
                )
                or "Macro reply",
                "updated_at": normalize_index_text(
                    macro.get(
                        "updated_at",
                        "",
                    )
                ),
                "url": "",
            }
        )

    return (
        published_documents
        + published_articles
        + published_macros
    )


def build_workspace_fingerprint(records):

    serialized_records = json.dumps(
        [
            {
                "body": normalize_index_text(
                    record.get("body", "")
                ),
                "category": normalize_index_text(
                    record.get("category", "")
                ),
                "id": str(record.get("id", "")),
                "keywords": record.get(
                    "keywords",
                    [],
                ),
                "record_kind": record.get(
                    "record_kind",
                    "",
                ),
                "source_key": record.get(
                    "source_key",
                    "",
                ),
                "source_name": normalize_index_text(
                    record.get("source_name", "")
                ),
                "source_type": normalize_index_text(
                    record.get("source_type", "")
                ),
                "summary": normalize_index_text(
                    record.get("summary", "")
                ),
                "tags": record.get(
                    "tags",
                    [],
                ),
                "title": normalize_index_text(
                    record.get("title", "")
                ),
                "updated_at": normalize_index_text(
                    record.get("updated_at", "")
                ),
                "url": normalize_index_text(
                    record.get("url", "")
                ),
            }
            for record in records
        ],
        ensure_ascii=True,
        sort_keys=True,
    )

    return hashlib.sha256(
        serialized_records.encode("utf-8")
    ).hexdigest()


def build_chunk_search_text(record, chunk_text):

    tag_values = record.get(
        "tags",
        [],
    ) or record.get(
        "keywords",
        [],
    ) or []

    return normalize_index_text(
        "\n".join(
            [
                f"Title: {record.get('title', '')}",
                f"Category: {record.get('category', '')}",
                (
                    f"Tags: {', '.join(tag_values)}"
                    if tag_values
                    else ""
                ),
                (
                    f"Source: {record.get('source_name', '')}"
                    if record.get("source_name")
                    else ""
                ),
                (
                    f"URL: {record.get('url', '')}"
                    if record.get("url")
                    else ""
                ),
                f"Summary: {record.get('summary', '')}",
                f"Content: {chunk_text}",
            ]
        )
    )


def build_chunk_entries(records):

    chunk_entries = []

    for record in records:
        record_summary = str(
            record.get("summary", "") or ""
        ).replace(
            "\r",
            "",
        ).strip()
        record_body = str(
            record.get("body", "") or ""
        ).replace(
            "\r",
            "",
        ).strip()
        base_text = normalize_index_text(
            "\n\n".join(
                [
                    record_summary,
                    record_body,
                ]
            )
        )
        text_chunks = split_text_into_chunks(
            base_text
        ) or [
            normalize_index_text(
                record.get("summary", "")
            )
        ]
        cleaned_tag_values = [
            normalize_index_text(tag)
            for tag in (
                record.get("tags", [])
                or record.get("keywords", [])
                or []
            )
            if normalize_index_text(tag)
        ]

        for index, chunk_text in enumerate(
            text_chunks
        ):
            if not chunk_text:
                continue

            search_text = build_chunk_search_text(
                record,
                chunk_text,
            )
            content_term_text = normalize_index_text(
                chunk_text
            )
            chunk_entries.append(
                {
                    "category": normalize_index_text(
                        record.get("category", "")
                    )
                    or "Support",
                    "chunk_id": f"{record['source_key']}:{index + 1}",
                    "content_terms": sorted(
                        tokenize_index_text(
                            content_term_text
                        )
                    ),
                    "body_text": chunk_text,
                    "dedupe_key": hashlib.sha256(
                        normalize_index_text(
                            "|".join(
                                [
                                    record[
                                        "record_kind"
                                    ],
                                    str(
                                        record.get(
                                            "source_name",
                                            "",
                                        )
                                    ),
                                    str(
                                        record.get(
                                            "title",
                                            "",
                                        )
                                    ),
                                    chunk_text[:320],
                                ]
                            )
                        ).encode("utf-8")
                    ).hexdigest(),
                    "excerpt": chunk_text[:240].strip(),
                    "record_id": str(
                        record.get("id", "")
                    ),
                    "record_kind": record[
                        "record_kind"
                    ],
                    "record_body": record_body,
                    "record_summary": record_summary,
                    "search_text": search_text,
                    "source_key": record[
                        "source_key"
                    ],
                    "source_name": normalize_index_text(
                        record.get("source_name", "")
                    ),
                    "source_type": normalize_index_text(
                        record.get("source_type", "")
                    )
                    or (
                        "article"
                        if record["record_kind"]
                        == "article"
                        else "manual"
                    ),
                    "status": normalize_index_text(
                        record.get("status", "")
                    )
                    or "Published",
                    "summary": normalize_index_text(
                        record.get("summary", "")
                    ),
                    "tag_terms": cleaned_tag_values,
                    "title": normalize_index_text(
                        record.get("title", "")
                    )
                    or "Knowledge record",
                    "title_terms": sorted(
                        tokenize_index_text(
                            record.get("title", "")
                        )
                    ),
                    "url": normalize_index_text(
                        record.get("url", "")
                    ),
                }
            )

    return chunk_entries


def load_workspace_index_file():

    if not WORKSPACE_INDEX_PATH.exists():
        return None

    try:
        return json.loads(
            WORKSPACE_INDEX_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return None


def write_workspace_index_file(index_payload):

    ensure_ai_index_dir()
    temp_path = WORKSPACE_INDEX_PATH.with_suffix(
        ".tmp"
    )
    temp_path.write_text(
        json.dumps(
            index_payload,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    temp_path.replace(
        WORKSPACE_INDEX_PATH
    )


def set_workspace_index_state(
    *,
    cached_index=None,
    is_building=None,
    is_dirty=None,
):

    global WORKSPACE_INDEX_BUILDING
    global WORKSPACE_INDEX_CACHE
    global WORKSPACE_INDEX_DIRTY

    with INDEX_LOCK:
        if cached_index is not None:
            WORKSPACE_INDEX_CACHE = cached_index

        if is_building is not None:
            WORKSPACE_INDEX_BUILDING = is_building

        if is_dirty is not None:
            WORKSPACE_INDEX_DIRTY = is_dirty


def get_workspace_index_state():

    with INDEX_LOCK:
        return {
            "cached_index": WORKSPACE_INDEX_CACHE,
            "is_building": WORKSPACE_INDEX_BUILDING,
            "is_dirty": WORKSPACE_INDEX_DIRTY,
        }


def build_workspace_index_payload(
    fingerprint,
    records,
):

    chunk_entries = build_chunk_entries(
        records
    )
    index_payload = {
        "built_at": "",
        "embed_model": "",
        "fingerprint": fingerprint,
        "index_error": "",
        "items": chunk_entries,
        "schema_version": WORKSPACE_INDEX_SCHEMA_VERSION,
        "semantic_search_enabled": is_semantic_search_enabled(),
    }

    return index_payload


def build_workspace_index(
    force_refresh=False,
):
    records = build_workspace_records()
    fingerprint = build_workspace_fingerprint(
        records
    )

    with INDEX_BUILD_LOCK:
        existing_index = (
            None
            if force_refresh
            else load_workspace_index_file()
        )

        if (
            existing_index
            and existing_index.get("fingerprint")
            == fingerprint
            and existing_index.get(
                "schema_version"
            )
            == WORKSPACE_INDEX_SCHEMA_VERSION
        ):
            return existing_index

        next_index = build_workspace_index_payload(
            fingerprint=fingerprint,
            records=records,
        )
        next_index["built_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        next_index["record_count"] = len(
            records
        )
        next_index["chunk_count"] = len(
            next_index.get("items", [])
        )
        write_workspace_index_file(
            next_index
        )
        set_workspace_index_state(
            cached_index=next_index,
            is_dirty=False,
        )

        return next_index


def refresh_workspace_index(
    force_refresh=False,
):

    state = get_workspace_index_state()

    if state["is_building"]:
        cached_index = state["cached_index"]

        if cached_index is not None:
            return cached_index

    set_workspace_index_state(
        is_building=True,
    )

    try:
        return build_workspace_index(
            force_refresh=force_refresh,
        )
    finally:
        set_workspace_index_state(
            is_building=False,
        )


def refresh_workspace_index_async(
    force_refresh=False,
):

    state = get_workspace_index_state()

    if state["is_building"]:
        return False

    set_workspace_index_state(
        is_building=True,
        is_dirty=True,
    )

    def run_refresh():

        try:
            build_workspace_index(
                force_refresh=force_refresh,
            )
        finally:
            set_workspace_index_state(
                is_building=False,
            )

    Thread(
        target=run_refresh,
        daemon=True,
    ).start()

    return True


def mark_workspace_index_dirty(
    rebuild_async=True,
):

    set_workspace_index_state(
        is_dirty=True,
    )

    if rebuild_async:
        refresh_workspace_index_async(
            force_refresh=True,
        )


def ensure_workspace_index(
    force_refresh=False,
):

    if force_refresh:
        return refresh_workspace_index(
            force_refresh=True,
        )

    state = get_workspace_index_state()

    if (
        state["is_dirty"]
        and not state["is_building"]
    ):
        return refresh_workspace_index(
            force_refresh=True,
        )

    if (
        state["cached_index"] is not None
        and (
            not state["is_dirty"]
            or state["is_building"]
        )
    ):
        return state["cached_index"]

    file_index = load_workspace_index_file()

    if file_index is not None:
        set_workspace_index_state(
            cached_index=file_index,
        )

        if state["is_building"]:
            return file_index

        return refresh_workspace_index(
            force_refresh=False,
        )

    return refresh_workspace_index(
        force_refresh=True,
    )


def compute_cosine_similarity(
    left_vector,
    left_norm,
    right_vector,
    right_norm,
):

    if (
        not left_vector
        or not right_vector
        or not left_norm
        or not right_norm
        or len(left_vector)
        != len(right_vector)
    ):
        return 0.0

    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(
            left_vector,
            right_vector,
        )
    )

    return dot_product / (
        left_norm * right_norm
    )


def score_chunk_lexically(
    chunk_entry,
    query_tokens,
    full_query,
    article_hint_url="",
):

    overlap_details = (
        get_chunk_overlap_details(
            chunk_entry,
            query_tokens,
        )
    )
    title_tokens = overlap_details[
        "title_tokens"
    ]
    tag_tokens = overlap_details[
        "tag_tokens"
    ]
    content_tokens = overlap_details[
        "content_tokens"
    ]
    strong_query_tokens = {
        token
        for token in query_tokens
        if token not in LOW_SIGNAL_QUERY_TERMS
    }
    low_signal_query_tokens = (
        query_tokens
        - strong_query_tokens
    )
    score = 0.0

    score += len(
        strong_query_tokens
        & title_tokens
    ) * 4.8
    score += len(
        strong_query_tokens
        & tag_tokens
    ) * 3.2
    score += min(
        len(
            strong_query_tokens
            & content_tokens
        ),
        12,
    ) * 3.0
    score += len(
        low_signal_query_tokens
        & title_tokens
    ) * 0.4
    score += len(
        low_signal_query_tokens
        & tag_tokens
    ) * 0.25
    score += min(
        len(
            low_signal_query_tokens
            & content_tokens
        ),
        12,
    ) * 0.15

    search_text = normalize_index_text(
        chunk_entry.get(
            "search_text",
            "",
        )
    ).lower()

    if full_query and full_query in search_text:
        score += 3.0

    if (
        article_hint_url
        and chunk_entry.get("record_kind")
        == "article"
        and normalize_index_text(
            chunk_entry.get("url", "")
        ).rstrip("/").lower()
        == normalize_index_text(
            article_hint_url
        ).rstrip("/").lower()
    ):
        score += 8.0

    return score


def is_chunk_relevant(
    *,
    lexical_score,
    semantic_score,
    full_query,
    overlap_tokens,
    search_text,
    strong_content_overlap_tokens,
    strong_overlap_tokens,
    strong_tag_overlap_tokens,
    strong_title_overlap_tokens,
):

    if (
        full_query
        and len(full_query) >= 12
        and full_query in search_text
    ):
        return True

    if len(strong_overlap_tokens) >= 2:
        return True

    if len(strong_overlap_tokens) == 1:
        if (
            strong_content_overlap_tokens
            or strong_tag_overlap_tokens
        ):
            return (
                lexical_score >= 3.0
                or semantic_score >= 0.45
            )

        if strong_title_overlap_tokens:
            return (
                lexical_score >= 6.5
                or semantic_score >= 0.52
            )

        return (
            lexical_score >= 3.0
            or semantic_score >= 0.45
        )

    if len(overlap_tokens) >= 2:
        return (
            lexical_score >= 6.2
            or semantic_score >= 0.52
        )

    return semantic_score >= 0.62


def group_chunk_matches(
    scored_chunks,
    limit,
):

    grouped_matches = {}

    for chunk in scored_chunks:
        source_key = chunk.get(
            "dedupe_key",
            chunk["source_key"],
        )
        existing_match = grouped_matches.get(
            source_key
        )

        if existing_match is None or chunk[
            "score"
        ] > existing_match["score"]:
            grouped_matches[source_key] = {
                **chunk,
            }

    ordered_matches = sorted(
        grouped_matches.values(),
        key=lambda match: (
            -match["score"],
            match["title"],
        ),
    )

    return ordered_matches[
        : max(limit, 1)
    ]


def build_article_match(chunk_entry):

    return {
        "body": chunk_entry.get(
            "record_body",
            "",
        )
        or chunk_entry.get(
            "body_text",
            "",
        ),
        "category": chunk_entry.get(
            "category",
            "Support",
        ),
        "id": chunk_entry.get(
            "record_id",
            "",
        ),
        "keywords": chunk_entry.get(
            "tag_terms",
            [],
        ),
        "score": chunk_entry.get(
            "score",
            0,
        ),
        "source": "workspace",
        "status": chunk_entry.get(
            "status",
            "Published",
        ),
        "summary": chunk_entry.get(
            "record_summary",
            "",
        )
        or chunk_entry.get(
            "summary",
            "",
        ),
        "title": chunk_entry.get(
            "title",
            "Support article",
        ),
        "url": chunk_entry.get(
            "url",
            "",
        ),
    }


def build_knowledge_match(chunk_entry):

    return {
        "body": chunk_entry.get(
            "record_body",
            "",
        )
        or chunk_entry.get(
            "body_text",
            "",
        ),
        "category": chunk_entry.get(
            "category",
            "Knowledge",
        ),
        "id": int(
            chunk_entry.get(
                "record_id",
                0,
            )
            or 0
        ),
        "score": chunk_entry.get(
            "score",
            0,
        ),
        "source": "workspace",
        "source_name": chunk_entry.get(
            "source_name",
            "",
        ),
        "source_type": chunk_entry.get(
            "source_type",
            "",
        )
        or "manual",
        "status": chunk_entry.get(
            "status",
            "Published",
        ),
        "summary": chunk_entry.get(
            "record_summary",
            "",
        )
        or chunk_entry.get(
            "summary",
            "",
        ),
        "tags": chunk_entry.get(
            "tag_terms",
            [],
        ),
        "title": chunk_entry.get(
            "title",
            "Knowledge document",
        ),
    }


def search_workspace_knowledge(
    query,
    limit=3,
    article_hint_url="",
):

    workspace_index = ensure_workspace_index()
    full_query = normalize_index_text(
        query
    ).lower()
    query_tokens = tokenize_index_text(
        full_query
    )
    query_tokens = expand_query_tokens(
        query_tokens,
        workspace_vocabulary=collect_workspace_vocabulary(
            workspace_index
        ),
    )
    query_embedding = []
    query_norm = 0.0
    retrieval_mode = "lexical"
    embedding_error = ""


    scored_chunks = []

    for chunk_entry in workspace_index.get(
        "items",
        [],
    ):
        overlap_details = (
            get_chunk_overlap_details(
                chunk_entry,
                query_tokens,
            )
        )
        lexical_score = score_chunk_lexically(
            chunk_entry,
            query_tokens=query_tokens,
            full_query=full_query,
            article_hint_url=article_hint_url,
        )
        semantic_score = 0.0

        if query_embedding:
            semantic_score = max(
                compute_cosine_similarity(
                    left_vector=query_embedding,
                    left_norm=query_norm,
                    right_vector=chunk_entry.get(
                        "embedding",
                        [],
                    ),
                    right_norm=float(
                        chunk_entry.get(
                            "vector_norm",
                            0.0,
                        )
                        or 0.0
                    ),
                ),
                0.0,
            )

        final_score = lexical_score + (
            semantic_score * 8.0
        )

        search_text = normalize_index_text(
            chunk_entry.get(
                "search_text",
                "",
            )
        ).lower()

        if final_score <= 0 or not is_chunk_relevant(
            lexical_score=lexical_score,
            semantic_score=semantic_score,
            full_query=full_query,
            overlap_tokens=overlap_details[
                "overlap_tokens"
            ],
            search_text=search_text,
            strong_content_overlap_tokens=overlap_details[
                "strong_content_overlap_tokens"
            ],
            strong_overlap_tokens=overlap_details[
                "strong_overlap_tokens"
            ],
            strong_tag_overlap_tokens=overlap_details[
                "strong_tag_overlap_tokens"
            ],
            strong_title_overlap_tokens=overlap_details[
                "strong_title_overlap_tokens"
            ],
        ):
            continue

        scored_chunks.append(
            {
                **chunk_entry,
                "overlap_terms": sorted(
                    overlap_details[
                        "overlap_tokens"
                    ]
                ),
                "score": round(
                    final_score,
                    4,
                ),
                "semantic_score": round(
                    semantic_score,
                    4,
                ),
                "strong_overlap_terms": sorted(
                    overlap_details[
                        "strong_overlap_tokens"
                    ]
                ),
            }
        )

    ordered_chunks = sorted(
        scored_chunks,
        key=lambda chunk: (
            -chunk["score"],
            chunk["title"],
        ),
    )[:MAX_SEARCH_RESULTS]
    grouped_matches = group_chunk_matches(
        ordered_chunks,
        limit=max(limit, 1) * 2,
    )
    article_matches = [
        build_article_match(match)
        for match in grouped_matches
        if match.get("record_kind")
        == "article"
    ][: max(limit, 1)]
    knowledge_matches = [
        build_knowledge_match(match)
        for match in grouped_matches
        if match.get("record_kind")
        == "knowledge"
    ][: max(limit, 1)]
    matched_chunks = [
        {
            "category": chunk.get(
                "category",
                "Support",
            ),
            "chunk_id": chunk.get(
                "chunk_id",
                "",
            ),
            "body_text": chunk.get(
                "body_text",
                "",
            ),
            "excerpt": chunk.get(
                "excerpt",
                "",
            ),
            "record_body": chunk.get(
                "record_body",
                "",
            ),
            "record_id": chunk.get(
                "record_id",
                "",
            ),
            "record_kind": chunk.get(
                "record_kind",
                "",
            ),
            "record_summary": chunk.get(
                "record_summary",
                "",
            ),
            "score": chunk.get(
                "score",
                0,
            ),
            "source_name": chunk.get(
                "source_name",
                "",
            ),
            "source_type": chunk.get(
                "source_type",
                "",
            ),
            "overlap_terms": chunk.get(
                "overlap_terms",
                [],
            ),
            "strong_overlap_terms": chunk.get(
                "strong_overlap_terms",
                [],
            ),
            "title": chunk.get(
                "title",
                "",
            ),
            "url": chunk.get(
                "url",
                "",
            ),
        }
        for chunk in grouped_matches[
            : max(limit, 1) + 2
        ]
    ]

    return {
        "articles": article_matches,
        "embedding_error": embedding_error,
        "index_built_at": workspace_index.get(
            "built_at"
        ),
        "index_error": workspace_index.get(
            "index_error",
            "",
        ),
        "knowledge_documents": knowledge_matches,
        "matched_chunks": matched_chunks,
        "retrieval_mode": (
            "empty"
            if not workspace_index.get("items")
            else retrieval_mode
        ),
    }



