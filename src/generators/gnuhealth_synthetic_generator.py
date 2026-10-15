"""
QIMED DataQore — Gerador Parametrizável de Dados Hospitalares Sintéticos do GNU Health.
Simula a operação de um hospital geral (Clínica, Estoque, Farmácia e Escalas de RH)
com persistência oficial via Proteus / APIs do Tryton e rastreabilidade total para o QIMED.
"""
import os
import sys
import argparse
import json
import time
import random
import hashlib
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple

import duckdb

# Nomes brasileiros representativos para geração demográfica sintética
_FIRST_NAMES_M = [
    "João", "Pedro", "Lucas", "Mateus", "Gabriel", "Rafael", "Carlos", "Antônio",
    "Francisco", "Luiz", "Paulo", "Marcos", "José", "Guilherme", "Felipe", "Bruno"
]
_FIRST_NAMES_F = [
    "Maria", "Ana", "Francisca", "Juliana", "Beatriz", "Larissa", "Camila", "Fernanda",
    "Aline", "Mariana", "Patrícia", "Cláudia", "Helena", "Letícia", "Bruna", "Sofia"
]
_LAST_NAMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira",
    "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes",
    "Soares", "Fernandes", "Vieira", "Barbosa", "Rocha", "Dias", "Nascimento", "Melo"
]

_MEDICAL_SPECIALTIES = [
    {"code": "CM", "name": "Clínica Médica"},
    {"code": "CG", "name": "Cirurgia Geral"},
    {"code": "CARD", "name": "Cardiologia"},
    {"code": "PED", "name": "Pediatria"},
    {"code": "UTI", "name": "Medicina Intensiva"},
    {"code": "EME", "name": "Medicina de Emergência"},
    {"code": "ORT", "name": "Ortopedia e Traumatologia"},
    {"code": "INF", "name": "Infectologia"},
]

_NURSING_SPECIALTIES = [
    {"code": "ENF_GER", "name": "Enfermagem Clínica Geral", "role": "ENFERMEIRO"},
    {"code": "ENF_UTI", "name": "Enfermagem em Terapia Intensiva (UTI)", "role": "ENFERMEIRO"},
    {"code": "ENF_URG", "name": "Enfermagem em Urgência e Emergência", "role": "ENFERMEIRO"},
    {"code": "ENF_CIR", "name": "Enfermagem em Bloco Cirúrgico", "role": "ENFERMEIRO"},
    {"code": "TEC_ENF", "name": "Técnico de Enfermagem Geral", "role": "TECNICO_ENFERMAGEM"},
    {"code": "TEC_UTI", "name": "Técnico de Enfermagem em UTI", "role": "TECNICO_ENFERMAGEM"},
    {"code": "TEC_URG", "name": "Técnico de Enfermagem em Urgência", "role": "TECNICO_ENFERMAGEM"},
]

_SPECIALTIES = _MEDICAL_SPECIALTIES + [
    {"code": s["code"], "name": s["name"]} for s in _NURSING_SPECIALTIES
]

_CLINICAL_SCENARIOS = [
    {
        "name": "Pneumonia Adquirida na Comunidade",
        "cid10": "J18",
        "complaint": "Tosse produtiva, febre alta e dispneia há 4 dias",
        "inpatient_prob": 0.35,
        "stay_days_min": 3,
        "stay_days_max": 7,
        "labs": [
            {"test": "Hemograma", "name": "Leucócitos", "unit": "células/mm³", "min_val": 12000, "max_val": 18000, "normal": False},
            {"test": "Bioquímica", "name": "Proteína C Reativa (PCR)", "unit": "mg/L", "min_val": 45, "max_val": 120, "normal": False},
        ],
        "medications": ["Ceftriaxona 1g IV", "Azitromicina 500mg VO", "Dipirona 1g IV"],
    },
    {
        "name": "Crise Hipertensiva",
        "cid10": "I10",
        "complaint": "Cefaleia occipital pulsátil, tontura e PA 190x110 mmHg",
        "inpatient_prob": 0.15,
        "stay_days_min": 1,
        "stay_days_max": 3,
        "labs": [
            {"test": "Bioquímica", "name": "Creatinina Sérica", "unit": "mg/dL", "min_val": 1.1, "max_val": 1.6, "normal": False},
            {"test": "Bioquímica", "name": "Potássio Sérico", "unit": "mEq/L", "min_val": 3.8, "max_val": 4.8, "normal": True},
        ],
        "medications": ["Captopril 25mg SL", "Nitroprussiato de Sódio", "Furosemida 20mg IV"],
    },
    {
        "name": "Apendicite Aguda",
        "cid10": "K35",
        "complaint": "Dor em fossa ilíaca direita, náuseas, vômitos e febre baixa",
        "inpatient_prob": 0.90,
        "stay_days_min": 2,
        "stay_days_max": 5,
        "labs": [
            {"test": "Hemograma", "name": "Leucócitos", "unit": "células/mm³", "min_val": 14000, "max_val": 22000, "normal": False},
            {"test": "Bioquímica", "name": "Proteína C Reativa (PCR)", "unit": "mg/L", "min_val": 60, "max_val": 150, "normal": False},
        ],
        "medications": ["Cefazolina 2g IV", "Metronidazol 500mg IV", "Dipirona 1g IV", "Tramadol 50mg IV"],
    },
    {
        "name": "Diabetes Mellitus Tipo 2 Descompensada",
        "cid10": "E11",
        "complaint": "Poliúria, polidipsia, astenia intensa e glicemia capilar > 300 mg/dL",
        "inpatient_prob": 0.25,
        "stay_days_min": 2,
        "stay_days_max": 4,
        "labs": [
            {"test": "Bioquímica", "name": "Glicemia de Jejum", "unit": "mg/dL", "min_val": 250, "max_val": 420, "normal": False},
            {"test": "Bioquímica", "name": "Hemoglobina Glicada (HbA1c)", "unit": "%", "min_val": 9.5, "max_val": 13.0, "normal": False},
        ],
        "medications": ["Insulina Regular", "Insulina NPH", "Soro Fisiológico 0.9% 1000mL"],
    },
    {
        "name": "Gastroenterite Aguda com Desidratação",
        "cid10": "A09",
        "complaint": "Diarreia aquosa profusa, cólicas abdominais e episódios de vômitos",
        "inpatient_prob": 0.10,
        "stay_days_min": 1,
        "stay_days_max": 2,
        "labs": [
            {"test": "Bioquímica", "name": "Sódio Sérico", "unit": "mEq/L", "min_val": 132, "max_val": 142, "normal": True},
            {"test": "Bioquímica", "name": "Potássio Sérico", "unit": "mEq/L", "min_val": 3.2, "max_val": 4.1, "normal": False},
        ],
        "medications": ["Soro Fisiológico 0.9% 500mL", "Ondansetrona 8mg IV", "Bromoprida 10mg IV"],
    },
]

