# Security

## Sensitive Files
The following files must NEVER be committed to Git:
- `.env` — contains API keys
- `service_account.json` — contains Google credentials

Both are listed in `.gitignore` for protection.

## For Deployment
Instead of uploading files, use environment variables:
- Set `GEMINI_API_KEY` directly in Render dashboard
- Paste the full contents of `service_account.json` as the value of `GOOGLE_SERVICE_ACCOUNT_JSON` in Render dashboard
