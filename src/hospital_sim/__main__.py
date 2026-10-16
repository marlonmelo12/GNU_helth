"""
CLI do hospital simulado v2.

  python -m src.hospital_sim gerar --perfil config/hospital_profiles/hrn_sobral.yaml \
      --inicio 2026-05-01 --fim 2026-05-31 --semente 42 --saida data/lotes_v2/hrn_202605
  python -m src.hospital_sim verificar --lote data/lotes_v2/hrn_202605
  python -m src.hospital_sim verificar --lote data/synthetic_output/batch_fase_b_v1   # lote v1

Codigo de saida: 0 = lote aprovado em todas as invariantes; 1 = reprovado.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta

from . import __version__
from . import lote as lote_io
from .assistencial import Assistencial
from .escala import Plantao, furos_execucao, gerar_quadro, planejar, realizar
from .estoque import Estoque
from .invariantes import verificar
from .perfil import RAIZ, carregar_perfil


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _recortar(assist: Assistencial, inicio: date) -> None:
    """Remove o aquecimento: fica o que acontece no periodo + internacoes em curso no seu inicio."""
    corte = datetime(inicio.year, inicio.month, inicio.day).isoformat()
    o = assist.out
    def fim_int(i):
        return i["data_desfecho"] or "9999"
    o["internacoes"] = [i for i in o["internacoes"] if fim_int(i) >= corte]
    ids_int = {i["id"] for i in o["internacoes"]}
    o["movimentacoes_leito"] = [m for m in o["movimentacoes_leito"] if m["internacao_id"] in ids_int and (m["fim"] or "9999") >= corte]
    o["cirurgias"] = [c for c in o["cirurgias"] if c["inicio"] >= corte]
    o["prescricoes"] = [p for p in o["prescricoes"] if p["data_hora"] >= corte]
    ids_presc = {p["id"] for p in o["prescricoes"]}
    o["itens_prescricao"] = [i for i in o["itens_prescricao"] if i["prescricao_id"] in ids_presc]
    o["exames"] = [e for e in o["exames"] if e["data_hora"] >= corte]
    o["prescricoes_nao_realizadas"] = [p for p in o["prescricoes_nao_realizadas"] if p["data"] >= corte[:10]]
    ps_int = {i["atendimento_ps_id"] for i in o["internacoes"] if i["atendimento_ps_id"]}
    o["atendimentos_ps"] = [a for a in o["atendimentos_ps"] if a["chegada"] >= corte or a["id"] in ps_int]
    usados = ({i["paciente_id"] for i in o["internacoes"]} | {a["paciente_id"] for a in o["atendimentos_ps"]})
    o["pacientes"] = [p for p in o["pacientes"] if p["id"] in usados]
    refs = {i["id"] for i in o["itens_prescricao"]} | {c["id"] for c in o["cirurgias"]}
    assist.demanda = [d for d in assist.demanda if d["quando"].isoformat() >= corte and d["referencia"] in refs]


def gerar(perfil_path: str, inicio: date, fim: date, semente: int, saida: str, escala_porte=None,
          aquecimento_dias: int = 45) -> dict:
    t0 = time.time()
    perfil = carregar_perfil(perfil_path, escala_porte)
    sub = lambda k: random.Random(semente * 1000 + k)  # fluxos independentes e reprodutiveis
    # Aquecimento: o hospital ja esta ocupado no primeiro dia do periodo (nao comeca vazio)
    sim_ini = inicio - timedelta(days=aquecimento_dias)
    quadro = gerar_quadro(perfil, sub(1), inicio, fim)
    planejada, furos_plan = planejar(perfil, quadro, sim_ini, fim, semente)
    realizada = realizar(perfil, quadro, planejada, sub(2))
    furos_exec = furos_execucao(perfil, realizada, inicio, fim)
    assist = Assistencial(perfil, Plantao(realizada), quadro, sub(3))
    assist.simular(sim_ini, fim)
    _recortar(assist, inicio)
    corte = inicio.isoformat()
    # mantem o plantao noturno que comecou na vespera e termina dentro do periodo
    planejada = [r for r in planejada if r["fim"] > corte]
    realizada = [r for r in realizada if r["fim"] > corte]
    furos_plan = [f for f in furos_plan if f["data"] >= corte]
    est = Estoque(perfil, sub(4), inicio, fim)
    est.simular(assist.demanda)
    setores = []
    requisitos = []
    for s in perfil.setores:
        setores.append({"codigo": s.codigo, "nome": s.nome, "tipo": s.tipo, "leitos": s.leitos, "salas": s.salas,
                        "publico": s.publico, "cuidado": s.cuidado, "especialidades": s.especialidades,
                        "farmacia": s.farmacia, "parametro_sem_fonte": s.parametro, "cnes_codleito_referencia": s.cnes_codleito})
        if any(s.medicos_turno.values()):
            requisitos.append({"setor": s.codigo, "papel": "MEDICO", "dia": s.medicos_turno.get("dia", 0), "noite": s.medicos_turno.get("noite", 0)})
        if s.enfermeiros_turno:
            requisitos.append({"setor": s.codigo, "papel": "ENFERMEIRO", "dia": s.enfermeiros_turno, "noite": s.enfermeiros_turno})
        if s.tecnicos_turno:
            requisitos.append({"setor": s.codigo, "papel": "TECNICO_ENFERMAGEM", "dia": s.tecnicos_turno, "noite": s.tecnicos_turno})
    leitos = [{"leito": l, "setor": sc, "extra": False} for sc, ls in assist.leitos.leitos.items() for l in ls]
    leitos += [{"leito": l, "setor": sc, "extra": True} for sc, ls in assist.leitos.extras.items() for l in ls]
    entidades = {
        "setores": setores, "leitos": leitos, "requisitos_escala": requisitos,
        "locais_estoque": perfil.estoque["locais"],
        "profissionais": quadro, "escala_planejada": planejada, "escala_realizada": realizada,
        "furos_cobertura": furos_plan + furos_exec,
        **{k: v for k, v in assist.out.items()},
        **{k: v for k, v in est.out.items()},
    }
    cal = perfil.calibracao["internacoes"]
    fator = perfil.bruto["escala_porte"]
    meses = [f"{m:02d}" for m in range(1, 13)]
    alvo_mes = sum(v for k, v in cal["por_competencia"].items()) / len(cal["por_competencia"]) * fator
    calib_path = os.path.join(RAIZ, perfil.hospital["calibracao"])
    meta = {
        "gerador": f"hospital_sim {__version__}", "semente": semente,
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "hospital": {**perfil.hospital, "escala_porte": fator,
                     "leitos_total": sum(s.leitos for s in perfil.setores_internacao)},
        "perfil": {"arquivo": os.path.relpath(perfil_path, RAIZ), "sha256": _sha(perfil_path)},
        "calibracao": {"arquivo": perfil.hospital["calibracao"], "sha256": _sha(calib_path),
                       "cnes_referencia": perfil.calibracao.get("cnes_referencia")},
        "regimes": perfil.escala["regimes"],
        "alvos_calibracao": {"internacoes_mes": round(alvo_mes, 1), "obito_pct": cal["obito_pct"],
                             "media_permanencia_dias": cal["media_permanencia_dias"], "uti_pct": cal["uti_pct"]},
        "aquecimento_dias": aquecimento_dias,
        "is_synthetic": True,
        "duracao_segundos": round(time.time() - t0, 1),
    }
    return lote_io.gravar(saida, entidades, meta)


def _relatorio(res, destino: str) -> None:
    with open(os.path.join(destino, "relatorio_invariantes.json"), "w", encoding="utf-8") as fh:
        json.dump(res.resumo(), fh, ensure_ascii=False, indent=2, default=str)
    linhas = [f"# Invariantes do lote: {'APROVADO' if res.aprovado else 'REPROVADO'}", "",
              "| Codigo | Grupo | Regra | Status | Ocorrencias |", "|---|---|---|---|---|"]
    for c in res.checks:
        linhas.append(f"| {c['codigo']} | {c['grupo']} | {c['descricao']} | {c['status']} | {c['ocorrencias']} |")
    for c in res.checks:
        if c["status"] != "OK" and c["exemplos"]:
            linhas += ["", f"**{c['codigo']}** exemplos: " + "; ".join(map(str, c["exemplos"]))]
    with open(os.path.join(destino, "relatorio_invariantes.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(linhas) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hospital_sim", description=__doc__.splitlines()[1])
    sp = ap.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("gerar")
    g.add_argument("--perfil", default="config/hospital_profiles/hrn_sobral.yaml")
    g.add_argument("--inicio", required=True)
    g.add_argument("--fim", required=True)
    g.add_argument("--semente", type=int, default=42)
    g.add_argument("--escala-porte", type=float, default=None)
    g.add_argument("--aquecimento-dias", type=int, default=45)
    g.add_argument("--saida", required=True)
    v = sp.add_parser("verificar")
    v.add_argument("--lote", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "gerar":
        ini, fim = date.fromisoformat(a.inicio), date.fromisoformat(a.fim)
        if fim < ini:
            ap.error("--fim anterior a --inicio")
        man = gerar(a.perfil, ini, fim, a.semente, a.saida, a.escala_porte, a.aquecimento_dias)
        print(json.dumps({k: v["registros"] for k, v in man["entidades"].items()}, ensure_ascii=False))
        print(f"gerado em {man['duracao_segundos']} s -> {a.saida}")
        destino = a.saida
    else:
        destino = a.lote
    res = verificar(destino)
    if lote_io.eh_v2(destino):  # nao grava relatorio dentro de lotes v1 versionados
        _relatorio(res, destino)
    print(json.dumps({"aprovado": res.aprovado, "falhas": [c["codigo"] for c in res.checks if c["status"] != "OK"]}))
    return 0 if res.aprovado else 1


if __name__ == "__main__":
    sys.exit(main())
