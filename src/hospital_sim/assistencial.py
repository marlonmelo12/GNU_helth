"""
Fluxo assistencial: pronto-socorro, internacoes, leitos, cirurgias, prescricoes, exames e contas.

Simulacao cronologica por paciente (fila FIFO de leitos por setor). Distribuicoes de CID,
idade/sexo, permanencia, obito, UTI, carater e residencia vem da calibracao (SIH agregado).
Regras duras: obito encerra o paciente; CID compativel com idade e sexo; leito com um
paciente por vez; paciente com uma internacao por vez.
"""
from __future__ import annotations

import calendar
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from . import catalogo
from .escala import Plantao
from .perfil import FAIXAS, Perfil, Setor
from .referencia import NOMES_F, NOMES_M, SOBRENOMES, cid_compativel

TRIAGEM = [("VERMELHO", 0.02), ("LARANJA", 0.10), ("AMARELO", 0.30), ("VERDE", 0.45), ("AZUL", 0.13)]  # parametro
HORA_CHEGADA = [1, 1, 1, 1, 1, 1, 2, 3, 5, 6, 6, 6, 5, 5, 5, 5, 5, 5, 5, 5, 4, 3, 2, 1]  # pesos por hora (parametro)


def _quantil(rng: random.Random, pontos: List[Tuple[float, float]]) -> float:
    """Amostra por interpolacao linear da funcao quantil (u, valor)."""
    u = rng.random()
    for (u0, v0), (u1, v1) in zip(pontos, pontos[1:]):
        if u <= u1:
            return v0 + (v1 - v0) * (u - u0) / max(u1 - u0, 1e-9)
    return pontos[-1][1]


def _cpf_invalido(rng: random.Random) -> str:
    """Numero com formato de CPF e digitos verificadores propositalmente INVALIDOS (nunca colide com CPF real)."""
    d = [rng.randint(0, 9) for _ in range(9)]
    s = sum(d[i] * (10 - i) for i in range(9)); d1 = (s * 10 % 11) % 10
    s = sum((d + [d1])[i] * (11 - i) for i in range(10)); d2 = (s * 10 % 11) % 10
    return "".join(map(str, d)) + str((d1 + 1) % 10) + str(d2)


class Calibracao:
    def __init__(self, perfil: Perfil):
        c = perfil.calibracao["internacoes"]
        self.fator = perfil.bruto["escala_porte"]
        self.por_comp = c["por_competencia"]
        self.grupos = {g["grupo"]: g for g in c["grupos"]}
        self.total = sum(g["n"] for g in c["grupos"])
        self.saz = defaultdict(dict)
        for r in c["sazonalidade"]:
            self.saz[r["competencia"][5:7]][r["grupo"]] = r["n"]
        self.idsx = defaultdict(list)
        geral = defaultdict(int)
        for r in c["idade_sexo"]:
            self.idsx[r["grupo"]].append(((r["faixa"], r["sexo"]), r["n"]))
            geral[(r["faixa"], r["sexo"])] += r["n"]
        self.idsx_geral = list(geral.items())
        self.dow = {int(k): v for k, v in c["dia_semana_domingo_1"].items()}
        self.residencia = [(r["municipio"], r["n"]) for r in c["municipio_residencia"]]
        explicitos = {g for g in self.grupos if not g.startswith("CAP_")}
        self.cid_por_capitulo = defaultdict(list)
        for cid in perfil.cid3_validos:
            if cid not in explicitos:
                self.cid_por_capitulo[cid[0]].append(cid)
        amb = perfil.calibracao.get("ambulatorial", [])
        self.ps_mes = sum(r["quantidade_aprovada"] for r in amb if r["subgrupo_sigtap"] == "030106") / max(
            len({r["competencia"] for r in amb}), 1)

    def internacoes_mes(self, ano: int, mes: int) -> float:
        mm = f"{mes:02d}"
        vals = [v for k, v in self.por_comp.items() if k[5:7] == mm]
        base = vals[-1] if vals else self.total / 12
        return base * self.fator

    def pesos_grupo(self, mes: int) -> List[Tuple[str, float]]:
        mm = f"{mes:02d}"
        tot_mes = sum(self.saz[mm].values()) or 1
        out = []
        for g, info in self.grupos.items():
            w = self.saz[mm].get(g)
            if w is None:
                w = info["n"] / 12.0 * (tot_mes / (self.total / 12.0))
            out.append((g, w))
        return out


