#!/usr/bin/env python3
"""
Fase D: valida se os 50 numeros dos leads tem WhatsApp via Evolution API Contabo.
Usa SSH pra nao expor API externamente.
"""
import csv, json, os, sys, io, subprocess, re

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = r"G:\Meu Drive\Claude\workspace\entregas\leads-certificadoras-bh-2026-04-22"
CSV_IN = os.path.join(BASE, "leads_bh_merged.csv")
OUT = os.path.join(BASE, "wa_validado.json")

# Extrai numeros E.164 unicos dos 50 leads
numeros = []
seen = set()
with open(CSV_IN, "r", encoding="utf-8-sig") as fh:
    for i, row in enumerate(csv.DictReader(fh), 1):
        if i > 50: break
        wa = re.sub(r"\D", "", row.get("whatsapp") or "")
        if wa and wa not in seen:
            seen.add(wa)
            numeros.append({"id": i, "nome": row["nome"], "numero": wa})

print(f"Validando {len(numeros)} numeros via Evolution API (SSH Contabo)...")

# Monta payload JSON (so os numeros)
payload = {"numbers": [n["numero"] for n in numeros]}
payload_json = json.dumps(payload)

# SSH + curl
cmd = [
    "ssh", "contabo",
    f"curl -s -X POST 'http://localhost:8080/chat/whatsappNumbers/backup-whatsapp' "
    f"-H 'apikey: whatsapp-backup-2026' "
    f"-H 'Content-Type: application/json' "
    f"-d '{payload_json}'"
]

try:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"ERRO SSH: {r.stderr}")
        sys.exit(1)
    resp = json.loads(r.stdout)
except Exception as e:
    print(f"ERRO: {e}")
    print(f"STDOUT: {r.stdout[:500] if 'r' in dir() else 'N/A'}")
    sys.exit(1)

# Map resposta por numero
resp_by_num = {item["number"]: item for item in resp}

# Cruza com leads
resultado = []
for n in numeros:
    r = resp_by_num.get(n["numero"], {})
    exists = r.get("exists", False)
    resultado.append({
        "id": n["id"],
        "nome": n["nome"],
        "numero": n["numero"],
        "wa_ativo": exists,
        "wa_jid": r.get("jid"),
        "wa_name": r.get("name") or None,
    })

# Stats
ativos = sum(1 for r in resultado if r["wa_ativo"])
print(f"\n==========")
print(f"WhatsApp ATIVO: {ativos}/{len(resultado)}")
print(f"WhatsApp INATIVO: {len(resultado) - ativos}")

# Lista os ATIVOS
print("\nAtivos:")
for r in resultado:
    if r["wa_ativo"]:
        name = f' | "{r["wa_name"]}"' if r["wa_name"] else ""
        print(f"  [OK] {r['nome'][:45]:45s} | {r['numero']}{name}")

# Lista os INATIVOS
print("\nInativos (sem WA):")
for r in resultado:
    if not r["wa_ativo"]:
        print(f"  [--] {r['nome'][:45]:45s} | {r['numero']}")

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(resultado, fh, ensure_ascii=False, indent=2)
print(f"\nSalvo: {OUT}")
