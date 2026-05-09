"""
BookMind — FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import recommendations, readers, children, books, feedback, affiliate
from db.session import engine
from db.models import Base

app = FastAPI(
    title="BookMind API",
    description="AI-powered book recommendations for adults and children",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["Recommendations"])
app.include_router(readers.router,         prefix="/api/v1/readers",         tags=["Readers"])
app.include_router(children.router,        prefix="/api/v1/children",        tags=["Children"])
app.include_router(books.router,           prefix="/api/v1/books",           tags=["Books"])
app.include_router(feedback.router,        prefix="/api/v1/feedback",        tags=["Feedback"])
app.include_router(affiliate.router,       prefix="/api/v1/affiliate",       tags=["Affiliate"])


@app.on_event("startup")
async def startup():
    # Create tables (use Alembic migrations in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "BookMind API"}
