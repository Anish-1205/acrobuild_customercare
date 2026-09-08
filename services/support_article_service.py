import os
import re
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from services.database_service import (
    get_support_articles as get_saved_support_articles,
)

# -----------------------------------
# CONFIG
# -----------------------------------

DEFAULT_SUPPORT_BASE_URL = "https://support.acrobuild.com"
DEFAULT_SUPPORT_TIMEOUT_SECONDS = 5
DEFAULT_SUPPORT_CACHE_TTL_MINUTES = 30
DEFAULT_SUPPORT_MAX_ARTICLES = 24

SUPPORT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": "AcrobuildSupportAgent/1.0",
}

FALLBACK_ARTICLES = [
    {
        "body": (
            "When a customer asks for a site visit, confirm the project, preferred time, and callback number, "
            "then route the request to the site operations team for scheduling."
        ),
        "category": "Site Visit",
        "keywords": ["site visit", "inspection", "sample flat", "tour", "visit"],
        "slug": "site-visit-booking-checklist",
        "summary": (
            "How to confirm visit requests, collect key details, and set expectations for scheduling."
        ),
        "title": "Site visit booking checklist",
    },
    {
        "body": (
            "Use this article to explain how pricing checks, unit availability, and quotation follow-up work "
            "for Acrobuild residential and commercial projects."
        ),
        "category": "Sales",
        "keywords": ["quotation", "pricing", "availability", "inventory", "brochure"],
        "slug": "quotation-inventory-follow-up",
        "summary": (
            "Quotation guidance, inventory checks, and sales follow-up steps for active projects."
        ),
        "title": "Quotation and inventory follow-up playbook",
    },
    {
        "body": (
            "This article explains how payment receipts, invoices, ledger clarifications, and installment questions "
            "should be reviewed before escalation to project finance."
        ),
        "category": "Payments",
        "keywords": ["payment", "receipt", "invoice", "ledger", "installment"],
        "slug": "payment-ledger-clarification",
        "summary": (
            "Payment acknowledgement, receipt checks, and finance escalation guidance."
        ),
        "title": "Payment receipts and ledger clarification",
    },
    {
        "body": (
            "Construction updates should stay aligned with approved milestone information. "
            "Do not promise exact completion or possession dates unless the confirmed update already includes them."
        ),
        "category": "Construction",
        "keywords": ["construction", "progress", "milestone", "timeline", "delay"],
        "slug": "construction-progress-playbook",
        "summary": (
            "Guidance for progress questions, milestone updates, and delay follow-up."
        ),
        "title": "Construction progress update playbook",
    },
    {
        "body": (
            "Buyers who ask for agreements, approvals, NOC, registration, or KYC-linked documents should be asked for "
            "the project, booking reference, and exact document needed before routing to the documentation desk."
        ),
        "category": "Documentation",
        "keywords": ["agreement", "registration", "approval", "noc", "kyc"],
        "slug": "legal-documents-registration-checklist",
        "summary": (
            "Checklist guidance for legal, registration, and buyer-document requests."
        ),
        "title": "Legal documents and registration checklist",
    },
    {
        "body": (
            "Handover and maintenance cases should capture the project name, tower or unit reference, and photo evidence. "
            "Safety-sensitive issues must be escalated immediately to the care team."
        ),
        "category": "Handover",
        "keywords": ["handover", "possession", "maintenance", "defect", "snag"],
        "slug": "handover-maintenance-triage",
        "summary": (
            "Triage guidance for possession, snag, and maintenance support."
        ),
        "title": "Handover and maintenance triage guide",
    },
    {
        "body": (
            "Customers who write after hours should be told that their request is queued for the next active support window "
            "unless the issue needs urgent escalation."
        ),
        "category": "Operations",
        "keywords": ["after hours", "business hours", "response time", "sla"],
        "slug": "business-hours-expectations",
        "summary": (
            "Sets reply-time expectations for requests raised outside the normal support window."
        ),
        "title": "Business-hours and after-hours expectations",
    },
]
ARTICLE_CACHE = {
    "articles": [],
    "error": "",
    "fetched_at": None,
    "last_synced_at": None,
    "source_status": "fallback",
    "support_base_url": DEFAULT_SUPPORT_BASE_URL,
}

ARTICLE_CACHE_LOCK = Lock()


