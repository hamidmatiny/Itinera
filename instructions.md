# Role & Objective
You are an expert, staff-level Full-Stack Engineer and AI Architect. Your task is to architect and build the foundational MVP for a hyper-personalized "AI Itinerary Generator". The application must be written with enterprise-grade, production-ready, clean, and modular code following industry best practices.

# Tech Stack Specification
- Backend: Python with FastAPI (async, structured Pydantic schemas, modular routers).
- Frontend: Streamlit (clean, professional UI, utilizing columns, metrics, and interactive maps).
- AI/LLM Integration: OpenAI SDK or Anthropic SDK (structured outputs using JSON mode/instructor).
- Database/Data Layer: In-memory/mock database using typed dictionaries (to be easily swapped with PostgreSQL/PostGIS later).

# Application Architecture & Features to Implement

## 1. Core AI Engine & Schema (Backend)
- Implement a robust data validation layer using Pydantic for user preferences:
  - Logistics: Destination, Duration (days), Travel Party (Solo/Couple/Family/Group), Pace (Relaxed, Moderate, Packed).
  - Budget: Hard constraints mapped to tiers (Budget, Mid-range, Luxury).
  - Interests: Multi-select tags (Foodie, Culture, Nature, Hidden Gems).
- Create a service layer that constructs a strict system prompt ensuring the AI returns a valid, structured JSON array matching a daily itinerary schema:
  - Day Number -> Time Slot (Morning, Lunch, Afternoon, Evening) -> Activity Name, Description, Estimated Cost, Lat/Lng Coordinates, and a "Hidden Gem" boolean flag.

## 2. Professional Streamlit User Interface (Frontend)
- Sidebar: Clean configuration panel for inputting the user profile, destination, and budget.
- Main Dashboard: 
  - Loading State: Professional spinner with contextual messages while the AI generates the plan.
  - Tabs Interface: 
    - Tab 1: "Daily Itinerary" (Using `st.expander` for each day, displaying clear time blocks, budget metrics, and activity details).
    - Tab 2: "Foodie & Hidden Gems" (Highlighting localized culinary spots and exclusive, low-crowd attractions).
    - Tab 3: "Map View" (Using `st.map` or `st.components.v1` to plot coordinates of the generated route).

## 3. Advanced Logic & Constraints
- Implement an algorithm or explicit prompt constraint that enforces a "Progressive Foodie Tour" feature (e.g., pairing a lunch spot with a nearby dessert or coffee walking route).
- Ensure strict error handling: if the LLM payload fails to parse as valid JSON, catch the error, log it professionally, and execute a retry mechanism.

# Coding Standards & Deliverables
- Write fully typed, self-documenting code with clear docstrings.
- Separate business logic (AI prompt engineering and data parsing) from the presentation layer (Streamlit components).
- Provide a clean `requirements.txt` file.
- Organize the project structure cleanly:
  ├── app.py              # Streamlit Frontend Entrypoint
  ├── main.py             # FastAPI Backend Entrypoint
  ├── schemas.py          # Pydantic Data Models
  ├── services/
  │   └── ai_engine.py    # LLM Interaction & Prompt Engineering
  └── README.md