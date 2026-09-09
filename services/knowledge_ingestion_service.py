import base64
import csv
import hashlib
import ipaddress
import io
import json
import logging
import re
import socket
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup, Tag
import requests

from services.database_service import create_knowledge_document

logger = logging.getLogger(__name__)
MAX_REMOTE_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_REMOTE_REDIRECTS = 5

# -----------------------------------
# CONFIG
# -----------------------------------

SUPPORTED_KNOWLEDGE_EXTENSIONS = {
    ".csv",
    ".docx",
    ".htm",
    ".html",
    ".json",
    ".md",
    ".markdown",
    ".pdf",
    ".txt",
}

MAX_CHARS_PER_DOCUMENT = 4000
MAX_DOCUMENTS_PER_FILE = None
DEFAULT_FETCH_USER_AGENT = "CustomerSupportAgentKnowledgeBot/1.0"
MAX_REMOTE_SITE_PAGES = 200
MAX_REMOTE_DISCOVERED_LINKS = 2000
REMOTE_CRAWL_PRIORITY_KEYWORDS = (
    "about",
    "availability",
    "booking",
    "construction",
    "contact",
    "faq",
    "handover",
    "help",
    "inventory",
    "payment",
    "possession",
    "pricing",
    "project",
    "property",
    "registration",
    "site-visit",
    "support",
    "terms",
)
REMOTE_CRAWL_SKIP_PATH_KEYWORDS = (
    "account",
    "cart",
    "checkout",
    "login",
    "register",
    "search",
)
REMOTE_CRAWL_SKIP_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".png",
    ".rss",
    ".svg",
    ".tif",
    ".tiff",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xml",
    ".zip",
}
HTML_CONTENT_ROOT_SELECTORS = (
    "main",
    "article",
    "[role='main']",
    "#main",
    ".main",
    "#content",
    ".content",
)
HTML_SKIP_TAGS = {
    "canvas",
    "iframe",
    "input",
    "nav",
    "noscript",
    "script",
    "style",
    "svg",
    "template",
    "textarea",
}
HTML_HEADING_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}
HTML_TEXT_BLOCK_TAGS = HTML_HEADING_TAGS.union(
    {
        "blockquote",
        "button",
        "caption",
        "code",
        "dd",
        "dt",
        "figcaption",
        "label",
        "legend",
        "option",
        "p",
        "pre",
        "summary",
        "td",
        "th",
    }
)


# -----------------------------------
# TEXT HELPERS
# -----------------------------------

def normalize_knowledge_text(value):

    text = str(value or "").replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )
    text = re.sub(
        r"[ \t]+\n",
        "\n",
        text,
    )
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )
    text = re.sub(
        r"[ \t]{2,}",
        " ",
        text,
    )

    return text.strip()


def decode_text_bytes(file_bytes):

    for encoding in (
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "latin-1",
    ):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(
        "The uploaded file could not be decoded as text."
    )


def summarize_knowledge_text(text):

    cleaned_text = normalize_knowledge_text(
        text
    )

    if not cleaned_text:
        return ""

    sentences = re.split(
        r"(?<=[.!?])\s+",
        cleaned_text,
    )
    summary = " ".join(
        sentence.strip()
        for sentence in sentences[:2]
        if sentence.strip()
    ).strip()

    if len(summary) >= 220:
        return summary[:217].rstrip() + "..."

    if summary:
        return summary

    return cleaned_text[:217].rstrip() + (
        "..."
        if len(cleaned_text) > 220
        else ""
    )


def split_paragraph_into_segments(
    paragraph,
    max_chars=MAX_CHARS_PER_DOCUMENT,
):

    cleaned_paragraph = normalize_knowledge_text(
        paragraph
    )

    if not cleaned_paragraph:
        return []

    if len(cleaned_paragraph) <= max_chars:
        return [cleaned_paragraph]

    sentences = re.split(
        r"(?<=[.!?])\s+",
        cleaned_paragraph,
    )
    segments = []
    current_segment = []
    current_length = 0

    for sentence in sentences:
        cleaned_sentence = sentence.strip()

        if not cleaned_sentence:
            continue

        if len(cleaned_sentence) > max_chars:
            if current_segment:
                segments.append(
                    " ".join(current_segment)
                )
                current_segment = []
                current_length = 0

            for index in range(
                0,
                len(cleaned_sentence),
                max_chars,
            ):
                segments.append(
                    cleaned_sentence[
                        index:index + max_chars
                    ].strip()
                )

            continue

        next_length = current_length + len(
            cleaned_sentence
        ) + (
            1
            if current_segment
            else 0
        )

        if current_segment and next_length > max_chars:
            segments.append(
                " ".join(current_segment)
            )
            current_segment = [cleaned_sentence]
            current_length = len(
                cleaned_sentence
            )
            continue

        current_segment.append(
            cleaned_sentence
        )
        current_length = next_length

    if current_segment:
        segments.append(
            " ".join(current_segment)
        )

    return segments