# -----------------------------------
# HELPERS
# -----------------------------------

def get_support_base_url():
    base_url = str(
        os.getenv("ACROBUILD_SUPPORT_BASE_URL", DEFAULT_SUPPORT_BASE_URL)
    ).strip()

    return base_url.rstrip("/") or DEFAULT_SUPPORT_BASE_URL


def get_support_timeout_seconds():
    try:
        return float(
            os.getenv("ACROBUILD_SUPPORT_TIMEOUT_SECONDS", str(DEFAULT_SUPPORT_TIMEOUT_SECONDS))
        )
    except ValueError:
        return DEFAULT_SUPPORT_TIMEOUT_SECONDS


def get_support_cache_ttl():
    try:
        cache_ttl_minutes = int(
            os.getenv("ACROBUILD_SUPPORT_CACHE_TTL_MINUTES", str(DEFAULT_SUPPORT_CACHE_TTL_MINUTES))
        )
    except ValueError:
        cache_ttl_minutes = DEFAULT_SUPPORT_CACHE_TTL_MINUTES

    return timedelta(minutes=max(cache_ttl_minutes, 1))


def get_support_max_articles():
    try:
        return max(
            int(
                os.getenv("ACROBUILD_SUPPORT_MAX_ARTICLES", str(DEFAULT_SUPPORT_MAX_ARTICLES))
            ),
            6,
        )
    except ValueError:
        return DEFAULT_SUPPORT_MAX_ARTICLES


def normalize_whitespace(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_url(value):
    return normalize_whitespace(value).rstrip("/")


def slugify(value):
    cleaned_value = normalize_whitespace(value).lower()
    return re.sub(r"[^a-z0-9]+", "-", cleaned_value).strip("-")


def tokenize_text(value):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_whitespace(value).lower())
        if len(token) > 1
    }


def first_sentences(value, count=2):
    cleaned_value = normalize_whitespace(value)

    if not cleaned_value:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", cleaned_value)
    return " ".join(sentences[:count]).strip()


def build_article_record(
    title,
    url,
    summary,
    body,
    category="Support",
    source="live",
    keywords=None,
):
    article_url = normalize_url(url)
    article_title = normalize_whitespace(title) or "Support article"
    article_summary = normalize_whitespace(summary) or first_sentences(body, count=1)
    article_body = normalize_whitespace(body) or article_summary
    article_category = normalize_whitespace(category) or "Support"
    provided_keywords = tokenize_text(" ".join(keywords or []))
    article_keywords = sorted(
        provided_keywords
        | tokenize_text(article_title)
        | tokenize_text(article_category)
    )

    return {
        "body": article_body,
        "category": article_category,
        "id": slugify(article_title) or slugify(article_url) or "support-article",
        "keywords": article_keywords,
        "source": source,
        "summary": article_summary,
        "title": article_title,
        "url": article_url,
    }


def build_fallback_articles():
    support_base_url = get_support_base_url()
    saved_articles = get_saved_support_articles()
    article_source = saved_articles or FALLBACK_ARTICLES
    articles = []

    for fallback_article in article_source:
        article_url = normalize_url(
            fallback_article.get("url", "")
        )

        if not article_url:
            slug_value = slugify(
                fallback_article.get("title", "")
            ) or "support-article"
            article_url = urljoin(
                f"{support_base_url}/",
                f"articles/{slug_value}",
            )

        article_keywords = fallback_article.get(
            "keywords",
            [],
        )

        if isinstance(
            article_keywords,
            str,
        ):
            article_keywords = [
                keyword.strip()
                for keyword in article_keywords.split(",")
                if keyword.strip()
            ]

        if not article_url.startswith(("http://", "https://")):
            article_url = urljoin(
                f"{support_base_url}/",
                article_url.lstrip("/"),
            )

        articles.append(
            build_article_record(
                title=fallback_article.get("title", "Support article"),
                url=article_url,
                summary=fallback_article.get("summary", ""),
                body=fallback_article.get("body", ""),
                category=fallback_article.get("category", "Support"),
                source="fallback",
                keywords=article_keywords,
            )
        )

    return articles


