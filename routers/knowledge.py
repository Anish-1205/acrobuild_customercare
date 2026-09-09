"""Knowledge HTTP endpoints."""
from fastapi import APIRouter
from api_context import (
    HTTPException,
    KnowledgeDocumentCreateRequest,
    KnowledgeDocumentDeleteRequest,
    KnowledgeDocumentUpdateRequest,
    KnowledgeDocumentUploadRequest,
    KnowledgeDocumentUrlImportRequest,
    SupportArticleCreateRequest,
    SupportArticleUpdateRequest,
    clear_assist_response_cache,
    create_knowledge_document,
    create_support_article,
    delete_knowledge_documents,
    get_knowledge_document,
    get_knowledge_documents,
    get_support_article,
    get_support_articles,
    ingest_uploaded_knowledge_files,
    ingest_url_knowledge_source,
    logger,
    refresh_support_assist_state,
    refresh_workspace_index,
    reset_workspace_knowledge,
    update_knowledge_document,
    update_support_article,
)

router = APIRouter(tags=["knowledge"])

@router.get("/api/admin/articles")
@router.get("/admin/articles")
def get_admin_articles_api():

    return {
        "articles": get_support_articles(),
    }

@router.post("/api/admin/articles")
@router.post("/admin/articles")
def create_admin_article_api(request: SupportArticleCreateRequest):

    try:
        article = create_support_article(
            title=request.title,
            category=request.category,
            status=request.status,
            summary=request.summary,
            body=request.body,
            keywords=request.keywords,
            url=request.url,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    refresh_support_assist_state()

    return {
        "article": article,
    }

@router.put("/api/admin/articles/{article_id}")
@router.put("/admin/articles/{article_id}")
def update_admin_article_api(article_id: int, request: SupportArticleUpdateRequest):

    existing_article = get_support_article(article_id)

    if not existing_article:
        raise HTTPException(status_code=404, detail="Article not found.")

    article = update_support_article(
        article_id=article_id,
        title=request.title,
        category=request.category,
        status=request.status,
        summary=request.summary,
        body=request.body,
        keywords=request.keywords,
        url=request.url,
    )
    refresh_support_assist_state()

    return {
        "article": article,
    }

@router.get("/api/admin/knowledge-documents")
@router.get("/admin/knowledge-documents")
def get_admin_knowledge_documents_api():

    return {
        "documents": get_knowledge_documents(),
    }

@router.post("/api/admin/knowledge-documents")
@router.post("/admin/knowledge-documents")
def create_admin_knowledge_document_api(request: KnowledgeDocumentCreateRequest):

    try:
        document = create_knowledge_document(
            title=request.title,
            category=request.category,
            status=request.status,
            summary=request.summary,
            body=request.body,
            tags=request.tags,
            source_name=request.source_name,
            source_type=request.source_type,
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    refresh_support_assist_state()

    return {
        "document": document,
    }

@router.post("/api/admin/knowledge-documents/upload")
@router.post("/admin/knowledge-documents/upload")
def upload_admin_knowledge_documents_api(
    request: KnowledgeDocumentUploadRequest,
):

    if not request.files:
        raise HTTPException(
            status_code=400,
            detail="Add at least one training file before uploading.",
        )

    try:
        upload_result = ingest_uploaded_knowledge_files(
            uploaded_files=[
                file_item.model_dump()
                for file_item in request.files
            ],
            category=request.category,
            status=request.status,
            tags=request.tags,
            source_name=request.source_name,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        logger.exception("Knowledge document deletion failed")
        raise HTTPException(
            status_code=500,
            detail="Knowledge document deletion failed.",
        ) from error

    refresh_support_assist_state()

    return upload_result

@router.post("/api/admin/knowledge-documents/import-url")
@router.post("/admin/knowledge-documents/import-url")
def import_admin_knowledge_url_api(
    request: KnowledgeDocumentUrlImportRequest,
):

    try:
        import_result = ingest_url_knowledge_source(
            raw_url=request.url,
            category=request.category,
            status=request.status,
            tags=request.tags,
            title_prefix=request.title_prefix,
            summary_override=request.summary,
            body_note=request.body_note,
            source_type=request.source_type,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        logger.exception("Workspace knowledge reset failed")
        raise HTTPException(
            status_code=500,
            detail="Workspace knowledge reset failed.",
        ) from error

    refresh_support_assist_state()

    return import_result

@router.put("/api/admin/knowledge-documents/{document_id}")
@router.put("/admin/knowledge-documents/{document_id}")
def update_admin_knowledge_document_api(
    document_id: int,
    request: KnowledgeDocumentUpdateRequest,
):

    existing_document = get_knowledge_document(document_id)

    if not existing_document:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")

    document = update_knowledge_document(
        document_id=document_id,
        title=request.title,
        category=request.category,
        status=request.status,
        summary=request.summary,
        body=request.body,
        tags=request.tags,
        source_name=request.source_name,
        source_type=request.source_type,
    )
    refresh_support_assist_state()

    return {
        "document": document,
    }

@router.post("/api/admin/knowledge-documents/delete")
@router.post("/admin/knowledge-documents/delete")
def delete_admin_knowledge_documents_api(
    request: KnowledgeDocumentDeleteRequest,
):

    if not request.document_ids:
        raise HTTPException(
            status_code=400,
            detail="Select at least one knowledge item to delete.",
        )

    try:
        delete_result = delete_knowledge_documents(
            request.document_ids
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    refresh_support_assist_state()

    return delete_result

@router.post("/api/admin/knowledge-documents/reset")
@router.post("/admin/knowledge-documents/reset")
def reset_admin_workspace_knowledge_api():

    try:
        reset_result = reset_workspace_knowledge()
        clear_assist_response_cache()
        refresh_workspace_index(force_refresh=True)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    return reset_result
