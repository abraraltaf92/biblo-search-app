# Biblo Bookstore Finder — search app

A live search interface on top of the [Biblo data pipeline](https://github.com/abraraltaf92/biblo-data-pipeline).
Type a book title → see which independent bookstores carry it, in stock, with price.

- `GET /` — search page
- `GET /api/search?q=<title>` — JSON results
- `GET /health` — health check

## Run locally

```bash
pip install -r requirements.txt

# point at your local pipeline Postgres (the one from docker compose, port 5433)
export DATABASE_URL="postgresql://biblo:biblo@localhost:5433/biblo"

uvicorn main:app --reload --port 8000
# open http://localhost:8000
```

## Deploy so anyone can use it (free tiers)

The app needs (1) a hosted Postgres with your pipeline's `analytics` tables, and
(2) the app itself hosted. Airflow/the pipeline do NOT need to be deployed — the
app just reads the modeled data.

### 1. Free hosted Postgres — Neon

- Create a free project at [neon.tech](https://neon.tech), copy the connection string.

### 2. Load your data into it

```bash
# make sure your local pipeline has run (analytics tables exist)
export CLOUD_DB_URL="postgresql://...neon connection string..."
python load_to_cloud.py
```

### 3. Deploy the app — Render

- Push this folder to a GitHub repo.
- On [render.com](https://render.com): New → Web Service → connect the repo.
- It auto-detects `render.yaml`. In the dashboard, set the `DATABASE_URL`
  env var to your Neon connection string.
- Deploy → you get a public URL like `https://biblo-bookstore-finder.onrender.com`.

That URL is the live demo — anyone can open it and search.

## How it works

The app runs one query against the star schema the pipeline builds:
`fact_inventory` joined to `dim_bookstore` and `dim_book`, filtered to in-stock
rows and matched on title. Store locations and book data are real (OpenStreetMap,
Open Library); inventory is simulated for the demo.