def _escolher(rng: random.Random, pares):
    tot = sum(w for _, w in pares)
    u = rng.random() * tot
    for k, w in pares:
        u -= w
        if u <= 0:
            return k
    return pares[-1][0]


class Leitos:
    """Ocupacao por intervalos [inicio, fim) para cada leito de cada setor."""

    def __init__(self, perfil: Perfil):
        self.leitos: Dict[str, List[str]] = {}
        self.ocup: Dict[str, List[Tuple[datetime, datetime]]] = defaultdict(list)
        extra = float(perfil.bruto.get("leitos_extras_pct", 0.0))
        self.extras: Dict[str, List[str]] = {}
        for s in perfil.setores_internacao:
            self.leitos[s.codigo] = [f"{s.codigo}-L{i:03d}" for i in range(1, s.leitos + 1)]
            n_extra = int(round(s.leitos * extra)) if s.tipo == "enfermaria" else 0  # UTI nao tem leito extra
            self.extras[s.codigo] = [f"{s.codigo}-X{i:02d}" for i in range(1, n_extra + 1)]

    def _livre(self, leito: str, a: datetime, b: datetime) -> bool:
        return all(b <= x or a >= y for x, y in self.ocup[leito])

    def primeiro_livre(self, setor: str, a: datetime, dur: timedelta, limite: datetime) -> Optional[Tuple[str, datetime]]:
        """Leito e o primeiro instante >= a (ate limite) em que fica livre por dur."""
        todos = self.leitos[setor] + self.extras.get(setor, [])
        candidatos = sorted({a} | {y for l in todos for _, y in self.ocup[l] if a < y <= limite})
        for t in candidatos:
            for l in todos:  # regulares primeiro; leito extra so com a enfermaria cheia
                if self._livre(l, t, t + dur):
                    return l, t
        return None

    def podar(self, antes_de: datetime) -> None:
        """Descarta ocupacoes encerradas antes do dia de chegada em processamento (nao interferem mais)."""
        for l, ivs in list(self.ocup.items()):
            if any(y < antes_de for _, y in ivs):
                self.ocup[l] = [iv for iv in ivs if iv[1] >= antes_de]

    def reservar(self, leito: str, a: datetime, b: datetime) -> None:
        self.ocup[leito].append((a, b))

    def estender(self, leito: str, a: datetime, b_antigo: datetime, b_novo: datetime) -> bool:
        if not self._livre(leito, b_antigo, b_novo):
            return False
        self.ocup[leito].remove((a, b_antigo))
        self.ocup[leito].append((a, b_novo))
        return True


EXAMES = {  # (nome, unidade, faixa normal adulto)
    "HB": ("Hemoglobina", "g/dL", (12.0, 16.0)), "LEUCO": ("Leucocitos", "/mm3", (4000, 10000)),
    "PLAQ": ("Plaquetas", "/mm3", (150000, 400000)), "CREAT": ("Creatinina", "mg/dL", (0.6, 1.2)),
    "UREIA": ("Ureia", "mg/dL", (15, 45)), "NA": ("Sodio", "mEq/L", (135, 145)), "K": ("Potassio", "mEq/L", (3.5, 5.0)),
    "PCR": ("Proteina C reativa", "mg/L", (0, 5)), "GLIC": ("Glicemia", "mg/dL", (70, 99)),
    "LACT": ("Lactato", "mmol/L", (0.5, 2.0)), "BT": ("Bilirrubina total", "mg/dL", (0.2, 1.2)),
}
ALTERACAO = {  # grupo diagnostico -> exames deslocados (fator multiplicativo sobre o limite superior)
    "A41": {"LEUCO": 2.0, "PCR": 30, "LACT": 2.2, "CREAT": 1.8, "PLAQ": 0.5}, "J18": {"LEUCO": 1.6, "PCR": 15},
    "K35": {"LEUCO": 1.6, "PCR": 12}, "E10": {"GLIC": 3.0}, "E11": {"GLIC": 2.6}, "O24": {"GLIC": 1.8},
    "N17": {"CREAT": 3.0, "UREIA": 2.5, "K": 1.15}, "N18": {"CREAT": 4.5, "UREIA": 3.0, "K": 1.15, "HB": 0.7},
    "P59": {"BT": 10.0}, "K92": {"HB": 0.6}, "I21": {"PCR": 3},
}


