import csv
import os
from html import escape
from io import StringIO
from pathlib import Path


DEFAULT_LOCAL_PRODUCT_FEED_PATHS = {
    "macros": Path(
        r"C:\Users\ROOTS_GRAPHICS1\Desktop\products_export_macros.csv"
    ),
    "soulara": Path(
        r"C:\Users\ROOTS_GRAPHICS1\Desktop\products_export_soulara.csv"
    ),
}
LOCAL_PRODUCT_FEED_ENV_VARS = {
    "macros": "LOCAL_MACROS_PRODUCTS_CSV_PATH",
    "soulara": "LOCAL_SOULARA_PRODUCTS_CSV_PATH",
}
PRODUCT_FEED_COLUMNS = {
    "description": "Body (HTML)",
    "handle": "Handle",
    "image": "Image Src",
    "price": "Variant Price",
    "published": "Published",
    "tags": "Tags",
    "title": "Title",
    "type": "Type",
    "vendor": "Vendor",
}


def get_available_local_product_feed_keys():

    return sorted(
        DEFAULT_LOCAL_PRODUCT_FEED_PATHS.keys()
    )


def get_local_product_feed_path(
    feed_key,
):

    normalized_feed_key = str(
        feed_key or ""
    ).strip().lower()

    if (
        normalized_feed_key
        not in DEFAULT_LOCAL_PRODUCT_FEED_PATHS
    ):
        raise ValueError(
            f"Unknown local product feed: {feed_key}"
        )

    env_name = LOCAL_PRODUCT_FEED_ENV_VARS[
        normalized_feed_key
    ]
    configured_path = str(
        os.getenv(
            env_name,
            "",
        )
    ).strip()

    if configured_path:
        return Path(
            configured_path
        )

    return DEFAULT_LOCAL_PRODUCT_FEED_PATHS[
        normalized_feed_key
    ]


def read_local_product_feed_csv(
    feed_key,
):

    csv_path = get_local_product_feed_path(
        feed_key
    )

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Local product feed file not found: {csv_path}"
        )

    for encoding_name in (
        "utf-8-sig",
        "utf-8",
        "cp1252",
    ):
        try:
            return csv_path.read_text(
                encoding=encoding_name,
                errors="replace",
            )
        except UnicodeDecodeError:
            continue

    return csv_path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def parse_local_product_feed_rows(
    feed_key,
):

    csv_text = read_local_product_feed_csv(
        feed_key
    )
    csv_reader = csv.DictReader(
        StringIO(csv_text)
    )
    unique_products = []
    seen_product_keys = set()

    for row in csv_reader:
        handle = str(
            row.get(
                PRODUCT_FEED_COLUMNS["handle"],
                "",
            )
            or ""
        ).strip()
        title = str(
            row.get(
                PRODUCT_FEED_COLUMNS["title"],
                "",
            )
            or ""
        ).strip()

        if not handle or not title:
            continue

        product_key = (
            handle.lower(),
            title.lower(),
        )

        if product_key in seen_product_keys:
            continue

        seen_product_keys.add(
            product_key
        )
        unique_products.append(
            {
                "description": str(
                    row.get(
                        PRODUCT_FEED_COLUMNS[
                            "description"
                        ],
                        "",
                    )
                    or ""
                ).strip(),
                "handle": handle,
                "image": str(
                    row.get(
                        PRODUCT_FEED_COLUMNS[
                            "image"
                        ],
                        "",
                    )
                    or ""
                ).strip(),
                "price": str(
                    row.get(
                        PRODUCT_FEED_COLUMNS[
                            "price"
                        ],
                        "",
                    )
                    or ""
                ).strip(),
                "published": str(
                    row.get(
                        PRODUCT_FEED_COLUMNS[
                            "published"
                        ],
                        "",
                    )
                    or ""
                ).strip(),
                "tags": str(
                    row.get(
                        PRODUCT_FEED_COLUMNS[
                            "tags"
                        ],
                        "",
                    )
                    or ""
                ).strip(),
                "title": title,
                "type": str(
                    row.get(
                        PRODUCT_FEED_COLUMNS[
                            "type"
                        ],
                        "",
                    )
                    or ""
                ).strip(),
                "vendor": str(
                    row.get(
                        PRODUCT_FEED_COLUMNS[
                            "vendor"
                        ],
                        "",
                    )
                    or ""
                ).strip(),
            }
        )

    return unique_products


def get_local_product_feed_summary(
    feed_key,
):

    feed_rows = parse_local_product_feed_rows(
        feed_key
    )
    published_count = sum(
        1
        for row in feed_rows
        if row["published"].lower()
        in {
            "true",
            "1",
            "yes",
        }
    )

    return {
        "feed_key": str(
            feed_key or ""
        ).strip().lower(),
        "products": feed_rows,
        "published_count": published_count,
        "total_count": len(feed_rows),
    }


def build_local_product_feed_html(
    feed_key,
):

    feed_summary = (
        get_local_product_feed_summary(
            feed_key
        )
    )
    safe_feed_title = escape(
        feed_summary["feed_key"].upper()
    )
    product_rows = []

    for product in feed_summary[
        "products"
    ]:
        product_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td>{escape(product['title'])}</td>",
                    f"<td>{escape(product['handle'])}</td>",
                    f"<td>{escape(product['vendor'])}</td>",
                    f"<td>{escape(product['type'])}</td>",
                    f"<td>{escape(product['price'] or '-')}</td>",
                    f"<td>{escape(product['published'] or '-')}</td>",
                    "</tr>",
                ]
            )
        )

    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "<meta charset=\"utf-8\">",
            f"<title>{safe_feed_title} local product feed</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 24px; color: #111827; }",
            "h1 { margin-bottom: 8px; }",
            "p { color: #4b5563; line-height: 1.5; }",
            ".meta { display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0 24px; }",
            ".pill { padding: 8px 12px; border-radius: 999px; background: #f3f4f6; font-weight: 700; }",
            "table { width: 100%; border-collapse: collapse; margin-top: 16px; }",
            "th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }",
            "th { background: #f9fafb; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{safe_feed_title} local product feed</h1>",
            "<p>This page is generated from the local CSV file and updates whenever the CSV changes.</p>",
            "<div class=\"meta\">",
            f"<div class=\"pill\">Total products: {feed_summary['total_count']}</div>",
            f"<div class=\"pill\">Published products: {feed_summary['published_count']}</div>",
            f"<div class=\"pill\">CSV URL: /local-data/products/{escape(feed_summary['feed_key'])}.csv</div>",
            "</div>",
            "<table>",
            "<thead>",
            "<tr>",
            "<th>Title</th>",
            "<th>Handle</th>",
            "<th>Vendor</th>",
            "<th>Type</th>",
            "<th>Price</th>",
            "<th>Published</th>",
            "</tr>",
            "</thead>",
            "<tbody>",
            *product_rows,
            "</tbody>",
            "</table>",
            "</body>",
            "</html>",
        ]
    )

