from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import router as api_router
from app.db.session import engine
import asyncio
import os
from app.db.mongodb import get_mongo_db

app = FastAPI()

# ✅ Add CORS Middleware here
origins = os.getenv("CORS_ORIGINS", "")
allow_origins = [o.strip() for o in origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,  # or ["*"] for all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/v1/api")


@app.on_event("startup")
async def on_startup():
    try:
        # test DB connection
        async with engine.connect() as conn:
            await conn.run_sync(lambda conn: None)
        print("✅ Database connection successful.")

    except Exception as e:
        print(f"❌ Database connection failed: {e}")

        # MongoDB check
    try:
        mongo_db = get_mongo_db()
        # Perform a simple command to ensure connection
        mongo_db.command("ping")
        print("✅ MongoDB connection successful.")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")


@app.get("/")
async def root():
    return {"message": "fastapi backend app  up and Running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
