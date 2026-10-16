"""
Invariantes de lote: um lote so pode ir para o ERP se TODAS passarem.

Le lotes v2 (manifest + JSON Lines) e tambem lotes v1 (JSON do gerador antigo), para provar
que as regras detectam os defeitos conhecidos. Estrutura ausente conta como falha.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from . import lote as lote_io
from .referencia import cid_compativel

PRESENTE = ("CUMPRIDO", "TROCA_ASSUMIDA", "HORA_EXTRA")


class Resultado:
    def __init__(self):
        self.checks: List[Dict[str, Any]] = []

    def add(self, codigo: str, grupo: str, descricao: str, falhas: List[Any], aplicavel: bool = True, info: Any = None):
        ok = aplicavel and not falhas
        self.checks.append({"codigo": codigo, "grupo": grupo, "descricao": descricao,
                            "status": "OK" if ok else ("ESTRUTURA_AUSENTE" if not aplicavel else "FALHA"),
                            "ocorrencias": len(falhas), "exemplos": falhas[:5], "info": info})

    @property
    def aprovado(self) -> bool:
        return all(c["status"] == "OK" for c in self.checks)

    def resumo(self) -> Dict[str, Any]:
        return {"aprovado": self.aprovado, "total": len(self.checks),
                "falhas": [c["codigo"] for c in self.checks if c["status"] != "OK"], "checks": self.checks}


def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


# ============================================================================ v2
def verificar_v2(d: Dict[str, Any], perfil=None) -> Resultado:
    r = Resultado()
    man = d["manifest"]
    ini = date.fromisoformat(man["periodo"]["inicio"])
    fim = date.fromisoformat(man["periodo"]["fim"])
    fim_dt = datetime(fim.year, fim.month, fim.day) + timedelta(days=1)

    # ------------------------------------------------------------ ESTOQUE
    lotes = {l["lote"]: l for l in d.get("lotes", [])}
    movs = sorted(d.get("movimentos_estoque", []), key=lambda m: (m["data_hora"], m["id"]))
    saldo = defaultdict(lambda: defaultdict(int))  # (local, item) -> {lote: qtd}
    neg, vencido, sem_lote, fefo = [], [], [], []
    internos = {"ALMOX", "FARM_CENTRAL", "FARM_UTI", "FARM_CC"}
    for m in movs:
        if m["lote"] not in lotes:
            sem_lote.append(m["id"]); continue
        val = lotes[m["lote"]]["validade"]
        hoje = m["data_hora"][:10]
        if m["tipo"] in ("DISPENSACAO", "TRANSFERENCIA") and hoje > val:
            vencido.append(m["id"])
        if m["origem"] in internos:
            bolso = saldo[(m["origem"], m["item"])]
            if m["tipo"] == "DISPENSACAO":
                # FEFO: nenhum outro lote do item no local com validade anterior, saldo positivo e nao vencido
                if any(q > 0 and lt != m["lote"] and hoje <= lotes[lt]["validade"] < val for lt, q in bolso.items()):
                    fefo.append(m["id"])
            bolso[m["lote"]] -= m["quantidade"]
            if bolso[m["lote"]] < 0:
                neg.append(m["id"])
        if m["destino"] in internos:
            saldo[(m["destino"], m["item"])][m["lote"]] += m["quantidade"]
    r.add("E1", "estoque", "Saldo por item, lote e local nunca negativo (replay do livro-razao)", neg, bool(movs))
    r.add("E2", "estoque", "Todo movimento referencia um lote cadastrado", sem_lote, bool(movs))
    r.add("E3", "estoque", "Nenhuma saida de lote vencido", vencido, bool(movs))
    r.add("E4", "estoque", "Dispensacao respeita FEFO (vence primeiro, sai primeiro)", fefo, bool(movs))
    finais = {(s["local"], s["item"], s["lote"]): s["quantidade"] for s in d.get("saldos_finais", [])}
    calc = {(loc, it, lt): q for (loc, it), b in saldo.items() for lt, q in b.items() if q != 0}
    dif = [f"{k}: replay={calc.get(k, 0)} informado={finais.get(k, 0)}" for k in set(calc) | set(finais) if calc.get(k, 0) != finais.get(k, 0)]
    r.add("E5", "estoque", "Saldo final informado = soma dos movimentos", dif, bool(movs))
    pedidos = {p["id"]: p for p in d.get("pedidos_compra", [])}
    rec_ruim = [x["id"] for x in d.get("recebimentos", [])
                if x["pedido_id"] not in pedidos or x["data_hora"][:10] <= pedidos[x["pedido_id"]]["data_hora"][:10]]
    tem_entrada = any(m["tipo"] == "RECEBIMENTO" for m in movs)
    longo = (fim - ini).days >= 20
    r.add("E6", "estoque", "Recebimentos ligados a pedido e posteriores a ele; ha compras no periodo",
          rec_ruim + ([] if tem_entrada or not longo else ["nenhum RECEBIMENTO em periodo >= 20 dias"]), bool(movs))
    itens_presc = {i["id"]: i for i in d.get("itens_prescricao", [])}
    cirurgias = {c["id"]: c for c in d.get("cirurgias", [])}
    internacoes = {i["id"]: i for i in d.get("internacoes", [])}
    sem_causa, fora_int = [], []
    for m in movs:
        if m["tipo"] != "DISPENSACAO":
            continue
        ref = m.get("referencia")
        if ref not in itens_presc and ref not in cirurgias:
            sem_causa.append(m["id"]); continue
        it = internacoes.get(m.get("internacao_id"))
        if not it or not it["data_admissao"]:
            fora_int.append(m["id"]); continue
        fim_int = _dt(it["data_alta"]) or fim_dt
        if not (_dt(it["data_admissao"]) <= _dt(m["data_hora"]) <= fim_int + timedelta(hours=3)):
            fora_int.append(m["id"])
    r.add("E7", "estoque", "Toda dispensacao tem prescricao ou cirurgia de origem", sem_causa, bool(movs))
    r.add("E8", "estoque", "Dispensacao ocorre durante a internacao do paciente", fora_int, bool(movs))
    disp_ref = defaultdict(int)
    for m in movs:
        if m["tipo"] == "DISPENSACAO":
            disp_ref[(m["referencia"], m["origem"])] += m["quantidade"]
    rup = [x["id"] for x in d.get("rupturas", []) if disp_ref[(x["referencia"], x["local"])] < x["atendido"]]
    r.add("E9", "estoque", "Ruptura registrada bate com o que foi efetivamente dispensado", rup, bool(movs))

    # ------------------------------------------------------------ ESCALA
    plan = d.get("escala_planejada", [])
    real = d.get("escala_realizada", [])
    prof = {p["id"]: p for p in d.get("profissionais", [])}
    reg = (man.get("regimes") or {})
    por_prof = defaultdict(list)
    for x in real:
        if x["situacao"] in PRESENTE:
            por_prof[x["profissional_id"]].append((_dt(x["inicio"]), _dt(x["fim"]), x["id"]))
    sobre, descanso = [], []
    for pid, lst in por_prof.items():
        lst.sort()
        for a, b in zip(lst, lst[1:]):
            if b[0] < a[1]:
                sobre.append(f"{pid} {a[2]} x {b[2]}")
        # turnos encostados formam um bloco continuo (plantao de 24 h so onde o regime permite)
        blocos = []
        for a, b, i in lst:
            if blocos and a == blocos[-1][1]:
                blocos[-1] = (blocos[-1][0], b, blocos[-1][2] + "+" + i)
            else:
                blocos.append((a, b, i))
        regime = reg.get(prof.get(pid, {}).get("regime"), {})
        max_bloco = timedelta(hours=24 if regime.get("permite_24h") else 12)
        for a, b in zip(blocos, blocos[1:]):
            if b[0] - a[1] < timedelta(hours=11):
                descanso.append(f"{pid} {a[2]} -> {b[2]}")
        descanso += [f"{pid} bloco {x[2]} de {(x[1] - x[0])}" for x in blocos if x[1] - x[0] > max_bloco]
    r.add("R1", "escala", "Ninguem em dois turnos ao mesmo tempo (escala realizada)", sobre, bool(real))
    r.add("R2", "escala", "Descanso minimo de 11 h entre jornadas e jornada continua dentro do regime", descanso, bool(real))
    plan_prof = defaultdict(list)
    for x in plan:
        plan_prof[x["profissional_id"]].append(_dt(x["inicio"]))
    desc36 = []
    for pid, lst in plan_prof.items():
        if prof.get(pid, {}).get("regime") == "CLT_12x36":
            lst.sort()
            desc36 += [f"{pid} {a}->{b}" for a, b in zip(lst, lst[1:]) if b - a < timedelta(hours=48)]  # 12 h + 36 h
    r.add("R3", "escala", "Escala planejada 12x36 respeita 36 h de descanso", desc36, bool(plan))
    teto = []
    cont = defaultdict(int)
    for x in plan:
        cont[(x["profissional_id"], x["data"][:7])] += 1
    for (pid, mes), n in cont.items():
        mx = reg.get(prof.get(pid, {}).get("regime"), {}).get("max_turnos_mes", 31)
        if n > mx:
            teto.append(f"{pid} {mes}: {n} > {mx}")
    r.add("R4", "escala", "Turnos planejados por mes dentro do teto do regime", teto, bool(plan))
    esp_setor = {s["codigo"]: s.get("especialidades", []) for s in d.get("setores", [])}
    habil = []
    for x in real:
        if x["situacao"] not in PRESENTE:
            continue
        p = prof.get(x["profissional_id"])
        if p is None:
            habil.append(x["id"]); continue
        if x["papel"] == "MEDICO":
            if p["especialidade"] not in esp_setor.get(x["setor"], []):
                habil.append(f"{x['id']} {p['especialidade']}@{x['setor']}")
        elif p["categoria"] != x["papel"] or p["lotacao"] != x["setor"]:
            habil.append(f"{x['id']} {p['categoria']}/{p['lotacao']}@{x['setor']}")
    r.add("R5", "escala", "Habilitacao compativel com o setor (especialidade medica; lotacao da enfermagem)", habil, bool(real))
    req = {(q["setor"], q["papel"]): (q["dia"], q["noite"]) for q in d.get("requisitos_escala", [])}
    pres = defaultdict(int)
    for x in real:
        if x["situacao"] in PRESENTE:
            pres[(x["setor"], x["papel"], x["inicio"])] += 1
    furos_inf = {(f["setor"], f["papel"], f["inicio"]): f["deficit"] for f in d.get("furos_cobertura", []) if f["origem"] == "EXECUCAO"}
    inconsist = []
    dia = ini
    while dia <= fim:
        for (setor, papel), (rd, rn) in req.items():
            for h, rq in ((7, rd), (19, rn)):
                if not rq:
                    continue
                k = (setor, papel, datetime(dia.year, dia.month, dia.day, h).isoformat())
                deficit = max(0, rq - pres[k])
                if deficit != furos_inf.get(k, 0):
                    inconsist.append(f"{k}: calculado={deficit} registrado={furos_inf.get(k, 0)}")
        dia += timedelta(days=1)
    r.add("R6", "escala", "Furos de cobertura registrados = exigido - presentes, em todo turno do periodo", inconsist, bool(req) and bool(real))
    exigido = defaultdict(int)
    for (setor, papel), (rd, rn) in req.items():
        exigido[papel] += (rd + rn) * ((fim - ini).days + 1)
    deficit = defaultdict(int)
    for f in d.get("furos_cobertura", []):
        if f["origem"] == "EXECUCAO" and ini.isoformat() <= f["data"] <= fim.isoformat():
            deficit[f["papel"]] += f["deficit"]
    limite = float(man.get("limite_furo_pct", 0.10))
    taxa = {p: round(deficit[p] / v, 4) for p, v in exigido.items() if v}
    r.add("R8", "escala", f"Deficit de cobertura executado ate {limite:.0%} do exigido, por categoria",
          [f"{p}: {x:.1%}" for p, x in taxa.items() if x > limite], bool(req), info=taxa)
    from .escala import Plantao
    pl = Plantao(real)
    def presente(pid, quando):
        return any(pid in pl.de_plantao(s, "MEDICO", quando) for s in esp_setor)
    corte = ini.isoformat()
    sem_plantao = [p["id"] for p in d.get("prescricoes", []) if not presente(p["medico_id"], _dt(p["data_hora"]))]
    sem_plantao += [a["id"] for a in d.get("atendimentos_ps", []) if a.get("medico_id") and a["inicio_atendimento"] >= corte
                    and not presente(a["medico_id"], _dt(a["inicio_atendimento"]))]
    r.add("R7", "escala", "Prescricoes e atendimentos feitos por medico de plantao naquele horario", sem_plantao, bool(real))

    # ------------------------------------------------------------ CLINICO
    pac = {p["id"]: p for p in d.get("pacientes", [])}
    obito = {i["paciente_id"]: _dt(i["data_desfecho"]) for i in internacoes.values() if i["desfecho"] == "OBITO"}
    pos = []
    for a in d.get("atendimentos_ps", []):
        if a["paciente_id"] in obito and _dt(a["chegada"]) > obito[a["paciente_id"]]:
            pos.append(a["id"])
    for i in internacoes.values():
        t = _dt(i["data_solicitacao"])
        if i["paciente_id"] in obito and t > obito[i["paciente_id"]]:
            pos.append(i["id"])
    for p in d.get("prescricoes", []):
        if p["paciente_id"] in obito and _dt(p["data_hora"]) > obito[p["paciente_id"]]:
            pos.append(p["id"])
    r.add("C1", "clinico", "Nenhum evento depois do obito", pos, bool(internacoes))
    leito_occ = defaultdict(list)
    pac_occ = defaultdict(list)
    for m in d.get("movimentacoes_leito", []):
        a, b = _dt(m["inicio"]), _dt(m["fim"]) or fim_dt
        if m["leito"]:
            leito_occ[m["leito"]].append((a, b, m["id"]))
        pac_occ[m["paciente_id"]].append((a, b, m["id"]))
    dupla = []
    for k, lst in list(leito_occ.items()) + list(pac_occ.items()):
        lst.sort()
        dupla += [f"{k}: {x[2]} x {y[2]}" for x, y in zip(lst, lst[1:]) if y[0] < x[1]]
    r.add("C2", "clinico", "Leito com um paciente por vez e paciente em um lugar por vez", dupla, bool(leito_occ))
    incomp = []
    for i in internacoes.values():
        p = pac.get(i["paciente_id"])
        if not p:
            incomp.append(i["id"]); continue
        ref = _dt(i["data_solicitacao"]).date()
        idade = (ref - date.fromisoformat(p["data_nascimento"])).days // 365
        if not cid_compativel(i["cid_principal"], p["sexo"], idade):
            incomp.append(f"{i['id']} {i['cid_principal']} {p['sexo']} {idade}a")
    r.add("C3", "clinico", "CID compativel com sexo e idade", incomp, bool(internacoes))
    crono = []
    for i in internacoes.values():
        p = pac.get(i["paciente_id"])
        if p and i["data_admissao"] and p["data_nascimento"] > i["data_admissao"][:10]:
            crono.append(i["id"])
        if i["data_admissao"] and i["data_alta"] and i["data_alta"] < i["data_admissao"]:
            crono.append(i["id"])
    r.add("C4", "clinico", "Cronologia: nascimento <= admissao <= alta", crono, bool(internacoes))
    mov_int = defaultdict(list)
    for m in d.get("movimentacoes_leito", []):
        if m["leito"]:
            mov_int[m["internacao_id"]].append((_dt(m["inicio"]), _dt(m["fim"]) or fim_dt, m["setor"]))
    setor_errado = []
    for p in d.get("prescricoes", []):
        t = _dt(p["data_hora"])
        onde = [s for a, b, s in mov_int.get(p["internacao_id"], []) if a <= t < b]
        if onde != [p["setor"]]:
            setor_errado.append(f"{p['id']} prescrita em {p['setor']} paciente em {onde}")
    r.add("C5", "clinico", "Prescricao feita no setor onde o paciente esta internado", setor_errado, bool(internacoes))

    # ------------------------------------------------------------ CALIBRACAO (tolerancias)
    alvo = man.get("alvos_calibracao") or {}
    dias = (fim - ini).days + 1
    if alvo and dias >= 28:
        concl = [i for i in internacoes.values() if i["desfecho"] in ("ALTA", "OBITO", "TRANSFERENCIA_EXTERNA")
                 and i["data_alta"] and ini.isoformat() <= i["data_alta"][:10] <= fim.isoformat()]
        fora = []
        if concl:
            mort = sum(i["desfecho"] == "OBITO" for i in concl) / len(concl)
            perm = sum((_dt(i["data_alta"]) - _dt(i["data_admissao"])).total_seconds() / 86400 for i in concl) / len(concl)
            if not (alvo["obito_pct"] * 0.6 <= mort <= alvo["obito_pct"] * 1.4):
                fora.append(f"mortalidade {mort:.3f} fora de {alvo['obito_pct']} +-40%")
            if not (alvo["media_permanencia_dias"] * 0.6 <= perm <= alvo["media_permanencia_dias"] * 1.4):
                fora.append(f"permanencia media {perm:.1f} fora de {alvo['media_permanencia_dias']} +-40%")
        solic = sum(1 for i in internacoes.values() if ini.isoformat() <= i["data_solicitacao"][:10] <= fim.isoformat()) * 30.4 / dias
        if not (alvo["internacoes_mes"] * 0.8 <= solic <= alvo["internacoes_mes"] * 1.2):
            fora.append(f"solicitacoes de internacao/mes {solic:.0f} fora de {alvo['internacoes_mes']:.0f} +-20%")
        r.add("Q1", "calibracao", "Volume, mortalidade e permanencia dentro da faixa da referencia (SIH)", fora, info={"alvo": alvo})
    return r


# ============================================================================ v1 (gerador antigo)
def verificar_v1(dir_lote: str) -> Resultado:
    def L(n):
        p = os.path.join(dir_lote, n)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    r = Resultado()
    moves, items, shifts, profs = L("stock_moves.json"), L("stock_items.json"), L("shifts.json"), L("professionals.json")
    pats, encs, inps = L("patients.json"), L("encounters.json"), L("inpatients.json")
    r.add("E1", "estoque", "Saldo por item, lote e local nunca negativo (replay do livro-razao)", [], False)
    r.add("E2", "estoque", "Todo movimento referencia um lote cadastrado", [m["id"] for m in moves if not m.get("lot")], bool(moves))
    r.add("E3", "estoque", "Nenhuma saida de lote vencido", [], False)
    r.add("E4", "estoque", "Dispensacao respeita FEFO", [], False)
    r.add("E5", "estoque", "Saldo final informado = soma dos movimentos", [], False)
    r.add("E6", "estoque", "Recebimentos ligados a pedido; ha compras no periodo",
          [] if any(m.get("type") == "RECEIPT" for m in moves) else ["nenhuma entrada de estoque no lote"], bool(moves))
    nomes = {i["name"] for i in items}
    r.add("E7", "estoque", "Toda dispensacao tem prescricao de origem", [m["id"] for m in moves if not m.get("prescription_id")], bool(moves))
    # escala
    por_prof = defaultdict(list)
    for s in shifts:
        por_prof[s["professional_id"]].append((s["start_time"], s["end_time"], s["id"]))
    desc = []
    for pid, lst in por_prof.items():
        lst.sort()
        desc += [pid for a, b in zip(lst, lst[1:]) if datetime.fromisoformat(b[0]) - datetime.fromisoformat(a[1]) < timedelta(hours=11)]
    r.add("R2", "escala", "Descanso minimo de 11 h entre turnos", desc, bool(shifts))
    spec = {p["id"]: p.get("specialty_code") for p in profs}
    habil = [s["id"] for s in shifts if s.get("team_type") == "MEDICA" and s["ward"] == "UTI Adulto" and spec.get(s["professional_id"]) not in ("UTI", "CM")]
    habil += [s["id"] for s in shifts if s["ward"] == "Ambulatório de Especialidades" and s["shift_type"].startswith("NOTURNO")]
    r.add("R5", "escala", "Habilitacao compativel com o setor (UTI so intensivista/clinico; ambulatorio so diurno)", habil, bool(shifts))
    datas_atend = sorted({e["appointment_date"] for e in encs})
    datas_esc = {s["date"] for s in shifts}
    descob = [d_ for d_ in datas_atend if d_ not in datas_esc]
    r.add("R6", "escala", "Escala cobre todos os dias com atendimento", descob, bool(shifts))
    uti_leitos = None
    r.add("R8", "escala", "Enfermagem da UTI dimensionada pela RDC 7/2010 (>=1 tecnico/2 leitos por turno)",
          [d_ for d_ in sorted(datas_esc) if sum(1 for s in shifts if s["date"] == d_ and s["ward"] == "UTI Adulto"
                                                 and s.get("professional_role") == "TECNICO_ENFERMAGEM" and s["shift_type"].startswith("DIURNO")) < 2], bool(shifts))
    # clinico
    pac = {p["id"]: p for p in pats}
    obito = {i["patient_id"]: i["discharge_date"] for i in inps if i.get("discharge_reason") == "OBITO"}
    pos = [e["id"] for e in encs if e["patient_id"] in obito and e["appointment_date"] > obito[e["patient_id"]]]
    r.add("C1", "clinico", "Nenhum evento depois do obito", pos, bool(encs))
    incomp = []
    for e in encs:
        p = pac.get(e["patient_id"])
        if p:
            idade = (date.fromisoformat(e["appointment_date"]) - date.fromisoformat(p["birth_date"])).days // 365
            sexo = "F" if p["gender"] == "female" else "M"
            if not cid_compativel(e["diagnosis_cid10"], sexo, idade):
                incomp.append(f"{e['id']} {e['diagnosis_cid10']} {idade}a")
    r.add("C3", "clinico", "CID compativel com sexo e idade", incomp, bool(encs))
    return r


def verificar(dir_lote: str) -> Resultado:
    if lote_io.eh_v2(dir_lote):
        return verificar_v2(lote_io.ler(dir_lote))
    return verificar_v1(dir_lote)
