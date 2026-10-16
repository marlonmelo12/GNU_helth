"""
Estoque como livro-razao: todo saldo e a soma de movimentos e todo movimento tem causa.

Fluxos: inventario inicial documentado, pedido de compra, recebimento por nota com lote e
validade, transferencia central -> satelites, dispensacao FEFO por prescricao/cirurgia,
devolucao, perda por validade e avaria, inventario ciclico com ajuste e livro de
controlados. Sem saldo, a dispensacao NAO acontece: a ruptura e registrada.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple

from . import catalogo
from .perfil import Perfil

DIA = timedelta(days=1)


def _cnpj_invalido(rng: random.Random) -> str:
    """Formato de CNPJ com digitos verificadores propositalmente invalidos (ficticio por design)."""
    base = [rng.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = 11 - sum(a * b for a, b in zip(base, p1)) % 11
    d1 = 0 if d1 >= 10 else d1
    return "".join(map(str, base)) + str((d1 + 1) % 10) + str(rng.randint(0, 9))


class Estoque:
    def __init__(self, perfil: Perfil, rng: random.Random, inicio: date, fim: date):
        self.p, self.rng, self.inicio, self.fim = perfil, rng, inicio, fim
        self.cfg = perfil.estoque
        self.itens = {c["codigo"]: c for c in catalogo.CATALOGO}
        self.saldo: Dict[Tuple[str, str], List[List]] = defaultdict(list)  # (local, item) -> [[lote, validade, qtd], ...]
        self.lotes: Dict[str, Dict] = {}
        self.out = defaultdict(list)
        self.seq = defaultdict(int)
        self.pendentes: List[Dict] = []          # recebimentos previstos
        self.em_pedido: Dict[str, int] = defaultdict(int)
        self.devolucoes: List[Tuple[datetime, str, str, str, int, Dict]] = []

    def _id(self, pref: str) -> str:
        self.seq[pref] += 1
        return f"{pref}{self.seq[pref]:07d}"

    # ------------------------------------------------------------------ utilidades de saldo
    def _total(self, local: str, item: str) -> int:
        return sum(l[2] for l in self.saldo[(local, item)])

    def _mov(self, quando: datetime, tipo: str, item: str, lote: str, origem: str, destino: str, qtd: int, **extra) -> None:
        self.out["movimentos_estoque"].append({
            "id": self._id("MVE"), "data_hora": quando.isoformat(), "tipo": tipo, "item": item, "lote": lote,
            "origem": origem, "destino": destino, "quantidade": qtd,
            "custo_unitario": self.lotes[lote]["custo_unitario"], **extra})

    def _entrar(self, local: str, item: str, lote: str, qtd: int) -> None:
        lst = self.saldo[(local, item)]
        for l in lst:
            if l[0] == lote:
                l[2] += qtd
                break
        else:
            lst.append([lote, self.lotes[lote]["validade"], qtd])
            lst.sort(key=lambda z: (z[1], z[0]))  # FEFO: vence primeiro, sai primeiro

    def _sair_fefo(self, local: str, item: str, qtd: int, quando: datetime) -> List[Tuple[str, int]]:
        tirado, resto = [], qtd
        lst = self.saldo[(local, item)]
        for l in lst:
            if resto <= 0:
                break
            if l[2] <= 0 or l[1] < quando.date().isoformat():
                continue
            q = min(l[2], resto)
            l[2] -= q
            resto -= q
            tirado.append((l[0], q))
        self.saldo[(local, item)] = [l for l in lst if l[2] > 0]
        return tirado

    def _novo_lote(self, item: str, quando: datetime, custo: float, fornecedor: str, nota: str) -> str:
        rng = self.rng
        vmin, vmax = self.cfg["validade_meses"]
        meses = rng.uniform(2, 4) if rng.random() < self.cfg["prob_lote_validade_curta"] else rng.uniform(vmin, vmax)
        lote = f"L{quando:%y%m}{self._id('')[-5:]}{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}"
        self.lotes[lote] = {"lote": lote, "item": item, "fabricacao": (quando.date() - timedelta(days=rng.randint(15, 120))).isoformat(),
                            "validade": (quando.date() + timedelta(days=int(meses * 30.4))).isoformat(),
                            "custo_unitario": round(custo, 4), "fornecedor_id": fornecedor, "nota_fiscal": nota}
        self.out["lotes"].append(self.lotes[lote])
        return lote

    # ------------------------------------------------------------------ parametros a partir da demanda
    def _parametrizar(self, demanda: List[Dict]) -> None:
        dias = (self.fim - self.inicio).days + 1
        tot = defaultdict(int)
        for d in demanda:
            tot[(d["local"], d["item"])] += d["quantidade"]
        self.diario = {k: v / dias for k, v in tot.items()}
        # demanda que a farmacia central precisa suprir = propria + satelites
        self.diario_central = defaultdict(float)
        for (loc, item), v in self.diario.items():
            raiz = "ALMOX" if loc == "ALMOX" else "FARM_CENTRAL"
            self.diario_central[(raiz, item)] += v
        valor = {item: sum(v for (l, i), v in self.diario_central.items() if i == item) * self.itens[item]["custo_referencia"]
                 for item in self.itens}
        ordem = sorted(valor, key=lambda i: -valor[i])
        total_valor = sum(valor.values()) or 1
        acum, self.abc = 0.0, {}
        for i in ordem:
            acum += valor[i]
            self.abc[i] = "A" if acum <= 0.80 * total_valor else ("B" if acum <= 0.95 * total_valor else "C")
        rng = self.rng
        lt0, lt1 = self.cfg["lead_time_dias"]
        self.fornecedores = []
        for k in range(1, self.cfg["fornecedores"] + 1):
            f = {"id": f"FORN{k:03d}", "razao_social": f"Distribuidora Hospitalar Ficticia {k:02d} Ltda",
                 "cnpj_sintetico": _cnpj_invalido(rng), "lead_time_dias": rng.randint(lt0, lt1)}
            self.fornecedores.append(f)
        self.out["fornecedores"] = self.fornecedores
        self.forn_item = {i: rng.choice(self.fornecedores) for i in sorted(self.itens)}
        for c in catalogo.CATALOGO:
            self.out["itens"].append({**c, "classe_abc": self.abc[c["codigo"]],
                                      "consumo_medio_diario_previsto": round(self.diario_central.get((c["local_principal"], c["codigo"]), 0.0), 3)})

    def _nivel_max(self, raiz: str, item: str) -> int:
        d = self.diario_central.get((raiz, item), 0.0)
        # o maximo cobre sempre o prazo do fornecedor + seguranca + atraso tipico (nunca abaixo do ponto de pedido)
        dias = max(self.cfg["cobertura_dias"][self.abc[item]],
                   self.forn_item[item]["lead_time_dias"] + self.cfg["estoque_seguranca_dias"] + 10)
        return max(10, math.ceil(d * dias))

    def _ponto_pedido(self, raiz: str, item: str) -> int:
        d = self.diario_central.get((raiz, item), 0.0)
        return math.ceil(d * (self.forn_item[item]["lead_time_dias"] + self.cfg["estoque_seguranca_dias"]))

    # ------------------------------------------------------------------ operacao diaria
    def _inventario_inicial(self) -> None:
        t0 = datetime(self.inicio.year, self.inicio.month, self.inicio.day, 0, 0)
        for c in catalogo.CATALOGO:
            item, raiz = c["codigo"], c["local_principal"]
            qtd = self._nivel_max(raiz, item)
            partes = [qtd] if qtd < 30 else [qtd // 2, qtd - qtd // 2]
            for q in partes:
                lote = self._novo_lote(item, t0 - timedelta(days=self.rng.randint(10, 60)), c["custo_referencia"], self.forn_item[item]["id"], "SALDO-INICIAL")
                self._entrar(raiz, item, lote, q)
                self._mov(t0, "INVENTARIO_INICIAL", item, lote, "INVENTARIO", raiz, q)
        for loc in ("FARM_UTI", "FARM_CC"):
            self._repor_satelite(loc, t0)

    def _repor_satelite(self, loc: str, quando: datetime) -> None:
        mn, mx = self.cfg["satelite_min_max_dias"]
        for (l, item), d in sorted(self.diario.items()):
            if l != loc:
                continue
            if self._total(loc, item) < math.ceil(d * mn):
                falta = math.ceil(d * mx) - self._total(loc, item)
                for lote, q in self._sair_fefo("FARM_CENTRAL", item, falta, quando):
                    self._entrar(loc, item, lote, q)
                    self._mov(quando, "TRANSFERENCIA", item, lote, "FARM_CENTRAL", loc, q)

    def _vencimentos(self, dia: date) -> None:
        t = datetime(dia.year, dia.month, dia.day, 6, 0)
        for (loc, item), lst in list(self.saldo.items()):
            for l in lst:
                if l[2] > 0 and l[1] < dia.isoformat():
                    self._mov(t, "PERDA_VALIDADE", item, l[0], loc, "PERDAS", l[2])
                    l[2] = 0
            self.saldo[(loc, item)] = [l for l in lst if l[2] > 0]

    def _receber(self, dia: date) -> None:
        t = datetime(dia.year, dia.month, dia.day, 10, 0)
        hoje = [r for r in self.pendentes if r["previsto"] == dia]
        self.pendentes = [r for r in self.pendentes if r["previsto"] != dia]
        for r in hoje:
            item, raiz, q = r["item"], r["destino"], r["quantidade"]
            nota = f"NF-{self._id('NF')[-6:]}"
            custo = self.itens[item]["custo_referencia"] * self.rng.uniform(0.9, 1.1)
            lote = self._novo_lote(item, t, custo, r["fornecedor_id"], nota)
            self._entrar(raiz, item, lote, q)
            self.em_pedido[item] -= q
            self._mov(t, "RECEBIMENTO", item, lote, f"FORNECEDOR:{r['fornecedor_id']}", raiz, q, pedido_id=r["pedido_id"], nota_fiscal=nota)
            self.out["recebimentos"].append({"id": self._id("REC"), "pedido_id": r["pedido_id"], "nota_fiscal": nota, "data_hora": t.isoformat(),
                                             "item": item, "lote": lote, "quantidade": q, "fornecedor_id": r["fornecedor_id"],
                                             "custo_unitario": self.lotes[lote]["custo_unitario"]})

    def _comprar(self, dia: date) -> None:
        rng = self.rng
        t = datetime(dia.year, dia.month, dia.day, 17, 0)
        for c in catalogo.CATALOGO:
            item, raiz = c["codigo"], c["local_principal"]
            if self.diario_central.get((raiz, item), 0) <= 0:
                continue
            posicao = self._total(raiz, item) + self.em_pedido[item]
            if posicao > self._ponto_pedido(raiz, item):
                continue
            qtd = self._nivel_max(raiz, item) - posicao
            if qtd <= 0:
                continue
            f = self.forn_item[item]
            pid = self._id("PC")
            lt = f["lead_time_dias"] + (rng.randint(1, 7) if rng.random() < self.cfg["prob_atraso_entrega"] else 0)
            self.out["pedidos_compra"].append({"id": pid, "data_hora": t.isoformat(), "item": item, "quantidade": qtd,
                                               "fornecedor_id": f["id"], "previsao_entrega": (dia + timedelta(days=f["lead_time_dias"])).isoformat(),
                                               "classe_abc": self.abc[item]})
            self.em_pedido[item] += qtd
            if rng.random() < self.cfg["prob_entrega_parcial"]:
                q1 = max(1, int(qtd * rng.uniform(0.5, 0.8)))
                self.pendentes.append({"pedido_id": pid, "item": item, "quantidade": q1, "destino": raiz, "fornecedor_id": f["id"], "previsto": dia + timedelta(days=lt)})
                self.pendentes.append({"pedido_id": pid, "item": item, "quantidade": qtd - q1, "destino": raiz, "fornecedor_id": f["id"], "previsto": dia + timedelta(days=lt + rng.randint(3, 7))})
            else:
                self.pendentes.append({"pedido_id": pid, "item": item, "quantidade": qtd, "destino": raiz, "fornecedor_id": f["id"], "previsto": dia + timedelta(days=lt)})

    def _dispensar(self, d: Dict) -> None:
        rng = self.rng
        loc, item, q, quando = d["local"], d["item"], d["quantidade"], d["quando"]
        saiu = self._sair_fefo(loc, item, q, quando)
        entregue = 0
        for lote, qq in saiu:
            entregue += qq
            self._mov(quando, "DISPENSACAO", item, lote, loc, f"CONSUMO:{d['setor_consumo']}", qq,
                      internacao_id=d["internacao_id"], referencia=d["referencia"])
            if rng.random() < self.cfg["prob_devolucao"] and qq > 1:
                self.devolucoes.append((quando + timedelta(hours=rng.randint(12, 30)), loc, item, lote, rng.randint(1, qq - 1), d))
        if entregue < q:
            self.out["rupturas"].append({"id": self._id("RUP"), "data_hora": quando.isoformat(), "local": loc, "item": item,
                                         "solicitado": q, "atendido": entregue, "faltante": q - entregue,
                                         "internacao_id": d["internacao_id"], "referencia": d["referencia"]})
        if self.itens[item]["unidade"] in ("ampola", "frasco", "frasco-ampola") and rng.random() < self.cfg["prob_avaria_por_dispensacao"]:
            for lote, qq in self._sair_fefo(loc, item, 1, quando):
                self._mov(quando, "PERDA_AVARIA", item, lote, loc, "PERDAS", qq)

    def _devolver(self, ate: datetime) -> None:
        resto = []
        for t, loc, item, lote, q, d in self.devolucoes:
            if t <= ate and lote in self.lotes and self.lotes[lote]["validade"] >= t.date().isoformat():
                self._entrar(loc, item, lote, q)
                self._mov(t, "DEVOLUCAO", item, lote, f"CONSUMO:{d['setor_consumo']}", loc, q,
                          internacao_id=d["internacao_id"], referencia=d["referencia"])
            elif t > ate:
                resto.append((t, loc, item, lote, q, d))
        self.devolucoes = resto

    def _inventario_ciclico(self, dia: date) -> None:
        rng = self.rng
        t = datetime(dia.year, dia.month, dia.day, 20, 0)
        locais = sorted({loc for loc, _ in self.saldo})
        for loc in locais:
            itens = sorted({i for l, i in self.saldo if l == loc and self._total(loc, i) > 0})
            amostra = [i for i in itens if rng.random() < self.cfg["inventario_ciclico_pct_itens_mes"]]
            for item in amostra:
                sistema = self._total(loc, item)
                contado = sistema
                if rng.random() < self.cfg["prob_divergencia_inventario"]:
                    delta = rng.choice([-3, -2, -1, -1, -1, 1])
                    contado = max(0, sistema + delta)
                    lote = self.saldo[(loc, item)][0][0]
                    if contado < sistema:
                        for lt, q in self._sair_fefo(loc, item, sistema - contado, t):
                            self._mov(t, "AJUSTE_INVENTARIO", item, lt, loc, "AJUSTE", q, motivo="FALTA_NA_CONTAGEM")
                    else:
                        self._entrar(loc, item, lote, contado - sistema)
                        self._mov(t, "AJUSTE_INVENTARIO", item, lote, "AJUSTE", loc, contado - sistema, motivo="SOBRA_NA_CONTAGEM")
                self.out["contagens_inventario"].append({"id": self._id("CNT"), "data_hora": t.isoformat(), "local": loc, "item": item,
                                                         "saldo_sistema": sistema, "saldo_contado": contado, "divergencia": contado - sistema})

    def _livro_controlados(self, dia: date) -> None:
        for (loc, item), lst in sorted(self.saldo.items()):
            if self.itens[item]["controlado_lista"]:
                self.out["livro_controlados"].append({"data": dia.isoformat(), "local": loc, "item": item,
                                                      "lista_portaria_344": self.itens[item]["controlado_lista"],
                                                      "saldo_final_dia": sum(l[2] for l in lst)})

    def simular(self, demanda: List[Dict]) -> None:
        self._parametrizar(demanda)
        self._inventario_inicial()
        por_dia = defaultdict(list)
        for d in demanda:
            por_dia[d["quando"].date()].append(d)
        dia = self.inicio
        while dia <= self.fim:
            # Linha do tempo do dia: operacoes fixas e dispensacoes na ordem real dos horarios,
            # para que o livro-razao reproduza exatamente a sequencia de saldos.
            base = datetime(dia.year, dia.month, dia.day)
            fixos = [(base + timedelta(hours=6), 0, "VENC"), (base + timedelta(hours=7), 1, "SATELITE"),
                     (base + timedelta(hours=10), 2, "RECEBER"), (base + timedelta(hours=17), 3, "COMPRAR")]
            if dia.day == 25 or dia == self.fim:
                fixos.append((base + timedelta(hours=20), 4, "INVENTARIO"))
            fila = [(x[0], x[1], x[2], None) for x in fixos]
            fila += [(d["quando"], 9, "DISP", d) for d in por_dia.get(dia, [])]
            fila.sort(key=lambda z: (z[0], z[1], z[3]["referencia"] if z[3] else ""))
            for quando, _, tipo, d in fila:
                self._devolver(quando)
                if tipo == "VENC":
                    self._vencimentos(dia)
                elif tipo == "SATELITE":
                    for loc in ("FARM_UTI", "FARM_CC"):
                        self._repor_satelite(loc, quando)
                elif tipo == "RECEBER":
                    self._receber(dia)
                elif tipo == "COMPRAR":
                    self._comprar(dia)
                elif tipo == "INVENTARIO":
                    self._inventario_ciclico(dia)
                else:
                    self._dispensar(d)
            self._devolver(base + timedelta(hours=23, minutes=59))
            self._livro_controlados(dia)
            dia += DIA
        for (loc, item), lst in sorted(self.saldo.items()):
            for lote, val, q in lst:
                if q > 0:
                    self.out["saldos_finais"].append({"local": loc, "item": item, "lote": lote, "validade": val, "quantidade": q})
        self.out["pedidos_em_aberto"] = [{**r, "previsto": r["previsto"].isoformat()} for r in self.pendentes]
