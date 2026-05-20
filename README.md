# Itinera — AI Itinerary Generator (MVP)

Hyper-personalized travel itineraries powered by **xAI Grok**, with a FastAPI backend and Streamlit frontend.

## Features

- **Structured preferences**: destination, duration, travel party, pace, budget tier, and multi-select interests
- **AI-generated daily plans**: Morning → Lunch → Afternoon → Evening blocks with costs and coordinates
- **Progressive Foodie Tour**: lunch blocks paired with nearby dessert/coffee walking routes
- **Hidden gems**: low-crowd local favorites flagged in the itinerary
- **Retry on bad JSON**: automatic retries when LLM output fails validation
- **SQLite persistence**: SQLAlchemy async layer (`database.py`), migratable to PostgreSQL
- **Structured Grok outputs**: native `json_schema` with Pydantic-backed validation
- **Geocoding fallbacks**: `geopy` + city bounding-box offsets so maps never break
- **Saved trips**: reload historical itineraries from the sidebar without re-calling xAI
- **Route maps**: Folium polylines connect daily stops in timeline order
- **Share links**: public `GET /shared/itinerary/{uuid}` + `?trip=` view-only Streamlit mode
- **Offline export**: Markdown travel guides via `st.download_button`

## Project structure

```
Itinera/
├── app.py                 # Streamlit frontend entrypoint
├── main.py                # FastAPI backend entrypoint
├── schemas.py             # Pydantic data models
├── config.py              # Environment-based settings
├── database.py            # SQLAlchemy async ORM (SQLite / Postgres)
├── requirements.txt
├── services/
│   ├── ai_engine.py       # Grok structured outputs, parsing, retries
│   ├── db_service.py      # Itinerary CRUD
│   └── geocoding.py       # Coordinate validation & fallbacks
├── routers/
│   └── itinerary.py       # REST API routes
├── data/
│   └── store.py           # In-memory itinerary store
└── frontend/
    ├── api_client.py      # HTTP client for backend
    └── components.py      # Streamlit UI components
```

## Quick start

### 1. Install dependencies

```bash
cd Itinera
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

For local development without an API key, set `USE_MOCK_LLM=true` in `.env`.

To use xAI Grok, set your key and disable mock mode:

```env
XAI_API_KEY=xai-...
XAI_MODEL=grok-4.3
USE_MOCK_LLM=false
```

### 3. Start the backend

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

### 4. Start the frontend

In a second terminal:

```bash
streamlit run app.py
```

Open http://localhost:8501, configure your trip in the sidebar, and click **Generate Itinerary**.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/itinerary/generate` | Generate and store an itinerary |
| `GET` | `/api/itinerary/{id}` | Fetch itinerary by ID |
| `GET` | `/api/itinerary` | List all stored itineraries |
| `GET` | `/shared/itinerary/{id}` | Public view-only itinerary (share token) |

### Example request

```bash
curl -X POST http://127.0.0.1:8000/api/itinerary/generate \
  -H "Content-Type: application/json" \
  -d '{
    "preferences": {
      "destination": "Tokyo",
      "duration_days": 2,
      "travel_party": "Couple",
      "pace": "Moderate",
      "budget_tier": "Mid-range",
      "interests": ["Foodie", "Culture", "Hidden Gems"]
    }
  }'
```

## Architecture notes

- **Business logic** lives in `services/ai_engine.py` (prompts, JSON parsing, validation, retries).
- **Presentation** lives in `frontend/components.py` and `app.py`.
- **Data layer** is `database.py` + `services/db_service.py`. Set `DATABASE_URL=postgresql+asyncpg://...` for production.

## License

MIT
