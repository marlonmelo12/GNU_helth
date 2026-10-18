"""
Gerador v2 (src/hospital_sim): reprodutibilidade, invariantes e deteccao de defeitos.
Roda no container `hospital-sim` (ortools); sem ERP e sem rede.
"""
import json
import os
from datetime import date

import pytest

pytest.importorskip("ortools")

from src.hospital_sim import lote as lote_io  # noqa: E402
from src.hospital_sim.__main__ import gerar  # noqa: E402
from src.hospital_sim.invariantes import verificar, verificar_v2  # noqa: E402

PERFIL = "config/hospital_profiles/hrn_sobral.yaml"
V1 = "data/synthetic_output/batch_fase_b_v1"


@pytest.fixture(scope="module")
def lote(tmp_path_factory):
    d = tmp_path_factory.mktemp("lote")
    man = gerar(PERFIL, date(2026, 5, 1), date(2026, 5, 4), 7, str(d / "a"), escala_porte=0.4, aquecimento_dias=10)
    return str(d / "a"), man


def test_lote_pequeno_passa_em_todas_as_invariantes(lote):
    res = verificar(lote[0])
    assert res.aprovado, [c for c in res.checks if c["status"] != "OK"]


def test_mesma_semente_gera_o_mesmo_lote(lote, tmp_path):
    man2 = gerar(PERFIL, date(2026, 5, 1), date(2026, 5, 4), 7, str(tmp_path / "b"), escala_porte=0.4, aquecimento_dias=10)
    assert {k: v["sha256"] for k, v in man2["entidades"].items()} == {k: v["sha256"] for k, v in lote[1]["entidades"].items()}


def test_lote_tem_todos_os_fluxos(lote):
    n = {k: v["registros"] for k, v in lote[1]["entidades"].items()}
    for k in ("profissionais", "escala_planejada", "escala_realizada", "pacientes", "internacoes", "prescricoes",
              "movimentos_estoque", "lotes", "itens"):
        assert n.get(k, 0) > 0, k
    tipos = {m["tipo"] for m in lote_io.ler(lote[0])["movimentos_estoque"]}
    assert {"INVENTARIO_INICIAL", "DISPENSACAO", "TRANSFERENCIA"} <= tipos


def test_adulteracao_de_saldo_e_detectada(lote):
    d = lote_io.ler(lote[0])
    d["saldos_finais"][0]["quantidade"] += 1
    assert "E5" in verificar_v2(d).resumo()["falhas"]


def test_evento_apos_obito_e_detectado(lote):
    d = lote_io.ler(lote[0])
    alvo = d["internacoes"][0]
    alvo["desfecho"], alvo["data_desfecho"] = "OBITO", "2026-04-01T00:00:00"
    assert "C1" in verificar_v2(d).resumo()["falhas"]


def test_lote_corrompido_e_recusado(lote, tmp_path):
    import shutil
    dst = tmp_path / "c"
    shutil.copytree(lote[0], dst)
    with open(dst / "internacoes.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "INVENTADA"}) + "\n")
    with pytest.raises(ValueError, match="corrompido"):
        lote_io.ler(str(dst))


@pytest.mark.skipif(not os.path.isdir(V1), reason="lote v1 nao presente")
def test_lote_v1_e_reprovado_pelos_defeitos_do_diagnostico():
    res = verificar(V1)
    falhas = set(res.resumo()["falhas"])
    assert not res.aprovado
    # estoque sem lote/entradas/prescricao, escala que nao cobre o periodo e UTI subdimensionada,
    # atendimentos apos obito e CID incompativel com idade
    assert {"E2", "E6", "E7", "R6", "R8", "C1", "C3"} <= falhas


def test_sazonalidade_de_ausencias_multiplica_faltas_e_atestados_do_mes():
    import random
    from datetime import datetime, timedelta
    from src.hospital_sim.escala import gerar_quadro, realizar
    from src.hospital_sim.perfil import carregar_perfil

    perfil = carregar_perfil(PERFIL, 0.4)
    quadro = gerar_quadro(perfil, random.Random(1), date(2026, 5, 1), date(2026, 5, 31))
    enf = [p for p in quadro if p["categoria"] == "ENFERMEIRO"][:40]
    planejada = []
    for i in range(1200):  # turnos de 12 h espacados por profissional (descanso respeitado)
        p = enf[i % len(enf)]
        ini = datetime(2026, 5, 1, 7) + timedelta(days=(i // len(enf)) % 30, hours=12 * ((i // len(enf)) // 30))
        planejada.append({"id": f"P{i}", "profissional_id": p["id"], "data": ini.date().isoformat(),
                          "inicio": ini.isoformat(), "fim": (ini + timedelta(hours=12)).isoformat(),
                          "setor": p["lotacao"], "papel": "ENFERMEIRO", "turno": "D"})

    def ausencias(saz):
        perfil.bruto["escala"]["sazonalidade_ausencia"] = saz
        r = realizar(perfil, quadro, planejada, random.Random(2))
        return sum(x["situacao"] in ("FALTA", "ATESTADO") for x in r)

    base = ausencias({})
    assert ausencias({"06": 3.0}) == base  # fator de outro mes nao muda maio
    assert ausencias({"05": 3.0}) > 2 * base
