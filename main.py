"""
Biblo Bookstore Finder — search API + web page.

Answers Biblo's core question: "which independent bookstores carry this book?"
by querying the analytics star schema (dim_bookstore + fact_inventory + dim_book)
that the data pipeline produces.

- GET /                -> the search page (HTML)
- GET /api/search?q=   -> JSON: books matching q + which stores carry them
- GET /health         -> health check (for the host)

The database connection is read from the DATABASE_URL env var, so the same app
runs against local Postgres or a hosted cloud Postgres (Neon/Supabase) without
code changes.
"""

from __future__ import annotations

import os

import psycopg
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

# Connection string. Locally points at the Dockerized Postgres; in the cloud,
# set DATABASE_URL to the hosted Postgres connection string.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://biblo:biblo@localhost:5433/biblo",
)

app = FastAPI(title="Biblo Bookstore Finder")


def search_books(q: str, limit: int = 30) -> list[dict]:
    """Find books matching q and the in-stock stores that carry them."""
    sql = """
        SELECT
            bk.title,
            bk.authors,
            s.store_name  AS bookstore,
            s.city,
            s.website,
            f.price_usd,
            f.quantity
        FROM analytics.fact_inventory f
        JOIN analytics.dim_bookstore s ON s.bookstore_id = f.bookstore_id
        JOIN analytics.dim_book     bk ON bk.book_id      = f.book_id
        WHERE bk.title ILIKE %s
          AND f.quantity > 0
        ORDER BY bk.title, f.price_usd
        LIMIT %s;
    """
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(sql, (f"%{q}%", limit))
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


@app.get("/health")
def health():
    try:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1, description="book title to search")):
    results = search_books(q)
    # group by book for a cleaner shape
    books: dict[str, dict] = {}
    for r in results:
        key = r["title"]
        books.setdefault(key, {"title": r["title"], "authors": r["authors"], "stores": []})
        books[key]["stores"].append({
            "bookstore": r["bookstore"],
            "city": r["city"],
            "website": r["website"],
            "price_usd": float(r["price_usd"]) if r["price_usd"] is not None else None,
            "quantity": r["quantity"],
        })
    return {"query": q, "count": len(books), "results": list(books.values())}


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML_PAGE


HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Biblo — Find a book at an indie bookstore</title>
<style>
  :root { --ink:#1a1a2e; --accent:#7c3aed; --muted:#6b7280; --line:#e5e7eb; --bg:#faf9fb; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin:0; background:var(--bg); color:var(--ink); }
  .wrap { max-width: 760px; margin: 0 auto; padding: 48px 20px 80px; }
  h1 { font-size: 1.9rem; margin: 0 0 6px; }
  .sub { color: var(--muted); margin: 0 0 28px; }
  .searchbar { display:flex; gap:10px; }
  input { flex:1; padding: 14px 16px; font-size: 1rem; border:1px solid var(--line);
          border-radius: 10px; outline:none; }
  input:focus { border-color: var(--accent); }
  button { padding: 14px 22px; font-size: 1rem; border:none; border-radius:10px;
           background: var(--accent); color:#fff; cursor:pointer; font-weight:600; }
  button:disabled { opacity:.6; cursor:default; }
  .hint { color:var(--muted); font-size:.85rem; margin-top:10px; }
  .book { background:#fff; border:1px solid var(--line); border-radius:12px;
          padding:18px 20px; margin-top:18px; }
  .book h3 { margin:0 0 2px; font-size:1.15rem; }
  .book .author { color:var(--muted); font-size:.9rem; margin-bottom:12px; }
  .store { display:flex; justify-content:space-between; align-items:center;
           padding:8px 0; border-top:1px solid var(--line); font-size:.95rem; }
  .store .name { font-weight:600; }
  .store .city { color:var(--muted); font-weight:400; font-size:.85rem; margin-left:6px; }
  .price { font-variant-numeric: tabular-nums; }
  .qty { color:var(--muted); font-size:.8rem; margin-left:10px; }
  .empty { color:var(--muted); margin-top:24px; }
  footer { margin-top:40px; color:var(--muted); font-size:.8rem; }
  a { color: var(--accent); }
</style>
</head>
<body>
<div class="wrap">
  <h1>📚 Find a book at an indie bookstore</h1>
  <p class="sub">Search a title and see which independent bookstores carry it, in stock.</p>

  <div class="searchbar">
    <input id="q" type="text" placeholder="e.g. Frankenstein, Dorian Gray, Shatter Me"
           autocomplete="off" />
    <button id="go">Search</button>
  </div>
  <div class="hint">Real NYC-area indie bookstores (OpenStreetMap) · book data from Open Library · inventory is simulated for the demo.</div>

  <div id="results"></div>

  <footer>
    Powered by the Biblo data pipeline — multi-source ingestion → PostgreSQL warehouse →
    dbt star schema + data-quality tests → Airflow.
  </footer>
</div>

<script>
const qEl = document.getElementById('q');
const goEl = document.getElementById('go');
const out = document.getElementById('results');

async function run() {
  const q = qEl.value.trim();
  if (!q) return;
  goEl.disabled = true; goEl.textContent = 'Searching…';
  out.innerHTML = '';
  try {
    const res = await fetch('/api/search?q=' + encodeURIComponent(q));
    const data = await res.json();
    if (!data.results.length) {
      out.innerHTML = '<div class="empty">No in-stock matches found. Try another title.</div>';
    } else {
      out.innerHTML = data.results.map(b => `
        <div class="book">
          <h3>${escapeHtml(b.title)}</h3>
          <div class="author">${b.authors ? escapeHtml(b.authors) : ''}</div>
          ${b.stores.map(s => `
            <div class="store">
              <div><span class="name">${escapeHtml(s.bookstore)}</span>
                   <span class="city">${s.city ? escapeHtml(s.city) : ''}</span></div>
              <div><span class="price">$${s.price_usd?.toFixed(2) ?? '—'}</span>
                   <span class="qty">${s.quantity} in stock</span></div>
            </div>`).join('')}
        </div>`).join('');
    }
  } catch (e) {
    out.innerHTML = '<div class="empty">Something went wrong. Please try again.</div>';
  } finally {
    goEl.disabled = false; goEl.textContent = 'Search';
  }
}
function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
goEl.addEventListener('click', run);
qEl.addEventListener('keydown', e => { if (e.key === 'Enter') run(); });
</script>
</body>
</html>
"""