def looks_like_article_url(candidate_url, support_base_url):
    normalized_candidate = normalize_url(candidate_url)

    if not normalized_candidate:
        return False

    parsed_candidate = urlparse(normalized_candidate)
    parsed_base = urlparse(support_base_url)

    if parsed_candidate.scheme not in ("http", "https"):
        return False

    if parsed_candidate.netloc != parsed_base.netloc:
        return False

    if parsed_candidate.fragment:
        return False

    lower_path = parsed_candidate.path.lower()

    if not lower_path or lower_path in ("/", "/articles", "/help", "/support"):
        return False

    if lower_path.endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".svg",
            ".webp",
            ".gif",
            ".css",
            ".js",
            ".json",
            ".ico",
            ".pdf",
            ".xml",
        )
    ):
        return False

    article_markers = (
        "/article",
        "/articles/",
        "/help/",
        "/hc/",
        "/faq/",
        "/faqs/",
    )

    return any(marker in lower_path for marker in article_markers) or "faq" in lower_path


def fetch_url(session, url):
    response = session.get(
        url,
        headers=SUPPORT_HEADERS,
        timeout=get_support_timeout_seconds(),
    )
    response.raise_for_status()
    return response


def extract_sitemap_urls(xml_text):
    urls = []
    soup = BeautifulSoup(xml_text, "xml")

    for location in soup.find_all("loc"):
        value = normalize_whitespace(location.get_text())

        if value:
            urls.append(value)

    return urls


def extract_html_links(html_text, base_url):
    urls = []
    soup = BeautifulSoup(html_text, "html.parser")

    for anchor in soup.find_all("a", href=True):
        href = normalize_whitespace(anchor.get("href"))

        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue

        urls.append(urljoin(base_url, href))

    return urls


def collect_candidate_pages(session, support_base_url):
    candidate_pages = [
        urljoin(f"{support_base_url}/", "robots.txt"),
        urljoin(f"{support_base_url}/", "sitemap.xml"),
        urljoin(f"{support_base_url}/", "sitemap_index.xml"),
        support_base_url,
    ]
    discovered_pages = []

    for candidate_page in candidate_pages:
        try:
            response = fetch_url(session, candidate_page)
        except Exception:
            continue

        content_type = str(response.headers.get("Content-Type", "")).lower()
        response_text = response.text

        if "robots.txt" in candidate_page:
            sitemap_urls = [
                line.split(":", 1)[1].strip()
                for line in response_text.splitlines()
                if line.lower().startswith("sitemap:")
            ]
            discovered_pages.extend(sitemap_urls)
            continue

        if "xml" in content_type or candidate_page.endswith(".xml"):
            discovered_pages.extend(extract_sitemap_urls(response_text))
            continue

        discovered_pages.extend(extract_html_links(response_text, support_base_url))

    seen_urls = set()
    ordered_pages = []

    for discovered_page in discovered_pages:
        normalized_page = normalize_url(discovered_page)

        if not normalized_page or normalized_page in seen_urls:
            continue

        seen_urls.add(normalized_page)
        ordered_pages.append(normalized_page)

    return ordered_pages


def collect_article_urls(session, support_base_url):
    candidate_pages = collect_candidate_pages(session, support_base_url)
    article_urls = []
    seen_urls = set()

    for candidate_page in candidate_pages:
        if looks_like_article_url(candidate_page, support_base_url):
            if candidate_page not in seen_urls:
                seen_urls.add(candidate_page)
                article_urls.append(candidate_page)
            continue

        lower_path = urlparse(candidate_page).path.lower()

        if lower_path.endswith(".xml"):
            continue

        if not any(
            marker in lower_path
            for marker in ("/help", "/support", "/faq", "/hc", "/articles")
        ):
            continue

        try:
            response = fetch_url(session, candidate_page)
        except Exception:
            continue

        for discovered_link in extract_html_links(response.text, support_base_url):
            if looks_like_article_url(discovered_link, support_base_url):
                normalized_link = normalize_url(discovered_link)

                if normalized_link in seen_urls:
                    continue

                seen_urls.add(normalized_link)
                article_urls.append(normalized_link)

        if len(article_urls) >= get_support_max_articles():
            break

    return article_urls[: get_support_max_articles()]


def select_article_root(soup):
    selectors = [
        "article",
        "main article",
        "main",
        "[role='main']",
        ".article-content",
        ".help-center-article",
        ".article-body",
        ".content",
    ]

    for selector in selectors:
        root = soup.select_one(selector)

        if root is not None:
            return root

    return soup.body or soup