def split_text_into_documents(
    text,
    max_chars=MAX_CHARS_PER_DOCUMENT,
    max_documents=MAX_DOCUMENTS_PER_FILE,
):

    cleaned_text = normalize_knowledge_text(
        text
    )

    if not cleaned_text:
        return {
            "chunks": [],
            "was_truncated": False,
        }

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(
            r"\n\s*\n",
            cleaned_text,
        )
        if paragraph.strip()
    ]
    chunks = []
    current_chunk = []
    current_length = 0
    was_truncated = False

    for paragraph in paragraphs:
        paragraph_segments = (
            split_paragraph_into_segments(
                paragraph,
                max_chars=max_chars,
            )
        )

        for segment in paragraph_segments:
            segment_length = len(segment) + (
                2
                if current_chunk
                else 0
            )

            if (
                current_chunk
                and current_length + segment_length > max_chars
            ):
                chunks.append(
                    "\n\n".join(
                        current_chunk
                    ).strip()
                )
                current_chunk = [segment]
                current_length = len(
                    segment
                )
            else:
                current_chunk.append(
                    segment
                )
                current_length += segment_length

            if (
                max_documents is not None
                and len(chunks) >= max_documents
            ):
                was_truncated = True
                break

        if (
            max_documents is not None
            and len(chunks) >= max_documents
        ):
            break

    if current_chunk and (
        max_documents is None
        or len(chunks) < max_documents
    ):
        chunks.append(
            "\n\n".join(
                current_chunk
            ).strip()
        )
    elif current_chunk:
        was_truncated = True

    return {
        "chunks": [
            chunk
            for chunk in chunks
            if chunk
        ],
        "was_truncated": was_truncated,
    }


# -----------------------------------
# FORMAT EXTRACTORS
# -----------------------------------

def extract_docx_text(file_bytes):

    try:
        with zipfile.ZipFile(
            io.BytesIO(file_bytes)
        ) as archive:
            document_xml = archive.read(
                "word/document.xml"
            )
    except Exception as error:
        raise ValueError(
            "The DOCX file could not be read."
        ) from error

    namespace = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    }

    try:
        root = ElementTree.fromstring(
            document_xml
        )
    except ElementTree.ParseError as error:
        raise ValueError(
            "The DOCX document content could not be parsed."
        ) from error

    paragraphs = []

    for paragraph in root.findall(
        ".//w:p",
        namespace,
    ):
        text_parts = []

        for node in paragraph.iter():
            if node.tag.endswith("}t"):
                text_parts.append(
                    node.text or ""
                )
            elif node.tag.endswith("}tab"):
                text_parts.append(" ")
            elif node.tag.endswith("}br"):
                text_parts.append("\n")

        paragraph_text = normalize_knowledge_text(
            "".join(text_parts)
        )

        if paragraph_text:
            paragraphs.append(
                paragraph_text
            )

    return "\n\n".join(paragraphs)


def extract_pdf_text(file_bytes):

    try:
        from pypdf import PdfReader
    except Exception as error:
        raise ValueError(
            "PDF upload support is not available until the pypdf package is installed."
        ) from error

    try:
        reader = PdfReader(
            io.BytesIO(file_bytes)
        )
    except Exception as error:
        raise ValueError(
            "The PDF file could not be read."
        ) from error

    page_text = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        extracted_text = ""

        for extract_text in (
            lambda: page.extract_text(
                extraction_mode="layout"
            ),
            lambda: page.extract_text(),
        ):
            try:
                extracted_text = normalize_knowledge_text(
                    extract_text() or ""
                )
            except TypeError:
                continue
            except Exception:
                extracted_text = ""

            if extracted_text:
                break

        if extracted_text:
            page_text.append(
                f"Page {page_number}\n{extracted_text}"
            )

    return "\n\n".join(page_text)


def extract_csv_text(file_bytes):

    decoded_text = decode_text_bytes(
        file_bytes
    )
    reader = csv.reader(
        io.StringIO(decoded_text)
    )
    rows = []

    for row in reader:
        cleaned_row = [
            normalize_knowledge_text(
                cell
            )
            for cell in row
            if normalize_knowledge_text(
                cell
            )
        ]

        if cleaned_row:
            rows.append(
                " | ".join(cleaned_row)
            )

    return "\n".join(rows)


