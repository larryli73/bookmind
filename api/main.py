"""
BookMind — FastAPI Application with Rate Limiting
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from api.routes import recommendations, readers, children, books, feedback, affiliate, auth, analytics, seo
import os

limiter = Limiter(key_func=get_remote_address, default_limits=["500/day","200/hour","30/minute"])

app = FastAPI(title="BookMind API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["Recommendations"])
app.include_router(readers.router,         prefix="/api/v1/readers",         tags=["Readers"])
app.include_router(children.router,        prefix="/api/v1/children",        tags=["Children"])
app.include_router(books.router,           prefix="/api/v1/books",           tags=["Books"])
app.include_router(feedback.router,        prefix="/api/v1/feedback",        tags=["Feedback"])
app.include_router(analytics.router,      prefix="/api/v1/analytics",       tags=["Analytics"])
app.include_router(auth.router,          prefix="/api/v1/auth",           tags=["Auth"])
app.include_router(affiliate.router,       prefix="/api/v1/affiliate",       tags=["Affiliate"])

# SEO pages — no prefix, served at root level
app.include_router(seo.router, tags=["SEO"])


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
    
    # Create analytics tables
    try:
        from db.session import engine
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS search_logs (
                    id SERIAL PRIMARY KEY,
                    reader_id VARCHAR(36),
                    query TEXT,
                    results_count INTEGER,
                    session_id VARCHAR(36),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS click_logs (
                    id SERIAL PRIMARY KEY,
                    reader_id VARCHAR(36),
                    session_id VARCHAR(36),
                    book_id VARCHAR(36),
                    book_title TEXT,
                    book_author TEXT,
                    click_type VARCHAR(20),
                    position INTEGER,
                    query TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
        print("✅ Analytics tables ready")
    except Exception as e:
        print(f"⚠️ Analytics table error: {e}")


@app.get("/", response_class=HTMLResponse)
async def frontend():
    """Serve the BookMind frontend"""
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend.html")
    with open(frontend_path, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/analytics-dashboard", response_class=HTMLResponse)
async def analytics_dashboard():
    """Serve the analytics dashboard"""
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analytics_dashboard.html")
    with open(path, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/health")
async def health():
    return {"status": "ok", "service": "BookMind API"}

@app.get("/googleef6d3a05af95cc99.html", response_class=HTMLResponse)
async def google_verify():
    return HTMLResponse("google-site-verification: googleef6d3a05af95cc99.html")
