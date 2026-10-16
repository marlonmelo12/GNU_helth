"""
Catalogo de medicamentos e materiais e protocolos de prescricao do hospital simulado.

Custos de referencia sao SINTETICOS (ordem de grandeza plausivel, nao tabela de mercado).
Controle especial segue as listas da Portaria SVS/MS 344/1998 (referencia.CONTROLADOS).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .referencia import CONTROLADOS

# (nome, categoria, unidade de dispensacao, custo de referencia R$ por unidade)
_MEDICAMENTOS: List[Tuple[str, str, str, float]] = [
    ("Dipirona 500mg/mL ampola 2mL", "Analgesico", "ampola", 0.90),
    ("Paracetamol 500mg comprimido", "Analgesico", "comprimido", 0.12),
    ("Cetoprofeno 100mg frasco-ampola IV", "Anti-inflamatorio", "frasco-ampola", 4.80),
    ("Tenoxicam 20mg frasco-ampola", "Anti-inflamatorio", "frasco-ampola", 6.10),
    ("Tramadol 50mg/mL ampola 2mL", "Opioide", "ampola", 2.40),
    ("Morfina 10mg/mL ampola 1mL", "Opioide", "ampola", 3.90),
    ("Fentanila 50mcg/mL frasco 10mL", "Opioide", "frasco", 9.50),
    ("Codeína 30mg comprimido", "Opioide", "comprimido", 0.85),
    ("Ceftriaxona 1g frasco-ampola", "Antibiotico", "frasco-ampola", 7.20),
    ("Cefazolina 1g frasco-ampola", "Antibiotico", "frasco-ampola", 5.60),
    ("Azitromicina 500mg comprimido", "Antibiotico", "comprimido", 1.90),
    ("Meropenem 1g frasco-ampola", "Antibiotico", "frasco-ampola", 38.00),
    ("Vancomicina 500mg frasco-ampola", "Antibiotico", "frasco-ampola", 14.50),
    ("Piperacilina+Tazobactam 4,5g frasco-ampola", "Antibiotico", "frasco-ampola", 42.00),
    ("Ciprofloxacino 200mg/100mL bolsa", "Antibiotico", "bolsa", 6.30),
    ("Oxacilina 500mg frasco-ampola", "Antibiotico", "frasco-ampola", 3.10),
    ("Amoxicilina+Clavulanato 500/125mg comprimido", "Antibiotico", "comprimido", 1.40),
    ("Ampicilina 1g frasco-ampola", "Antibiotico", "frasco-ampola", 3.80),
    ("Gentamicina 80mg/2mL ampola", "Antibiotico", "ampola", 1.30),
    ("Metronidazol 500mg/100mL bolsa", "Antimicrobiano", "bolsa", 4.20),
    ("Fluconazol 200mg/100mL bolsa", "Antifungico", "bolsa", 12.80),
    ("Noradrenalina 2mg/mL ampola 4mL", "Vasopressor", "ampola", 6.90),
    ("Epinefrina 1mg/mL ampola", "Vasopressor", "ampola", 2.10),
    ("Dobutamina 12,5mg/mL ampola 20mL", "Inotropico", "ampola", 9.80),
    ("Amiodarona 50mg/mL ampola 3mL", "Antiarritmico", "ampola", 3.40),
    ("Enalapril 10mg comprimido", "Anti-hipertensivo", "comprimido", 0.08),
    ("Losartana 50mg comprimido", "Anti-hipertensivo", "comprimido", 0.10),
    ("Anlodipino 5mg comprimido", "Anti-hipertensivo", "comprimido", 0.09),
    ("Carvedilol 6,25mg comprimido", "Cardiovascular", "comprimido", 0.15),
    ("Furosemida 10mg/mL ampola 2mL", "Diuretico", "ampola", 0.95),
    ("Furosemida 40mg comprimido", "Diuretico", "comprimido", 0.07),
    ("Espironolactona 25mg comprimido", "Diuretico", "comprimido", 0.18),
    ("Ácido acetilsalicílico 100mg comprimido", "Antiagregante", "comprimido", 0.05),
    ("Clopidogrel 75mg comprimido", "Antiagregante", "comprimido", 0.60),
    ("Sinvastatina 40mg comprimido", "Hipolipemiante", "comprimido", 0.12),
    ("Enoxaparina 40mg/0,4mL seringa", "Anticoagulante", "seringa", 11.50),
    ("Enoxaparina 60mg/0,6mL seringa", "Anticoagulante", "seringa", 16.20),
    ("Heparina 5.000UI/mL frasco 5mL", "Anticoagulante", "frasco", 18.00),
    ("Insulina NPH 100UI/mL frasco 10mL", "Hipoglicemiante", "frasco", 22.00),
    ("Insulina regular 100UI/mL frasco 10mL", "Hipoglicemiante", "frasco", 22.00),
    ("Metformina 850mg comprimido", "Hipoglicemiante", "comprimido", 0.09),
    ("Glicose 50% ampola 10mL", "Solucao hipertonica", "ampola", 0.70),
    ("Omeprazol 40mg frasco-ampola IV", "Protetor gastrico", "frasco-ampola", 6.40),
    ("Omeprazol 20mg capsula", "Protetor gastrico", "capsula", 0.10),
    ("Ondansetrona 4mg/2mL ampola", "Antiemetico", "ampola", 1.60),
    ("Metoclopramida 5mg/mL ampola 2mL", "Antiemetico", "ampola", 0.55),
    ("Bromoprida 10mg/2mL ampola", "Antiemetico", "ampola", 0.80),
    ("Dexametasona 4mg/mL ampola 2,5mL", "Corticoide", "ampola", 1.10),
    ("Hidrocortisona 100mg frasco-ampola", "Corticoide", "frasco-ampola", 4.90),
    ("Prednisona 20mg comprimido", "Corticoide", "comprimido", 0.14),
    ("Salbutamol 100mcg spray", "Broncodilatador", "frasco", 9.80),
    ("Ipratrópio 0,25mg/mL solucao 20mL", "Broncodilatador", "frasco", 3.20),
    ("Midazolam 5mg/mL ampola 10mL", "Sedativo", "ampola", 7.80),
    ("Propofol 10mg/mL ampola 20mL", "Anestesico", "ampola", 9.60),
    ("Cetamina 50mg/mL frasco 10mL", "Anestesico", "frasco", 24.00),
    ("Rocurônio 10mg/mL frasco 5mL", "Bloqueador neuromuscular", "frasco", 19.50),
    ("Lidocaína 2% sem vasoconstritor frasco 20mL", "Anestesico local", "frasco", 3.70),
    ("Bupivacaína 0,5% pesada ampola 4mL", "Anestesico local", "ampola", 5.20),
    ("Diazepam 5mg/mL ampola 2mL", "Benzodiazepinico", "ampola", 0.95),
    ("Fenitoína 50mg/mL ampola 5mL", "Anticonvulsivante", "ampola", 2.60),
    ("Ocitocina 5UI/mL ampola", "Uterotonico", "ampola", 1.70),
    ("Sulfato de magnésio 50% ampola 10mL", "Eletrolito", "ampola", 1.20),
    ("Cloreto de potássio 19,1% ampola 10mL", "Eletrolito", "ampola", 0.60),
    ("Gluconato de cálcio 10% ampola 10mL", "Eletrolito", "ampola", 0.90),
    ("Bicarbonato de sódio 8,4% frasco 250mL", "Eletrolito", "frasco", 6.80),
    ("Vitamina K1 10mg/mL ampola", "Vitamina", "ampola", 1.90),
    ("Cloreto de sódio 0,9% 100mL bolsa", "Solucao parenteral", "bolsa", 2.10),
    ("Cloreto de sódio 0,9% 500mL bolsa", "Solucao parenteral", "bolsa", 3.20),
    ("Cloreto de sódio 0,9% 1000mL bolsa", "Solucao parenteral", "bolsa", 4.60),
    ("Ringer lactato 500mL bolsa", "Solucao parenteral", "bolsa", 3.60),
    ("Glicose 5% 500mL bolsa", "Solucao parenteral", "bolsa", 3.40),
    ("Poractanto alfa 80mg/mL frasco 1,5mL", "Surfactante", "frasco", 1450.00),
    ("Cafeína citrato 20mg/mL ampola", "Estimulante respiratorio neonatal", "ampola", 28.00),
    ("Ampicilina 500mg frasco-ampola", "Antibiotico", "frasco-ampola", 2.70),
]

_MATERIAIS: List[Tuple[str, str, str, float]] = [
    ("Seringa 10mL sem agulha", "Material", "unidade", 0.32),
    ("Seringa 5mL com agulha", "Material", "unidade", 0.28),
    ("Agulha 40x12", "Material", "unidade", 0.08),
    ("Equipo macrogotas", "Material", "unidade", 1.40),
    ("Equipo para bomba de infusao", "Material", "unidade", 14.00),
    ("Cateter venoso periferico 20G", "Material", "unidade", 1.20),
    ("Cateter venoso central duplo lumen", "Material", "unidade", 85.00),
    ("Luva de procedimento (par)", "EPI", "par", 0.30),
    ("Luva cirurgica esteril 7,5 (par)", "EPI", "par", 1.60),
    ("Mascara cirurgica", "EPI", "unidade", 0.15),
    ("Avental descartavel", "EPI", "unidade", 2.20),
    ("Compressa de gaze 7,5x7,5 (pacote 10)", "Curativo", "pacote", 0.90),
    ("Atadura de crepe 15cm", "Curativo", "unidade", 0.70),
    ("Fio de sutura nylon 3-0", "Material cirurgico", "unidade", 3.50),
    ("Fio de sutura absorvivel 2-0", "Material cirurgico", "unidade", 8.90),
    ("Sonda vesical de demora 16Fr", "Material", "unidade", 4.10),
    ("Sonda nasogastrica 16Fr", "Material", "unidade", 1.90),
    ("Coletor de urina sistema fechado", "Material", "unidade", 6.40),
    ("Tubo endotraqueal 7,5 com balao", "Material", "unidade", 7.80),
    ("Circuito para ventilador mecanico", "Material", "unidade", 48.00),
    ("Fralda geriatrica G", "Higiene", "unidade", 1.30),
    ("Fralda neonatal RN", "Higiene", "unidade", 0.45),
    ("Kit parto normal descartavel", "Material obstetrico", "kit", 38.00),
    ("Eletrodo descartavel para monitorizacao", "Material", "unidade", 0.35),
]

# Itens dispensados pelo almoxarifado (materiais) e pela farmacia (medicamentos)
CATALOGO: List[Dict] = []
for i, (nome, cat, und, custo) in enumerate(_MEDICAMENTOS, 1):
    lista = next((v for k, v in CONTROLADOS.items() if nome.lower().startswith(k.lower())), None)
    CATALOGO.append({"codigo": f"MED{i:04d}", "nome": nome, "categoria": cat, "unidade": und,
                     "custo_referencia": custo, "tipo": "MEDICAMENTO", "controlado_lista": lista,
                     "local_principal": "FARM_CENTRAL"})
for i, (nome, cat, und, custo) in enumerate(_MATERIAIS, 1):
    CATALOGO.append({"codigo": f"MAT{i:04d}", "nome": nome, "categoria": cat, "unidade": und,
                     "custo_referencia": custo, "tipo": "MATERIAL", "controlado_lista": None,
                     "local_principal": "ALMOX"})
POR_NOME = {c["nome"]: c for c in CATALOGO}


def item(nome: str) -> str:
    """Codigo do item pelo nome exato (falha alto se o protocolo citar item inexistente)."""
    return POR_NOME[nome]["codigo"]


# Protocolo = lista de (item, unidades por dia, probabilidade, dias maximos ou None = ate a alta)
Protocolo = List[Tuple[str, int, float, int]]

BASE_SETOR: Dict[str, Protocolo] = {
    "enfermaria_adulto": [
        ("Dipirona 500mg/mL ampola 2mL", 3, 0.70, None), ("Omeprazol 40mg frasco-ampola IV", 1, 0.50, None),
        ("Enoxaparina 40mg/0,4mL seringa", 1, 0.55, None), ("Cloreto de sódio 0,9% 500mL bolsa", 2, 0.60, 2),
        ("Ondansetrona 4mg/2mL ampola", 2, 0.25, 3), ("Seringa 10mL sem agulha", 6, 1.0, None),
        ("Equipo macrogotas", 1, 0.8, None), ("Luva de procedimento (par)", 12, 1.0, None),
        ("Cateter venoso periferico 20G", 1, 0.35, None), ("Compressa de gaze 7,5x7,5 (pacote 10)", 2, 0.6, None),
    ],
    "uti_adulto": [
        ("Midazolam 5mg/mL ampola 10mL", 6, 0.55, None), ("Fentanila 50mcg/mL frasco 10mL", 3, 0.50, None),
        ("Noradrenalina 2mg/mL ampola 4mL", 4, 0.40, None), ("Propofol 10mg/mL ampola 20mL", 3, 0.15, None),
        ("Heparina 5.000UI/mL frasco 5mL", 1, 0.45, None), ("Omeprazol 40mg frasco-ampola IV", 1, 0.90, None),
        ("Insulina regular 100UI/mL frasco 10mL", 1, 0.30, None), ("Cloreto de potássio 19,1% ampola 10mL", 3, 0.35, None),
        ("Cloreto de sódio 0,9% 100mL bolsa", 6, 1.0, None), ("Dipirona 500mg/mL ampola 2mL", 3, 0.6, None),
        ("Seringa 10mL sem agulha", 14, 1.0, None), ("Equipo para bomba de infusao", 3, 1.0, None),
        ("Luva de procedimento (par)", 30, 1.0, None), ("Eletrodo descartavel para monitorizacao", 5, 1.0, None),
        ("Cateter venoso central duplo lumen", 1, 0.10, None), ("Circuito para ventilador mecanico", 1, 0.06, None),
        ("Fralda geriatrica G", 6, 0.8, None),
    ],
    "pediatria": [
        ("Dipirona 500mg/mL ampola 2mL", 2, 0.60, None), ("Cloreto de sódio 0,9% 100mL bolsa", 2, 0.50, 3),
        ("Seringa 5mL com agulha", 6, 1.0, None), ("Luva de procedimento (par)", 10, 1.0, None),
        ("Cateter venoso periferico 20G", 1, 0.30, None),
    ],
    "neonatal": [
        ("Cafeína citrato 20mg/mL ampola", 1, 0.25, None), ("Ampicilina 500mg frasco-ampola", 2, 0.30, 7),
        ("Gentamicina 80mg/2mL ampola", 1, 0.30, 7), ("Glicose 5% 500mL bolsa", 1, 0.50, None),
        ("Fralda neonatal RN", 8, 1.0, None), ("Seringa 5mL com agulha", 6, 1.0, None),
        ("Luva de procedimento (par)", 12, 1.0, None),
    ],
    "obstetricia": [
        ("Dipirona 500mg/mL ampola 2mL", 3, 0.70, 3), ("Paracetamol 500mg comprimido", 3, 0.4, None),
        ("Ocitocina 5UI/mL ampola", 2, 0.30, 1), ("Seringa 10mL sem agulha", 4, 1.0, None),
        ("Luva de procedimento (par)", 8, 1.0, None), ("Compressa de gaze 7,5x7,5 (pacote 10)", 2, 1.0, None),
    ],
}

# Protocolos por grupo diagnostico (prefixo do CID-10). O primeiro prefixo que casar vence.
POR_CID: List[Tuple[Tuple[str, ...], Protocolo]] = [
    (("A41", "A40"), [("Meropenem 1g frasco-ampola", 3, 0.65, 10), ("Vancomicina 500mg frasco-ampola", 4, 0.45, 10),
                      ("Piperacilina+Tazobactam 4,5g frasco-ampola", 4, 0.30, 10), ("Noradrenalina 2mg/mL ampola 4mL", 4, 0.6, 5),
                      ("Hidrocortisona 100mg frasco-ampola", 4, 0.3, 5), ("Ringer lactato 500mL bolsa", 4, 0.8, 2)]),
    (("J18", "J15", "J13", "J69"), [("Ceftriaxona 1g frasco-ampola", 2, 0.85, 7), ("Azitromicina 500mg comprimido", 1, 0.6, 5),
                                    ("Ipratrópio 0,25mg/mL solucao 20mL", 1, 0.3, 3)]),
    (("J21", "J20", "J45", "J44", "J80"), [("Salbutamol 100mcg spray", 1, 0.4, None), ("Ipratrópio 0,25mg/mL solucao 20mL", 1, 0.6, 3),
                                           ("Prednisona 20mg comprimido", 2, 0.4, 5), ("Hidrocortisona 100mg frasco-ampola", 3, 0.3, 3)]),
    (("K35", "K36", "K37"), [("Ceftriaxona 1g frasco-ampola", 2, 0.8, 5), ("Metronidazol 500mg/100mL bolsa", 3, 0.8, 5),
                             ("Tramadol 50mg/mL ampola 2mL", 3, 0.6, 3), ("Cetoprofeno 100mg frasco-ampola IV", 2, 0.5, 3)]),
    (("K80", "K81", "K56", "K92", "K40", "K42"), [("Ceftriaxona 1g frasco-ampola", 2, 0.4, 5), ("Metronidazol 500mg/100mL bolsa", 3, 0.3, 5),
                                                ("Bromoprida 10mg/2mL ampola", 3, 0.4, 3), ("Omeprazol 40mg frasco-ampola IV", 2, 0.5, None)]),
    (("A08", "A09", "A00", "A01", "A02", "A03", "A04", "A05", "A06", "A07"),
     [("Ringer lactato 500mL bolsa", 3, 0.7, 2), ("Ondansetrona 4mg/2mL ampola", 2, 0.6, 2), ("Bromoprida 10mg/2mL ampola", 2, 0.3, 2)]),
    (("I63", "I64", "I61", "I60"), [("Ácido acetilsalicílico 100mg comprimido", 1, 0.6, None), ("Sinvastatina 40mg comprimido", 1, 0.6, None),
                                    ("Enalapril 10mg comprimido", 2, 0.5, None), ("Fenitoína 50mg/mL ampola 5mL", 3, 0.1, 5)]),
    (("I21", "I20", "I24", "I25"), [("Ácido acetilsalicílico 100mg comprimido", 1, 0.95, None), ("Clopidogrel 75mg comprimido", 1, 0.85, None),
                                    ("Enoxaparina 60mg/0,6mL seringa", 2, 0.7, 5), ("Sinvastatina 40mg comprimido", 1, 0.9, None),
                                    ("Carvedilol 6,25mg comprimido", 2, 0.6, None), ("Morfina 10mg/mL ampola 1mL", 2, 0.3, 2)]),
    (("I50", "I11", "I10", "I48"), [("Furosemida 10mg/mL ampola 2mL", 3, 0.7, 4), ("Furosemida 40mg comprimido", 1, 0.5, None),
                                    ("Espironolactona 25mg comprimido", 1, 0.5, None), ("Enalapril 10mg comprimido", 2, 0.6, None),
                                    ("Losartana 50mg comprimido", 2, 0.3, None), ("Amiodarona 50mg/mL ampola 3mL", 3, 0.15, 3)]),
    (("I70", "I74", "L97", "E10", "E11", "E14"), [("Insulina NPH 100UI/mL frasco 10mL", 1, 0.55, None), ("Insulina regular 100UI/mL frasco 10mL", 1, 0.5, None),
                                                ("Oxacilina 500mg frasco-ampola", 8, 0.35, 10), ("Ciprofloxacino 200mg/100mL bolsa", 2, 0.3, 10),
                                                ("Metformina 850mg comprimido", 2, 0.3, None), ("Atadura de crepe 15cm", 2, 0.7, None)]),
    (("N39", "N10", "N30"), [("Ciprofloxacino 200mg/100mL bolsa", 2, 0.6, 7), ("Ceftriaxona 1g frasco-ampola", 1, 0.4, 7)]),
    (("N17", "N18", "N19"), [("Furosemida 10mg/mL ampola 2mL", 4, 0.5, None), ("Bicarbonato de sódio 8,4% frasco 250mL", 1, 0.3, 3),
                             ("Gluconato de cálcio 10% ampola 10mL", 1, 0.3, 3)]),
    (("O82",), [("Cefazolina 1g frasco-ampola", 2, 0.95, 1), ("Bupivacaína 0,5% pesada ampola 4mL", 1, 0.95, 1),
                ("Ocitocina 5UI/mL ampola", 4, 0.95, 1), ("Fio de sutura absorvivel 2-0", 3, 1.0, 1), ("Morfina 10mg/mL ampola 1mL", 1, 0.5, 1),
                ("Cetoprofeno 100mg frasco-ampola IV", 2, 0.7, 2)]),
    (("O80", "O81", "O83", "O84"), [("Ocitocina 5UI/mL ampola", 2, 0.9, 1), ("Kit parto normal descartavel", 1, 1.0, 1),
                                    ("Lidocaína 2% sem vasoconstritor frasco 20mL", 1, 0.6, 1)]),
    (("O14", "O13", "O15", "O11"), [("Sulfato de magnésio 50% ampola 10mL", 4, 0.8, 2), ("Enalapril 10mg comprimido", 2, 0.4, None)]),
    (("O24", "O99", "O26", "O23"), [("Insulina NPH 100UI/mL frasco 10mL", 1, 0.4, None), ("Cefazolina 1g frasco-ampola", 1, 0.2, 3)]),
    (("P22", "P07", "P36"), [("Poractanto alfa 80mg/mL frasco 1,5mL", 1, 0.20, 1), ("Ampicilina 500mg frasco-ampola", 2, 0.7, 7),
                             ("Gentamicina 80mg/2mL ampola", 1, 0.7, 7), ("Cafeína citrato 20mg/mL ampola", 1, 0.5, None)]),
    (("P59",), [("Glicose 5% 500mL bolsa", 1, 0.3, 2)]),
    (("C",), [("Morfina 10mg/mL ampola 1mL", 4, 0.5, None), ("Ondansetrona 4mg/2mL ampola", 2, 0.6, None),
              ("Dexametasona 4mg/mL ampola 2,5mL", 2, 0.5, None)]),
    (("S", "T"), [("Cetoprofeno 100mg frasco-ampola IV", 2, 0.6, 4), ("Tramadol 50mg/mL ampola 2mL", 3, 0.5, 4),
                  ("Cefazolina 1g frasco-ampola", 3, 0.4, 2), ("Atadura de crepe 15cm", 2, 0.5, None)]),
    (("G40", "G41", "R56"), [("Diazepam 5mg/mL ampola 2mL", 2, 0.6, 2), ("Fenitoína 50mg/mL ampola 5mL", 3, 0.6, None)]),
    (("A90", "A91", "A92"), [("Paracetamol 500mg comprimido", 3, 0.8, None), ("Ringer lactato 500mL bolsa", 3, 0.7, 3)]),
]

# Itens do ato cirurgico (dispensados pela farmacia do centro cirurgico)
CIRURGIA: Protocolo = [
    ("Propofol 10mg/mL ampola 20mL", 2, 0.85, 1), ("Fentanila 50mcg/mL frasco 10mL", 1, 0.85, 1),
    ("Rocurônio 10mg/mL frasco 5mL", 2, 0.6, 1), ("Lidocaína 2% sem vasoconstritor frasco 20mL", 1, 0.7, 1),
    ("Cefazolina 1g frasco-ampola", 2, 0.8, 1), ("Ondansetrona 4mg/2mL ampola", 1, 0.7, 1),
    ("Luva cirurgica esteril 7,5 (par)", 6, 1.0, 1), ("Fio de sutura nylon 3-0", 2, 0.8, 1),
    ("Fio de sutura absorvivel 2-0", 2, 0.8, 1), ("Avental descartavel", 4, 1.0, 1), ("Mascara cirurgica", 6, 1.0, 1),
    ("Tubo endotraqueal 7,5 com balao", 1, 0.6, 1), ("Sonda vesical de demora 16Fr", 1, 0.4, 1),
    ("Coletor de urina sistema fechado", 1, 0.4, 1),
]


def protocolo_base(setor_tipo: str, publico: str) -> Protocolo:
    if setor_tipo == "uti" and publico == "adulto":
        return BASE_SETOR["uti_adulto"]
    if publico == "neonatal":
        return BASE_SETOR["neonatal"]
    if publico == "pediatrico":
        return BASE_SETOR["pediatria"]
    if publico == "obstetrico":
        return BASE_SETOR["obstetricia"]
    return BASE_SETOR["enfermaria_adulto"]


def protocolo_cid(cid3: str) -> Protocolo:
    for prefixos, prot in POR_CID:
        if any(cid3.startswith(p) for p in prefixos):
            return prot
    return []


def validar_catalogo() -> None:
    """Todo item citado por protocolo existe no catalogo (falha alto na importacao)."""
    usados = {n for p in BASE_SETOR.values() for n, *_ in p}
    usados |= {n for _, p in POR_CID for n, *_ in p}
    usados |= {n for n, *_ in CIRURGIA}
    faltando = sorted(usados - set(POR_NOME))
    if faltando:
        raise ValueError(f"Protocolos citam itens fora do catalogo: {faltando}")


validar_catalogo()
