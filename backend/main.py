from fastapi import FastAPI
from .api.routers import analyze as analyze_router
from .api.routers import compare as compare_router
from .api.routers import health as health_router

app = FastAPI(title="OpsTune Backend API", version='0.0.1')

app.include_router(analyze_router)
app.include_router(compare_router)
app.include_router(health_router)