def extract_json_text(file_bytes):

    decoded_text = decode_text_bytes(
        file_bytes
    )

    try:
        payload = json.loads(
            decoded_text
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "The JSON file is not valid."
        ) from error

    return json.dumps(
        payload,
        ensure_ascii=True,
        indent=2,
    )


def extract_html_text(file_bytes):

    return extract_remote_html_payload(
        file_bytes
    )["body"]


def extract_uploaded_knowledge_text(
    file_name,
    mime_type,
    file_bytes,
):

    suffix = Path(
        str(file_name or "")
    ).suffix.lower()
    normalized_mime_type = str(
        mime_type or ""
    ).strip().lower()

    if suffix == ".pdf" or normalized_mime_type == "application/pdf":
        return extract_pdf_text(
            file_bytes
        )

    if suffix == ".docx":
        return extract_docx_text(
            file_bytes
        )

    if suffix == ".csv":
        return extract_csv_text(
            file_bytes
        )

    if suffix == ".json":
        return extract_json_text(
            file_bytes
        )

    if suffix in (
        ".htm",
        ".html",
    ):
        return extract_html_text(
            file_bytes
        )

    if suffix in (
        ".md",
        ".markdown",
        ".txt",
    ) or normalized_mime_type.startswith(
        "text/"
    ):
        return decode_text_bytes(
            file_bytes
        )

    supported_formats = ", ".join(
        sorted(
            SUPPORTED_KNOWLEDGE_EXTENSIONS
        )
    )

    raise ValueError(
        f"Unsupported knowledge file format for {file_name}. Supported formats: {supported_formats}."
    )


def select_html_content_root(soup):

    for selector in HTML_CONTENT_ROOT_SELECTORS:
        content_root = soup.select_one(
            selector
        )

        if content_root is not None:
            return content_root

    return soup.body or soup


def extract_html_table_text(table_node):

    rows = []

    for row in table_node.find_all("tr"):
        cells = [
            normalize_knowledge_text(
                cell.get_text(
                    " ",
                    strip=True,
                )
            )
            for cell in row.find_all(
                [
                    "th",
                    "td",
                ]
            )
        ]
        cells = [
            cell
            for cell in cells
            if cell
        ]

        if cells:
            rows.append(
                " | ".join(cells)
            )

    return "\n".join(rows)


def extract_html_list_items(list_node):

    items = []

    for item in list_node.find_all(
        "li",
        recursive=False,
    ):
        item_text = normalize_knowledge_text(
            item.get_text(
                " ",
                strip=True,
            )
        )

        if item_text:
            items.append(
                f"- {item_text}"
            )

    return items


def extract_html_definition_list_items(list_node):

    items = []
    current_term = ""

    for child in list_node.find_all(
        [
            "dt",
            "dd",
        ],
        recursive=False,
    ):
        child_text = normalize_knowledge_text(
            child.get_text(
                " ",
                strip=True,
            )
        )

        if not child_text:
            continue

        if child.name == "dt":
            current_term = child_text
            items.append(
                current_term
            )
            continue

        if current_term:
            items.append(
                f"{current_term}: {child_text}"
            )
        else:
            items.append(child_text)

    return items


def collect_html_content_blocks(node):

    blocks = []

    for child in getattr(
        node,
        "children",
        [],
    ):
        if not isinstance(
            child,
            Tag,
        ):
            continue

        child_name = (
            child.name or ""
        ).lower()

        if child_name in HTML_SKIP_TAGS:
            continue

        if child_name == "table":
            table_text = extract_html_table_text(
                child
            )

            if table_text:
                blocks.append(
                    table_text
                )

            continue

        if child_name in (
            "ul",
            "ol",
        ):
            blocks.extend(
                extract_html_list_items(
                    child
                )
            )
            continue

        if child_name == "dl":
            blocks.extend(
                extract_html_definition_list_items(
                    child
                )
            )
            continue

        if child_name in HTML_TEXT_BLOCK_TAGS:
            separator = (
                "\n"
                if child_name in (
                    "code",
                    "pre",
                )
                else " "
            )
            block_text = normalize_knowledge_text(
                child.get_text(
                    separator,
                    strip=True,
                )
            )

            if not block_text:
                continue

            if child_name in HTML_HEADING_TAGS:
                heading_level = min(
                    int(child_name[1]),
                    3,
                )
                blocks.append(
                    f"{'#' * heading_level} {block_text}"
                )
            else:
                blocks.append(block_text)

            continue

        blocks.extend(
            collect_html_content_blocks(
                child
            )
        )

    return blocks


