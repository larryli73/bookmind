# 📚 BookMind — AI Book Recommendation Engine

> Personalized book recommendations for adults and children.
> Free to use. Powered by Claude Sonnet 4 + pgvector. Revenue from affiliate links.

---

## Tech Stack

| Layer | Tool |
|---|---|
| LLM | Claude Sonnet 4 (anthropic) |
| Agent | LangGraph |
| Embeddings | OpenAI text-embedding-3-small |
| Database | PostgreSQL + pgvector |
| Cache/Queue | Redis + ARQ |
| API | FastAPI |
| Observability | Langfuse |
| Email | SendGrid |
| Hosting | Railway |

---

## Quick Start

### 1. Clone and setup
```bash
git clone https://github.com/yourname/bookmind
cd bookmind
cp .env.example .env
# Fill in your API keys in .env
```

### 2. Start infrastructure
```bash
docker-compose up -d db redis
```

### 3. Install dependencies
```bash
pip install poetry
poetry install
```

### 4. Run the API
```bash
uvicorn api.main:app --reload
# API docs at http://localhost:8000/docs
```

### 5. Ingest your first books
```bash
python -m scripts.ingest_books --query "bestseller fiction" --limit 200
python -m scripts.ingest_books --query "children fantasy" --limit 200
python -m scripts.ingest_books --query "picture books" --limit 100
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/readers/` | Create reader account |
| GET | `/api/v1/readers/{id}` | Get reader profile |
| POST | `/api/v1/children/` | Add child profile |
| GET | `/api/v1/children/{id}/series` | Get child's series progress |
| POST | `/api/v1/recommendations/for-me` | Get adult recommendations |
| POST | `/api/v1/recommendations/for-child` | Get kids recommendations |
| POST | `/api/v1/feedback/adult` | Submit reading feedback |
| POST | `/api/v1/feedback/child` | Submit child's reading feedback |
| POST | `/api/v1/affiliate/click` | Track affiliate click |

---

## Project Structure

```
bookmind/
├── agent/              # LangGraph recommendation pipeline
│   ├── graph.py        # Main agent graph
│   ├── state.py        # AgentState dataclass
│   ├── prompts.py      # All Claude system prompts
│   ├── nodes/          # Pipeline nodes
│   └── tools/          # Agent tools
├── api/                # FastAPI application
│   ├── main.py         # App entry point
│   └── routes/         # Route handlers
├── db/                 # Database layer
│   ├── models.py       # SQLAlchemy models
│   ├── vector_store.py # pgvector helpers
│   └── session.py      # DB session
├── integrations/       # External API clients
├── workers/            # Background jobs
├── scripts/            # CLI tools
└── infra/              # Docker, Railway config
```

---

## Revenue Model

- **Amazon Associates:** 4-8% on book purchases
- **Bookshop.org:** 10% on book purchases  
- **Audible:** $5-15 per trial signup
- All affiliate links auto-generated per recommendation

---

## Roadmap

- [ ] Phase 1 (Weeks 1-3): Core recommendation engine + MVP
- [ ] Phase 2 (Weeks 4-7): Full agent loop + series tracker + weekly digest
- [ ] Phase 3 (Weeks 8-11): Launch + affiliate integration + SEO pages