def _valor_exame(rng: random.Random, cod: str, cid3: str, gravidade: float) -> float:
    lo, hi = EXAMES[cod][2]
    v = rng.uniform(lo, hi)
    f = ALTERACAO.get(cid3, {}).get(cod)
    if f:
        alvo = hi * f if f > 1 else lo * f
        v = v + (alvo - v) * min(1.0, gravidade) * rng.uniform(0.7, 1.1)
    return round(v, 2 if hi < 20 else 0)


class Assistencial:
    def __init__(self, perfil: Perfil, plantao: Plantao, quadro: List[Dict], rng: random.Random):
        self.p, self.plantao, self.rng = perfil, plantao, rng
        self.cal = Calibracao(perfil)
        self.leitos = Leitos(perfil)
        self.quadro = {q["id"]: q for q in quadro}
        self.pacientes: List[Dict] = []
        self.obito: Dict[str, datetime] = {}
        self.ultimo_evento: Dict[str, datetime] = {}  # fim do ultimo evento (PS ou internacao) do paciente
        self.out = defaultdict(list)
        self.seq = defaultdict(int)
        self.salas_cc = [[] for _ in range(max(1, next((s.salas for s in perfil.setores if s.tipo == "centro_cirurgico"), 1)))]
        self.max_espera = timedelta(days=perfil.bruto.get("dias_maximos_espera_leito", 2))
        self.demanda: List[Dict] = []  # pedidos de dispensacao para o modulo de estoque

    def _id(self, pref: str) -> str:
        self.seq[pref] += 1
        return f"{pref}{self.seq[pref]:07d}"

    # ----------------------------------------------------------------- pacientes
    def _novo_paciente(self, idade: int, sexo: str, quando: datetime, municipio: str) -> Dict:
        nasc = quando.date() - timedelta(days=idade * 365 + self.rng.randrange(0, 365))
        fem = sexo == "F"
        pac = {"id": self._id("PAC"), "nome": f"{self.rng.choice(NOMES_F if fem else NOMES_M)} {self.rng.choice(SOBRENOMES)} {self.rng.choice(SOBRENOMES)}",
               "sexo": sexo, "data_nascimento": nasc.isoformat(), "cpf_sintetico": _cpf_invalido(self.rng),
               "municipio_residencia_ibge": municipio, "uf": "CE", "is_synthetic": True}
        self.pacientes.append(pac)
        self.out["pacientes"].append(pac)
        return pac

    def _paciente(self, idade: int, sexo: str, quando: datetime, municipio: str, prob_retorno: float) -> Dict:
        if self.pacientes and self.rng.random() < prob_retorno:
            for _ in range(20):
                c = self.rng.choice(self.pacientes)
                idade_c = (quando.date() - date.fromisoformat(c["data_nascimento"])).days // 365
                if (c["id"] not in self.obito and self.ultimo_evento.get(c["id"], datetime.min) < quando
                        and c["sexo"] == sexo and abs(idade_c - idade) <= 2):
                    return c
        return self._novo_paciente(idade, sexo, quando, municipio)

    # ----------------------------------------------------------------- amostragem clinica
    def _caso(self, mes: int) -> Dict:
        rng = self.rng
        for _ in range(100):
            g = _escolher(rng, self.cal.pesos_grupo(mes))
            info = self.cal.grupos[g]
            if g.startswith("CAP_"):
                lista = self.cal.cid_por_capitulo.get(g[4:])
                if not lista:
                    continue
                cid3 = rng.choice(lista)
            else:
                cid3 = g
            faixa, sexo = _escolher(rng, self.cal.idsx.get(g) or self.cal.idsx_geral)
            if sexo == "I":
                sexo = "F" if rng.random() < (info.get("feminino_pct") or 0.5) else "M"
            lo, hi = FAIXAS[faixa]
            idade = rng.randint(lo, hi)
            if cid_compativel(cid3, sexo, idade):
                return {"grupo": g, "cid3": cid3, "idade": idade, "sexo": sexo, "info": info}
        raise RuntimeError("Nao foi possivel sortear um caso clinico compativel (calibracao inconsistente?).")

    def _permanencia(self, info: Dict) -> int:
        q = info["perm_quantis"]
        pts = [(0.0, max(0.0, q[0] - 1)), (0.1, q[0]), (0.25, q[1]), (0.5, q[2]), (0.75, q[3]), (0.9, q[4]),
               (1.0, max(q[4], info.get("perm_max") or q[4]))]
        return max(0, int(round(_quantil(self.rng, pts))))

    def _dias_uti(self, info: Dict, perm: int) -> int:
        q = info.get("dias_uti_quantis") or [3, 10]
        d = _quantil(self.rng, [(0.0, 1), (0.5, q[0]), (0.9, q[1]), (1.0, q[1] * 1.5)])
        return max(1, min(perm, int(round(d))))

    def _setor_destino(self, caso: Dict, uti: bool) -> Tuple[str, Optional[str]]:
        """(setor de internacao, setor de UTI ou None) conforme publico do perfil."""
        cid, idade = caso["cid3"], caso["idade"]
        cods = {s.codigo: s for s in self.p.setores_internacao}
        def primeiro(publico, tipo):
            return next((s.codigo for s in self.p.setores_internacao if s.publico == publico and s.tipo == tipo), None)
        if cid.startswith("P") or idade == 0 and cid.startswith(("P", "Q")):
            return (primeiro("neonatal", "enfermaria") or primeiro("pediatrico", "enfermaria"),
                    primeiro("neonatal", "uti") if uti else None)
        if cid.startswith("O") or cid.startswith("Z3"):
            return primeiro("obstetrico", "enfermaria"), (primeiro("adulto", "uti") if uti else None)
        if idade < 14:
            return primeiro("pediatrico", "enfermaria"), (primeiro("pediatrico", "uti") if uti else None)
        if caso.get("cirurgico"):
            return next((c for c in cods if c.startswith("CIRURG")), primeiro("adulto", "enfermaria")), (primeiro("adulto", "uti") if uti else None)
        clin = [s for s in self.p.setores_internacao if s.publico == "adulto" and s.tipo == "enfermaria" and not s.codigo.startswith("CIRURG")]
        alvo = _escolher(self.rng, [(s.codigo, s.leitos) for s in clin])
        return alvo, (primeiro("adulto", "uti") if uti else None)

    def _medico(self, setor: str, quando: datetime, ate_horas: int = 24) -> Tuple[Optional[str], datetime]:
        """Medico de plantao no setor (ou, na falta, em setor que aceite a mesma especialidade)."""
        for h in range(0, ate_horas + 1):
            t = quando + timedelta(hours=h)
            ids = self.plantao.de_plantao(setor, "MEDICO", t)
            if ids:
                return self.rng.choice(sorted(ids)), t
            esps = set(self.p.setor(setor).especialidades)
            for s in self.p.setores:
                for pid in sorted(self.plantao.de_plantao(s.codigo, "MEDICO", t)):
                    if self.quadro[pid]["especialidade"] in esps:
                        return pid, t
        return None, quando

    # ----------------------------------------------------------------- simulacao
    def simular(self, inicio: date, fim: date) -> None:
        rng = self.rng
        self.fim_dt = datetime(fim.year, fim.month, fim.day) + timedelta(days=1)
        eventos = []
        d = inicio
        while d <= fim:
            dias_mes = calendar.monthrange(d.year, d.month)[1]
            media = self.cal.internacoes_mes(d.year, d.month) / dias_mes
            dow = self.cal.dow
            fdow = dow.get((d.weekday() + 1) % 7, 1) / (sum(dow.values()) / 7.0) if dow else 1.0
            n = _poisson(rng, media * fdow)
            for _ in range(n):
                eventos.append((d, "INT"))
            n_ps = _poisson(rng, self.cal.ps_mes * self.cal.fator / dias_mes) if self.cal.ps_mes else 0
            for _ in range(max(0, n_ps - n)):  # internacoes de urgencia ja geram atendimento no PS
                eventos.append((d, "PS"))
            d += timedelta(days=1)
        rng.shuffle(eventos)
        eventos.sort(key=lambda e: e[0])
        ultimo_dia = None
        for dia, tipo in eventos:
            if dia != ultimo_dia:  # chegadas em ordem de dia: o que terminou antes de ontem nao conflita
                self.leitos.podar(datetime(dia.year, dia.month, dia.day) - timedelta(days=1))
                ultimo_dia = dia
            if tipo == "INT":
                self._internacao(dia, fim)
            else:
                self._atendimento_ps(dia, None)
        for k in ("atendimentos_ps", "internacoes", "movimentacoes_leito", "cirurgias", "prescricoes", "itens_prescricao",
                  "exames", "pacientes"):
            self.out[k].sort(key=lambda r: (r.get("inicio") or r.get("data_hora") or r.get("chegada") or r.get("data_admissao") or "", r["id"]))

    def _hora(self, eletivo: bool) -> int:
        if eletivo:
            return self.rng.randint(7, 11)
        return _escolher(self.rng, list(enumerate(HORA_CHEGADA)))

    def _atendimento_ps(self, dia: date, caso: Optional[Dict], chegada: Optional[datetime] = None) -> Tuple[Dict, Dict]:
        rng = self.rng
        chegada = chegada or datetime(dia.year, dia.month, dia.day, self._hora(False), rng.randint(0, 59))
        if caso is None:
            idade = rng.choice([rng.randint(0, 13), rng.randint(14, 90), rng.randint(14, 90)])
            sexo = "F" if rng.random() < 0.55 else "M"
            mun = _escolher(rng, self.cal.residencia) if self.cal.residencia else self.p.hospital["municipio_ibge"]
            pac = self._paciente(idade, sexo, chegada, mun, prob_retorno=0.15)
            if pac["id"] in self.obito or self.ultimo_evento.get(pac["id"], datetime.min) >= chegada:
                pac = self._novo_paciente(idade, sexo, chegada, mun)
        else:
            pac = caso["paciente"]
        cor = _escolher(rng, TRIAGEM) if caso is None else rng.choice(["VERMELHO", "LARANJA", "AMARELO"])
        medico, atendido = self._medico("PS", chegada + timedelta(minutes=rng.randint(5, 180)), ate_horas=6)
        if caso is None:
            r = rng.random()
            destino = "ALTA" if r < 0.93 else ("EVASAO" if r < 0.97 else "TRANSFERENCIA_EXTERNA")
            saida = atendido + timedelta(minutes=rng.randint(20, 360))
        else:
            destino, saida = "INTERNACAO", atendido + timedelta(minutes=rng.randint(60, 240))
        at = {"id": self._id("PSA"), "paciente_id": pac["id"], "chegada": chegada.isoformat(), "classificacao_risco": cor,
              "medico_id": medico, "inicio_atendimento": atendido.isoformat(), "saida": saida.isoformat(), "destino": destino,
              "cid_principal": caso["cid3"] if caso else None, "is_synthetic": True}
        self.out["atendimentos_ps"].append(at)
        self.ultimo_evento[pac["id"]] = max(self.ultimo_evento.get(pac["id"], datetime.min), saida)
        return at, pac

    def _internacao(self, dia: date, fim_periodo: date) -> None:
        rng = self.rng
        caso = self._caso(dia.month)
        info = caso["info"]
        eletivo = rng.random() < (info.get("eletivo_pct") or 0)
        caso["cirurgico"] = rng.random() < (info.get("cirurgico_pct") or 0)
        perm = self._permanencia(info)
        morre = rng.random() < (info.get("obito_pct") or 0)
        uti = rng.random() < (info.get("uti_pct") or 0) and perm >= 1
        setor, setor_uti = self._setor_destino(caso, uti)
        if setor is None:
            return
        mun = _escolher(rng, self.cal.residencia) if self.cal.residencia else self.p.hospital["municipio_ibge"]
        quando = datetime(dia.year, dia.month, dia.day, self._hora(eletivo), rng.randint(0, 59))
        pac = self._paciente(caso["idade"], caso["sexo"], quando, mun, prob_retorno=0.08)
        idade_real = (quando.date() - date.fromisoformat(pac["data_nascimento"])).days // 365
        if (pac["id"] in self.obito or self.ultimo_evento.get(pac["id"], datetime.min) >= quando
                or not cid_compativel(caso["cid3"], pac["sexo"], idade_real)):
            pac = self._novo_paciente(caso["idade"], caso["sexo"], quando, mun)
        caso["paciente"] = pac
        ps = None
        if not eletivo:
            ps, _ = self._atendimento_ps(dia, caso, chegada=quando)
            quando = datetime.fromisoformat(ps["saida"])
        # fases: UTI primeiro (urgencia) ou no fim (obito); enfermaria pelo restante
        dur_total = timedelta(days=perm, hours=rng.randint(0, 20)) if perm else timedelta(hours=rng.randint(6, 20))
        fases: List[Tuple[str, timedelta]] = []
        if setor_uti:
            du = timedelta(days=self._dias_uti(info, max(perm, 1)))
            du = min(du, dur_total)
            resto = dur_total - du
            # obito: parte chega grave direto a UTI; parte piora na enfermaria e sobe para a UTI no fim
            uti_no_fim = morre and rng.random() < 0.4
            fases = ([(setor, resto), (setor_uti, du)] if uti_no_fim else [(setor_uti, du), (setor, resto)])
            fases = [f for f in fases if f[1] > timedelta(0)]
        else:
            fases = [(setor, dur_total)]
        # leito da 1a fase: espera em fila FIFO ate o limite; sem leito -> transferencia por falta de leito
        primeiro = self.leitos.primeiro_livre(fases[0][0], quando, fases[0][1], quando + self.max_espera)
        int_id = self._id("INT")
        movs = []
        if primeiro is None:
            self.out["internacoes"].append({
                "id": int_id, "paciente_id": pac["id"], "atendimento_ps_id": ps["id"] if ps else None,
                "data_admissao": None, "data_solicitacao": quando.isoformat(), "data_alta": None, "carater": "ELETIVO" if eletivo else "URGENCIA",
                "cid_principal": caso["cid3"], "grupo_calibracao": caso["grupo"],
                "desfecho": "AGUARDANDO_LEITO" if quando + self.max_espera >= self.fim_dt else "TRANSFERENCIA_FALTA_DE_LEITO",
                "data_desfecho": None if quando + self.max_espera >= self.fim_dt else (quando + self.max_espera).isoformat(), "setor_solicitado": fases[0][0], "medico_responsavel_id": None,
                "valor_aih_brl": None, "is_synthetic": True})
            self.ultimo_evento[pac["id"]] = max(self.ultimo_evento.get(pac["id"], datetime.min), quando + self.max_espera)
            return
        leito, t = primeiro
        if t >= self.fim_dt:  # ainda aguardando leito quando o periodo termina
            self.out["internacoes"].append({
                "id": int_id, "paciente_id": pac["id"], "atendimento_ps_id": ps["id"] if ps else None,
                "data_admissao": None, "data_solicitacao": quando.isoformat(), "data_alta": None, "carater": "ELETIVO" if eletivo else "URGENCIA",
                "cid_principal": caso["cid3"], "grupo_calibracao": caso["grupo"], "desfecho": "AGUARDANDO_LEITO",
                "data_desfecho": None, "setor_solicitado": fases[0][0], "medico_responsavel_id": None,
                "valor_aih_brl": None, "is_synthetic": True})
            self.ultimo_evento[pac["id"]] = max(self.ultimo_evento.get(pac["id"], datetime.min), self.fim_dt)
            return
        if t > quando:
            movs.append({"setor": "PS", "leito": None, "inicio": quando, "fim": t, "motivo": "AGUARDANDO_LEITO"})
        admissao = t
        cursor = t
        for i, (sc, dur) in enumerate(fases):
            if i == 0:
                l, ini, fim = leito, cursor, cursor + dur
                self.leitos.reservar(l, ini, fim)
            else:
                achado = self.leitos.primeiro_livre(sc, cursor, dur, cursor + timedelta(days=10))
                if achado is None:
                    break  # sem leito na fase seguinte em 10 dias: permanece onde esta ate a alta
                l, ini = achado
                fim = ini + dur
                if ini > cursor:  # retido na fase anterior ate abrir vaga (ex.: alta da UTI retida)
                    ant = movs[-1]
                    if self.leitos.estender(ant["leito"], ant["inicio"], ant["fim"], ini):
                        ant["fim"], ant["motivo"] = ini, ant["motivo"] + "|RETIDO_SEM_VAGA"
                    else:
                        break
                self.leitos.reservar(l, ini, fim)
            movs.append({"setor": sc, "leito": l, "inicio": ini, "fim": fim, "motivo": "ADMISSAO" if i == 0 else "TRANSFERENCIA_INTERNA"})
            cursor = fim
        alta = movs[-1]["fim"]
        em_curso = alta >= self.fim_dt
        if em_curso:  # fotografia no fim do periodo: paciente segue internado, nada futuro e gerado
            movs = [m for m in movs if m["inicio"] < self.fim_dt]
            movs[-1]["fim"] = None
            morre = False
        desfecho = "EM_CURSO" if em_curso else ("OBITO" if morre else ("TRANSFERENCIA_EXTERNA" if rng.random() < 0.03 else "ALTA"))
        medico, _ = self._medico(fases[0][0], admissao, ate_horas=12)
        valor_q = info.get("valor_quantis") or [300, 1000, 5000]
        internacao = {
            "id": int_id, "paciente_id": pac["id"], "atendimento_ps_id": ps["id"] if ps else None,
            "data_solicitacao": quando.isoformat(), "data_admissao": admissao.isoformat(), "data_alta": None if em_curso else alta.isoformat(),
            "carater": "ELETIVO" if eletivo else "URGENCIA", "cid_principal": caso["cid3"], "grupo_calibracao": caso["grupo"],
            "desfecho": desfecho, "data_desfecho": None if em_curso else alta.isoformat(), "setor_solicitado": fases[0][0],
            "medico_responsavel_id": medico,
            "valor_aih_brl": round(_quantil(rng, [(0.0, valor_q[0] * 0.5), (0.1, valor_q[0]), (0.5, valor_q[1]), (0.9, valor_q[2]), (1.0, valor_q[2] * 1.5)]), 2),
            "is_synthetic": True,
        }
        self.out["internacoes"].append(internacao)
        self.ultimo_evento[pac["id"]] = max(self.ultimo_evento.get(pac["id"], datetime.min), alta)
        if morre:
            self.obito[pac["id"]] = alta
        for m in movs:
            self.out["movimentacoes_leito"].append({"id": self._id("MOV"), "internacao_id": int_id, "paciente_id": pac["id"],
                                                    "setor": m["setor"], "leito": m["leito"], "inicio": m["inicio"].isoformat(),
                                                    "fim": m["fim"].isoformat() if m["fim"] else None, "motivo": m["motivo"]})
        if caso["cirurgico"]:
            self._cirurgia(internacao, caso, admissao)
        self._prescricoes_e_exames(internacao, caso, movs, morre)

    def _cirurgia(self, internacao: Dict, caso: Dict, admissao: datetime) -> None:
        rng = self.rng
        desejado = admissao + timedelta(hours=rng.randint(2, 20))
        dur = timedelta(minutes=rng.choice([60, 90, 120, 150, 180, 240]))
        alta = datetime.fromisoformat(internacao["data_alta"]) if internacao["data_alta"] else self.fim_dt
        melhor = None
        for i, sala in enumerate(self.salas_cc):
            t = desejado
            for a, b in sorted(sala):
                if t < b and t + dur > a:
                    t = b
            if melhor is None or t < melhor[1]:
                melhor = (i, t)
        i, ini = melhor
        if ini + dur > alta:
            return  # sem sala antes da alta: cirurgia nao realizada nesta internacao
        self.salas_cc[i].append((ini, ini + dur))
        setor_cir = "OBST" if caso["cid3"].startswith("O") and any(s.codigo == "OBST" for s in self.p.setores) else internacao["setor_solicitado"]
        cirurgiao, _ = self._medico(setor_cir, ini, ate_horas=0)
        anest, _ = self._medico("CC", ini, ate_horas=0)
        cir = {"id": self._id("CIR"), "internacao_id": internacao["id"], "paciente_id": internacao["paciente_id"],
               "sala": f"SALA-{i + 1:02d}", "inicio": ini.isoformat(), "fim": (ini + dur).isoformat(),
               "cirurgiao_id": cirurgiao, "anestesista_id": anest, "cid_principal": caso["cid3"]}
        self.out["cirurgias"].append(cir)
        for nome, qtd, prob, _ in catalogo.CIRURGIA + [x for x in catalogo.protocolo_cid(caso["cid3"]) if x[3] == 1]:
            if rng.random() < prob:
                self.demanda.append({"quando": ini, "item": catalogo.item(nome), "quantidade": qtd, "local": "FARM_CC"
                                     if catalogo.POR_NOME[nome]["tipo"] == "MEDICAMENTO" else "ALMOX",
                                     "internacao_id": internacao["id"], "referencia": cir["id"], "setor_consumo": "CC"})

    def _prescricoes_e_exames(self, internacao: Dict, caso: Dict, movs: List[Dict], morre: bool) -> None:
        rng = self.rng
        cid = caso["cid3"]
        adm = datetime.fromisoformat(internacao["data_admissao"])
        alta = datetime.fromisoformat(internacao["data_alta"]) if internacao["data_alta"] else self.fim_dt
        prot_cid = [x for x in catalogo.protocolo_cid(cid) if x[3] != 1 or not caso.get("cirurgico")]
        ativos_cid = [x for x in prot_cid if rng.random() < x[2]]
        base_por_setor: Dict[str, List] = {}
        # exames de admissao
        self._exames(internacao, adm, cid, ["HB", "LEUCO", "PLAQ", "CREAT", "UREIA", "NA", "K", "PCR", "GLIC"]
                     + (["BT"] if cid == "P59" else []), gravidade=1.0)
        dia = adm.date()
        n_dia = 0
        while datetime(dia.year, dia.month, dia.day, 9) < alta:
            t = max(datetime(dia.year, dia.month, dia.day, 9, rng.randint(0, 59)), adm + timedelta(minutes=30))
            if t >= alta:
                break
            mov = next((m for m in movs if m["leito"] and m["inicio"] <= t < (m["fim"] or self.fim_dt)), None)
            if mov is None:
                dia += timedelta(days=1); n_dia += 1
                continue
            s = self.p.setor(mov["setor"])
            if s.codigo not in base_por_setor:
                base_por_setor[s.codigo] = [x for x in catalogo.protocolo_base(s.tipo, s.publico) if rng.random() < x[2]]
            medico, t_presc = self._medico(s.codigo, t, ate_horas=12)
            if medico is None or t_presc >= min(alta, mov["fim"] or self.fim_dt):
                self.out["prescricoes_nao_realizadas"].append({"internacao_id": internacao["id"], "data": dia.isoformat(),
                                                               "setor": s.codigo, "motivo": "SEM_MEDICO_DE_PLANTAO"})
                dia += timedelta(days=1); n_dia += 1
                continue
            presc = {"id": self._id("PRE"), "internacao_id": internacao["id"], "paciente_id": internacao["paciente_id"],
                     "setor": s.codigo, "data_hora": t_presc.isoformat(), "medico_id": medico, "dia_internacao": n_dia}
            self.out["prescricoes"].append(presc)
            itens = [x for x in base_por_setor[s.codigo] if x[3] is None or n_dia < x[3]]
            itens += [x for x in ativos_cid if x[3] is None or n_dia < x[3]]
            vistos = set()
            for nome, qtd, _, _ in itens:
                cod = catalogo.item(nome)
                if cod in vistos:
                    continue
                vistos.add(cod)
                it = {"id": self._id("PIT"), "prescricao_id": presc["id"], "item": cod, "quantidade_dia": qtd}
                self.out["itens_prescricao"].append(it)
                med = catalogo.POR_NOME[nome]["tipo"] == "MEDICAMENTO"
                self.demanda.append({"quando": t_presc + timedelta(minutes=rng.randint(30, 120)), "item": cod, "quantidade": qtd,
                                     "local": s.farmacia if med else "ALMOX", "internacao_id": internacao["id"],
                                     "referencia": it["id"], "setor_consumo": s.codigo})
            if s.tipo == "uti":
                grav = 1.0 if not morre else 1.0 + n_dia / max(1, (alta - adm).days)
                self._exames(internacao, t_presc - timedelta(hours=3), cid, ["HB", "LEUCO", "CREAT", "K", "LACT"],
                             gravidade=grav if morre else max(0.2, 1.0 - n_dia * 0.15))
            dia += timedelta(days=1); n_dia += 1

    def _exames(self, internacao: Dict, quando: datetime, cid: str, codigos: List[str], gravidade: float) -> None:
        coleta = max(quando, datetime.fromisoformat(internacao["data_admissao"]))
        for c in codigos:
            nome, und, (lo, hi) = EXAMES[c]
            v = _valor_exame(self.rng, c, cid, gravidade)
            self.out["exames"].append({"id": self._id("EXA"), "internacao_id": internacao["id"], "paciente_id": internacao["paciente_id"],
                                       "codigo": c, "exame": nome, "data_hora": coleta.isoformat(),
                                       "resultado": v, "unidade": und, "referencia_min": lo, "referencia_max": hi,
                                       "alterado": not (lo <= v <= hi)})


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 50:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1
