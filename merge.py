#!/usr/bin/env python3
"""Merge + dedup dos CSVs do extrator GMN para prospeccao BH (Ethos)."""
import csv, glob, os, sys, io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SRC = r"G:\Meu Drive\Automações\agente-vendas-gmn\prospects"
DATE = "2026-04-22"
OUT_DIR = r"G:\Meu Drive\Claude\workspace\entregas\leads-certificadoras-bh-2026-04-22"

pattern = os.path.join(SRC, f"{DATE}_*.csv")
files = [f for f in glob.glob(pattern) if "_agente" not in f]
print(f"Lendo {len(files)} CSVs:")
for f in files:
    print(f"  {os.path.basename(f)}")

all_rows = []
seen_phone = set()
seen_name = set()
dup_count = 0

for f in sorted(files):
    origem = os.path.basename(f).replace(f"{DATE}_", "").replace(".csv", "")
    with open(f, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            # Campo whatsapp nesse CSV e o NUMERO E.164, nao status
            phone = (row.get("whatsapp") or "").strip()
            name_key = (row.get("nome") or "").strip().lower()
            if phone and phone in seen_phone:
                dup_count += 1
                continue
            if name_key and name_key in seen_name:
                dup_count += 1
                continue
            if phone:
                seen_phone.add(phone)
            if name_key:
                seen_name.add(name_key)
            row["query_origem"] = origem
            all_rows.append(row)

print(f"\nTotal unicos: {len(all_rows)} (duplicados removidos: {dup_count})")

# Estatisticas: celular=Sim e proxy de WhatsApp provavel
eh_celular = [r for r in all_rows if (r.get("celular") or "").strip().lower() == "sim"]
com_site = [r for r in all_rows if (r.get("site") or "").strip()]
cel_e_site = [r for r in all_rows if (r.get("celular") or "").strip().lower() == "sim" and (r.get("site") or "").strip()]

print(f"Celular (WhatsApp provavel): {len(eh_celular)}")
print(f"Com site: {len(com_site)}")
print(f"Celular E site: {len(cel_e_site)}")

# Remover repartições publicas, receita federal, prefeituras, orgaos publicos, lojas aleatorias
BLACKLIST_TERMS = [
    "repartição pública", "repartição publica",
    "receita federal", "prefeitura",
    "unidas sede", "offcomp",
    "tabelionato", "cartório",  # cartorios sao indiretos, pula por ora
]
NICHE_TERMS = [
    "certific", "cert ", "ecnpj", "e-cnpj", "e-cpf",
    "ecpf", "digital", "assinatura", "icp-brasil", "icpbrasil",
    "ar ", "criptocert", "ac3r", "soluti", "certisign",
    "safeweb", "valid", "serasa", "comprovei", "crea-se",
]
MG_DDDS = {"31", "32", "33", "34", "35", "37", "38"}
def is_valid(row):
    nome = (row.get("nome") or "").lower()
    cat = (row.get("categoria") or "").lower()
    endereco = (row.get("endereco") or "").upper()
    telefone = row.get("telefone") or ""
    for term in BLACKLIST_TERMS:
        if term in nome or term in cat:
            return False
    # Exige endereco em MG
    if " MG" not in endereco and "MINAS GERAIS" not in endereco:
        return False
    # Se tem telefone, DDD deve ser de MG (ou numero 0800/sem DDD claro)
    import re
    ddd_match = re.search(r"\((\d{2})\)", telefone)
    if ddd_match and ddd_match.group(1) not in MG_DDDS:
        return False
    return any(t in nome for t in NICHE_TERMS)

# Aceitar leads com celular OU com site (ter site eh indicador forte)
candidatos = [r for r in all_rows if (r.get("celular") or "").strip().lower() == "sim" or (r.get("site") or "").strip()]
filtrados = [r for r in candidatos if is_valid(r)]
print(f"Apos filtro de nicho: {len(filtrados)}")

# Ranquear: priorizar score desc + menor NRL (menor NRL = mais dor, mais oportunidade)
def rank_key(row):
    try:
        score = float(row.get("score") or 0)
    except: score = 0
    try:
        nrl = float(row.get("nrl") or 10)
    except: nrl = 10
    try:
        avals = int(row.get("avaliacoes") or 0)
    except: avals = 0
    # ordem: score desc, NRL asc (fragil/critica primeiro), avaliacoes desc
    return (-score, nrl, -avals)

filtrados.sort(key=rank_key)

# Top 50
TOP_N = 50
selecionados = filtrados[:TOP_N]

# Salvar CSV merged
out_csv = os.path.join(OUT_DIR, "leads_bh_merged.csv")
if selecionados:
    fieldnames = list(selecionados[0].keys())
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selecionados)
    print(f"\nCSV merged salvo: {out_csv}")
    print(f"Selecionados (top {len(selecionados)} de {len(filtrados)}):")
    for i, r in enumerate(selecionados[:60], 1):
        print(f"  {i:2d}. {r['nome'][:55]:55s} | score {r.get('score'):>3} | NRL {r.get('nrl'):>4} | {r.get('whatsapp_status')}")