def dedupe_consecutive_blocks(blocks):

    deduped_blocks = []
    previous_block = ""

    for block in blocks:
        cleaned_block = normalize_knowledge_text(
            block
        )

        if (
            not cleaned_block
            or cleaned_block == previous_block
        ):
            continue

        deduped_blocks.append(
            cleaned_block
        )
        previous_block = cleaned_block

    return deduped_blocks


def append_unique_html_blocks(
    base_blocks,
    extra_blocks,
):

    merged_blocks = list(base_blocks)
    seen_blocks = {
        normalize_knowledge_text(block)
        for block in base_blocks
        if normalize_knowledge_text(block)
    }

    for block in extra_blocks:
        cleaned_block = normalize_knowledge_text(
            block
        )

        if (
            not cleaned_block
            or cleaned_block in seen_blocks
        ):
            continue

        seen_blocks.add(
            cleaned_block
        )
        merged_blocks.append(
            cleaned_block
        )

    return merged_blocks


def extract_remote_html_payload(
    html_source,
):

    if isinstance(
        html_source,
        bytes,
    ):
        decoded_text = decode_text_bytes(
            html_source
        )
    else:
        decoded_text = str(
            html_source or ""
        )

    soup = BeautifulSoup(
        decoded_text,
        "html.parser",
    )

    for node in soup.find_all(
        HTML_SKIP_TAGS
    ):
        node.decompose()

    page_title = normalize_knowledge_text(
        soup.title.get_text(
            " ",
            strip=True,
        )
        if soup.title
        else ""
    )
    content_root = select_html_content_root(
        soup
    )
    sections = dedupe_consecutive_blocks(
        collect_html_content_blocks(
            content_root
        )
    )
    page_root = soup.body or soup

    if page_root is not content_root:
        full_page_sections = (
            dedupe_consecutive_blocks(
                collect_html_content_blocks(
                    page_root
                )
            )
        )
        sections = append_unique_html_blocks(
            sections,
            full_page_sections,
        )

    if not sections:
        fallback_root = content_root or soup
        fallback_text = normalize_knowledge_text(
            fallback_root.get_text(
                "\n",
                strip=True,
            )
        )

        if fallback_text:
            sections = [fallback_text]

    body = "\n\n".join(
        section
        for section in sections
        if section
    ).strip()

    return {
        "body": body,
        "title": page_title,
    }


def derive_url_title(raw_url):

    parsed_url = urlparse(
        str(raw_url or "")
    )
    path_segments = [
        segment
        for segment in parsed_url.path.split("/")
        if segment.strip()
    ]

    if path_segments:
        last_segment = path_segments[-1]
        cleaned_segment = re.sub(
            r"[-_]+",
            " ",
            last_segment,
        )
        cleaned_segment = normalize_knowledge_text(
            cleaned_segment
        )

        if cleaned_segment:
            return cleaned_segment

    return normalize_knowledge_text(
        parsed_url.netloc
    ) or "Imported page"


def normalize_remote_domain(netloc):

    normalized_netloc = normalize_knowledge_text(
        netloc
    ).lower()

    if normalized_netloc.startswith(
        "www."
    ):
        return normalized_netloc[4:]

    return normalized_netloc


def is_allowed_remote_crawl_domain(
    candidate_domain,
    allowed_domain,
):

    normalized_candidate = normalize_remote_domain(
        candidate_domain
    )
    normalized_allowed = normalize_remote_domain(
        allowed_domain
    )

    if (
        not normalized_candidate
        or not normalized_allowed
    ):
        return False

    return (
        normalized_candidate
        == normalized_allowed
        or normalized_candidate.endswith(
            f".{normalized_allowed}"
        )
        or normalized_allowed.endswith(
            f".{normalized_candidate}"
        )
    )


def normalize_remote_crawl_url(raw_url):

    cleaned_url = normalize_knowledge_text(
        raw_url
    )

    if not cleaned_url:
        return ""

    parsed_url = urlparse(
        cleaned_url
    )

    if parsed_url.username is not None or parsed_url.password is not None:
        return ""

    if parsed_url.scheme not in (
        "http",
        "https",
    ):
        return ""

    normalized_path = (
        parsed_url.path or "/"
    )

    if (
        normalized_path != "/"
        and normalized_path.endswith("/")
    ):
        normalized_path = normalized_path.rstrip("/")

    return urlunparse(
        (
            parsed_url.scheme.lower(),
            parsed_url.netloc.lower(),
            normalized_path or "/",
            "",
            "",
            "",
        )
    )


