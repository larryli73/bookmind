"""
BookMind — FastAPI Application with Rate Limiting
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from api.routes import recommendations, readers, children, books, feedback, affiliate

# Rate limiter — generous limits real users will never hit
limiter = Limiter(key_func=get_remote_address, default_limits=["500/day", "200/hour", "30/minute"])

app = FastAPI(
    title="BookMind API",
    description="AI-powered book recommendations for adults and children",
    version="0.1.0",
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["Recommendations"])
app.include_router(readers.router,         prefix="/api/v1/readers",         tags=["Readers"])
app.include_router(children.router,        prefix="/api/v1/children",        tags=["Children"])
app.include_router(books.router,           prefix="/api/v1/books",           tags=["Books"])
app.include_router(feedback.router,        prefix="/api/v1/feedback",        tags=["Feedback"])
app.include_router(affiliate.router,       prefix="/api/v1/affiliate",       tags=["Affiliate"])


@app.on_event("startup")
async def startup():
    try:
        from db.session import engine
        from db.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables created")
    except Exception as e:
        print(f"⚠️ Database startup error: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "BookMind API"}
