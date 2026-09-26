# Deploying CodeSentinel (free)

Backend → **Render** (free web service). Frontend → **Vercel** (free hobby plan). Both deploy from GitHub, so push the project to a GitHub repository first.

## 1. Push to GitHub

1. Create an empty repository on github.com (no README), e.g. `codesentinel`.
2. From the project folder:
   ```bash
   git add .
   git commit -m "CodeSentinel"
   git remote add origin https://github.com/<you>/codesentinel.git
   git push -u origin main
   ```
   `.env` files are git-ignored — your API key is not uploaded.

## 2. Backend on Render

1. Sign up at [render.com](https://render.com) with GitHub. No card is needed for the free plan.
2. **New → Blueprint**, pick your repository. Render reads [`render.yaml`](render.yaml).
3. When prompted for secret values:
   - `GEMINI_API_KEY` — your key.
   - `FRONTEND_ORIGINS` — leave as `https://placeholder.vercel.app` for now; you'll fix it in step 4.
4. Deploy. When it's live, open `https://<your-service>.onrender.com/api/health` — it should return `{"status":"ok",...}`.

## 3. Frontend on Vercel

1. Sign up at [vercel.com](https://vercel.com) with GitHub.
2. **Add New → Project**, import the repository.
3. Set **Root Directory** to `frontend`. Framework preset: Vite (detected automatically).
4. Add environment variables:
   - `VITE_API_URL` = `https://<your-service>.onrender.com/api`
   - `VITE_WS_URL` = `wss://<your-service>.onrender.com/ws` (note **wss**)
5. Deploy and copy the URL, e.g. `https://codesentinel.vercel.app`.

## 4. Connect them

In Render → your service → **Environment**, set `FRONTEND_ORIGINS` to your Vercel URL (no trailing slash) and save. Render redeploys.

## 5. Check the deployed version

Walk the full journey on the **deployed** site: Start a New Run → B1 → Run Agent → watch the Live Trace → View Fix → History.

## Free-tier behavior to know

- **Cold starts:** Render's free service sleeps after ~15 minutes idle; the first request takes ~50 seconds. Open `/api/health` a minute before a demo.
- **History resets:** the free service has no persistent disk, so SQLite history is wiped on redeploys and restarts. Fine for a demo; move to PostgreSQL for durable history.
- **Quota:** `MAX_RUNS_PER_DAY` (default 10 in `render.yaml`) stops a public link from exhausting the free Gemini quota.
- **One run at a time:** a second visitor gets "The agent is already working…" with a link to watch the current run.
