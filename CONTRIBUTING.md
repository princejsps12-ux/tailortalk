# Contributing

## Local Setup

1. Fork the repo
2. Clone your fork
3. Create `.env` from `.env.example`
4. Add your `service_account.json`
5. Install dependencies
6. Run backend and frontend

## Project Structure

- `backend/` — FastAPI server + LangChain agent
- `frontend/` — Streamlit chat UI
- `assets/` — Images and demo GIF

## Making Changes

- Keep all secrets in `.env` — never hardcode
- Test backend with curl before touching frontend
- Run `TESTING.md` curl tests before submitting a PR