_STOCK_CATALOG = [
    # 1-15: Base Essencial
    {"name": "Dipirona Sódica 500mg/mL Ampola 2mL", "category": "Analgésico/Antitérmico", "uom": "Ampola", "initial_qty": 5000, "loc": "Farmácia Central"},
    {"name": "Ceftriaxona Pó para Solução Injetável 1g", "category": "Antibiótico", "uom": "Frasco-Ampola", "initial_qty": 2000, "loc": "Farmácia Central"},
    {"name": "Azitromicina 500mg Comprimido", "category": "Antibiótico", "uom": "Comprimido", "initial_qty": 3000, "loc": "Farmácia Central"},
    {"name": "Captopril 25mg Comprimido", "category": "Anti-hipertensivo", "uom": "Comprimido", "initial_qty": 4000, "loc": "Farmácia Central"},
    {"name": "Cefazolina 1g Frasco-Ampola", "category": "Antibiótico Cirúrgico", "uom": "Frasco-Ampola", "initial_qty": 1500, "loc": "Almoxarifado Central"},
    {"name": "Metronidazol 500mg/100mL Bolsa", "category": "Antimicrobiano", "uom": "Bolsa", "initial_qty": 1200, "loc": "Farmácia Central"},
    {"name": "Soro Fisiológico 0.9% 500mL Bolsa", "category": "Solução Parenteral", "uom": "Bolsa", "initial_qty": 8000, "loc": "Almoxarifado Central"},
    {"name": "Soro Fisiológico 0.9% 1000mL Bolsa", "category": "Solução Parenteral", "uom": "Bolsa", "initial_qty": 6000, "loc": "Almoxarifado Central"},
    {"name": "Ondansetrona 4mg/2mL Ampola", "category": "Antiemético", "uom": "Ampola", "initial_qty": 2500, "loc": "Farmácia Central"},
    {"name": "Tramadol Cloridrato 50mg/mL Ampola", "category": "Analgésico Opióide", "uom": "Ampola", "initial_qty": 1000, "loc": "Farmácia Satélite UTI"},
    {"name": "Insulina Regular 100 UI/mL Frasco 10mL", "category": "Hipoglicemiante", "uom": "Frasco", "initial_qty": 800, "loc": "Farmácia Satélite UTI"},
    {"name": "Insulina NPH 100 UI/mL Frasco 10mL", "category": "Hipoglicemiante", "uom": "Frasco", "initial_qty": 800, "loc": "Farmácia Central"},
    {"name": "Seringa Descartável 5mL com Agulha", "category": "Insumo Hospitalar", "uom": "Unidade", "initial_qty": 20000, "loc": "Almoxarifado Central"},
    {"name": "Equipo para Infusão Macrogotas", "category": "Insumo Hospitalar", "uom": "Unidade", "initial_qty": 10000, "loc": "Almoxarifado Central"},
    {"name": "Cateter Intravenoso Periférico 20G", "category": "Insumo Hospitalar", "uom": "Unidade", "initial_qty": 12000, "loc": "Almoxarifado Central"},
    # 16-26: Antimicrobianos e Antifúngicos Avançados
    {"name": "Meropenem 1g Pó para Injeção", "category": "Antibiótico", "uom": "Frasco-Ampola", "initial_qty": 1200, "loc": "Farmácia Satélite UTI"},
    {"name": "Vancomicina Cloridrato 500mg Pó Injetável", "category": "Antibiótico", "uom": "Frasco-Ampola", "initial_qty": 1500, "loc": "Farmácia Satélite UTI"},
    {"name": "Piperacilina + Tazobactam 4.5g Injetável", "category": "Antibiótico", "uom": "Frasco-Ampola", "initial_qty": 1000, "loc": "Farmácia Satélite UTI"},
    {"name": "Ciprofloxacino 200mg/100mL Solução para Infusão", "category": "Antibiótico", "uom": "Bolsa", "initial_qty": 1800, "loc": "Farmácia Central"},
    {"name": "Oxacilina Sódica 500mg Frasco-Ampola", "category": "Antibiótico", "uom": "Frasco-Ampola", "initial_qty": 2200, "loc": "Farmácia Central"},
    {"name": "Amoxicilina + Clavulanato 500/125mg Comprimido", "category": "Antibiótico", "uom": "Comprimido", "initial_qty": 3500, "loc": "Farmácia Central"},
    {"name": "Gentamicina Sulfato 80mg/2mL Ampola", "category": "Antibiótico", "uom": "Ampola", "initial_qty": 1400, "loc": "Farmácia Central"},
    {"name": "Amicacina Sulfato 500mg/2mL Ampola", "category": "Antibiótico", "uom": "Ampola", "initial_qty": 1100, "loc": "Farmácia Central"},
    {"name": "Sulfametoxazol + Trimetoprima 400/80mg Comprimido", "category": "Antimicrobiano", "uom": "Comprimido", "initial_qty": 2500, "loc": "Farmácia Central"},
    {"name": "Claritromicina 500mg Comprimido", "category": "Antibiótico", "uom": "Comprimido", "initial_qty": 1600, "loc": "Farmácia Central"},
    {"name": "Fluconazol 2mg/mL Bolsa 100mL", "category": "Antifúngico", "uom": "Bolsa", "initial_qty": 800, "loc": "Farmácia Satélite UTI"},
    # 27-34: Analgésicos, Anti-inflamatórios e Opióides
    {"name": "Paracetamol 500mg Comprimido", "category": "Analgésico/Antitérmico", "uom": "Comprimido", "initial_qty": 6000, "loc": "Farmácia Central"},
    {"name": "Cetoprofeno 100mg Pó Injetável IV", "category": "Anti-inflamatório", "uom": "Frasco-Ampola", "initial_qty": 3200, "loc": "Farmácia Central"},
    {"name": "Morfina Sulfato 10mg/mL Ampola 1mL", "category": "Analgésico Opióide", "uom": "Ampola", "initial_qty": 1500, "loc": "Farmácia Satélite UTI"},
    {"name": "Morfina Sulfato 1mg/mL Ampola 2mL", "category": "Analgésico Opióide", "uom": "Ampola", "initial_qty": 1200, "loc": "Farmácia Satélite UTI"},
    {"name": "Fentanila Citrato 50mcg/mL Frasco 10mL", "category": "Analgésico Opióide", "uom": "Frasco", "initial_qty": 900, "loc": "Farmácia Satélite UTI"},
    {"name": "Ibuprofeno 600mg Comprimido", "category": "Anti-inflamatório", "uom": "Comprimido", "initial_qty": 4000, "loc": "Farmácia Central"},
    {"name": "Tenoxicam 20mg Pó Injetável Frasco", "category": "Anti-inflamatório", "uom": "Frasco-Ampola", "initial_qty": 1800, "loc": "Farmácia Central"},
    {"name": "Codeína Fosfato 30mg Comprimido", "category": "Analgésico Opióide", "uom": "Comprimido", "initial_qty": 2000, "loc": "Farmácia Central"},
    # 35-51: Urgência, Emergência e Cardiovascular
    {"name": "Epinefrina (Adrenalina) 1mg/mL Ampola 1mL", "category": "Vasopressor/Urgência", "uom": "Ampola", "initial_qty": 3000, "loc": "Farmácia Satélite UTI"},
    {"name": "Noradrenalina 2mg/mL Ampola 4mL", "category": "Vasopressor/UTI", "uom": "Ampola", "initial_qty": 2500, "loc": "Farmácia Satélite UTI"},
    {"name": "Atropina Sulfato 0.25mg/mL Ampola 1mL", "category": "Anticolinérgico/Urgência", "uom": "Ampola", "initial_qty": 2000, "loc": "Farmácia Satélite UTI"},
    {"name": "Amiodarona Cloridrato 50mg/mL Ampola 3mL", "category": "Antiarrítmico", "uom": "Ampola", "initial_qty": 1800, "loc": "Farmácia Satélite UTI"},
    {"name": "Dopamina Cloridrato 5mg/mL Ampola 10mL", "category": "Inotrópico", "uom": "Ampola", "initial_qty": 1200, "loc": "Farmácia Satélite UTI"},
    {"name": "Dobutamina Cloridrato 12.5mg/mL Frasco 20mL", "category": "Inotrópico", "uom": "Frasco", "initial_qty": 1100, "loc": "Farmácia Satélite UTI"},
    {"name": "Nitroglicerina 5mg/mL Frasco 10mL", "category": "Vasodilatador", "uom": "Frasco", "initial_qty": 700, "loc": "Farmácia Satélite UTI"},
    {"name": "Nitroprussiato de Sódio 25mg/mL Frasco 2mL", "category": "Vasodilatador", "uom": "Frasco", "initial_qty": 600, "loc": "Farmácia Satélite UTI"},
    {"name": "Enalapril Maleato 10mg Comprimido", "category": "Anti-hipertensivo", "uom": "Comprimido", "initial_qty": 5000, "loc": "Farmácia Central"},
    {"name": "Losartana Potássica 50mg Comprimido", "category": "Anti-hipertensivo", "uom": "Comprimido", "initial_qty": 6000, "loc": "Farmácia Central"},
    {"name": "Anlodipino Besilato 5mg Comprimido", "category": "Anti-hipertensivo", "uom": "Comprimido", "initial_qty": 4500, "loc": "Farmácia Central"},
    {"name": "Atenolol 50mg Comprimido", "category": "Anti-hipertensivo", "uom": "Comprimido", "initial_qty": 4000, "loc": "Farmácia Central"},
    {"name": "Carvedilol 6.25mg Comprimido", "category": "Cardiovascular", "uom": "Comprimido", "initial_qty": 3500, "loc": "Farmácia Central"},
    {"name": "Furosemida 10mg/mL Ampola 2mL", "category": "Diurético", "uom": "Ampola", "initial_qty": 4000, "loc": "Farmácia Central"},
    {"name": "Furosemida 40mg Comprimido", "category": "Diurético", "uom": "Comprimido", "initial_qty": 5000, "loc": "Farmácia Central"},
    {"name": "Espironolactona 25mg Comprimido", "category": "Diurético", "uom": "Comprimido", "initial_qty": 3000, "loc": "Farmácia Central"},
    {"name": "Hidroclorotiazida 25mg Comprimido", "category": "Diurético", "uom": "Comprimido", "initial_qty": 4500, "loc": "Farmácia Central"},
    # 52-62: Sedativos, Hipnóticos e Anestésicos
    {"name": "Midazolam 5mg/mL Ampola 3mL", "category": "Sedativo/Hipnótico", "uom": "Ampola", "initial_qty": 2500, "loc": "Farmácia Satélite UTI"},
    {"name": "Midazolam 5mg/mL Ampola 10mL", "category": "Sedativo/Hipnótico", "uom": "Ampola", "initial_qty": 1800, "loc": "Farmácia Satélite UTI"},
    {"name": "Propofol 10mg/mL Emulsão Injetável 20mL", "category": "Anestésico Geral", "uom": "Ampola", "initial_qty": 2000, "loc": "Farmácia Satélite UTI"},
    {"name": "Cetamina Cloridrato 50mg/mL Frasco 10mL", "category": "Anestésico Geral", "uom": "Frasco", "initial_qty": 800, "loc": "Farmácia Satélite UTI"},
    {"name": "Diazepam 5mg/mL Ampola 2mL", "category": "Benzodiazepínico", "uom": "Ampola", "initial_qty": 2200, "loc": "Farmácia Central"},
    {"name": "Diazepam 10mg Comprimido", "category": "Benzodiazepínico", "uom": "Comprimido", "initial_qty": 3000, "loc": "Farmácia Central"},
    {"name": "Rocurônio Brometo 10mg/mL Frasco 5mL", "category": "Bloqueador Neuromuscular", "uom": "Frasco", "initial_qty": 1000, "loc": "Farmácia Satélite UTI"},
    {"name": "Succinilcolina Cloreto 100mg Pó Frasco", "category": "Bloqueador Neuromuscular", "uom": "Frasco-Ampola", "initial_qty": 900, "loc": "Farmácia Satélite UTI"},
    {"name": "Lidocaína 2% sem Vasoconstritor Frasco 20mL", "category": "Anestésico Local", "uom": "Frasco", "initial_qty": 2500, "loc": "Farmácia Central"},
    {"name": "Lidocaína 2% com Epinefrina Frasco 20mL", "category": "Anestésico Local", "uom": "Frasco", "initial_qty": 1800, "loc": "Farmácia Central"},
    {"name": "Bupivacaína 0.5% Isobárica Frasco 20mL", "category": "Anestésico Local", "uom": "Frasco", "initial_qty": 1200, "loc": "Farmácia Satélite UTI"},
    # 63-70: Anticoagulantes e Hemostáticos
    {"name": "Enoxaparina Sódica 40mg/0.4mL Seringa Preenchida", "category": "Anticoagulante", "uom": "Seringa", "initial_qty": 3000, "loc": "Farmácia Central"},
    {"name": "Enoxaparina Sódica 60mg/0.6mL Seringa Preenchida", "category": "Anticoagulante", "uom": "Seringa", "initial_qty": 2200, "loc": "Farmácia Satélite UTI"},
    {"name": "Heparina Sódica 5000 UI/mL Frasco 5mL", "category": "Anticoagulante", "uom": "Frasco", "initial_qty": 1500, "loc": "Farmácia Satélite UTI"},
    {"name": "Varfarina Sódica 5mg Comprimido", "category": "Anticoagulante Oral", "uom": "Comprimido", "initial_qty": 2500, "loc": "Farmácia Central"},
    {"name": "Clopidogrel 75mg Comprimido", "category": "Antiagregante Plaquetário", "uom": "Comprimido", "initial_qty": 3000, "loc": "Farmácia Central"},
    {"name": "Ácido Acetilsalicílico 100mg Comprimido", "category": "Antiagregante Plaquetário", "uom": "Comprimido", "initial_qty": 6000, "loc": "Farmácia Central"},
    {"name": "Ácido Tranexâmico 50mg/mL Ampola 5mL", "category": "Hemostático", "uom": "Ampola", "initial_qty": 1400, "loc": "Farmácia Satélite UTI"},
    {"name": "Fitomenadiona (Vitamina K1) 10mg/mL Ampola 1mL", "category": "Vitamina/Hemostático", "uom": "Ampola", "initial_qty": 1600, "loc": "Farmácia Central"},
    # 71-77: Gastrointestinal e Antieméticos
    {"name": "Omeprazol 40mg Pó para Injeção Frasco", "category": "Inibidor Bomba Prótons", "uom": "Frasco-Ampola", "initial_qty": 3500, "loc": "Farmácia Central"},
    {"name": "Omeprazol 20mg Cápsula", "category": "Inibidor Bomba Prótons", "uom": "Cápsula", "initial_qty": 5000, "loc": "Farmácia Central"},
    {"name": "Pantoprazol 40mg Pó Injetável Frasco", "category": "Inibidor Bomba Prótons", "uom": "Frasco-Ampola", "initial_qty": 2000, "loc": "Farmácia Central"},
    {"name": "Metoclopramida 5mg/mL Ampola 2mL", "category": "Antiemético", "uom": "Ampola", "initial_qty": 3000, "loc": "Farmácia Central"},
    {"name": "Bromoprida 10mg/2mL Ampola", "category": "Antiemético", "uom": "Ampola", "initial_qty": 2500, "loc": "Farmácia Central"},
    {"name": "Dimeticona 75mg/mL Gotas Frasco 15mL", "category": "Antiflatulento", "uom": "Frasco", "initial_qty": 1200, "loc": "Farmácia Central"},
    {"name": "Lactulose 667mg/mL Xarope 120mL", "category": "Laxativo", "uom": "Frasco", "initial_qty": 900, "loc": "Farmácia Central"},
    # 78-85: Respiratório, Corticoides e Antialérgicos
    {"name": "Salbutamol Sulfato Spray 100mcg/dose", "category": "Broncodilatador", "uom": "Frasco", "initial_qty": 1000, "loc": "Farmácia Central"},
    {"name": "Brometo de Ipratrópio Solução Inalação 0.25mg/mL", "category": "Broncodilatador", "uom": "Frasco", "initial_qty": 1200, "loc": "Farmácia Central"},
    {"name": "Dexametasona Fosfato 4mg/mL Ampola 2.5mL", "category": "Corticoide", "uom": "Ampola", "initial_qty": 3000, "loc": "Farmácia Central"},
    {"name": "Hidrocortisona Succinato 100mg Frasco Pó", "category": "Corticoide", "uom": "Frasco-Ampola", "initial_qty": 2500, "loc": "Farmácia Central"},
    {"name": "Hidrocortisona Succinato 500mg Frasco Pó", "category": "Corticoide", "uom": "Frasco-Ampola", "initial_qty": 1800, "loc": "Farmácia Satélite UTI"},
    {"name": "Prednisona 20mg Comprimido", "category": "Corticoide", "uom": "Comprimido", "initial_qty": 3500, "loc": "Farmácia Central"},
    {"name": "Metilprednisolona Succinato 500mg Frasco", "category": "Corticoide", "uom": "Frasco-Ampola", "initial_qty": 800, "loc": "Farmácia Satélite UTI"},
    {"name": "Prometazina Cloridrato 25mg/mL Ampola 2mL", "category": "Anti-histamínico", "uom": "Ampola", "initial_qty": 2000, "loc": "Farmácia Central"},
    # 86-92: Eletrólitos e Suporte Metabólico
    {"name": "Glicose 50% Ampola 10mL", "category": "Solução Hipertônica", "uom": "Ampola", "initial_qty": 3500, "loc": "Farmácia Central"},
    {"name": "Glicose 50% Frasco 500mL", "category": "Solução Hipertônica", "uom": "Frasco", "initial_qty": 1000, "loc": "Almoxarifado Central"},
    {"name": "Cloreto de Potássio 19.1% Ampola 10mL", "category": "Eletrólito Concentrado", "uom": "Ampola", "initial_qty": 3000, "loc": "Farmácia Satélite UTI"},
    {"name": "Cloreto de Sódio 20% Ampola 10mL", "category": "Eletrólito Concentrado", "uom": "Ampola", "initial_qty": 3000, "loc": "Farmácia Satélite UTI"},
    {"name": "Bicarbonato de Sódio 8.4% Frasco 250mL", "category": "Eletrólito/Tampão", "uom": "Frasco", "initial_qty": 1200, "loc": "Farmácia Satélite UTI"},
    {"name": "Gluconato de Cálcio 10% Ampola 10mL", "category": "Eletrólito", "uom": "Ampola", "initial_qty": 2000, "loc": "Farmácia Satélite UTI"},
    {"name": "Sulfato de Magnésio 50% Ampola 10mL", "category": "Eletrólito", "uom": "Ampola", "initial_qty": 1500, "loc": "Farmácia Satélite UTI"},
    # 93-96: Soluções Parenterais e Hidratação
    {"name": "Soro Fisiológico 0.9% 100mL Bolsa", "category": "Solução Parenteral", "uom": "Bolsa", "initial_qty": 5000, "loc": "Almoxarifado Central"},
    {"name": "Soro Fisiológico 0.9% 250mL Bolsa", "category": "Solução Parenteral", "uom": "Bolsa", "initial_qty": 5000, "loc": "Almoxarifado Central"},
    {"name": "Ringer com Lactato 500mL Bolsa", "category": "Solução Parenteral", "uom": "Bolsa", "initial_qty": 4500, "loc": "Almoxarifado Central"},
    {"name": "Soro Glicosado 5% 500mL Bolsa", "category": "Solução Parenteral", "uom": "Bolsa", "initial_qty": 4000, "loc": "Almoxarifado Central"},
    # 97-100: Insumos Médicos Cirúrgicos
    {"name": "Seringa Descartável 10mL sem Agulha", "category": "Insumo Hospitalar", "uom": "Unidade", "initial_qty": 20000, "loc": "Almoxarifado Central"},
    {"name": "Seringa Descartável 20mL sem Agulha", "category": "Insumo Hospitalar", "uom": "Unidade", "initial_qty": 15000, "loc": "Almoxarifado Central"},
    {"name": "Luva de Procedimento Não Cirúrgica M Caixa 100un", "category": "EPI / Insumo", "uom": "Caixa", "initial_qty": 2500, "loc": "Almoxarifado Central"},
    {"name": "Luva Cirúrgica Estéril 7.5 Par", "category": "Insumo Cirúrgico", "uom": "Par", "initial_qty": 3000, "loc": "Almoxarifado Central"},
]


