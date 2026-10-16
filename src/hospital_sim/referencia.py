"""Tabelas de referencia do gerador (nomes sinteticos, mapa CBO, regras clinicas)."""
from __future__ import annotations

NOMES_F = [
    "Maria", "Ana", "Francisca", "Antônia", "Adriana", "Juliana", "Márcia", "Fernanda", "Patrícia", "Aline",
    "Sandra", "Camila", "Amanda", "Bruna", "Jéssica", "Letícia", "Júlia", "Luciana", "Vanessa", "Mariana",
    "Gabriela", "Raimunda", "Rafaela", "Daniela", "Larissa", "Beatriz", "Natália", "Cláudia", "Simone", "Débora",
    "Rita", "Carla", "Tatiana", "Priscila", "Lúcia", "Sebastiana", "Isabela", "Sofia", "Helena", "Valentina",
    "Alice", "Laura", "Manuela", "Cícera", "Josefa", "Elaine", "Rosângela", "Fabiana", "Kelly", "Renata",
]
NOMES_M = [
    "José", "João", "Antônio", "Francisco", "Carlos", "Paulo", "Pedro", "Lucas", "Luiz", "Marcos",
    "Luís", "Gabriel", "Rafael", "Daniel", "Marcelo", "Bruno", "Eduardo", "Felipe", "Raimundo", "Rodrigo",
    "Manoel", "Mateus", "André", "Fernando", "Fábio", "Leonardo", "Gustavo", "Guilherme", "Leandro", "Tiago",
    "Anderson", "Ricardo", "Márcio", "Jorge", "Sebastião", "Alexandre", "Roberto", "Edson", "Diego", "Vitor",
    "Sérgio", "Cícero", "Davi", "Arthur", "Heitor", "Bernardo", "Samuel", "Miguel", "Joaquim", "Severino",
]
SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes",
    "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa",
    "Rocha", "Dias", "Nascimento", "Andrade", "Moreira", "Nunes", "Marques", "Machado", "Mendes", "Freitas",
    "Cardoso", "Ramos", "Gonçalves", "Santana", "Teixeira", "Araújo", "Cavalcante", "Bezerra", "Holanda", "Farias",
    "Aragão", "Ponte", "Linhares", "Frota", "Prado", "Mesquita", "Sampaio", "Arruda", "Feitosa", "Monteiro",
    "Parente", "Albuquerque", "Brito", "Pinheiro", "Coelho", "Xavier", "Magalhães", "Queiroz", "Macedo", "Rebouças",
]

# Familias CBO (4 primeiros digitos) -> categoria profissional
FAMILIA_CBO = {
    "2251": "MEDICO", "2252": "MEDICO", "2253": "MEDICO",
    "2235": "ENFERMEIRO",
    "3222": "TECNICO_ENFERMAGEM",
}

# CBO de medicos -> especialidade usada na alocacao a setores (CBO 2002, MTE).
# CBO nao listado vira "OUTRA" (nao e alocado a escala de internacao).
CBO_ESPECIALIDADE = {
    "225125": "CLINICA_MEDICA", "225170": "CLINICA_MEDICA", "225142": "CLINICA_MEDICA",
    "225150": "MEDICINA_INTENSIVA",
    "225124": "PEDIATRIA",
    "225225": "CIRURGIA_GERAL", "225220": "CIRURGIA_GERAL", "225210": "CIRURGIA_CARDIOVASCULAR",
    "225203": "CIRURGIA_VASCULAR", "225230": "CIRURGIA_PEDIATRICA", "225240": "CIRURGIA_TORACICA",
    "225260": "NEUROCIRURGIA", "225270": "ORTOPEDIA", "225285": "UROLOGIA", "225235": "CIRURGIA_PLASTICA",
    "225151": "ANESTESIOLOGIA",
    "225250": "OBSTETRICIA",
    "225120": "CARDIOLOGIA", "225112": "NEUROLOGIA", "225103": "INFECTOLOGIA", "225109": "NEFROLOGIA",
    "225127": "PNEUMOLOGIA", "225165": "GASTROENTEROLOGIA", "225121": "ONCOLOGIA", "225185": "HEMATOLOGIA",
    "225320": "RADIOLOGIA",
}

# Listas da Portaria SVS/MS 344/1998 para itens do catalogo (controle especial)
CONTROLADOS = {
    "Morfina": "A1", "Fentanila": "A1", "Metadona": "A1",
    "Codeína": "A2", "Tramadol": "A2",
    "Midazolam": "B1", "Diazepam": "B1", "Clonazepam": "B1",
    "Cetamina": "C1", "Propofol": "C1", "Fenitoína": "C1",
}

# Regras de coerencia CID x sexo x idade (aplicadas no gerador e verificadas no lote).
_SO_FEMININO = {f"C{n}" for n in range(51, 59)} | {"D25", "D26", "D27", "D28"}
_SO_MASCULINO = {"C60", "C61", "C62", "C63", "D29"} | {f"N{n}" for n in range(40, 52)}
_SO_ADULTO = {"E11", "I10", "I11", "I20", "I21", "I25", "I48", "I50", "I63", "I64", "J44", "N18"}


def cid_compativel(cid3: str, sexo: str, idade: int) -> bool:
    c = (cid3 or "").upper()[:3]
    if c.startswith("O"):
        return sexo == "F" and 10 <= idade <= 55
    if c.startswith("P"):
        return idade < 1
    if c in _SO_FEMININO or (c[:2] in ("N7", "N8", "N9") and c != "N99"):
        return sexo == "F"
    if c in _SO_MASCULINO:
        return sexo == "M"
    if c in _SO_ADULTO:
        return idade >= 15
    return True
