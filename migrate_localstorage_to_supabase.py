"""
migrate_localstorage_to_supabase.py
====================================

Migra o estado do CRM standalone (localStorage) para o Supabase.

Uso típico:

    1. No browser, abra o CRM antigo, abra o DevTools (F12), vá em Console e rode:
           copy(localStorage.getItem('ethos_crm_bh_2026_04_22'))
    2. Cole o JSON num arquivo (ex: localstorage_state.json).
    3. Rode:
           python migrate_localstorage_to_supabase.py --state localstorage_state.json

O script:
    - Lê o JSON do localStorage (formato: {"leads": {"<id>": {"status", "notes", "activity"}}, "theme": ...}).
    - Faz match com leads do Supabase via external_id (mesmo id local 1..N).
    - Atualiza status, notes, activity para os leads que foram trabalhados.
    - Não toca em leads que estão com status "novo" no localStorage (preserva o que veio do pipeline).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("[erro] python-dotenv nao instalado. Rode: pip install python-dotenv")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("[erro] requests nao instalado. Rode: pip install requests")
    sys.exit(1)


BASE = Path(__file__).parent


def carregar_env() -> dict:
    env_path = BASE / ".env"
    if not env_path.exists():
        print(f"[erro] .env nao encontrado em {env_path}")
        sys.exit(1)
    load_dotenv(env_path)
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    agencia = os.getenv("AGENCIA", "").strip()
    if not url or not key or not agencia:
        print("[erro] SUPABASE_URL, chave e AGENCIA obrigatorios no .env")
        sys.exit(1)
    return {"url": url, "key": key, "agencia": agencia}


def headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra localStorage do CRM standalone para o Supabase")
    parser.add_argument("--state", type=Path, required=True, help="Arquivo JSON exportado do localStorage")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem escrever")
    args = parser.parse_args()

    if not args.state.exists():
        print(f"[erro] arquivo nao encontrado: {args.state}")
        return 1

    cfg = carregar_env()
    print(f"[info] Agencia: {cfg['agencia']}")
    print(f"[info] Lendo estado de {args.state.name}")

    with args.state.open("r", encoding="utf-8") as fh:
        raw = fh.read().strip()
    # Pode vir como JSON wrapeado em aspas (se foi via copy())
    if raw.startswith('"') and raw.endswith('"'):
        raw = json.loads(raw)
    state = json.loads(raw) if isinstance(raw, str) else raw

    leads_state = state.get("leads", {})
    print(f"[info] {len(leads_state)} leads no localStorage")

    # Filtra apenas leads com trabalho real (status != novo OU notes OU activity)
    para_migrar = []
    for lid, info in leads_state.items():
        status = info.get("status", "novo")
        notes = info.get("notes", []) or []
        activity = info.get("activity", []) or []
        if status != "novo" or notes or activity:
            para_migrar.append({"external_id": str(lid), "status": status, "notes": notes, "activity": activity})

    print(f"[info] {len(para_migrar)} leads com trabalho a migrar (status, notas ou atividade)")

    if not para_migrar:
        print("[info] Nada a migrar. Encerrando.")
        return 0

    # Busca os UUIDs do Supabase via external_id
    print("[info] Buscando UUIDs no Supabase...")
    ext_ids = ",".join(f'"{p["external_id"]}"' for p in para_migrar)
    url = f"{cfg['url']}/rest/v1/leads"
    params = {
        "agencia": f"eq.{cfg['agencia']}",
        "external_id": f"in.({ext_ids})",
        "select": "id,external_id,status,notes,activity",
    }
    resp = requests.get(url, headers=headers(cfg["key"]), params=params, timeout=30)
    if resp.status_code != 200:
        print(f"[erro] HTTP {resp.status_code}: {resp.text[:200]}")
        return 1

    remotos = {r["external_id"]: r for r in resp.json()}
    print(f"[info] {len(remotos)} matches encontrados no Supabase")

    if args.dry_run:
        print("\n[dry-run] Diff que seria aplicado:")
        for p in para_migrar:
            r = remotos.get(p["external_id"])
            if r:
                print(f"  ext_id={p['external_id']}: {r['status']} -> {p['status']} (notes:{len(r['notes'])} -> {len(p['notes'])}, activity:{len(r['activity'])} -> {len(p['activity'])})")
            else:
                print(f"  ext_id={p['external_id']}: SEM MATCH no Supabase (ignorado)")
        return 0

    # Aplica updates
    ok = 0
    for p in para_migrar:
        r = remotos.get(p["external_id"])
        if not r:
            print(f"  [skip] ext_id={p['external_id']}: nao existe no Supabase")
            continue
        payload = {
            "status": p["status"],
            "notes": p["notes"],
            "activity": p["activity"],
        }
        # Se mudou pra fora de 'novo', limpa novo_nesta_rodada tambem
        if p["status"] != "novo":
            payload["novo_nesta_rodada"] = False
        resp = requests.patch(
            url,
            headers=headers(cfg["key"]),
            params={"id": f"eq.{r['id']}"},
            json=payload,
            timeout=30,
        )
        if resp.status_code in (200, 204):
            ok += 1
        else:
            print(f"  [erro] ext_id={p['external_id']}: HTTP {resp.status_code} {resp.text[:120]}")

    print(f"\n[ok] {ok}/{len(para_migrar)} leads migrados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