def validate_public_remote_url(raw_url):
    normalized_url = normalize_remote_crawl_url(raw_url)
    parsed = urlparse(normalized_url)
    hostname = parsed.hostname
    if not hostname or hostname.lower() == "localhost":
        raise ValueError("The URL must use a public host.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as error:
        raise ValueError("The URL host could not be resolved.") from error
    if not addresses:
        raise ValueError("The URL host could not be resolved.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Private, local, link-local, and reserved hosts are not allowed.")
    return normalized_url


def should_skip_remote_crawl_url(
    candidate_url,
    allowed_domain,
):

    normalized_candidate = (
        normalize_remote_crawl_url(
            candidate_url
        )
    )

    if not normalized_candidate:
        return True

    parsed_candidate = urlparse(
        normalized_candidate
    )
    candidate_domain = (
        normalize_remote_domain(
            parsed_candidate.netloc
        )
    )

    if not is_allowed_remote_crawl_domain(
        candidate_domain,
        allowed_domain,
    ):
        return True

    candidate_path = (
        parsed_candidate.path or "/"
    ).lower()

    if any(
        path_keyword in candidate_path
        for path_keyword in (
            REMOTE_CRAWL_SKIP_PATH_KEYWORDS
        )
    ):
        return True

    if Path(candidate_path).suffix.lower() in (
        REMOTE_CRAWL_SKIP_EXTENSIONS
    ):
        return True

    return False


def should_crawl_related_remote_pages(
    seed_url,
):

    parsed_seed_url = urlparse(
        seed_url
    )
    candidate_path = (
        parsed_seed_url.path or "/"
    ).lower()

    if Path(candidate_path).suffix.lower() in (
        REMOTE_CRAWL_SKIP_EXTENSIONS
    ):
        return False

    return True


def score_remote_crawl_candidate(
    candidate_url,
    link_text="",
):

    parsed_candidate = urlparse(
        candidate_url
    )
    candidate_domain = (
        normalize_remote_domain(
            parsed_candidate.netloc
        )
    )
    candidate_path = (
        parsed_candidate.path or "/"
    ).lower()
    normalized_link_text = (
        normalize_knowledge_text(
            link_text
        ).lower()
    )
    path_segments = [
        segment
        for segment in candidate_path.split("/")
        if segment
    ]
    score = 0

    if candidate_path in (
        "",
        "/",
    ):
        score += 2

    if any(
        keyword in candidate_domain.split(".")
        for keyword in (
            "faq",
            "help",
            "knowledge",
            "support",
        )
    ):
        score += 18

    if any(
        phrase in normalized_link_text
        for phrase in (
            "help centre",
            "help center",
            "knowledge base",
            "support centre",
            "support center",
        )
    ):
        score += 12

    for keyword in (
        REMOTE_CRAWL_PRIORITY_KEYWORDS
    ):
        if keyword in candidate_path:
            score += 8

        if keyword in normalized_link_text:
            score += 5

    if any(
        path_fragment in candidate_path
        for path_fragment in (
            "/blogs/",
            "/news/",
            "/press/",
        )
    ):
        score -= 4

    score -= max(
        len(path_segments) - 2,
        0,
    )

    return score


def extract_remote_html_links(
    html_source,
    *,
    base_url,
    allowed_domain,
):

    if isinstance(
        html_source,
        bytes,
    ):
        decoded_html = decode_text_bytes(
            html_source
        )
    else:
        decoded_html = str(
            html_source or ""
        )

    soup = BeautifulSoup(
        decoded_html,
        "html.parser",
    )
    discovered_links = []
    seen_urls = set()

    for anchor in soup.find_all(
        "a",
        href=True,
    ):
        href_value = normalize_knowledge_text(
            anchor.get(
                "href",
                "",
            )
        )

        if not href_value or href_value.startswith(
            (
                "#",
                "javascript:",
                "mailto:",
                "tel:",
            )
        ):
            continue

        candidate_url = (
            normalize_remote_crawl_url(
                urljoin(
                    base_url,
                    href_value,
                )
            )
        )

        if (
            not candidate_url
            or candidate_url in seen_urls
            or should_skip_remote_crawl_url(
                candidate_url,
                allowed_domain,
            )
        ):
            continue

        seen_urls.add(
            candidate_url
        )
        discovered_links.append(
            {
                "link_text": normalize_knowledge_text(
                    anchor.get_text(
                        " ",
                        strip=True,
                    )
                ),
                "url": candidate_url,
            }
        )

        if len(discovered_links) >= (
            MAX_REMOTE_DISCOVERED_LINKS
        ):
            break

    discovered_links.sort(
        key=lambda link: (
            -score_remote_crawl_candidate(
                link["url"],
                link_text=link[
                    "link_text"
                ],
            ),
            link["url"],
        )
    )

    return discovered_links


def build_remote_page_signature(
    page_payload,
):

    return hashlib.sha256(
        normalize_knowledge_text(
            "\n".join(
                [
                    page_payload.get(
                        "title",
                        "",
                    ),
                    page_payload.get(
                        "body",
                        "",
                    ),
                ]
            )
        ).encode("utf-8")
    ).hexdigest()


def fetch_remote_knowledge_source(
    raw_url,
):

    normalized_url = validate_public_remote_url(raw_url)

    if not normalized_url:
        raise ValueError(
            "Add a URL before importing."
        )

    parsed_url = urlparse(
        normalized_url
    )

    if parsed_url.scheme not in (
        "http",
        "https",
    ):
        raise ValueError(
            "Only http and https URLs are supported."
        )

    try:
        current_url = normalized_url
        for _ in range(MAX_REMOTE_REDIRECTS + 1):
            current_url = validate_public_remote_url(current_url)
            response = requests.get(
                current_url, timeout=20, stream=True, allow_redirects=False,
                headers={"User-Agent": DEFAULT_FETCH_USER_AGENT},
            )
            if response.is_redirect or response.is_permanent_redirect:
                destination = response.headers.get("location", "")
                response.close()
                if not destination:
                    raise ValueError("Remote redirect did not include a destination.")
                current_url = urljoin(current_url, destination)
                continue
            response.raise_for_status()
            break
        else:
            raise ValueError("Remote URL exceeded the redirect limit.")
        declared_size = int(response.headers.get("content-length", "0") or 0)
        if declared_size > MAX_REMOTE_DOWNLOAD_BYTES:
            response.close()
            raise ValueError("Remote document exceeds the 10 MB limit.")
        chunks = []
        received = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            received += len(chunk)
            if received > MAX_REMOTE_DOWNLOAD_BYTES:
                response.close()
                raise ValueError("Remote document exceeds the 10 MB limit.")
            chunks.append(chunk)
        response._content = b"".join(chunks)
        response.close()
        normalized_url = current_url
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            f"Could not read {normalized_url}."
        ) from error

    content_type = str(
        response.headers.get(
            "content-type",
            ""
        )
    ).split(
        ";",
        1,
    )[0].strip().lower()
    suffix = Path(
        parsed_url.path or ""
    ).suffix.lower()
    is_html_page = False
    discovered_links = []

    if suffix == ".pdf" or content_type == "application/pdf":
        extracted_text = extract_pdf_text(
            response.content
        )
        page_title = derive_url_title(
            normalized_url
        )
    elif (
        content_type in (
            "",
            "text/html",
            "application/xhtml+xml",
        )
        or not suffix
        or suffix in (
            ".htm",
            ".html",
        )
    ):
        is_html_page = True
        html_payload = extract_remote_html_payload(
            response.text
        )
        extracted_text = html_payload["body"]
        page_title = html_payload["title"] or derive_url_title(
            normalized_url
        )
        discovered_links = (
            extract_remote_html_links(
                response.text,
                base_url=normalized_url,
                allowed_domain=normalize_remote_domain(
                    parsed_url.netloc
                ),
            )
        )
    else:
        from services.upload_security_service import validate_knowledge_upload
        validate_knowledge_upload(response.content, parsed_url.path or "remote-file")
        extracted_text = extract_uploaded_knowledge_text(
            file_name=parsed_url.path or "remote-file",
            mime_type=content_type,
            file_bytes=response.content,
        )
        page_title = derive_url_title(
            normalized_url
        )

    cleaned_text = normalize_knowledge_text(
        extracted_text
    )

    if not cleaned_text:
        raise ValueError(
            f"The page at {normalized_url} did not contain readable text."
        )

    return {
        "body": cleaned_text,
        "content_type": content_type,
        "discovered_links": discovered_links,
        "is_html_page": is_html_page,
        "title": page_title,
        "url": normalized_url,
    }