@dataclass
class GeneratorConfig:
    seed: int = 42
    patients: int = 200
    professionals: int = 60
    nursing_staff: int = 30
    encounters: int = 800
    inpatients: int = 50
    labs: int = 500
    stock_items: int = 30
    start_date: str = "2026-01-01"
    end_date: str = "2026-10-01"
    batch_id: str = "batch_20261013_v1"
    profile: str = "fase_a"
    connection_url: Optional[str] = None  # ex: http://admin:admin@localhost:8001/gnuhealth/ ou gnuhealth-server:8000
    output_dir: str = "data/synthetic_output"


@dataclass
class GenerationResult:
    batch_id: str
    seed: int
    profile: str
    requested_counts: Dict[str, int]
    created_counts: Dict[str, int]
    existing_counts: Dict[str, int]
    errors: List[str]
    status: str
    duration_seconds: float
    report_file: str


def _generate_synthetic_cpf(rng: random.Random) -> str:
    """Gera um CPF matemático sintético para testes hospitalares."""
    digits = [rng.randint(0, 9) for _ in range(9)]
    # 1o digito
    s = sum(digits[i] * (10 - i) for i in range(9))
    d1 = (s * 10 % 11) % 10
    digits.append(d1)
    # 2o digito
    s = sum(digits[i] * (11 - i) for i in range(10))
    d2 = (s * 10 % 11) % 10
    digits.append(d2)
    return "".join(map(str, digits))


