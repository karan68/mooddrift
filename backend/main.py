from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.qdrant_service import create_collection
from routers.vapi_webhook import router as vapi_router
from routers.entries import router as entries_router
from routers.dashboard import router as dashboard_router
from routers.telegram_bot import router as telegram_router
from routers.time_capsule import router as time_capsule_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Defer collection creation to avoid blocking port binding on Render
    import threading
    threading.Thread(target=create_collection, daemon=True).start()
    yield


app = FastAPI(title="MoodDrift API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vapi_router)
app.include_router(entries_router)
app.include_router(dashboard_router)
app.include_router(telegram_router)
app.include_router(time_capsule_router)


@app.get("/health")
def health():
    return {"status": "ok"}