def fetch_remote_knowledge_sources(
    raw_url,
):

    seed_payload = fetch_remote_knowledge_source(
        raw_url
    )
    page_payloads = [seed_payload]
    crawl_warning = ""
    skipped_page_count = 0

    if (
        not seed_payload.get(
            "is_html_page"
        )
        or not should_crawl_related_remote_pages(
            seed_payload["url"]
        )
    ):
        return {
            "pages": page_payloads,
            "skipped_page_count": 0,
            "warning": crawl_warning,
        }

    allowed_domain = normalize_remote_domain(
        urlparse(
            seed_payload["url"]
        ).netloc
    )
    seen_urls = {
        seed_payload["url"]
    }
    seen_page_signatures = {
        build_remote_page_signature(
            seed_payload
        )
    }
    pending_links = list(
        seed_payload.get(
            "discovered_links",
            [],
        )
    )

    while (
        pending_links
        and len(page_payloads)
        < MAX_REMOTE_SITE_PAGES
    ):
        next_link = pending_links.pop(0)
        next_url = next_link["url"]

        if next_url in seen_urls:
            continue

        seen_urls.add(next_url)

        try:
            next_payload = (
                fetch_remote_knowledge_source(
                    next_url
                )
            )
        except ValueError as error:
            logger.warning("Skipping related knowledge URL %s: %s", next_url, error)
            skipped_page_count += 1
            continue

        next_page_signature = (
            build_remote_page_signature(
                next_payload
            )
        )

        if next_page_signature in (
            seen_page_signatures
        ):
            continue

        seen_page_signatures.add(
            next_page_signature
        )
        page_payloads.append(
            next_payload
        )

        if not next_payload.get(
            "is_html_page"
        ):
            continue

        for discovered_link in next_payload.get(
            "discovered_links",
            [],
        ):
            discovered_url = discovered_link[
                "url"
            ]

            if (
                discovered_url in seen_urls
                or should_skip_remote_crawl_url(
                    discovered_url,
                    allowed_domain,
                )
            ):
                continue

            pending_links.append(
                discovered_link
            )

        pending_links.sort(
            key=lambda link: (
                -score_remote_crawl_candidate(
                    link["url"],
                    link_text=link[
                        "link_text"
                    ],
                ),
                link["url"],
            )
        )

        if len(pending_links) > (
            MAX_REMOTE_DISCOVERED_LINKS
        ):
            pending_links = pending_links[
                : MAX_REMOTE_DISCOVERED_LINKS
            ]

    if pending_links:
        crawl_warning = (
            f"Crawled the first {MAX_REMOTE_SITE_PAGES} linked pages from {seed_payload['url']}. "
            "Import more specific URLs if you need deeper coverage."
        )

    return {
        "pages": page_payloads,
        "skipped_page_count": skipped_page_count,
        "warning": crawl_warning,
    }


