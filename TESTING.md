# Testing the API

## 1. Health Check

```bash
curl http://localhost:8000/health
```

Expected:

```json
{"status": "ok", "drive_connected": true, "message": "Drive API reachable"}
```

## 2. Basic Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "find all PDFs",
    "session_id": "test-session-1",
    "chat_history": []
  }'
```

## 3. Follow-up Query (Memory Test)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "now filter those by last week",
    "session_id": "test-session-1",
    "chat_history": []
  }'
```

Expected: agent remembers previous search context.

## 4. Typo Test

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "show me all spreadshet files",
    "session_id": "test-session-2",
    "chat_history": []
  }'
```

Expected: agent correctly searches for spreadsheets.

## 5. Clear Session

```bash
curl -X DELETE http://localhost:8000/chat/test-session-1
```