def extract_article_body(article_root):
    paragraph_text = [
        normalize_whitespace(node.get_text(" ", strip=True))
        for node in article_root.select("p, li")
    ]
    filtered_paragraphs = [
        paragraph
        for paragraph in paragraph_text
        if paragraph and len(paragraph) >= 32
    ]

    if filtered_paragraphs:
        return " ".join(filtered_paragraphs[:10])

    return normalize_whitespace(article_root.get_text(" ", strip=True))


def fetch_article_document(session, article_url):
    response = fetch_url(session, article_url)
    soup = BeautifulSoup(response.text, "html.parser")
    article_root = select_article_root(soup)
    heading_node = soup.select_one("h1")
    title_node_text = ""

    if soup.title and soup.title.string:
        title_node_text = soup.title.string

    if heading_node is not None:
        title_node_text = heading_node.get_text(" ", strip=True)

    title = normalize_whitespace(title_node_text)
    description_node = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta",
        attrs={"property": "og:description"},
    )
    summary = normalize_whitespace(
        description_node.get("content", "") if description_node else ""
    )
    category = normalize_whitespace(
        " ".join(
            breadcrumb.get_text(" ", strip=True)
            for breadcrumb in soup.select("nav, .breadcrumb, .breadcrumbs")
        )
    )
    body = extract_article_body(article_root)

    if not title and not body:
        return None

    return build_article_record(
        title=title or urlparse(article_url).path.split("/")[-1].replace("-", " "),
        url=article_url,
        summary=summary,
        body=body,
        category=category or "Support",
        source="live",
    )


def fetch_live_support_articles():
    support_base_url = get_support_base_url()
    session = requests.Session()
    article_urls = collect_article_urls(session, support_base_url)

    if not article_urls:
        raise RuntimeError(
            f"No support articles could be discovered at {support_base_url}."
        )

    articles = []

    for article_url in article_urls:
        try:
            article_document = fetch_article_document(session, article_url)
        except Exception:
            continue

        if article_document is not None:
            articles.append(article_document)

    if not articles:
        raise RuntimeError(
            f"Support articles were discovered at {support_base_url}, but none could be parsed."
        )

    return articles


# -----------------------------------
# CACHE
# -----------------------------------

def get_support_articles(force_refresh=False):
    support_base_url = get_support_base_url()
    cache_ttl = get_support_cache_ttl()
    current_time = datetime.now(timezone.utc)

    with ARTICLE_CACHE_LOCK:
        if (
            not force_refresh
            and ARTICLE_CACHE["articles"]
            and ARTICLE_CACHE["support_base_url"] == support_base_url
            and ARTICLE_CACHE["fetched_at"] is not None
            and current_time - ARTICLE_CACHE["fetched_at"] < cache_ttl
        ):
            return dict(ARTICLE_CACHE)

        existing_cache = dict(ARTICLE_CACHE)

    try:
        live_articles = fetch_live_support_articles()
    except Exception as error:
        fallback_articles = build_fallback_articles()

        with ARTICLE_CACHE_LOCK:
            if existing_cache.get("articles"):
                ARTICLE_CACHE["error"] = str(error)
                ARTICLE_CACHE["fetched_at"] = current_time
                ARTICLE_CACHE["support_base_url"] = support_base_url
                return dict(ARTICLE_CACHE)

            ARTICLE_CACHE["articles"] = fallback_articles
            ARTICLE_CACHE["error"] = str(error)
            ARTICLE_CACHE["fetched_at"] = current_time
            ARTICLE_CACHE["last_synced_at"] = current_time.isoformat()
            ARTICLE_CACHE["source_status"] = "fallback"
            ARTICLE_CACHE["support_base_url"] = support_base_url
            return dict(ARTICLE_CACHE)

    with ARTICLE_CACHE_LOCK:
        ARTICLE_CACHE["articles"] = live_articles
        ARTICLE_CACHE["error"] = ""
        ARTICLE_CACHE["fetched_at"] = current_time
        ARTICLE_CACHE["last_synced_at"] = current_time.isoformat()
        ARTICLE_CACHE["source_status"] = "live"
        ARTICLE_CACHE["support_base_url"] = support_base_url
        return dict(ARTICLE_CACHE)


