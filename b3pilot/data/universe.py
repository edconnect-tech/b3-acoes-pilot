"""Universo segmentado de ativos da B3: Blue Chips, Small & Mid Caps e Fora do Radar."""

from typing import List, Dict

# 1. Blue Chips e Grandes Empresas (IBOVESPA Tradicional)
BLUE_CHIPS = [
    "ABEV3.SA",
    "AXIA3.SA",
    "B3SA3.SA",
    "BBAS3.SA",
    "BBDC3.SA",
    "BBDC4.SA",
    "BBSE3.SA",
    "BPAC11.SA",
    "BRAP4.SA",
    "BRFS3.SA",
    "CCRO3.SA",
    "CMIG4.SA",
    "CPFE3.SA",
    "CPLE3.SA",
    "CSAN3.SA",
    "CSNA3.SA",
    "EGIE3.SA",
    "EMBJ3.SA",
    "EQTL3.SA",
    "GGBR4.SA",
    "ITSA4.SA",
    "ITUB4.SA",
    "JBSS32.SA",
    "KLBN11.SA",
    "PETR3.SA",
    "PETR4.SA",
    "PRIO3.SA",
    "RADL3.SA",
    "RAIL3.SA",
    "RENT3.SA",
    "SANB11.SA",
    "SBSP3.SA",
    "SUZB3.SA",
    "TAEE11.SA",
    "TIMS3.SA",
    "UGPA3.SA",
    "USIM5.SA",
    "VALE3.SA",
    "VBBR3.SA",
    "VIVT3.SA",
    "WEGE3.SA",
]

# 2. Small Caps, Mid Caps e Oportunidades Fora do Radar (Índice SMLL e nichos de alto crescimento)
SMALL_MID_CAPS = [
    "AGRO3.SA",   # BrasilAgro (Agronegócio e terras)
    "ALOS3.SA",   # Allos (Shoppings)
    "ALUP11.SA",  # Alupar (Transmissão de energia)
    "AURE3.SA",   # Auren Energia
    "BLAU3.SA",   # Blau Farmacêutica
    "BMOB3.SA",   # Bemobi Mobile Tech
    "CAML3.SA",   # Camil Alimentos
    "CEAB3.SA",   # C&A Modas
    "CURY3.SA",   # Cury Construtora (Alta rentabilidade/dividendos)
    "CYRE3.SA",   # Cyrela
    "DIRR3.SA",   # Direcional Engenharia
    "DXCO3.SA",   # Dexco (Deca/Duratex)
    "ENEV3.SA",   # Eneva (Gás e energia)
    "ENGI11.SA",  # Energisa
    "FIQE3.SA",   # Unifique Telecom
    "FLRY3.SA",   # Grupo Fleury
    "FRAS3.SA",   # Fras-le (Autopeças)
    "HAPV3.SA",   # Hapvida
    "HYPE3.SA",   # Hypera Pharma
    "INTB3.SA",   # Intelbras (Segurança e eletrônica)
    "IRBR3.SA",   # IRB Brasil Resseguros
    "JALL3.SA",   # Jalles Machado (Açúcar e etanol)
    "KEPL3.SA",   # Kepler Weber (Silos e armazenagem agrícola)
    "LAVV3.SA",   # Lavvi Incorporadora
    "LEVE3.SA",   # Mahle Metal Leve (Autopeças / Altos proventos)
    "LOGG3.SA",   # LOG Commercial Properties (Galpões logísticos)
    "LREN3.SA",   # Lojas Renner
    "MDIA3.SA",   # M. Dias Branco (Líder em massas e biscoitos)
    "MGLU3.SA",   # Magazine Luiza
    "MULT3.SA",   # Multiplan Shoppings
    "MYPK3.SA",   # Iochpe-Maxion (Autopeças global)
    "ODPV3.SA",   # Odontoprev
    "PLPL3.SA",   # Plano&Plano Construtora
    "PNVL3.SA",   # Dimed / Panvel Farmácias
    "POMO4.SA",   # Marcopolo (Carrocerias de ônibus / Exportação)
    "PORT3.SA",   # Wilson Sons (Operadora portuária)
    "POSI3.SA",   # Positivo Tecnologia
    "RAPT4.SA",   # Randoncorp (Implementos rodoviários)
    "RECV3.SA",   # PetroReconcavo (Junior Oil)
    "SEER3.SA",   # Ser Educacional
    "SHUL4.SA",   # Schulz Compressores
    "SIMH3.SA",   # Simpar (Holding logística)
    "SLCE3.SA",   # SLC Agrícola (Grãos e terras)
    "SMTO3.SA",   # São Martinho (Açúcar e etanol)
    "SOJA3.SA",   # Boa Safra Sementes
    "STBP3.SA",   # Santos Brasil (Terminais de contêineres)
    "TEND3.SA",   # Construtora Tenda
    "TGMA3.SA",   # Tegma Gestão Logística
    "TOTS3.SA",   # Totvs (Software empresarial líder)
    "TTEN3.SA",   # 3Tentos Agroindustrial
    "TUPY3.SA",   # Tupy Fundição
    "VAMO3.SA",   # Vamos (Locação de caminhões)
    "VLID3.SA",   # Valid (Certificação digital e identificação)
    "VULC3.SA",   # Vulcabras (Olympikus, Mizuno, Under Armour)
    "WIZC3.SA",   # Wiz Co (Corretagem de seguros e crédito)
    "YDUQ3.SA",   # Yduqs Educação
]

# Top 20 Liquidez Absoluta (Amostra rápida de Blue Chips)
TOP_LIQUID_TICKERS = [
    "PETR4.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "BBDC4.SA",
    "BBAS3.SA",
    "WEGE3.SA",
    "PRIO3.SA",
    "RENT3.SA",
    "AXIA3.SA",
    "GGBR4.SA",
    "SUZB3.SA",
    "RADL3.SA",
    "RAIL3.SA",
    "CPLE3.SA",
    "CMIG4.SA",
    "VIVT3.SA",
    "EQTL3.SA",
    "JBSS32.SA",
    "CSNA3.SA",
    "EMBJ3.SA",
]

# Universo Completo Combinado (~100 Ações com liquidez para Swing Trade)
B3_FULL_UNIVERSE = list(dict.fromkeys(BLUE_CHIPS + SMALL_MID_CAPS))


def get_universe(category: str = "all", top_only: bool = False) -> List[str]:
    """Retorna a lista de ativos conforme a categoria desejada.
    
    Categorias:
      - 'all': Todas as ações (~100 ativos entre grandes empresas e Small Caps).
      - 'small_caps': Apenas Small e Mid Caps (empresas menores e fora do radar).
      - 'blue_chips': Apenas empresas grandes / IBOVESPA tradicional.
      - 'top20': Amostra rápida das 20 maiores empresas da B3.
    """
    if top_only or category == "top20":
        return TOP_LIQUID_TICKERS.copy()
    elif category == "small_caps":
        return SMALL_MID_CAPS.copy()
    elif category == "blue_chips":
        return BLUE_CHIPS.copy()
    return B3_FULL_UNIVERSE.copy()
