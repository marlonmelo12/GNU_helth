"""Carga e validacao do perfil do hospital e da calibracao (agregados publicos)."""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAIXAS = {"0": (0, 0), "1-4": (1, 4), "5-14": (5, 14), "15-29": (15, 29), "30-44": (30, 44),
          "45-59": (45, 59), "60-74": (60, 74), "75+": (75, 95)}


@dataclass
class Setor:
    codigo: str
    nome: str
    tipo: str
    leitos: int
    publico: str
    cuidado: Optional[str]
    medicos_turno: Dict[str, int]
    especialidades: List[str]
    farmacia: str
    salas: int = 0
    parametro: bool = False
    enfermagem_turno: Optional[Dict[str, int]] = None
    cnes_codleito: Optional[str] = None
    # derivados
    enfermeiros_turno: int = 0
    tecnicos_turno: int = 0


@dataclass
class Perfil:
    bruto: Dict[str, Any]
    setores: List[Setor]
    calibracao: Dict[str, Any]
    cid3_validos: List[str]
    nomes_cid: Dict[str, str] = field(default_factory=dict)
    # turnos exigidos por dia, por categoria, no porte atual e no porte da referencia (1.0)
    exigencia: Dict[str, float] = field(default_factory=dict)
    exigencia_referencia: Dict[str, float] = field(default_factory=dict)

    @property
    def hospital(self) -> Dict[str, Any]:
        return self.bruto["hospital"]

    @property
    def estoque(self) -> Dict[str, Any]:
        return self.bruto["estoque"]

    @property
    def escala(self) -> Dict[str, Any]:
        return self.bruto["escala"]

    def setor(self, codigo: str) -> Setor:
        for s in self.setores:
            if s.codigo == codigo:
                return s
        raise KeyError(codigo)

    @property
    def setores_internacao(self) -> List[Setor]:
        return [s for s in self.setores if s.tipo in ("enfermaria", "uti")]


def _dimensionar(s: Setor, cuidado: Dict[str, Any], ocupacao: float) -> None:
    """Enfermagem minima por turno de 12 h (COFEN 543/2017; RDC 7/2010 nas UTIs)."""
    if s.enfermagem_turno:
        s.enfermeiros_turno = int(s.enfermagem_turno["enfermeiro"])
        s.tecnicos_turno = int(s.enfermagem_turno["tecnico"])
        return
    if not s.leitos or not s.cuidado:
        return
    c = cuidado[s.cuidado]
    pacientes = s.leitos * ocupacao
    presentes = math.ceil(pacientes * c["horas"] / 24.0)  # profissionais presentes a qualquer hora
    enf = max(1, math.ceil(presentes * c["pct_enfermeiro"]))
    tec = max(1, presentes - enf)
    if s.tipo == "uti":  # RDC 7/2010: >= 1 enfermeiro / 10 leitos e >= 1 tecnico / 2 leitos por turno
        enf = max(enf, math.ceil(s.leitos / 10))
        tec = max(tec, math.ceil(s.leitos / 2))
    s.enfermeiros_turno, s.tecnicos_turno = enf, tec


def carregar_perfil(caminho: str, escala_porte: Optional[float] = None) -> Perfil:
    with open(caminho, encoding="utf-8") as fh:
        bruto = yaml.safe_load(fh)
    fator = float(escala_porte if escala_porte is not None else bruto.get("escala_porte", 1.0))
    if not 0.05 <= fator <= 2.0:
        raise ValueError(f"escala_porte fora de [0.05, 2.0]: {fator}")
    bruto["escala_porte"] = fator
    setores = []
    for d in bruto["setores"]:
        s = Setor(
            codigo=d["codigo"], nome=d["nome"], tipo=d["tipo"],
            leitos=max(1, round(d.get("leitos", 0) * fator)) if d.get("leitos") else 0,
            publico=d.get("publico", "todos"), cuidado=d.get("cuidado"),
            medicos_turno=d.get("medicos_turno", {"dia": 0, "noite": 0}),
            especialidades=d.get("especialidades", []), farmacia=d.get("farmacia", "FARM_CENTRAL"),
            salas=max(1, round(d.get("salas", 0) * fator)) if d.get("salas") else 0,
            parametro=bool(d.get("parametro", False)), enfermagem_turno=d.get("enfermagem_turno"),
            cnes_codleito=d.get("cnes_codleito"),
        )
        if fator != 1.0 and s.medicos_turno:
            s.medicos_turno = {k: (max(1, round(v * fator)) if v else 0) for k, v in s.medicos_turno.items()}
        _dimensionar(s, bruto["cuidado"], float(bruto.get("ocupacao_referencia", 0.85)))
        if s.enfermagem_turno and fator != 1.0:
            s.enfermeiros_turno = max(1, round(s.enfermeiros_turno * fator))
            s.tecnicos_turno = max(1, round(s.tecnicos_turno * fator))
        setores.append(s)
    codigos = [s.codigo for s in setores]
    if len(set(codigos)) != len(codigos):
        raise ValueError("Codigos de setor duplicados no perfil.")
    calib_path = os.path.join(RAIZ, bruto["hospital"]["calibracao"])
    with open(calib_path, encoding="utf-8") as fh:
        calib = json.load(fh)
    with open(os.path.join(RAIZ, "config", "dim_cid10_datasus.json"), encoding="utf-8") as fh:
        cids = json.load(fh)
    cid3 = sorted({c["code"] for c in cids if len(c["code"]) == 3})
    nomes = {c["code"]: c["name"][6:].strip() if len(c["name"]) > 6 else c["name"] for c in cids if len(c["code"]) == 3}
    perfil = Perfil(bruto=bruto, setores=setores, calibracao=calib, cid3_validos=cid3, nomes_cid=nomes)
    perfil.exigencia = _exigencia(setores)
    if fator == 1.0:
        perfil.exigencia_referencia = dict(perfil.exigencia)
    else:
        perfil.exigencia_referencia = carregar_perfil(caminho, 1.0).exigencia
    return perfil


def _exigencia(setores: List[Setor]) -> Dict[str, float]:
    e = {"MEDICO": 0.0, "ENFERMEIRO": 0.0, "TECNICO_ENFERMAGEM": 0.0}
    for s in setores:
        e["MEDICO"] += sum(s.medicos_turno.values())
        e["ENFERMEIRO"] += 2 * s.enfermeiros_turno
        e["TECNICO_ENFERMAGEM"] += 2 * s.tecnicos_turno
    return e
