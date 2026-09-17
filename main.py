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
            s.latitude,
            s.longitude,
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
            "latitude": float(r["latitude"]) if r["latitude"] is not None else None,
            "longitude": float(r["longitude"]) if r["longitude"] is not None else None,
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
<title>Biblo — Find any book at an independent bookshop</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400&family=Newsreader:ital,opsz@0,6..72;1,6..72&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#f4efe6;      /* warm cream paper */
    --paper-2:#efe8db;
    --ink:#211d17;        /* near-black ink */
    --ink-soft:#6b6155;   /* faded ink */
    --rule:#d8cfbe;       /* hairline */
    --accent:#8a2b1e;     /* deep oxblood red */
    --accent-soft:#a5432f;
    --card:#fbf8f1;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;}
  body{
    background:var(--paper);
    color:var(--ink);
    font-family:"Newsreader", Georgia, serif;
    font-size:18px; line-height:1.6;
    -webkit-font-smoothing:antialiased;
  }
  ::selection{background:var(--accent); color:var(--paper);}
  a{color:var(--accent); text-decoration:none; border-bottom:1px solid rgba(138,43,30,.35);}
  a:hover{border-bottom-color:var(--accent);}
  .wrap{max-width:680px; margin:0 auto; padding:0 28px;}

  /* masthead */
  header{border-bottom:1px solid var(--rule); padding:26px 0;}
  .masthead{display:flex; align-items:baseline; justify-content:space-between;}
  .mark{font-family:"Fraunces", serif; font-weight:600; font-size:1.35rem; letter-spacing:.01em;}
  .mark em{font-style:italic; font-weight:400;}
  .kicker{font-size:.72rem; letter-spacing:.18em; text-transform:uppercase; color:var(--ink-soft);}

  /* hero */
  .hero{padding:60px 0 30px; text-align:center;}
  .hero .eyebrow{font-size:.74rem; letter-spacing:.22em; text-transform:uppercase;
                 color:var(--accent); margin-bottom:22px;}
  .hero h1{font-family:"Fraunces", serif; font-weight:500; font-size:clamp(2.1rem,6vw,3.1rem);
           line-height:1.08; letter-spacing:-.01em; margin:0 auto 20px; max-width:12ch;}
  .hero h1 em{font-style:italic;}
  .hero .dek{font-size:1.12rem; color:var(--ink-soft); max-width:46ch; margin:0 auto;
             font-style:italic;}

  /* search */
  .search{margin:38px 0 8px;}
  .field{display:flex; align-items:center; gap:0; border-bottom:2px solid var(--ink);
         padding-bottom:6px;}
  .field input{flex:1; border:none; background:transparent; outline:none;
               font-family:"Fraunces", serif; font-size:1.5rem; color:var(--ink);
               padding:8px 2px;}
  .field input::placeholder{color:#b3a892; font-style:italic;}
  .field button{border:none; background:transparent; cursor:pointer; color:var(--accent);
                font-family:"Fraunces", serif; font-size:1.05rem; font-weight:600;
                letter-spacing:.02em; padding:8px 4px;}
  .field button:disabled{opacity:.5; cursor:default;}
  .tries{margin-top:16px; color:var(--ink-soft); font-size:.92rem;}
  .tries a{cursor:pointer; margin-right:14px; font-style:italic; border:none;
           border-bottom:1px dotted var(--ink-soft); color:var(--ink);}
  .tries a:hover{color:var(--accent); border-bottom-color:var(--accent);}
  .tries .lbl{font-style:normal; margin-right:6px; letter-spacing:.02em;}

  /* results */
  .results{margin-top:40px;}
  .summary{font-style:italic; color:var(--ink-soft); border-top:1px solid var(--rule);
           border-bottom:1px solid var(--rule); padding:12px 0; margin-bottom:8px;
           font-size:.98rem;}
  .book{padding:26px 0; border-bottom:1px solid var(--rule);}
  .book h3{font-family:"Fraunces", serif; font-weight:500; font-size:1.5rem; margin:0 0 2px;
           line-height:1.2;}
  .book .byline{color:var(--ink-soft); font-style:italic; margin-bottom:16px; font-size:1rem;}
  .store{display:flex; align-items:baseline; gap:14px; padding:7px 0;}
  .store .dots{flex:1; border-bottom:1px dotted var(--rule); transform:translateY(-4px);}
  .store .name{font-weight:500; color:var(--ink); border-bottom:1px solid transparent;}
  a.name:hover{border-bottom-color:var(--accent); color:var(--accent);}
  a.name .pin{font-size:.72rem; color:var(--ink-soft); margin-left:6px; font-style:italic;}
  a.name:hover .pin{color:var(--accent);}
  .store .city{color:var(--ink-soft); font-style:italic; font-size:.9rem; margin-left:8px;}
  .store .price{font-family:"Fraunces", serif; font-weight:600; font-variant-numeric:tabular-nums;}
  .store .qty{color:var(--ink-soft); font-size:.82rem; margin-left:10px; font-style:italic;}
  .empty{text-align:center; font-style:italic; color:var(--ink-soft); padding:40px 0;}

  /* colophon */
  .colophon{margin:64px 0 20px; padding-top:30px; border-top:2px solid var(--ink);}
  .colophon h2{font-family:"Fraunces", serif; font-weight:500; font-size:1.15rem; margin:0 0 14px;}
  .colophon p{color:var(--ink-soft); font-size:.98rem; margin:0 0 14px;}
  .steps{font-size:.95rem; color:var(--ink); margin:0; padding:0; list-style:none;}
  .steps li{padding:8px 0; border-bottom:1px solid var(--rule); display:flex; gap:16px;}
  .steps li:last-child{border-bottom:none;}
  .steps .n{font-family:"Fraunces", serif; color:var(--accent); font-weight:600; min-width:1.4em;}
  .steps .s strong{font-weight:600;}
  .steps .s span{color:var(--ink-soft);}
  .disclaim{font-size:.85rem; font-style:italic; color:var(--ink-soft); margin-top:18px;}

  footer{padding:30px 0 70px; text-align:center; color:var(--ink-soft); font-size:.9rem;}
  footer .sep{margin:0 8px; color:var(--rule);}
</style>
</head>
<body>

  <header>
    <div class="wrap masthead">
      <div class="mark">Biblo<em>.</em></div>
      <div class="kicker">A bookshop finder</div>
    </div>
  </header>

  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">Support your local independent bookshop</div>
      <h1>Find any book at a bookshop <em>near you</em>.</h1>
      <p class="dek">Search a title and see which independent bookshops have it on their shelves — in stock, with prices — before you default to Amazon.</p>
    </section>

    <section class="search">
      <div class="field">
        <input id="q" type="text" placeholder="Type a title…" autocomplete="off" />
        <button id="go">Search &rsaquo;</button>
      </div>
      <div class="tries">
        <span class="lbl">Perhaps</span>
        <a data-q="Frankenstein">Frankenstein</a>
        <a data-q="Dorian Gray">The Picture of Dorian Gray</a>
        <a data-q="Shatter Me">Shatter Me</a>
      </div>
    </section>

    <section class="results" id="results"></section>

    <section class="colophon">
      <h2>A note on how this works</h2>
      <p>This is not a static page. Every search runs a live query against a data pipeline I built and run end to end — the kind of system that turns scattered, messy sources into a single trustworthy answer.</p>
      <ol class="steps">
        <li><span class="n">i.</span><span class="s"><strong>Ingest</strong> — <span>real bookshops from OpenStreetMap and books from Open Library, pulled through their APIs.</span></span></li>
        <li><span class="n">ii.</span><span class="s"><strong>Warehouse</strong> — <span>landed untouched in PostgreSQL, then modeled — all running in Docker.</span></span></li>
        <li><span class="n">iii.</span><span class="s"><strong>Transform</strong> — <span>shaped with dbt into a clean star schema, guarded by sixteen data-quality tests.</span></span></li>
        <li><span class="n">iv.</span><span class="s"><strong>Orchestrate</strong> — <span>the whole flow scheduled and monitored with Apache Airflow.</span></span></li>
      </ol>
      <p class="disclaim">Bookshop locations and book data are real. Inventory is simulated for this demonstration — in production it would come from each shop's point-of-sale system.</p>
    </section>

    <footer>
      Made by <a href="https://abraraltaflone.com" target="_blank">Abrar Altaf Lone</a>
      <span class="sep">·</span>
      <a href="https://github.com/abraraltaf92/biblo-data-pipeline" target="_blank">The pipeline, on GitHub</a>
      <span class="sep">·</span>
      <a href="https://www.linkedin.com/in/abraraltaf92" target="_blank">LinkedIn</a>
    </footer>
  </div>

<script>
const qEl=document.getElementById('q');
const goEl=document.getElementById('go');
const out=document.getElementById('results');

async function run(){
  const q=qEl.value.trim();
  if(!q) return;
  goEl.disabled=true; goEl.textContent='Searching…'; out.innerHTML='';
  try{
    const res=await fetch('/api/search?q='+encodeURIComponent(q));
    const data=await res.json();
    if(!data.results.length){
      out.innerHTML='<div class="empty">No shelves hold “'+escapeHtml(q)+'” right now. Try another title.</div>';
    }else{
      const total=data.results.reduce((n,b)=>n+b.stores.length,0);
      out.innerHTML='<div class="summary">'+data.results.length+' '+
        (data.results.length===1?'title':'titles')+' found · '+total+' in-stock listings across independent shops</div>'+
        data.results.map(b=>`
        <div class="book">
          <h3>${escapeHtml(b.title)}</h3>
          <div class="byline">${b.authors?'by '+escapeHtml(b.authors):''}</div>
          ${b.stores.map(s=>`
            <div class="store">
              ${mapLink(s)}
              <span class="dots"></span>
              <span><span class="price">$${s.price_usd?.toFixed(2)??'—'}</span><span class="qty">${s.quantity} in stock</span></span>
            </div>`).join('')}
        </div>`).join('');
    }
  }catch(e){
    out.innerHTML='<div class="empty">Something went awry. Please try again.</div>';
  }finally{
    goEl.disabled=false; goEl.innerHTML='Search &rsaquo;';
    out.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function mapLink(s){
  const name=escapeHtml(s.bookstore);
  const city=s.city?'<span class="city">'+escapeHtml(s.city)+'</span>':'';
  // Prefer exact coordinates (from the pipeline); fall back to name + city search.
  let url;
  if(s.latitude!=null && s.longitude!=null){
    url='https://www.google.com/maps?q='+s.latitude+','+s.longitude;
  }else{
    url='https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(s.bookstore+' '+(s.city||''));
  }
  return '<a class="name" href="'+url+'" target="_blank" rel="noopener">'+name+city+
         '<span class="pin">→ map</span></a>';
}
goEl.addEventListener('click',run);
qEl.addEventListener('keydown',e=>{if(e.key==='Enter')run();});
document.querySelectorAll('.tries a').forEach(a=>a.addEventListener('click',()=>{qEl.value=a.dataset.q; run();}));
</script>
</body>
</html>
"""
