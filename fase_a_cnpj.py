#!/usr/bin/env python3
"""
Fase A: Scraping de CNPJ dos sites dos 50 leads.
Estrategia: GET site -> regex em rodape/about/contato pra \d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}.
Fallback: tenta paginas /contato, /sobre, /politica-privacidade, /termos.
Output: cnpj_encontrados.json
"""
import csv, json, os, re, sys, io, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import requests

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = r"G:\Meu Drive\Claude\workspace\entregas\leads-certificadoras-bh-2026-04-22"
CSV_IN = os.path.join(BASE, "leads_bh_merged.csv")
OUT = os.path.join(BASE, "cnpj_encontrados.json")

CNPJ_REGEX = re.compile(r"\b(\d{2})[\.\-]?(\d{3})[\.\-]?(\d{3})[\/\-]?(\d{4})[\-\.]?(\d{2})\b")
# Paginas onde costuma ter CNPJ
SUBPAGES = ["", "/contato", "/sobre", "/sobre-nos", "/quem-somos", "/politica-de-privacidade",
            "/politica-privacidade", "/termos", "/termos-de-uso", "/empresa"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

def normalize_cnpj(groups):
    return f"{groups[0]}.{groups[1]}.{groups[2]}/{groups[3]}-{groups[4]}"

def get_site_root(url):
    if not url: return None
    try:
        p = urlparse(url if url.startswith("http") else "http://" + url)
        return f"{p.scheme}://{p.netloc}"
    except:
        return None

def find_cnpj_in_text(text):
    for m in CNPJ_REGEX.finditer(text):
        cnpj = normalize_cnpj(m.groups())
        # valida minimamente (nao pode ser 00.000.000/0000-00)
        digits = re.sub(r"\D", "", cnpj)
        if len(set(digits)) > 1 and digits != "00000000000000":
            return cnpj
    return None

def scrape_site(lead):
    site = (lead.get("site") or "").strip()
    root = get_site_root(site)
    if not root:
        return {"id": lead["id"], "nome": lead["nome"], "site": site, "cnpj": None, "paginas_tentadas": [], "erro": "sem site"}

    paginas = []
    for sub in SUBPAGES:
        url = root + sub
        paginas.append(url)
        try:
            r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
            if r.status_code != 200:
                continue
            cnpj = find_cnpj_in_text(r.text)
            if cnpj:
                return {
                    "id": lead["id"], "nome": lead["nome"], "site": site,
                    "cnpj": cnpj, "pagina_origem": url, "paginas_tentadas": paginas,
                }
        except Exception as e:
            continue

    return {"id": lead["id"], "nome": lead["nome"], "site": site, "cnpj": None, "paginas_tentadas": paginas}

# Carrega leads
leads = []
with open(CSV_IN, "r", encoding="utf-8-sig") as fh:
    reader = csv.DictReader(fh)
    for i, row in enumerate(reader, 1):
        row["id"] = i
        leads.append(row)
leads = leads[:50]

print(f"Scrapeando CNPJ de {len(leads)} sites em paralelo (max 8 threads)...")
results = []
start = time.time()
with ThreadPoolExecutor(max_workers=8) as ex:
    futures = {ex.submit(scrape_site, lead): lead for lead in leads}
    for fut in as_completed(futures):
        r = fut.result()
        results.append(r)
        status = f"  [{r['id']:2d}] {r['nome'][:45]:45s} | "
        status += f"CNPJ {r['cnpj']}" if r.get("cnpj") else "—"
        print(status)

elapsed = time.time() - start
results.sort(key=lambda x: x["id"])

com_cnpj = [r for r in results if r.get("cnpj")]
print(f"\n==========")
print(f"Tempo: {elapsed:.1f}s")
print(f"CNPJs encontrados: {len(com_cnpj)}/{len(results)}")
print(f"CNPJs unicos: {len(set(r['cnpj'] for r in com_cnpj))}")

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(results, fh, ensure_ascii=False, indent=2)
print(f"Salvo: {OUT}")
