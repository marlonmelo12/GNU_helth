"""Gravacao e leitura de lotes (JSON Lines por entidade + manifest com contagens e SHA-256)."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, List

SCHEMA_VERSION = 2


def gravar(dir_lote: str, entidades: Dict[str, List[Dict]], meta: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(dir_lote, exist_ok=True)
    arquivos = {}
    for nome in sorted(entidades):
        caminho = os.path.join(dir_lote, f"{nome}.jsonl")
        h = hashlib.sha256()
        with open(caminho, "w", encoding="utf-8", newline="\n") as fh:
            for r in entidades[nome]:
                linha = json.dumps(r, ensure_ascii=False, sort_keys=True, default=str) + "\n"
                fh.write(linha)
                h.update(linha.encode("utf-8"))
        arquivos[nome] = {"arquivo": f"{nome}.jsonl", "registros": len(entidades[nome]), "sha256": h.hexdigest()}
    manifest = {"schema_version": SCHEMA_VERSION, **meta, "entidades": arquivos}
    with open(os.path.join(dir_lote, "manifest.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return manifest


def ler(dir_lote: str) -> Dict[str, Any]:
    """Le um lote v2 validando contagem e SHA-256 de cada arquivo contra o manifest."""
    with open(os.path.join(dir_lote, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    dados: Dict[str, Any] = {"manifest": manifest}
    for nome, info in manifest["entidades"].items():
        h = hashlib.sha256()
        linhas = []
        with open(os.path.join(dir_lote, info["arquivo"]), encoding="utf-8") as fh:
            for linha in fh:
                h.update(linha.encode("utf-8"))
                linhas.append(json.loads(linha))
        if len(linhas) != info["registros"] or h.hexdigest() != info["sha256"]:
            raise ValueError(f"Lote corrompido: {nome} (registros ou SHA-256 diferente do manifest).")
        dados[nome] = linhas
    return dados


def eh_v2(dir_lote: str) -> bool:
    return os.path.exists(os.path.join(dir_lote, "manifest.json"))
