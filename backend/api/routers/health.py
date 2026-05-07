from fastapi import APIRouter
# from .workflow import run_workflow

health_router = APIRouter()

@health_router.get("/health")
async def health_check():
    return {"status": "healthy", "version": "v1"}