def build_imported_url_title(
    page_title,
    raw_url,
    title_prefix="",
    index=1,
    total=1,
):

    resolved_title = normalize_knowledge_text(
        page_title
    ) or derive_url_title(
        raw_url
    )
    prefix = normalize_knowledge_text(
        title_prefix
    )

    if prefix:
        resolved_title = f"{prefix} - {resolved_title}"

    if total > 1:
        return f"{resolved_title} (Part {index})"

    return resolved_title


# -----------------------------------
# INGESTION
# -----------------------------------

def build_imported_document_summary(
    chunk,
    summary_override="",
    body_note="",
):

    cleaned_summary = normalize_knowledge_text(
        summary_override
    )
    cleaned_note = normalize_knowledge_text(
        body_note
    )
    combined_summary = normalize_knowledge_text(
        " ".join(
            value
            for value in (
                cleaned_summary,
                cleaned_note,
            )
            if value
        )
    )

    if combined_summary:
        if len(combined_summary) > 220:
            return (
                combined_summary[:217].rstrip()
                + "..."
            )

        return combined_summary

    return summarize_knowledge_text(chunk)


def build_imported_document_body(
    chunk,
    body_note="",
    index=1,
):

    cleaned_chunk = normalize_knowledge_text(
        chunk
    )
    cleaned_note = normalize_knowledge_text(
        body_note
    )

    if cleaned_note and index == 1:
        return (
            f"Import note: {cleaned_note}\n\n"
            f"{cleaned_chunk}"
        )

    return cleaned_chunk

def decode_base64_file_content(
    content_base64,
):

    cleaned_value = str(
        content_base64 or ""
    ).strip()

    if not cleaned_value:
        raise ValueError(
            "The uploaded file did not include any content."
        )

    if "," in cleaned_value and cleaned_value.lower().startswith(
        "data:"
    ):
        cleaned_value = cleaned_value.split(
            ",",
            1,
        )[1]

    try:
        return base64.b64decode(
            cleaned_value
        )
    except Exception as error:
        raise ValueError(
            "One of the uploaded files could not be decoded."
        ) from error


def build_uploaded_document_title(
    file_name,
    index=0,
    total=1,
):

    base_title = Path(
        str(file_name or "Knowledge document")
    ).stem.replace(
        "_",
        " ",
    ).replace(
        "-",
        " ",
    ).strip() or "Knowledge document"
    base_title = re.sub(
        r"\s+",
        " ",
        base_title,
    )

    if total <= 1:
        return base_title

    return (
        f"{base_title} Part {index + 1}"
    )


