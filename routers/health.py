"""Health HTTP endpoints."""
from fastapi import APIRouter
from services.provider_resilience_service import provider_health
from api_context import (
    HTMLResponse,
    HTTPException,
    Response,
    build_local_product_feed_html,
    get_cs_api_status,
    get_llm_provider,
    get_local_product_feed_summary,
    get_workspace_index_state,
    is_llm_available,
    logger,
    open_database_connection,
    read_local_product_feed_csv,
)

router = APIRouter(tags=["health"])


@router.get("/api/admin/provider-health")
def get_provider_health():
    return {"providers": provider_health(), "probe": "observed_calls"}

@router.get("/")
def home():

    return {
        "message": "AI Customer Support Backend Running"
    }

@router.get("/api/health")
def api_health():
    checks = {}
    try:
        conn = open_database_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks["sqlite"] = {"status": "ok"}
    except Exception:
        logger.exception("SQLite health check failed")
        checks["sqlite"] = {"status": "failed"}
    checks["llm"] = {
        "status": "ok" if is_llm_available() else "failed",
        "provider": get_llm_provider(),
    }
    cs_status = get_cs_api_status()
    checks["cs_api"] = {"status": "ok" if cs_status["configured"] else "failed"}
    index_state = get_workspace_index_state()
    checks["knowledge_index"] = {
        "status": "degraded" if index_state["is_dirty"] or index_state["is_building"] else "ok",
        "is_building": index_state["is_building"],
        "is_dirty": index_state["is_dirty"],
    }
    degraded = any(check["status"] != "ok" for check in checks.values())
    return {"status": "degraded" if degraded else "ok", "checks": checks}

@router.get("/api/local-product-feeds")
def get_local_product_feeds_api():

    feed_summaries = []

    for feed_key in (
        "macros",
        "soulara",
    ):
        try:
            summary = (
                get_local_product_feed_summary(
                    feed_key
                )
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=str(error),
            ) from error

        feed_summaries.append(
            {
                "csv_url": f"/local-data/products/{feed_key}.csv",
                "html_url": f"/local-data/products/{feed_key}",
                "key": feed_key,
                "published_count": summary[
                    "published_count"
                ],
                "total_count": summary[
                    "total_count"
                ],
            }
        )

    return {
        "feeds": feed_summaries,
    }

@router.get(
    "/local-data/products/{feed_key}.csv"
)
def get_local_product_feed_csv_api(
    feed_key: str,
):

    try:
        csv_text = read_local_product_feed_csv(
            feed_key
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        logger.exception("Knowledge file ingestion failed")
        raise HTTPException(
            status_code=500,
            detail="Knowledge file ingestion failed.",
        ) from error

    return Response(
        content=csv_text,
        headers={
            "Content-Disposition": (
                f'inline; filename="{feed_key}.csv"'
            )
        },
        media_type="text/csv",
    )

@router.get(
    "/local-data/products/{feed_key}"
)
def get_local_product_feed_html_api(
    feed_key: str,
):

    try:
        html_text = build_local_product_feed_html(
            feed_key
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        logger.exception("Knowledge URL import failed")
        raise HTTPException(
            status_code=500,
            detail="Knowledge URL import failed.",
        ) from error

    return HTMLResponse(
        content=html_text
    )
