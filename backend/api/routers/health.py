from fastapi import APIRouter
# from .workflow import run_workflow

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "healthy", "version": "v1"}