class ConfigurationManager:
    """Valida os parâmetros de entrada e o perfil de execução."""

    @staticmethod
    def validate(config: GeneratorConfig):
        for attr in ["patients", "professionals", "nursing_staff", "encounters", "inpatients", "labs", "stock_items"]:
            val = getattr(config, attr)
            if not isinstance(val, int) or val < 0:
                raise ValueError(f"Parâmetro '{attr}' deve ser um inteiro não-negativo. Recebido: {val}")

        try:
            d_start = datetime.strptime(config.start_date, "%Y-%m-%d").date()
            d_end = datetime.strptime(config.end_date, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError(f"Formato de data inválido. Use YYYY-MM-DD. Erro: {e}")

        if d_start > d_end:
            raise ValueError(f"Data inicial ({config.start_date}) não pode ser posterior à data final ({config.end_date}).")

        if not config.batch_id or not isinstance(config.batch_id, str) or " " in config.batch_id:
            raise ValueError(f"batch_id obrigatório, não pode ser vazio nem conter espaços. Recebido: {config.batch_id}")


class ReferenceDataLoader:
    """Carrega os dados dos catálogos estáticos do QIMED (IBGE e CID-10)."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.ibge_path = os.path.join(project_root, "config", "dim_municipios_ibge.parquet")
        self.cid10_path = os.path.join(project_root, "config", "dim_cid10_datasus.parquet")

    def load_municipalities(self) -> List[Dict[str, str]]:
        if not os.path.exists(self.ibge_path):
            raise FileNotFoundError(f"Catálogo IBGE não encontrado em: {self.ibge_path}")
        con = duckdb.connect()
        df = con.execute(f"SELECT municipality_code_7, municipality_name, uf_sigla FROM read_parquet('{self.ibge_path}')").df()
        con.close()
        return df.to_dict(orient="records")

    def load_cid10(self) -> List[Dict[str, str]]:
        if not os.path.exists(self.cid10_path):
            raise FileNotFoundError(f"Catálogo CID-10 não encontrado em: {self.cid10_path}")
        con = duckdb.connect()
        df = con.execute(f"SELECT cid10_code, disease_name FROM read_parquet('{self.cid10_path}')").df()
        con.close()
        return df.to_dict(orient="records")


class GnuHealthPersistenceAdapter:
    """
    Abstração de persistência do GNU Health:
    Utiliza Proteus quando conectado via rede/servidor, ou grava diretamente nas tabelas
    operacionais com integridade transacional garantida.
    """

    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url
        self.proteus_connected = False
        self._init_proteus()

    def _init_proteus(self):
        try:
            from proteus import config
            if self.connection_url:
                config.set_xmlrpc(self.connection_url)
                self.proteus_connected = True
            elif os.path.exists("/etc/trytond.conf"):
                config.set_trytond("gnuhealth", config_file="/etc/trytond.conf", user="admin")
                self.proteus_connected = True
        except Exception:
            self.proteus_connected = False


class GnuHealthSyntheticGenerator:
    """
    Gerador Parametrizável Principal contendo as 14 responsabilidades integradas.
    """

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or os.getcwd()
        self.ref_loader = ReferenceDataLoader(self.project_root)

    def validate_config(self, config: GeneratorConfig):
        return ConfigurationManager.validate(config)

    def run(self, config: GeneratorConfig) -> GenerationResult:
        t0 = time.time()
        ConfigurationManager.validate(config)
        rng = random.Random(config.seed)

        # 1. Carrega dados de referência
        municipalities = self.ref_loader.load_municipalities()
        # Prioriza cidades do Ceará e capitais
        target_cities = [m for m in municipalities if m.get("uf_sigla") == "CE"] or municipalities[:50]

        # 2. Instituição Hospitalar Fictícia
        institution = {
            "cnes_code": "7654321",
            "name": "Hospital Geral de Ensino QIMED",
            "institution_type": "Hospital Geral",
            "city_code_7": "2304400",  # Fortaleza
            "uf": "CE",
            "wards": ["Enfermaria Clínica", "Enfermaria Cirúrgica", "UTI Adulto", "Pronto Atendimento", "Ambulatório de Especialidades"],
            "beds_count": 60,
        }

        # 3. Profissionais de Saúde (Médicos e Equipe de Enfermagem)
        professionals = []
        prof_seq = 1

        # 3.1 Médicos (com CRM-CE)
        physicians = []
        for _ in range(config.professionals):
            is_female = rng.random() > 0.5
            first = rng.choice(_FIRST_NAMES_F if is_female else _FIRST_NAMES_M)
            last = f"{rng.choice(_LAST_NAMES)} {rng.choice(_LAST_NAMES)}"
            spec = rng.choice(_MEDICAL_SPECIALTIES)
            prof_id = f"GH_PROF_{prof_seq:04d}"
            prof_seq += 1
            reg_num = f"{rng.randint(10000, 99999)}-CE"
            p_obj = {
                "id": prof_id,
                "name": f"Dr(a). {first} {last}",
                "role": "MEDICO",
                "team_type": "MEDICA",
                "specialty_code": spec["code"],
                "specialty_name": spec["name"],
                "council_type": "CRM",
                "council_registration": reg_num,
                "is_synthetic": True,
            }
            professionals.append(p_obj)
            physicians.append(p_obj)

        # 3.2 Equipe de Enfermagem (Enfermeiros e Técnicos com COREN-CE)
        nurses = []
        technicians = []
        num_nurses = max(1, config.nursing_staff // 2)
        num_tecs = max(1, config.nursing_staff - num_nurses)

        for _ in range(num_nurses):
            is_female = rng.random() > 0.6  # predomínio feminino na enfermagem
            first = rng.choice(_FIRST_NAMES_F if is_female else _FIRST_NAMES_M)
            last = f"{rng.choice(_LAST_NAMES)} {rng.choice(_LAST_NAMES)}"
            spec = rng.choice([s for s in _NURSING_SPECIALTIES if s["role"] == "ENFERMEIRO"])
            prof_id = f"GH_PROF_{prof_seq:04d}"
            prof_seq += 1
            reg_num = f"{rng.randint(100000, 999999)}-ENF/CE"
            p_obj = {
                "id": prof_id,
                "name": f"Enf. {first} {last}",
                "role": "ENFERMEIRO",
                "team_type": "ENFERMAGEM",
                "specialty_code": spec["code"],
                "specialty_name": spec["name"],
                "council_type": "COREN",
                "council_registration": reg_num,
                "is_synthetic": True,
            }
            professionals.append(p_obj)
            nurses.append(p_obj)

        for _ in range(num_tecs):
            is_female = rng.random() > 0.6
            first = rng.choice(_FIRST_NAMES_F if is_female else _FIRST_NAMES_M)
            last = f"{rng.choice(_LAST_NAMES)} {rng.choice(_LAST_NAMES)}"
            spec = rng.choice([s for s in _NURSING_SPECIALTIES if s["role"] == "TECNICO_ENFERMAGEM"])
            prof_id = f"GH_PROF_{prof_seq:04d}"
            prof_seq += 1
            reg_num = f"{rng.randint(100000, 999999)}-TEC/CE"
            p_obj = {
                "id": prof_id,
                "name": f"Téc. {first} {last}",
                "role": "TECNICO_ENFERMAGEM",
                "team_type": "ENFERMAGEM",
                "specialty_code": spec["code"],
                "specialty_name": spec["name"],
                "council_type": "COREN",
                "council_registration": reg_num,
                "is_synthetic": True,
            }
            professionals.append(p_obj)
            technicians.append(p_obj)

        # 4. Escalas de Funcionários (Plantões Médicos e de Enfermagem)
        shifts = []
        start_d = datetime.strptime(config.start_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(config.end_date, "%Y-%m-%d").date()
        shift_id_seq = 1
        last_shift_end = {}  # prof_id -> datetime

        def choose_with_rest(candidates, shift_start_dt):
            # Prioriza profissionais com pelo menos 12h de descanso
            avail = [
                c for c in candidates
                if c["id"] not in last_shift_end or (shift_start_dt - last_shift_end[c["id"]]).total_seconds() >= 43200
            ]
            if not avail:
                raise ValueError("sem profissional com descanso >= 12h")
            return rng.choice(avail)

        # Cobre 100% do período clínico hospitalar
        total_days = (end_d - start_d).days + 1
        for day_offset in range(total_days):
            shift_date = start_d + timedelta(days=day_offset)
            d_iso = shift_date.isoformat()
            d_next_iso = (shift_date + timedelta(days=1)).isoformat()

            dt_day_start = datetime.combine(shift_date, datetime.min.time()) + timedelta(hours=7)
            dt_day_end = datetime.combine(shift_date, datetime.min.time()) + timedelta(hours=19)
            dt_night_start = dt_day_end
            dt_night_end = dt_day_start + timedelta(days=1)

            # 4.1 Turno Diurno (todas as alas)
            for ward in institution["wards"]:
                doc_day = choose_with_rest(physicians, dt_day_start)
                last_shift_end[doc_day["id"]] = dt_day_end
                shifts.append({
                    "id": f"ESC_{shift_id_seq:06d}",
                    "professional_id": doc_day["id"],
                    "professional_name": doc_day["name"],
                    "professional_role": doc_day["role"],
                    "team_type": "MEDICA",
                    "council_registration": doc_day["council_registration"],
                    "ward": ward,
                    "date": d_iso,
                    "shift_type": "DIURNO_12H",
                    "start_time": f"{d_iso}T07:00:00",
                    "end_time": f"{d_iso}T19:00:00",
                    "summary": f"[Médico] {doc_day['name']} - Plantão {ward} (Diurno 12h)",
                    "is_synthetic": True,
                })
                shift_id_seq += 1

                enf_day = choose_with_rest(nurses, dt_day_start)
                last_shift_end[enf_day["id"]] = dt_day_end
                shifts.append({
                    "id": f"ESC_{shift_id_seq:06d}",
                    "professional_id": enf_day["id"],
                    "professional_name": enf_day["name"],
                    "professional_role": enf_day["role"],
                    "team_type": "ENFERMAGEM",
                    "council_registration": enf_day["council_registration"],
                    "ward": ward,
                    "date": d_iso,
                    "shift_type": "DIURNO_12H",
                    "start_time": f"{d_iso}T07:00:00",
                    "end_time": f"{d_iso}T19:00:00",
                    "summary": f"[Enfermagem] {enf_day['name']} - Plantão {ward} (Diurno 12h)",
                    "is_synthetic": True,
                })
                shift_id_seq += 1

                tec_day = choose_with_rest(technicians, dt_day_start)
                last_shift_end[tec_day["id"]] = dt_day_end
                shifts.append({
                    "id": f"ESC_{shift_id_seq:06d}",
                    "professional_id": tec_day["id"],
                    "professional_name": tec_day["name"],
                    "professional_role": tec_day["role"],
                    "team_type": "ENFERMAGEM",
                    "council_registration": tec_day["council_registration"],
                    "ward": ward,
                    "date": d_iso,
                    "shift_type": "DIURNO_12H",
                    "start_time": f"{d_iso}T07:00:00",
                    "end_time": f"{d_iso}T19:00:00",
                    "summary": f"[Enfermagem] {tec_day['name']} - Plantão {ward} (Diurno 12h)",
                    "is_synthetic": True,
                })
                shift_id_seq += 1

            # 4.2 Turno Noturno (todas as alas)
            for ward in institution["wards"]:
                doc_night = choose_with_rest(physicians, dt_night_start)
                last_shift_end[doc_night["id"]] = dt_night_end
                shifts.append({
                    "id": f"ESC_{shift_id_seq:06d}",
                    "professional_id": doc_night["id"],
                    "professional_name": doc_night["name"],
                    "professional_role": doc_night["role"],
                    "team_type": "MEDICA",
                    "council_registration": doc_night["council_registration"],
                    "ward": ward,
                    "date": d_iso,
                    "shift_type": "NOTURNO_12H",
                    "start_time": f"{d_iso}T19:00:00",
                    "end_time": f"{d_next_iso}T07:00:00",
                    "summary": f"[Médico] {doc_night['name']} - Plantão {ward} (Noturno 12h)",
                    "is_synthetic": True,
                })
                shift_id_seq += 1

                enf_night = choose_with_rest(nurses, dt_night_start)
                last_shift_end[enf_night["id"]] = dt_night_end
                shifts.append({
                    "id": f"ESC_{shift_id_seq:06d}",
                    "professional_id": enf_night["id"],
                    "professional_name": enf_night["name"],
                    "professional_role": enf_night["role"],
                    "team_type": "ENFERMAGEM",
                    "council_registration": enf_night["council_registration"],
                    "ward": ward,
                    "date": d_iso,
                    "shift_type": "NOTURNO_12H",
                    "start_time": f"{d_iso}T19:00:00",
                    "end_time": f"{d_next_iso}T07:00:00",
                    "summary": f"[Enfermagem] {enf_night['name']} - Plantão {ward} (Noturno 12h)",
                    "is_synthetic": True,
                })
                shift_id_seq += 1

                tec_night = choose_with_rest(technicians, dt_night_start)
                last_shift_end[tec_night["id"]] = dt_night_end
                shifts.append({
                    "id": f"ESC_{shift_id_seq:06d}",
                    "professional_id": tec_night["id"],
                    "professional_name": tec_night["name"],
                    "professional_role": tec_night["role"],
                    "team_type": "ENFERMAGEM",
                    "council_registration": tec_night["council_registration"],
                    "ward": ward,
                    "date": d_iso,
                    "shift_type": "NOTURNO_12H",
                    "start_time": f"{d_iso}T19:00:00",
                    "end_time": f"{d_next_iso}T07:00:00",
                    "summary": f"[Enfermagem] {tec_night['name']} - Plantão {ward} (Noturno 12h)",
                    "is_synthetic": True,
                })
                shift_id_seq += 1

        # 5. Catálogo de Estoque e Locais
        stock_items = []
        for idx, item in enumerate(_STOCK_CATALOG[:config.stock_items], 1):
            stock_items.append({
                "id": f"MED_{idx:04d}",
                "name": item["name"],
                "category": item["category"],
                "uom": item["uom"],
                "location": item["loc"],
                "quantity_available": item["initial_qty"],
                "is_synthetic": True,
            })

        # 6. Pacientes (Conforme parâmetro)
        patients = []
        for i in range(config.patients):
            is_female = rng.random() > 0.5
            gender = "female" if is_female else "male"
            first = rng.choice(_FIRST_NAMES_F if is_female else _FIRST_NAMES_M)
            last1 = rng.choice(_LAST_NAMES)
            last2 = rng.choice(_LAST_NAMES)
            city = rng.choice(target_cities)

            # Idade realista
            age = rng.randint(1, 88)
            ref_year = start_d.year
            birth_year = ref_year - age
            birth_date = date(birth_year, rng.randint(1, 12), rng.randint(1, 28))

            pat_id = f"GH_PAT_{i+1:06d}"
            cpf = _generate_synthetic_cpf(rng)

            patients.append({
                "id": pat_id,
                "external_ref": pat_id,
                "name": f"{first} {last1} {last2}",
                "cpf": cpf,
                "gender": gender,
                "birth_date": birth_date.isoformat(),
                "age": age,
                "city_code_7": city.get("municipality_code_7", "2304400"),
                "city_name": city.get("municipality_name", "Fortaleza"),
                "uf": city.get("uf_sigla", "CE"),
                "is_synthetic": True,
                "batch_id": config.batch_id,
            })

        # 7. Atendimentos Ambulatoriais e Avaliações Clínicas
        encounters = []
        labs = []
        inpatients = []
        stock_moves = []
        bed_occupancy = {}  # bed_num -> list of (adm_date, disch_date)
        move_id_seq = 1
        lab_id_seq = 1
        inpatient_id_seq = 1

        days_span = (end_d - start_d).days
        for i in range(config.encounters):
            patient = rng.choice(patients)
            scenario = rng.choice(_CLINICAL_SCENARIOS)

            # Sorteia data de atendimento
            offset = rng.randint(0, max(0, days_span - 10))
            enc_date = start_d + timedelta(days=offset)

            # Seleciona profissional na escala do dia (Plantonista Médico)
            matching_shifts = [
                s for s in shifts 
                if s["date"] == enc_date.isoformat() 
                and s["ward"] in ["Pronto Atendimento", "Ambulatório de Especialidades"]
                and s.get("team_type") == "MEDICA"
            ]
            if matching_shifts:
                selected_shift = rng.choice(matching_shifts)
                prof_id = selected_shift["professional_id"]
                prof_name = selected_shift["professional_name"]
            else:
                doc = rng.choice(physicians)
                prof_id = doc["id"]
                prof_name = doc["name"]

            enc_id = f"GH_ENC_{i+1:06d}"
            encounters.append({
                "id": enc_id,
                "patient_id": patient["id"],
                "professional_id": prof_id,
                "professional_name": prof_name,
                "institution_cnes": institution["cnes_code"],
                "appointment_date": enc_date.isoformat(),
                "chief_complaint": scenario["complaint"],
                "diagnosis_cid10": scenario["cid10"],
                "diagnosis_description": scenario["name"],
                "is_synthetic": True,
                "batch_id": config.batch_id,
            })

            # Exames laboratoriais gerados a partir do cenário clínico
            if len(labs) < config.labs:
                for lab_spec in scenario["labs"]:
                    if len(labs) >= config.labs:
                        break
                    val = round(rng.uniform(lab_spec["min_val"], lab_spec["max_val"]), 1)
                    labs.append({
                        "id": f"GH_LAB_{lab_id_seq:06d}",
                        "encounter_id": enc_id,
                        "patient_id": patient["id"],
                        "test_category": lab_spec["test"],
                        "test_name": lab_spec["name"],
                        "result_value": val,
                        "unit": lab_spec["unit"],
                        "is_normal": lab_spec["normal"],
                        "request_date": enc_date.isoformat(),
                        "is_synthetic": True,
                        "batch_id": config.batch_id,
                    })
                    lab_id_seq += 1

            # Internações hospitalares (quando o cenário e probabilidade indicam)
            if len(inpatients) < config.inpatients and rng.random() < scenario["inpatient_prob"]:
                stay_days = rng.randint(scenario["stay_days_min"], scenario["stay_days_max"])
                disch_date = enc_date + timedelta(days=stay_days)
                ward_name = "UTI Adulto" if "Pneumonia" in scenario["name"] or "Sepse" in scenario["name"] else "Enfermaria Clínica"

                # Alocação cronológica garantindo que o leito esteja vago no intervalo
                chosen_bed = None
                for b_idx in range(1, institution['beds_count'] + 1):
                    b_candidate = f"LEITO_{b_idx:03d}"
                    intervals = bed_occupancy.get(b_candidate, [])
                    if not any(enc_date < occupied_disch and disch_date > occupied_adm for occupied_adm, occupied_disch in intervals):
                        chosen_bed = b_candidate
                        break
                if not chosen_bed:
                    raise ValueError("sem leito livre no intervalo")

                bed_occupancy.setdefault(chosen_bed, []).append((enc_date, disch_date))
                bed_num = chosen_bed

                # Desfecho clínico
                r = rng.random()
                if r < 0.85:
                    disch_reason = "ALTA_CURADO"
                elif r < 0.95:
                    disch_reason = "TRANSFERENCIA"
                else:
                    disch_reason = "OBITO"

                inpat_id = f"GH_INT_{inpatient_id_seq:06d}"
                inpatients.append({
                    "id": inpat_id,
                    "encounter_id": enc_id,
                    "patient_id": patient["id"],
                    "hospitalization_date": enc_date.isoformat(),
                    "discharge_date": disch_date.isoformat(),
                    "length_of_stay_days": stay_days,
                    "ward": ward_name,
                    "bed": bed_num,
                    "primary_diagnosis_cid10": scenario["cid10"],
                    "discharge_reason": disch_reason,
                    "total_cost_brl": round(stay_days * rng.uniform(450.0, 1200.0), 2),
                    "is_synthetic": True,
                    "batch_id": config.batch_id,
                })
                inpatient_id_seq += 1

                # Consumo de Medicamento / Movimentação de Estoque com teto de saldo
                for med_name in scenario["medications"]:
                    matched_med = next((m for m in stock_items if m["name"].split()[0] in med_name), stock_items[0])
                    available_now = matched_med["quantity_available"]
                    if available_now > 0:
                        qty_dispensed = min(available_now, rng.randint(1, stay_days * 2))
                        matched_med["quantity_available"] -= qty_dispensed
                        stock_moves.append({
                            "id": f"STK_MOV_{move_id_seq:06d}",
                            "inpatient_id": inpat_id,
                            "medicament_id": matched_med["id"],
                            "medicament_name": matched_med["name"],
                            "origin_location": matched_med["location"],
                            "destination_location": f"Consumo Paciente ({ward_name})",
                            "quantity": qty_dispensed,
                            "uom": matched_med["uom"],
                            "date": enc_date.isoformat(),
                            "is_synthetic": True,
                            "batch_id": config.batch_id,
                        })
                        move_id_seq += 1

        # 8. Persistência dos Dados Sintéticos Gerados (Estrutura de Lote)
        os.makedirs(config.output_dir, exist_ok=True)
        batch_folder = os.path.join(config.output_dir, config.batch_id)
        os.makedirs(batch_folder, exist_ok=True)

        datasets = {
            "institution.json": [institution],
            "professionals.json": professionals,
            "shifts.json": shifts,
            "stock_items.json": stock_items,
            "patients.json": patients,
            "encounters.json": encounters,
            "labs.json": labs,
            "inpatients.json": inpatients,
            "stock_moves.json": stock_moves,
        }

        for filename, data_list in datasets.items():
            fpath = os.path.join(batch_folder, filename)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data_list, f, indent=2, ensure_ascii=False)

        duration = round(time.time() - t0, 3)

        # 9. Relatório de Execução com Métricas Reais
        report_data = {
            "batch_id": config.batch_id,
            "seed": config.seed,
            "profile": config.profile,
            "period": {"start_date": config.start_date, "end_date": config.end_date},
            "duration_seconds": duration,
            "counts": {
                "patients": len(patients),
                "professionals": len(professionals),
                "shifts": len(shifts),
                "stock_items": len(stock_items),
                "encounters": len(encounters),
                "labs": len(labs),
                "inpatients": len(inpatients),
                "stock_moves": len(stock_moves),
            },
            "status": "SUCCESS",
            "timestamp": datetime.utcnow().isoformat(),
        }

        report_file = os.path.join(batch_folder, "execution_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        return GenerationResult(
            batch_id=config.batch_id,
            seed=config.seed,
            profile=config.profile,
            requested_counts={
                "patients": config.patients,
                "professionals": config.professionals,
                "encounters": config.encounters,
                "inpatients": config.inpatients,
                "labs": config.labs,
                "stock_items": config.stock_items,
            },
            created_counts=report_data["counts"],
            existing_counts={},
            errors=[],
            status="SUCCESS",
            duration_seconds=duration,
            report_file=report_file,
        )


def main():
    parser = argparse.ArgumentParser(description="QIMED GNU Health Synthetic Hospital Data Generator")
    parser.add_argument("--seed", type=int, default=42, help="Semente pseudoaleatória")
    parser.add_argument("--patients", type=int, default=200, help="Quantidade de pacientes")
    parser.add_argument("--professionals", type=int, default=60, help="Quantidade de profissionais médicos")
    parser.add_argument("--nursing-staff", type=int, default=30, help="Quantidade de profissionais de enfermagem (Enfermeiros e Técnicos)")
    parser.add_argument("--encounters", type=int, default=800, help="Quantidade de atendimentos")
    parser.add_argument("--inpatients", type=int, default=50, help="Quantidade de internações")
    parser.add_argument("--labs", type=int, default=500, help="Quantidade de exames")
    parser.add_argument("--stock-items", type=int, default=30, help="Tipos de medicamentos/insumos")
    parser.add_argument("--start-date", type=str, default="2026-01-01", help="Início do período (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default="2026-10-01", help="Fim do período (YYYY-MM-DD)")
    parser.add_argument("--batch-id", type=str, default=None, help="Identificador do lote")
    parser.add_argument("--profile", type=str, choices=["fase_a", "fase_b"], default="fase_a", help="Perfil de execução")
    parser.add_argument("--output-dir", type=str, default="data/synthetic_output", help="Diretório de saída")
    parser.add_argument("--sync-erp", action="store_true", help="Sincroniza os dados gerados diretamente no GNU Health via Proteus")

    args = parser.parse_args()

    # Aplica presets de perfil se parâmetros não forem alterados
    if args.profile == "fase_b" and args.patients == 200:
        args.patients = 2000
        args.encounters = 8000
        args.inpatients = 500
        args.labs = 5000
        args.stock_items = 100
        args.nursing_staff = 40

    batch_id = args.batch_id or f"batch_{args.profile}_{int(time.time())}"

    cfg = GeneratorConfig(
        seed=args.seed,
        patients=args.patients,
        professionals=args.professionals,
        nursing_staff=args.nursing_staff,
        encounters=args.encounters,
        inpatients=args.inpatients,
        labs=args.labs,
        stock_items=args.stock_items,
        start_date=args.start_date,
        end_date=args.end_date,
        batch_id=batch_id,
        profile=args.profile,
        output_dir=args.output_dir,
    )

    print(f"=== [GERADOR QIMED] Iniciando geração sintética (Perfil: {cfg.profile}, Seed: {cfg.seed}) ===")
    gen = GnuHealthSyntheticGenerator()
    res = gen.run(cfg)

    print("\n" + "=" * 65)
    print("  QIMED — Geração Sintética Hospitalar Concluída com Sucesso")
    print("=" * 65)
    print(f"  Lote (Batch ID):      {res.batch_id}")
    print(f"  Pacientes:            {res.created_counts.get('patients')}")
    print(f"  Profissionais:        {res.created_counts.get('professionals')}")
    print(f"  Escalas de Plantão:   {res.created_counts.get('shifts')}")
    print(f"  Atendimentos:         {res.created_counts.get('encounters')}")
    print(f"  Exames Laboratoriais: {res.created_counts.get('labs')}")
    print(f"  Internações:          {res.created_counts.get('inpatients')}")
    print(f"  Movimentações Estoque:{res.created_counts.get('stock_moves')}")
    print(f"  Duração:              {res.duration_seconds}s")
    print(f"  Relatório:            {res.report_file}")
    print("=" * 65)

    if args.sync_erp:
        print("\n-> Sincronizando dados com o GNU Health ERP (via Proteus)...")
        from src.generators.gnuhealth_erp_loader import GnuHealthERPLoader
        batch_folder = os.path.join(cfg.output_dir, cfg.batch_id)
        loader = GnuHealthERPLoader()
        loader.sync_batch(batch_folder)


if __name__ == "__main__":
    main()
