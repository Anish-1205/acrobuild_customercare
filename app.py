"""Application entry point; domain routes live in routers/."""
from api_context import api
from routers.cs_api_settings import router as cs_api_settings_router
api.include_router(cs_api_settings_router)
from routers.automation import router as automation_router
api.include_router(automation_router)
from routers.health import router as health_router
api.include_router(health_router)
from routers.customer import router as customer_router
api.include_router(customer_router)
from routers.properties import router as properties_router
api.include_router(properties_router)
from routers.assist import router as assist_router
api.include_router(assist_router)
from routers.workspace import router as workspace_router
api.include_router(workspace_router)
from routers.knowledge import router as knowledge_router
api.include_router(knowledge_router)
