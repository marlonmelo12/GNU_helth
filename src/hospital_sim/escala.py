"""
Quadro de pessoal e escalas (planejada por otimizacao + realizada com faltas, trocas e horas extras).

Planejada: OR-Tools CP-SAT, um modelo por mes e por grupo (enfermagem por setor; medicos em
conjunto), com 1 worker e limite de tempo deterministico -> mesma semente, mesma escala.
Restricoes: cobertura minima (com furo explicito quando faltar gente), habilitacao, regime
(12x36 ou plantao), descanso, teto mensal, ferias. Realizada: eventos sorteados por semente.
"""
from __future__ import annotations

import bisect
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from .perfil import Perfil
from .referencia import CBO_ESPECIALIDADE, FAMILIA_CBO, NOMES_F, NOMES_M, SOBRENOMES

TURNOS = (("D", 7), ("N", 19))  # inicio as 07h e as 19h, 12 h cada


def _slot_inicio(d0: date, t: int) -> datetime:
    d = d0 + timedelta(days=t // 2)
    return datetime(d.year, d.month, d.day, TURNOS[t % 2][1])


def _nome(rng: random.Random, fem: bool) -> str:
    return f"{rng.choice(NOMES_F if fem else NOMES_M)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}"


# --------------------------------------------------------------------------- quadro
def gerar_quadro(perfil: Perfil, rng: random.Random, inicio: date, fim: date) -> List[Dict]:
    """Profissionais a partir do CNES-PF agregado (contagem e horas por CBO), na escala de porte."""
    fator = perfil.bruto["escala_porte"]
    pf = perfil.calibracao.get("profissionais", {}).get("por_cbo", [])
    if not pf:
        raise ValueError("Calibracao sem CNES-PF: impossivel montar o quadro de pessoal.")
    regimes = perfil.escala["regime_por_categoria"]
    out: List[Dict] = []
    seq = 0
    for row in pf:
        cat = FAMILIA_CBO.get(str(row["cbo"])[:4])
        if not cat:
            continue
        # Em porte reduzido, o quadro acompanha os turnos exigidos (que tem minimos por setor e nao
        # escalam linearmente com os leitos), mantendo a razao pessoas/turno do hospital de referencia.
        ref = perfil.exigencia_referencia.get(cat) or 0
        prop = (perfil.exigencia.get(cat, 0) / ref) if ref else fator
        n = round(row["profissionais"] * (fator if fator == 1.0 else prop))
        horas = None
        if row.get("horas_hosp_semana") is not None and row["profissionais"]:
            horas = ((row["horas_hosp_semana"] or 0) + (row["horas_amb_semana"] or 0)
                     + (row["horas_outras_semana"] or 0)) / row["profissionais"]
        horas = horas if horas and horas > 0 else {"MEDICO": 24, "ENFERMEIRO": 36, "TECNICO_ENFERMAGEM": 40}[cat]
        esp = CBO_ESPECIALIDADE.get(str(row["cbo"]), "OUTRA") if cat == "MEDICO" else None
        for _ in range(n):
            seq += 1
            fem = rng.random() < (0.85 if cat != "MEDICO" else 0.45)
            # Ferias: bloco de 30 dias com inicio uniforme no ano corrente
            ini_f = date(inicio.year, 1, 1) + timedelta(days=rng.randrange(0, 365))
            prefixo = {"MEDICO": "Dr(a).", "ENFERMEIRO": "Enf.", "TECNICO_ENFERMAGEM": "Téc."}[cat]
            out.append({
                "id": f"PROF{seq:05d}", "nome": f"{prefixo} {_nome(rng, fem)}", "sexo": "F" if fem else "M",
                "categoria": cat, "cbo": str(row["cbo"]), "especialidade": esp,
                "conselho": "CRM" if cat == "MEDICO" else "COREN",
                "registro_conselho": f"SIM-{rng.randrange(10000, 99999)}-CE",  # sintetico por design
                "regime": regimes[cat],
                "horas_semana_contrato": round(horas, 1),
                "ferias_inicio": ini_f.isoformat(),
                "ferias_fim": (ini_f + timedelta(days=perfil.escala["ferias_dias_ano"] - 1)).isoformat(),
                "lotacao": None, "is_synthetic": True,
            })
    return out


def _em_ferias(p: Dict, d: date) -> bool:
    return p["ferias_inicio"] <= d.isoformat() <= p["ferias_fim"]


def _alvo_turnos(p: Dict, regime: Dict, dias: int) -> int:
    alvo = round(p["horas_semana_contrato"] * dias / 7.0 / regime["turno_horas"])
    return max(0, min(alvo, round(regime["max_turnos_mes"] * dias / 30.0)))


def lotar_enfermagem(perfil: Perfil, quadro: List[Dict], dias_mes: int = 30) -> Dict[Tuple[str, str], List[Dict]]:
    """Lotacao fixa por setor, proporcional a necessidade; excedente fica nao assistencial."""
    pools: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    regimes = perfil.escala["regimes"]
    for papel, campo in (("ENFERMEIRO", "enfermeiros_turno"), ("TECNICO_ENFERMAGEM", "tecnicos_turno")):
        pessoas = [p for p in quadro if p["categoria"] == papel]
        if not pessoas:
            continue
        cap_media = sum(_alvo_turnos(p, regimes[p["regime"]], dias_mes) for p in pessoas) / len(pessoas)
        necessidade = {s.codigo: getattr(s, campo) * 2 * dias_mes for s in perfil.setores if getattr(s, campo)}
        # pessoas necessarias por setor + indice de seguranca tecnica (ferias e ausencias)
        ist = float(perfil.escala.get("indice_seguranca_tecnica", 0.20))
        alvo = {k: math.ceil(v / max(cap_media, 1) * (1 + ist)) for k, v in necessidade.items()}
        total = sum(alvo.values())
        if total > len(pessoas):  # falta gente: reparte proporcionalmente (furos aparecerao)
            alvo = {k: math.floor(v * len(pessoas) / total) for k, v in alvo.items()}
        i = 0
        for setor, n in sorted(alvo.items()):
            for p in pessoas[i:i + n]:
                p["lotacao"] = setor
                pools[(setor, papel)].append(p)
            i += n
        for p in pessoas[i:]:
            p["lotacao"] = "NAO_ASSISTENCIAL"
    for p in quadro:
        if p["categoria"] == "MEDICO":
            p["lotacao"] = "CORPO_CLINICO" if p["especialidade"] != "OUTRA" else "NAO_ESCALADO"
    return pools


# --------------------------------------------------------------------------- planejamento (CP-SAT)
def _resolver_mes(pessoas: List[Dict], setores_req: Dict[str, List[int]], elegivel, custo_secundario,
                  regimes: Dict, d0: date, dias: int, historico: Dict[str, List[int]], segundos: float,
                  semente: int) -> Tuple[Dict[Tuple[str, str], List[int]], Dict[Tuple[str, int], int]]:
    """Retorna atribuicoes {(pessoa, setor): [slots]} e furos {(setor, slot): deficit}."""
    m = cp_model.CpModel()
    T = 2 * dias
    x: Dict[Tuple[int, str, int], cp_model.IntVar] = {}
    y: Dict[Tuple[int, int], List] = defaultdict(list)
    custo = []
    for i, p in enumerate(pessoas):
        for s in setores_req:
            if not elegivel(p, s):
                continue
            for t in range(T):
                if _em_ferias(p, d0 + timedelta(days=t // 2)):
                    continue
                v = m.NewBoolVar("")
                x[(i, s, t)] = v
                y[(i, t)].append(v)
                c = custo_secundario(p, s)
                if c:
                    custo.append(c * v)
    furo = {}
    for s, req in setores_req.items():
        for t in range(T):
            r = req[t % 2]
            if r <= 0:
                continue
            f = m.NewIntVar(0, r, "")
            furo[(s, t)] = f
            m.Add(sum(x[(i, s, t)] for i in range(len(pessoas)) if (i, s, t) in x) + f >= r)
    desvios = []
    for i, p in enumerate(pessoas):
        reg = regimes[p["regime"]]
        tot = []
        prev = historico.get(p["id"], [])  # ultimos slots trabalhados no mes anterior (negativos)
        def ocup(t):
            if t < 0:
                return 1 if t in prev else 0
            return sum(y.get((i, t), [])) if y.get((i, t)) else 0
        for t in range(T):
            if y.get((i, t)):
                m.Add(sum(y[(i, t)]) <= 1)
                tot.extend(y[(i, t)])
        for t in range(-3, T):
            # 12 h de trabalho + 36 h de descanso = no maximo 1 turno a cada 4 slots de 12 h
            janela = [ocup(t + k) for k in range(4)] if reg["descanso_min_horas"] >= 36 else [ocup(t), ocup(t + 1)]
            exprs = [e for e in janela if not isinstance(e, int)]
            const = sum(e for e in janela if isinstance(e, int))
            if not exprs:
                continue
            if reg["descanso_min_horas"] >= 36:
                m.Add(sum(exprs) + const <= 1)  # 12 h de trabalho -> 36 h de descanso
            else:
                # plantao: permite D+N no mesmo dia (24 h); proibe N seguido de D (0 h de descanso)
                if (t % 2 == 1) or not reg.get("permite_24h"):
                    m.Add(sum(exprs) + const <= 1)
        if tot:
            alvo = _alvo_turnos(p, reg, dias)
            m.Add(sum(tot) <= max(alvo, round(reg["max_turnos_mes"] * dias / 30.0)))
            dv = m.NewIntVar(0, T, "")
            m.Add(dv >= alvo - sum(tot))
            m.Add(dv >= sum(tot) - alvo)
            desvios.append(dv)
    m.Minimize(1000 * sum(furo.values()) + 5 * sum(desvios) + sum(custo))
    # Partida a quente: a solucao gulosa (viavel pelas mesmas regras) vira dica do CP-SAT,
    # que so pode melhora-la dentro do tempo deterministico.
    g_atrib, g_furos = _guloso(pessoas, setores_req, elegivel, regimes, d0, dias, historico)
    g_set = {(pid, s, tt) for (pid, s), ts in g_atrib.items() for tt in ts}
    ids = [p["id"] for p in pessoas]
    for (i, s, tt), v in x.items():
        m.AddHint(v, 1 if (ids[i], s, tt) in g_set else 0)
    for (s, tt), f in furo.items():
        m.AddHint(f, g_furos.get((s, tt), 0))
    st = cp_model.UNKNOWN
    for tentativa in range(2):
        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1
        solver.parameters.random_seed = semente
        solver.parameters.max_deterministic_time = segundos * (1 + 2 * tentativa)
        st = solver.Solve(m)
        if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        import sys
        print(f"[escala] CP-SAT sem solucao em {d0:%Y-%m} ({len(pessoas)} pessoas, setores {sorted(setores_req)}); "
              f"mantida a solucao gulosa", file=sys.stderr)
        return g_atrib, g_furos
    atrib: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for (i, s, t), v in x.items():
        if solver.Value(v):
            atrib[(pessoas[i]["id"], s)].append(t)
    furos = {k: solver.Value(v) for k, v in furo.items() if solver.Value(v) > 0}
    return atrib, furos


def _guloso(pessoas, setores_req, elegivel, regimes, d0, dias, historico):
    """Preenche slot a slot com quem esta descansado, habilitado e mais longe da meta mensal."""
    T = 2 * dias
    trab: Dict[str, List[int]] = {p["id"]: sorted(historico.get(p["id"], [])) for p in pessoas}
    cont: Dict[str, int] = defaultdict(int)
    alvo = {p["id"]: _alvo_turnos(p, regimes[p["regime"]], dias) for p in pessoas}
    teto = {p["id"]: max(alvo[p["id"]], round(regimes[p["regime"]]["max_turnos_mes"] * dias / 30.0)) for p in pessoas}
    atrib: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    furos: Dict[Tuple[str, int], int] = {}

    def pode(p, t):
        reg = regimes[p["regime"]]
        if _em_ferias(p, d0 + timedelta(days=t // 2)) or cont[p["id"]] >= teto[p["id"]]:
            return False
        for u in trab[p["id"]][-3:]:
            if reg["descanso_min_horas"] >= 36:
                if t - u < 4:
                    return False
            else:
                if u == t or (u == t - 1 and (u % 2 == 1 or not reg.get("permite_24h"))):
                    return False
                if u == t - 1 and len(trab[p["id"]]) >= 2 and trab[p["id"]][-2] == t - 2:
                    return False  # no maximo 24 h continuas
        return True

    for t in range(T):
        for s in sorted(setores_req):
            r = setores_req[s][t % 2]
            if r <= 0:
                continue
            cand = sorted((p for p in pessoas if elegivel(p, s) and pode(p, t)),
                          key=lambda p: (cont[p["id"]] - alvo[p["id"]], p["id"]))
            for p in cand[:r]:
                atrib[(p["id"], s)].append(t)
                trab[p["id"]].append(t)
                cont[p["id"]] += 1
            if len(cand) < r:
                furos[(s, t)] = r - len(cand)
    return atrib, furos


def _meses(inicio: date, fim: date):
    d = date(inicio.year, inicio.month, 1)
    while d <= fim:
        prox = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        yield max(d, inicio), min(prox - timedelta(days=1), fim)
        d = prox


def planejar(perfil: Perfil, quadro: List[Dict], inicio: date, fim: date, semente: int):
    regimes = perfil.escala["regimes"]
    seg = float(perfil.escala.get("solver_segundos_por_pool", 20))
    pools = lotar_enfermagem(perfil, quadro)
    medicos = [p for p in quadro if p["lotacao"] == "CORPO_CLINICO"]
    req_med = {s.codigo: [s.medicos_turno.get("dia", 0), s.medicos_turno.get("noite", 0)]
               for s in perfil.setores if any(s.medicos_turno.values())}
    esp_setor = {s.codigo: s.especialidades for s in perfil.setores}

    def eleg_med(p, s):
        return p["especialidade"] in esp_setor[s]

    def custo_med(p, s):
        return 0 if esp_setor[s] and p["especialidade"] == esp_setor[s][0] else 2

    planejada: List[Dict] = []
    furos: List[Dict] = []
    hist: Dict[str, List[int]] = {}
    seq = 0
    for a, b in _meses(inicio, fim):
        dias = (b - a).days + 1
        grupos = [("MEDICO", medicos, req_med, eleg_med, custo_med)]
        for (setor, papel), pessoas in sorted(pools.items()):
            s = perfil.setor(setor)
            r = s.enfermeiros_turno if papel == "ENFERMEIRO" else s.tecnicos_turno
            grupos.append((papel, pessoas, {setor: [r, r]}, lambda p, s_: True, lambda p, s_: 0))
        novo_hist: Dict[str, List[int]] = {}
        for papel, pessoas, req, eleg, custo in grupos:
            if not pessoas:
                for s_, r in req.items():
                    for t in range(2 * dias):
                        if r[t % 2]:
                            furos.append(_furo(s_, a, t, papel, r[t % 2], 0, "PLANEJAMENTO"))
                continue
            atrib, f = _resolver_mes(pessoas, req, eleg, custo, regimes, a, dias, hist, seg, semente)
            for (pid, setor), slots in sorted(atrib.items()):
                for t in sorted(slots):
                    seq += 1
                    ini = _slot_inicio(a, t)
                    planejada.append({"id": f"ESCP{seq:07d}", "profissional_id": pid, "setor": setor, "papel": papel,
                                      "data": ini.date().isoformat(), "turno": TURNOS[t % 2][0],
                                      "inicio": ini.isoformat(), "fim": (ini + timedelta(hours=12)).isoformat()})
                    if t >= 2 * dias - 4:
                        novo_hist.setdefault(pid, []).append(t - 2 * dias)
            for (setor, t), deficit in sorted(f.items()):
                r = req[setor][t % 2]
                furos.append(_furo(setor, a, t, papel, r, r - deficit, "PLANEJAMENTO"))
        hist = novo_hist
    return planejada, furos


def _furo(setor: str, d0: date, t: int, papel: str, exigido: int, presente: int, origem: str) -> Dict:
    ini = _slot_inicio(d0, t)
    return {"setor": setor, "data": ini.date().isoformat(), "turno": TURNOS[t % 2][0], "inicio": ini.isoformat(),
            "papel": papel, "exigido": exigido, "presente": presente, "deficit": exigido - presente, "origem": origem}


# --------------------------------------------------------------------------- execucao
def realizar(perfil: Perfil, quadro: List[Dict], planejada: List[Dict], rng: random.Random):
    """Escala realizada: faltas, atestados, trocas, horas extras e registro de ponto."""
    e = perfil.escala
    por_id = {p["id"]: p for p in quadro}
    trabalhos: Dict[str, List[Tuple[datetime, datetime]]] = defaultdict(list)  # intervalos realizados
    for r in planejada:
        trabalhos[r["profissional_id"]].append((datetime.fromisoformat(r["inicio"]), datetime.fromisoformat(r["fim"])))
    for v in trabalhos.values():
        v.sort()
    turnos_mes: Dict[Tuple[str, str], int] = defaultdict(int)
    for r in planejada:
        turnos_mes[(r["profissional_id"], r["data"][:7])] += 1

    def livre(pid: str, ini: datetime, fim: datetime) -> bool:
        lst = trabalhos[pid]
        k = bisect.bisect_left(lst, (ini, fim))
        antes = lst[k - 1] if k > 0 else None
        depois = lst[k] if k < len(lst) else None
        if antes and antes[1] > ini - timedelta(hours=11):
            return False
        if depois and depois[0] < fim + timedelta(hours=11):
            return False
        return True

    # candidatos por (setor, papel): mesma lotacao (enfermagem) ou especialidade habilitada (medicos)
    esp_setor = {s.codigo: s.especialidades for s in perfil.setores}
    def candidatos(setor, papel):
        if papel == "MEDICO":
            return [p for p in quadro if p["lotacao"] == "CORPO_CLINICO" and p["especialidade"] in esp_setor[setor]]
        return [p for p in quadro if p["lotacao"] == setor and p["categoria"] == papel]
    cache: Dict[Tuple[str, str], List[Dict]] = {}

    realizada: List[Dict] = []
    seq = 0
    atestado_ate: Dict[str, datetime] = {}

    def ponto(ini: datetime, fim: datetime):
        atraso = rng.randint(15, 40) if rng.random() < e["prob_atraso_relevante"] else rng.randint(-10, 8)
        return (ini + timedelta(minutes=atraso)).isoformat(), (fim + timedelta(minutes=rng.randint(-5, 25))).isoformat()

    for r in sorted(planejada, key=lambda z: (z["inicio"], z["setor"], z["papel"], z["profissional_id"])):
        ini, fim = datetime.fromisoformat(r["inicio"]), datetime.fromisoformat(r["fim"])
        pid = r["profissional_id"]
        u = rng.random()
        # sazonalidade: multiplicador do mes do turno sobre faltas e atestados (sem o parametro, 1.0)
        fator = float(e.get("sazonalidade_ausencia", {}).get(r["data"][5:7], 1.0))
        p_falta, p_atestado = e["prob_falta"] * fator, e["prob_atestado"] * fator
        situacao = "CUMPRIDO"
        if pid in atestado_ate and ini < atestado_ate[pid]:
            situacao = "ATESTADO"
        elif u < p_falta:
            situacao = "FALTA"
        elif u < p_falta + p_atestado:
            situacao = "ATESTADO"
            atestado_ate[pid] = ini + timedelta(days=rng.randint(1, 3))
        seq += 1
        base = {"id": f"ESCR{seq:07d}", "planejada_id": r["id"], "profissional_id": pid, "setor": r["setor"],
                "papel": r["papel"], "inicio": r["inicio"], "fim": r["fim"], "substitui_profissional_id": None}
        if situacao == "CUMPRIDO" and rng.random() < e["prob_troca"]:
            # troca entre pares: outro profissional assume; o titular folga (ambos registrados)
            key = (r["setor"], r["papel"])
            cache.setdefault(key, candidatos(*key))
            opcoes = [c for c in cache[key] if c["id"] != pid and not _em_ferias(c, ini.date()) and livre(c["id"], ini, fim)]
            if opcoes:
                c = rng.choice(opcoes)
                trabalhos[pid].remove((ini, fim))
                bisect.insort(trabalhos[c["id"]], (ini, fim))
                realizada.append({**base, "situacao": "TROCA_CEDIDA", "ponto_entrada": None, "ponto_saida": None})
                seq += 1
                pe, ps = ponto(ini, fim)
                realizada.append({**base, "id": f"ESCR{seq:07d}", "profissional_id": c["id"], "situacao": "TROCA_ASSUMIDA",
                                  "substitui_profissional_id": pid, "ponto_entrada": pe, "ponto_saida": ps})
                continue
        if situacao == "CUMPRIDO":
            pe, ps = ponto(ini, fim)
            realizada.append({**base, "situacao": situacao, "ponto_entrada": pe, "ponto_saida": ps})
            continue
        # ausencia: libera o intervalo e tenta cobrir com hora extra de alguem habilitado e descansado
        trabalhos[pid].remove((ini, fim))
        realizada.append({**base, "situacao": situacao, "ponto_entrada": None, "ponto_saida": None})
        key = (r["setor"], r["papel"])
        cache.setdefault(key, candidatos(*key))
        mes = r["data"][:7]
        opcoes = [c for c in cache[key] if c["id"] != pid and not _em_ferias(c, ini.date()) and livre(c["id"], ini, fim)
                  and turnos_mes[(c["id"], mes)] < perfil.escala["regimes"][c["regime"]]["max_turnos_mes"] + 2]
        if opcoes and rng.random() < 0.75:
            c = rng.choice(opcoes)
            bisect.insort(trabalhos[c["id"]], (ini, fim))
            turnos_mes[(c["id"], mes)] += 1
            seq += 1
            pe, ps = ponto(ini, fim)
            realizada.append({**base, "id": f"ESCR{seq:07d}", "planejada_id": None, "profissional_id": c["id"],
                              "situacao": "HORA_EXTRA", "substitui_profissional_id": pid, "ponto_entrada": pe, "ponto_saida": ps})
    return realizada


PRESENTE = ("CUMPRIDO", "TROCA_ASSUMIDA", "HORA_EXTRA")


def furos_execucao(perfil: Perfil, realizada: List[Dict], inicio: date, fim: date) -> List[Dict]:
    """Deficit de cobertura observado na escala realizada, por setor, turno e papel."""
    exig: Dict[Tuple[str, str], List[int]] = {}
    for s in perfil.setores:
        if any(s.medicos_turno.values()):
            exig[(s.codigo, "MEDICO")] = [s.medicos_turno.get("dia", 0), s.medicos_turno.get("noite", 0)]
        if s.enfermeiros_turno:
            exig[(s.codigo, "ENFERMEIRO")] = [s.enfermeiros_turno] * 2
        if s.tecnicos_turno:
            exig[(s.codigo, "TECNICO_ENFERMAGEM")] = [s.tecnicos_turno] * 2
    pres: Dict[Tuple[str, str, str], int] = defaultdict(int)
    for r in realizada:
        if r["situacao"] in PRESENTE:
            pres[(r["setor"], r["papel"], r["inicio"])] += 1
    out = []
    for t in range(2 * ((fim - inicio).days + 1)):
        ini = _slot_inicio(inicio, t).isoformat()
        for (setor, papel), req in exig.items():
            r = req[t % 2]
            p = pres[(setor, papel, ini)]
            if r and p < r:
                out.append(_furo(setor, inicio, t, papel, r, p, "EXECUCAO"))
    return out


class Plantao:
    """Consulta de quem esta efetivamente de plantao (escala realizada) num setor e instante."""

    def __init__(self, realizada: List[Dict]):
        self._idx: Dict[Tuple[str, str, str], List[str]] = defaultdict(list)
        for r in realizada:
            if r["situacao"] in PRESENTE:
                self._idx[(r["setor"], r["papel"], r["inicio"])].append(r["profissional_id"])

    def de_plantao(self, setor: str, papel: str, quando: datetime) -> List[str]:
        h = 7 if 7 <= quando.hour < 19 else 19
        d = quando.date() if quando.hour >= 7 else quando.date() - timedelta(days=1)
        return self._idx.get((setor, papel, datetime(d.year, d.month, d.day, h).isoformat()), [])
