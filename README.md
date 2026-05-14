# 🗂️ TailorTalk Drive Agent

> Your intelligent Google Drive file discovery assistant powered by Gemini AI

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.2-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.34-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Gemini](https://img.shields.io/badge/Gemini-1.5_Flash-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![Deployed on Render](https://img.shields.io/badge/Deployed_on-Render-46E3B7?logo=render&logoColor=white)](https://render.com/)

Find any file in your Drive by chatting in plain English. TailorTalk turns _"show me the spreadsheets I edited last week"_ into a real Google Drive query — and renders the results as a polished, card-based dark-themed UI.

---

## ✨ Features

- 🧠 **Natural-language search** — describe what you want, the agent builds the Drive `q` query for you
- 💬 **Conversational memory** — keeps context across turns within each session
- 🎯 **Folder-scoped access** — only sees the single Drive folder you grant
- 📁 **Rich file cards** — color-coded type badges, modified date, size, "Open in Drive" links
- 💡 **Smart follow-ups** — every reply ends with two suggested next searches
- 🕐 **Recent searches** — replay any of your last 5 queries in one click
- 🔌 **Live Drive status** — a pulsing dot in the sidebar tells you the API is healthy
- 🚦 **Rate limited & resilient** — 20 req/min/IP, friendly errors, agent never returns a 500

---

## 🏗️ Architecture

```
User → Streamlit Frontend
          ↓
      FastAPI Backend
          ↓
    LangChain Agent (Gemini 1.5 Flash)
          ↓
    DriveSearchTool
          ↓
  Google Drive API (Service Account)
          ↓
    Files Returned → Back to User
```

The agent owns the **natural-language → Drive `q`** translation. The backend wraps the Drive API behind a small `search_files(q)` function that always scopes results to the configured folder and trims responses to a clean shape the UI can render.

---

## 🌐 Live Demo

- Frontend: `https://tailortalk-frontend.onrender.com` _(placeholder — replace after deploying)_
- Backend health: `https://tailortalk-backend.onrender.com/health` _(placeholder)_

---

## 🎬 Demo

![TailorTalk Demo](assets/demo.gif)

### How to record your own demo GIF

1. Install [ScreenToGif](https://www.screentogif.com/) (Windows) or [Kap](https://getkap.co/) (Mac)
2. Run the project locally
3. Record these specific interactions in sequence:
   - Type: "find all PDFs" → show results appearing
   - Type: "now show only ones from this month" → show memory working
   - Click a suggestion chip → show it auto-searches
   - Click "Open in Drive →" on a file card
4. Keep GIF under 5 MB — reduce frame rate if needed (15 fps is fine)
5. Save as `assets/demo.gif`
6. It will automatically show in the README

---

## 💻 Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/yourname/tailortalk.git
cd tailortalk
```

### 2. Create `.env` from the template

```bash
cp .env.example .env
```

Fill in `GEMINI_API_KEY`, `DRIVE_FOLDER_ID`, and leave `GOOGLE_SERVICE_ACCOUNT_PATH=service_account.json` for local use.

### 3. Add your service account JSON

Drop the JSON key you downloaded from Google Cloud at the repo root and name it `service_account.json`. It's already covered by `.gitignore`, so you can't accidentally commit it.

### 4. Run the backend

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

Backend now serves on `http://localhost:8000`. Sanity check:

```bash
curl http://localhost:8000/health
```

### 5. Run the frontend (new terminal)

```bash
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

Streamlit prints a URL (usually `http://localhost:8501`). Open it and start chatting.

---

## 🚀 Deployment on Render

Both services are pre-declared in [`render.yaml`](./render.yaml). To deploy:

1. **Push to GitHub.** Render reads the blueprint from `render.yaml` on the default branch.
2. **Create a Blueprint.** In the Render dashboard → _New_ → _Blueprint_ → connect this repo. Render proposes two web services: `tailortalk-backend` and `tailortalk-frontend`.
3. **Set environment variables.** None of them sync from the blueprint (`sync: false`) — fill them in the dashboard:
   - **`tailortalk-backend`:**
     - `GEMINI_API_KEY` — your Google AI Studio key
     - `GOOGLE_SERVICE_ACCOUNT_JSON` — paste the **entire JSON contents** of `service_account.json`
     - `DRIVE_FOLDER_ID` — the folder you shared with the service account
   - **`tailortalk-frontend`:**
     - `BACKEND_URL` — the public URL of the backend service (e.g. `https://tailortalk-backend.onrender.com`)
4. **Apply.** Render builds both services. First boot takes ~3–5 minutes.

> ⚠️ Never commit `service_account.json` or `.env`. The `GOOGLE_SERVICE_ACCOUNT_JSON` env var carries the credentials at runtime — that's the deployment-safe path.

---

## 🔑 Getting API Keys

### Gemini API key

1. Open [Google AI Studio → API keys](https://aistudio.google.com/app/apikey)
2. Click **Create API key**
3. Copy the key and paste it into `.env` as `GEMINI_API_KEY`

### Google Drive Service Account

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or pick an existing one)
3. Enable the **Google Drive API** for that project
4. Navigate to _APIs & Services_ → _Credentials_ → **Create credentials** → **Service account**
5. After creation, open the service account → **Keys** tab → **Add key** → **Create new key** → **JSON**
6. Save the downloaded file as `service_account.json` at the repo root

### Sharing a Drive folder with the service account

The agent only sees files inside one folder, and only after you share that folder with the service account.

1. Copy the service account email (it looks like `tailortalk-bot@your-project.iam.gserviceaccount.com`)
2. In Google Drive, right-click the folder you want indexed → **Share**
3. Paste the service account email, grant **Viewer**, and send
4. Copy the folder ID from the URL — `drive.google.com/drive/folders/<FOLDER_ID>` — and paste it into `.env` as `DRIVE_FOLDER_ID`

---

## 🧠 How It Works

The agent's system prompt embeds a strict set of **QUERY BUILDING RULES**. When the user types a request, the agent emits a Drive `q` parameter string and calls `DriveSearchTool(q)`, which forwards it to `search_files`.

**Example translation:**

> **User:** "find financial reports from last month"

The agent reasons:

1. `"financial reports"` → `name contains 'financial'`
2. `"last month"` → `modifiedTime > '2025-04-01T00:00:00'`
3. Combine with `and`

**Drive query actually sent:**

```
name contains 'financial' and modifiedTime > '2025-04-01T00:00:00'
```

The backend automatically appends `'<DRIVE_FOLDER_ID>' in parents and trashed = false` so the search stays scoped. Drive returns up to 10 most-recently-modified files, the agent writes a one-sentence summary plus 2 follow-up suggestions, and the frontend renders the result as a card grid.

---

## 📸 Screenshots

_Add screenshots here once the app is deployed._

- **Chat view** — first search with file card grid
- **Sidebar** — pulsing Drive status, recent searches, example prompts
- **Empty state** — emoji art with two suggestion chips
- **File card hover** — outlined "Open in Drive" turns filled accent blue

---

## 🛠️ Tech Stack

| Layer        | Tech                                              |
| ------------ | ------------------------------------------------- |
| Frontend     | Streamlit 1.34, custom CSS, Inter font            |
| Backend      | FastAPI 0.111, Uvicorn                            |
| Agent        | LangChain 0.2 + `langchain-google-genai`          |
| LLM          | Google Gemini 1.5 Flash                           |
| Drive access | `google-api-python-client` + Service Account      |
| Memory       | In-process per-session, 1-hour TTL, auto-cleanup  |
| Rate limit   | slowapi (20 req/min/IP)                           |
| Hosting      | Render (web service × 2, blueprint-driven)        |

---

## 📄 License

[MIT](./LICENSE) — do whatever you want, just don't blame me.