def ingest_uploaded_knowledge_files(
    uploaded_files,
    category="Knowledge",
    status="Draft",
    tags=None,
    source_name="",
):

    created_documents = []
    file_summaries = []

    for uploaded_file in uploaded_files or []:
        file_name = str(
            uploaded_file.get(
                "name",
                "knowledge-upload",
            )
        ).strip() or "knowledge-upload"
        mime_type = str(
            uploaded_file.get(
                "mime_type",
                "",
            )
        ).strip()
        file_bytes = decode_base64_file_content(
            uploaded_file.get(
                "content_base64",
                "",
            )
        )
        from services.upload_security_service import validate_knowledge_upload
        validate_knowledge_upload(file_bytes, file_name)
        extracted_text = extract_uploaded_knowledge_text(
            file_name=file_name,
            mime_type=mime_type,
            file_bytes=file_bytes,
        )
        split_result = split_text_into_documents(
            extracted_text
        )
        text_chunks = split_result[
            "chunks"
        ]

        if not text_chunks:
            raise ValueError(
                f"{file_name} did not contain any readable training text."
            )

        documents_for_file = []

        for index, chunk in enumerate(
            text_chunks
        ):
            created_document = (
                create_knowledge_document(
                    title=build_uploaded_document_title(
                        file_name,
                        index=index,
                        total=len(
                            text_chunks
                        ),
                    ),
                    category=category,
                    status=status,
                    summary=summarize_knowledge_text(
                        chunk
                    ),
                    body=chunk,
                    tags=tags or [],
                    source_name=source_name
                    or file_name,
                    source_type="upload",
                )
            )
            created_documents.append(
                created_document
            )
            documents_for_file.append(
                created_document
            )

        warning = ""

        if (
            split_result[
                "was_truncated"
            ]
            and MAX_DOCUMENTS_PER_FILE is not None
        ):
            warning = (
                f"{file_name} was split into the first {MAX_DOCUMENTS_PER_FILE} AI documents. "
                "Shorter files work best for focused training."
            )

        file_summaries.append(
            {
                "document_count": len(
                    documents_for_file
                ),
                "file_name": file_name,
                "warning": warning,
            }
        )

    return {
        "documents": created_documents,
        "files": file_summaries,
    }


def ingest_url_knowledge_source(
    raw_url,
    category="Knowledge",
    status="Published",
    tags=None,
    title_prefix="",
    summary_override="",
    body_note="",
    source_type="url",
):

    remote_source_result = (
        fetch_remote_knowledge_sources(
            raw_url
        )
    )
    remote_pages = remote_source_result[
        "pages"
    ]

    if not remote_pages:
        raise ValueError(
            "The imported URL did not contain any readable text."
        )

    created_documents = []
    page_warnings = []

    for remote_payload in remote_pages:
        split_result = split_text_into_documents(
            remote_payload["body"]
        )
        text_chunks = split_result[
            "chunks"
        ]

        if not text_chunks:
            continue

        for index, chunk in enumerate(
            text_chunks,
            start=1,
        ):
            created_document = (
                create_knowledge_document(
                    title=build_imported_url_title(
                        remote_payload["title"],
                        remote_payload["url"],
                        title_prefix=title_prefix,
                        index=index,
                        total=len(
                            text_chunks
                        ),
                    ),
                    category=category,
                    status=status,
                    summary=build_imported_document_summary(
                        chunk,
                        summary_override=summary_override,
                        body_note=body_note,
                    ),
                    body=build_imported_document_body(
                        chunk,
                        body_note=body_note,
                        index=index,
                    ),
                    tags=tags or [],
                    source_name=remote_payload["url"],
                    source_type=source_type,
                )
            )
            created_documents.append(
                created_document
            )

        if (
            split_result[
                "was_truncated"
            ]
            and MAX_DOCUMENTS_PER_FILE is not None
        ):
            page_warnings.append(
                (
                    f"{remote_payload['url']} was split into the first {MAX_DOCUMENTS_PER_FILE} AI documents. "
                    "Shorter pages work best for focused training."
                )
            )

    if not created_documents:
        raise ValueError(
            "The imported URL did not contain any readable training text."
        )

    warning_parts = [
        remote_source_result.get(
            "warning",
            "",
        ),
        *page_warnings,
    ]
    warning = " ".join(
        part
        for part in warning_parts
        if normalize_knowledge_text(part)
    ).strip()
    lead_page = remote_pages[0]

    return {
        "documents": created_documents,
        "skipped_page_count": remote_source_result.get("skipped_page_count", 0),
        "title": lead_page["title"],
        "url": lead_page["url"],
        "warning": warning,
    }
