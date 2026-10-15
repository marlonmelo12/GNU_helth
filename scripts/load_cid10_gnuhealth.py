"""
Script de Carga do Catálogo OMS CID-10 no ERP GNU Health HIS via Proteus (Tryton ORM).
Carrega os códigos da Classificação Internacional de Doenças (OMS)
a partir de config/dim_cid10_datasus.parquet diretamente através do modelo gnuhealth.pathology.

Respeita estritamente a Decisão D3: uso do ORM oficial Proteus em lotes de 500, idempotente.

Uso:
    python scripts/load_cid10_gnuhealth.py --dry-run
    python scripts/load_cid10_gnuhealth.py --apply
"""
import os
import sys
import argparse
import time
from typing import Optional, List, Dict, Any

try:
    from proteus import config, Model
except ImportError:
    config = None
    Model = None


def init_proteus_connection(connection_url: Optional[str] = None, config_file: Optional[str] = None):
    """Inicializa conexão com o GNU Health via Trytond direto ou XML-RPC."""
    if "mock" in (connection_url or "") or config is None or Model is None:
        print("[CID10_LOADER] Modo mock detectado ou Proteus não disponível. Ignorando conexão.")
        return None

    cfg_file = config_file or "/etc/trytond.conf"
    if os.path.exists(cfg_file):
        print(f"[CID10_LOADER] Conectando via Trytond direto ({cfg_file}, db: gnuhealth)...")
        return config.set_trytond('gnuhealth', config_file=cfg_file)
    else:
        url = connection_url or os.getenv("GNUHEALTH_URL", "http://admin:admin@localhost:8001/gnuhealth/")
        print(f"[CID10_LOADER] Conectando via XML-RPC ({url})...")
        return config.set_xmlrpc(url)


def load_cid10_proteus(
    parquet_path: str = "config/dim_cid10_datasus.parquet",
    batch_size: int = 500,
    apply_changes: bool = False,
    connection_url: Optional[str] = None,
    config_file: Optional[str] = None
) -> Dict[str, Any]:
    """Carrega patologias CID-10 no GNU Health via Proteus em lotes idempotentes."""
    if not os.path.exists(parquet_path):
        json_alt = parquet_path.replace(".parquet", ".json")
        if os.path.exists(json_alt):
            parquet_path = json_alt
        else:
            raise FileNotFoundError(f"Arquivo de catálogo não encontrado: {parquet_path}")

    init_proteus_connection(connection_url=connection_url, config_file=config_file)

    if Model is None:
        raise RuntimeError("Proteus Model não disponível.")

    Pathology = Model.get('gnuhealth.pathology')

    records = []
    if parquet_path.endswith(".json"):
        import json
        with open(parquet_path, "r", encoding="utf-8") as f:
            records = json.load(f)
    elif parquet_path.endswith(".csv"):
        import csv
        with open(parquet_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = [{"code": r.get("cid10_code") or r.get("code"), "name": r.get("disease_name") or r.get("name")} for r in reader]
    else:
        try:
            import duckdb
            con_duck = duckdb.connect()
            records = con_duck.execute(f"""
                SELECT DISTINCT
                    TRIM(cid10_code) AS code,
                    TRIM(disease_name) AS name
                FROM '{parquet_path}'
                WHERE cid10_code IS NOT NULL AND disease_name IS NOT NULL
                ORDER BY code
            """).df().to_dict(orient="records")
            con_duck.close()
        except ImportError:
            json_alt = parquet_path.replace(".parquet", ".json")
            if os.path.exists(json_alt):
                import json
                with open(json_alt, "r", encoding="utf-8") as f:
                    records = json.load(f)
            else:
                raise ImportError("DuckDB não disponível para ler .parquet. Utilize o arquivo .json correspondente.")

    total_codes = len(records)
    print(f"=== INICIANDO CARGA DO CATÁLOGO CID-10 OMS NO GNU HEALTH (PROTEUS) ===")
    print(f"Total de registros a processar: {total_codes}")
    print(f"Modo: {'APLICAÇÃO' if apply_changes else 'DRY-RUN / SIMULAÇÃO'}")
    print(f"Tamanho do lote: {batch_size}")

    t0 = time.time()
    total_created = 0
    total_skipped = 0

    for i in range(0, total_codes, batch_size):
        chunk = records[i:i + batch_size]
        chunk_codes = [str(r["code"])[:16] for r in chunk]

        # Busca idempotente por códigos existentes no lote
        existing_objs = Pathology.find([('code', 'in', chunk_codes)])
        existing_codes = {getattr(p, 'code', '') for p in existing_objs}

        to_create = []
        for r in chunk:
            code = str(r["code"])[:16]
            name = str(r["name"])[:255]
            if code in existing_codes:
                total_skipped += 1
                continue

            pathology = Pathology(code=code, name=name, active=True)
            to_create.append(pathology)

        if to_create:
            if apply_changes:
                # Salva em lote de no máximo 500
                Pathology.save(to_create)
                total_created += len(to_create)
                print(f"  [Lote {i // batch_size + 1}] Salvos {len(to_create)} novos registros via Proteus.")
            else:
                total_created += len(to_create)
                print(f"  [Dry-Run Lote {i // batch_size + 1}] {len(to_create)} códigos seriam criados.")
        else:
            print(f"  [Lote {i // batch_size + 1}] Todos os {len(chunk)} códigos já existem (idempotente).")

    elapsed = time.time() - t0
    status_str = "APLICADO" if apply_changes else "SIMULADO"
    print(f"\n=== CARGA CID-10 {status_str}: {total_created} criados, {total_skipped} já existentes em {elapsed:.2f}s ===")

    return {
        "status": "success",
        "total_codes": total_codes,
        "created": total_created,
        "skipped": total_skipped,
        "applied": apply_changes
    }


def main():
    parser = argparse.ArgumentParser(description="Carrega catálogo CID-10 OMS no GNU Health via Proteus")
    parser.add_argument("--apply", action="store_true", help="Efetiva a carga no banco")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem persistir")
    parser.add_argument("--batch-size", type=int, default=500, help="Tamanho do lote (default: 500)")
    parser.add_argument("--parquet", type=str, default="config/dim_cid10_datasus.parquet", help="Caminho do parquet CID-10")
    args = parser.parse_args()

    load_cid10_proteus(
        parquet_path=args.parquet,
        batch_size=args.batch_size,
        apply_changes=args.apply
    )


if __name__ == "__main__":
    main()
