from fastapi import FastAPI
from api.routers.analyze import router as analyze_router
from api.routers.compare import router as compare_router
from api.routers.health import router as health_router

app = FastAPI(title="OpsTune Backend API", version='0.0.1')

app.include_router(analyze_router)
app.include_router(compare_router)
app.include_router(health_router)