# -----------------------------------
# SEARCH
# -----------------------------------

def score_article(article, query_tokens, full_query, article_hint_url=""):
    title_tokens = tokenize_text(article["title"])
    summary_tokens = tokenize_text(article["summary"])
    body_tokens = tokenize_text(article["body"])
    keyword_tokens = set(article.get("keywords", []))
    score = 0

    score += len(query_tokens & title_tokens) * 5
    score += len(query_tokens & keyword_tokens) * 4
    score += len(query_tokens & summary_tokens) * 3
    score += len(query_tokens & body_tokens) * 1

    combined_text = normalize_whitespace(
        " ".join([article["title"], article["summary"], article["body"]])
    ).lower()

    if full_query and full_query in combined_text:
        score += 5

    if article_hint_url and normalize_url(article["url"]) == normalize_url(article_hint_url):
        score += 14

    return score


def search_support_articles(query, limit=3, article_hint_url=""):
    support_articles = get_support_articles()
    query_text = normalize_whitespace(query).lower()
    query_tokens = tokenize_text(query_text)
    articles_with_scores = []

    for article in support_articles["articles"]:
        score = score_article(
            article,
            query_tokens=query_tokens,
            full_query=query_text,
            article_hint_url=article_hint_url,
        )

        articles_with_scores.append(
            {
                **article,
                "score": score,
            }
        )

    matching_articles = [
        article
        for article in sorted(
            articles_with_scores,
            key=lambda article: (-article["score"], article["title"]),
        )
        if article["score"] > 0
    ]

    if not matching_articles:
        matching_articles = articles_with_scores[:]

    return {
        "articles": matching_articles[: max(limit, 1)],
        "error": support_articles["error"],
        "last_synced_at": support_articles["last_synced_at"],
        "source_status": support_articles["source_status"],
        "support_base_url": support_articles["support_base_url"],
    }


# -----------------------------------
# ASSIST
# -----------------------------------

def build_support_answer(
    issue,
    customer_name="",
    business_hours_tag="",
    issue_type="",
    article_hint_url="",
    limit=3,
):
    article_search = search_support_articles(
        query=issue,
        limit=limit,
        article_hint_url=article_hint_url,
    )
    matched_articles = article_search["articles"]
    top_article = matched_articles[0] if matched_articles else None
    safe_customer_name = normalize_whitespace(customer_name) or "there"
    support_domain = urlparse(article_search["support_base_url"]).netloc or "support.acrobuild.com"
    is_live_source = article_search["source_status"] == "live"
    coverage_line = (
        "Your message is queued for the next active support window, and urgent cases will still be escalated."
        if normalize_whitespace(business_hours_tag).lower() == "after hours"
        else (
            f"I checked the current {support_domain} guidance so we can keep the answer aligned with the help centre."
            if is_live_source
            else "I checked our saved Acrobuild support guidance so the answer stays aligned with the help playbook."
        )
    )

    if top_article is not None:
        article_guidance = first_sentences(
            top_article["body"] or top_article["summary"],
            count=2,
        )
        topic_line = (
            f"Based on the current {support_domain} article \"{top_article['title']}\", {article_guidance}"
            if is_live_source
            else f"Based on the saved guidance article \"{top_article['title']}\", {article_guidance}"
        )
    else:
        fallback_topic = normalize_whitespace(issue_type).lower() or "support"
        topic_line = (
            f"I could not find a precise article match for this {fallback_topic} question, "
            "so the team may need to review it manually."
        )

    closing_line = (
        "I have also linked the most relevant help-centre articles below so you can open the full guidance."
        if matched_articles
        else "Reply here if you want us to raise this for the support team."
    )

    answer = "\n".join(
        [
            f"Hi {safe_customer_name},",
            "",
            coverage_line,
            topic_line,
            "",
            closing_line,
        ]
    )

    return {
        "answer": answer,
        "articles": matched_articles,
        "last_synced_at": article_search["last_synced_at"],
        "source_label": (
            f"Live {support_domain} articles"
            if article_search["source_status"] == "live"
            else "Saved Acrobuild support guidance"
        ),
        "source_status": article_search["source_status"],
        "support_base_url": article_search["support_base_url"],
        "sync_error": article_search["error"],
    }
