# Deploying PromoSensei (free tier)

This guide walks you through deploying the live demo on the **fully free, no-credit-card** path:

| Layer | Service | Cost | Card required? |
|-------|---------|------|----------------|
| Frontend | [Vercel](https://vercel.com) hobby | Free | No |
| Backend | [Render](https://render.com) free web service | Free | No |
| Database | [Neon](https://neon.tech) free Postgres | Free (3 GB, 0.25 vCPU) | No |
| CI | GitHub Actions | Free for public repos | No |

Total time from zero to live URL: **~25 minutes**.

> **Free-tier caveat.** Render's free web service sleeps after 15 minutes of inactivity. The first request after sleep takes ~30 seconds (cold start) before the rest are sub-second. That's fine for a portfolio demo; the frontend shows a "backend may be waking up" message on connection failure. If you want zero cold starts, see *[Upgrading to Fly.io](#upgrading-to-flyio-no-cold-starts)* at the bottom.

---

## 0. Prerequisites

- A GitHub account.
- Git installed locally (`git --version`).
- This project on disk at `Resume Projects/PromoSensei/`.

If the project isn't already a git repo, initialise it:

```bash
cd "Resume Projects/PromoSensei"
git init
git add .
git commit -m "Initial commit — PromoSensei phases 1–4"
```

---

## 1. Push to GitHub (3 min)

1. Sign in to [github.com](https://github.com).
2. **+ → New repository** · name it `promosensei` · public · **don't** add a README/.gitignore (we have them).
3. Follow the "push existing repository" instructions GitHub shows you. They look like:

```bash
git remote add origin https://github.com/Goutam-A-B/promosensei.git
git branch -M main
git push -u origin main
```

4. Update the badge URL in [README.md](README.md) — replace `YOUR_GITHUB_USERNAME` with your actual handle, then `git commit -am "Update CI badge" && git push`.

---

## 2. Create the database on Neon (5 min)

1. Go to [neon.tech](https://neon.tech) → **Sign up with GitHub** (no card needed).
2. **Create a project**:
   - Name: `promosensei`
   - Region: pick the one closest to where most recruiters click from (Singapore for IN/SEA, US East for North America).
   - Postgres version: 16 (default).
3. On the project dashboard, copy the **connection string** under "Connection Details". It looks like:
   ```
   postgresql://user:password@ep-cool-name-12345.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
4. **Replace `postgresql://` with `postgresql+psycopg2://`** for SQLAlchemy:
   ```
   postgresql+psycopg2://user:password@ep-cool-name-12345.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```
   Save this — you'll paste it into Render in step 3.

> **Why psycopg2 specifically?** SQLAlchemy needs the dialect prefix to know which DB driver to use. Neon ships with `?sslmode=require` and that's already in the connection string.

---

## 3. Deploy the backend on Render (10 min)

1. Go to [render.com](https://render.com) → **Sign up with GitHub**.
2. **New → Blueprint** → connect the `promosensei` repo.
3. Render reads [`render.yaml`](render.yaml) and proposes one service: `promosensei-api`. Click **Apply**.
4. After the first deploy starts, open the service → **Environment** tab and add the two `sync: false` secrets:

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | The Neon connection string from step 2 |
   | `API_CORS_ORIGINS` | `["https://promosensei.vercel.app"]` *(replace with your real Vercel URL after step 4)* |

   The other env vars are baked into `render.yaml` — don't touch them unless you know why.
5. Wait for the first deploy to go green. You'll see a URL like `https://promosensei-api.onrender.com`.
6. **Verify the API is up:**

   ```bash
   curl https://promosensei-api.onrender.com/health
   # {"status":"ok"}
   ```

7. **Seed the database.** From the Render dashboard, open the service → **Shell** tab and run:

   ```bash
   python scripts/seed_demo.py --reset
   ```

   This creates the 120-product demo catalogue and builds the embedding index. Takes ~30 seconds. You'll see one log line per platform, then `Demo seed complete — 120 products ready.`

8. **Verify search works:**

   ```bash
   curl "https://promosensei-api.onrender.com/search?q=earbuds&mode=hybrid" | head -c 500
   ```

   You should get JSON with grouped products.

---

## 4. Deploy the frontend on Vercel (5 min)

1. Go to [vercel.com](https://vercel.com) → **Sign up with GitHub**.
2. **Add New → Project** → import the `promosensei` repo.
3. Vercel auto-detects Next.js. Set **Root Directory** to `phase4/frontend`. Leave everything else default.
4. Add one environment variable under **Environment Variables**:

   | Key | Value |
   |-----|-------|
   | `NEXT_PUBLIC_API_BASE_URL` | The Render URL from step 3, e.g. `https://promosensei-api.onrender.com` |

5. Click **Deploy**. First build takes 1–2 minutes.
6. You'll get a URL like `https://promosensei.vercel.app` (or `promosensei-yourname.vercel.app`).
7. **Update CORS on the backend.** Go back to Render → service → **Environment** → edit `API_CORS_ORIGINS` to:

   ```json
   ["https://promosensei.vercel.app"]
   ```

   Save. Render will redeploy in ~1 minute.

8. **Open your live URL** — you should see the search UI with the 120 demo products. Try the example query chips.

---

## 5. Update the README (2 min)

1. Edit the top of [README.md](README.md) — replace `_[deploy and add the URL here]_` with your live Vercel URL.
2. Replace `YOUR_GITHUB_USERNAME` in the CI badge (if you haven't already).
3. Commit & push:

   ```bash
   git commit -am "docs: add live demo URL"
   git push
   ```

---

## 6. (Recommended) Pin the resume

Add to your resume:

```
PromoSensei — promosensei.vercel.app  ·  github.com/Goutam-A-B/promosensei
Cross-platform deal aggregator across Amazon / Flipkart / Nykaa.
4-phase build: scraping → semantic search → matcher → cache+observability.
Stack: FastAPI · Next.js · Postgres · Docker · GitHub Actions · 181 tests.
```

---

## Troubleshooting

**The frontend says "Couldn't reach the API".**
The Render free service is asleep — wait ~30 seconds and refresh. If it persists, check the Render logs for a crash and verify `DATABASE_URL` is set.

**`/search` returns 0 results.**
You forgot to seed. Open Render Shell → `python scripts/seed_demo.py --reset`.

**CORS errors in the browser console.**
`API_CORS_ORIGINS` doesn't match your Vercel URL exactly. The value must be a JSON array string: `["https://promosensei.vercel.app"]` — note the brackets and quotes.

**CI is failing.**
Open the failed run in GitHub Actions. Most likely a fresh dependency mismatch — pin the version that broke and re-push.

**Render keeps waking up to nothing.**
The free tier sleeps after 15 min of inactivity. That's expected. If you want it always-on, keep reading.

---

## Upgrading to Fly.io (no cold starts)

If a recruiter hits a 30-second cold start on the Render free tier and bounces, that's bad. Fly.io's free allowance covers a single small machine that doesn't sleep, but it does require a credit card on file (you won't be charged within the allowance).

```bash
# From phase4/backend/
flyctl auth signup            # one-time
flyctl launch --no-deploy     # accepts the bundled fly.toml
flyctl secrets set \
    DATABASE_URL='postgresql+psycopg2://…neon…' \
    API_CORS_ORIGINS='["https://promosensei.vercel.app"]'
flyctl deploy
flyctl ssh console -C 'python scripts/seed_demo.py --reset'
```

Update `NEXT_PUBLIC_API_BASE_URL` on Vercel to your Fly URL (`https://promosensei-api.fly.dev`) and redeploy the frontend.

---

## Rolling forward

When you push to `main`:

- **GitHub Actions** runs `pytest -q` (181 tests including the eval-regression gate) and the frontend build.
- **Render** auto-deploys the backend on the next push.
- **Vercel** auto-deploys the frontend on the next push.

If the eval-regression gate fails, the merge is blocked — that's by design. Tighten or loosen `EVAL_MIN_NDCG_AT_5` / `EVAL_MIN_PRECISION_AT_3` in [phase4/backend/app/config.py](phase4/backend/app/config.py) if you change the ranker intentionally.
