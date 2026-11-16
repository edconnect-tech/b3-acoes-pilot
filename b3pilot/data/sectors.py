"""Mapeamento Setorial, Segmentos e Macro-Clusters de Risco da B3.

Mapeia cada ativo do universo B3 para seu setor oficial, subsetor e tags de macro-clusters
(fatores de risco sistêmico compartilhados e correlações intersetoriais).

Casos críticos mapeados:
- BBAS3: Banco tradicional com >35% da carteira exposta a Crédito Rural / Agronegócio.
  Em períodos de quebra de safra, queda de commodities agrícolas ou recuperação judicial de produtores,
  BBAS3 sofre correlação direta com ações de agronegócios (SOJA3, SMTO3, SLCE3, AGRO3, KEPL3, TTEN3).
- Petróleo & Combustíveis: PETR3/PETR4, PRIO3, RECV3, VBBR3, UGPA3, CSAN3 (sensíveis ao Brent).
- Mineração & Siderurgia: VALE3, BRAP4, CSNA3, GGBR4, USIM5 (sensíveis ao minério de ferro/China).
- Construção Civil: CYRE3, DIRR3, CURY3, TEND3, LAVV3, PLPL3 (sensíveis à taxa Selic e crédito imobiliário).
- Varejo & Consumo Cíclico: LREN3, MGLU3, CEAB3, ALOS3, MULT3 (sensíveis a juros e renda).
- Utilidades Públicas / Elétricas: TAEE11, CPLE3, CMIG4, EGIE3, ALUP11, ENGI11, EQTL3, SBSP3 (defensivas).
"""

from typing import Dict, Any, List, Set, Optional

# Definição dos Macro-Clusters de Risco (fatores que fazem ações subirem/caírem juntas)
CLUSTER_AGRO = "AGRONEGOCIO"                   # Produtores, sementes, açúcar, insumos e crédito rural
CLUSTER_OIL_GAS = "PETROLEO_E_GAS"             # Exploração, refino e distribuição de combustíveis
CLUSTER_METALS = "MINERACAO_E_SIDERURGIA"      # Minério de ferro, aço e metais básicos
CLUSTER_REAL_ESTATE = "CONSTRUCAO_CIVIL"       # Incorporadoras e construtoras residenciais
CLUSTER_RETAIL = "VAREJO_E_CONSUMO"            # Varejo discricionário, moda e bens de consumo
CLUSTER_BANKS = "FINANCEIRO_BANCOS"            # Grandes bancos comerciais e múltiplos
CLUSTER_UTILITIES = "UTILIDADE_PUBLICA"        # Transmissão, geração de energia e saneamento (defensivos)
CLUSTER_PULP_PAPER = "PAPEL_E_CELULOSE"        # Exportadoras de celulose e papel
CLUSTER_PROTEIN = "FRIGORIFICOS_PROTEINA"      # Proteína animal (carne bovina, frango e suína)
CLUSTER_HEALTH = "SAUDE_E_FARMACIA"            # Farmácias, hospitais, diagnósticos
CLUSTER_TECH_TELCO = "TECNOLOGIA_E_TELECOM"    # Software, TI e operadoras de telecomunicações
CLUSTER_CAPITAL_GOODS = "BENS_DE_CAPITAL"      # Máquinas, equipamentos e autopeças
CLUSTER_TRANSPORT = "LOGISTICA_E_TRANSPORTE"   # Rodovias, portos, ferrovias e locação de veículos
CLUSTER_EDUCATION = "EDUCACAO"                 # Ensino superior e profissionalizante

# Mapeamento de Correlação Intersetorial Cruzada (setores que sobem/caem juntos)
# Se você tiver exposição ao cluster chave, os clusters correlacionados também carregam risco conjunto.
CORRELATED_CLUSTERS_MAP: Dict[str, List[str]] = {
    CLUSTER_AGRO: [CLUSTER_AGRO],
    CLUSTER_OIL_GAS: [CLUSTER_OIL_GAS],
    CLUSTER_METALS: [CLUSTER_METALS],
    CLUSTER_REAL_ESTATE: [CLUSTER_REAL_ESTATE, CLUSTER_RETAIL],  # Ambos sofrem fortemente com Selic alta
    CLUSTER_RETAIL: [CLUSTER_RETAIL, CLUSTER_REAL_ESTATE],       # Sensibilidade idêntica à taxa de juros
    CLUSTER_BANKS: [CLUSTER_BANKS],
    CLUSTER_UTILITIES: [CLUSTER_UTILITIES],
    CLUSTER_PULP_PAPER: [CLUSTER_PULP_PAPER],
    CLUSTER_PROTEIN: [CLUSTER_PROTEIN],
    CLUSTER_HEALTH: [CLUSTER_HEALTH],
    CLUSTER_TECH_TELCO: [CLUSTER_TECH_TELCO],
    CLUSTER_CAPITAL_GOODS: [CLUSTER_CAPITAL_GOODS, CLUSTER_TRANSPORT],
    CLUSTER_TRANSPORT: [CLUSTER_TRANSPORT, CLUSTER_CAPITAL_GOODS],
    CLUSTER_EDUCATION: [CLUSTER_EDUCATION],
}

# Base de Dados Setorial Completa para Ativos da B3
B3_SECTORS_DATA: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # AGRONEGÓCIO & ATIVOS COM EXPOSIÇÃO RURAL DIRETA
    # =========================================================================
    "SOJA3": {
        "company": "Boa Safra Sementes",
        "sector": "Agronegócio",
        "subsector": "Sementes e Grãos",
        "clusters": [CLUSTER_AGRO],
        "macro_risk_note": "Sensível à quebra de safra de soja, clima e preços de grãos.",
    },
    "SMTO3": {
        "company": "São Martinho",
        "sector": "Agronegócio",
        "subsector": "Açúcar e Etanol",
        "clusters": [CLUSTER_AGRO],
        "macro_risk_note": "Sensível ao preço global do açúcar, etanol, clima e safra de cana.",
    },
    "AGRO3": {
        "company": "BrasilAgro",
        "sector": "Agronegócio",
        "subsector": "Produção Agrícola e Terras",
        "clusters": [CLUSTER_AGRO],
        "macro_risk_note": "Sensível aos preços de commodities agrícolas e valorização imobiliária rural.",
    },
    "SLCE3": {
        "company": "SLC Agrícola",
        "sector": "Agronegócio",
        "subsector": "Grãos e Fibras (Soja/Milho/Algodão)",
        "clusters": [CLUSTER_AGRO],
        "macro_risk_note": "Sensível ao preço internacional de grãos e produtividade por hectare.",
    },
    "TTEN3": {
        "company": "3Tentos Agroindustrial",
        "sector": "Agronegócio",
        "subsector": "Insumos e Processamento de Grãos",
        "clusters": [CLUSTER_AGRO],
        "macro_risk_note": "Cadeia do agronegócio: fertilizantes, sementes e esmagamento de soja.",
    },
    "KEPL3": {
        "company": "Kepler Weber",
        "sector": "Bens de Capital",
        "subsector": "Silos e Armazenagem Agrícola",
        "clusters": [CLUSTER_AGRO, CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Altamente dependente da capacidade de investimento do produtor rural e Plano Safra.",
    },
    "JALL3": {
        "company": "Jalles Machado",
        "sector": "Agronegócio",
        "subsector": "Açúcar e Etanol",
        "clusters": [CLUSTER_AGRO],
        "macro_risk_note": "Exposta à safra canavieira e preços de combustíveis/açúcar.",
    },
    "CAML3": {
        "company": "Camil Alimentos",
        "sector": "Consumo Não Cíclico",
        "subsector": "Alimentos Básicos (Arroz/Feijão)",
        "clusters": [CLUSTER_AGRO],
        "macro_risk_note": "Margens dependentes de preços de safras de arroz, feijão e peixes.",
    },
    # CASO ESPECIAL: BANCO DO BRASIL (Exposição Agrícola Estrutural)
    "BBAS3": {
        "company": "Banco do Brasil",
        "sector": "Financeiro",
        "subsector": "Bancos",
        "clusters": [CLUSTER_BANKS, CLUSTER_AGRO],  # Tag explícita de risco agropecuário
        "macro_risk_note": "Maior financiador do agronegócio do Brasil (>35% da carteira de crédito é rural). Em quebras de safra ou inadimplência agrícola (RJs rurais), BBAS3 sofre correlação com ações do agronegócio.",
    },

    # =========================================================================
    # FINANCEIRO, BANCOS E SEGUROS
    # =========================================================================
    "ITUB4": {
        "company": "Itaú Unibanco",
        "sector": "Financeiro",
        "subsector": "Bancos",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Sensível a spread de crédito, inadimplência e curva de juros.",
    },
    "ITSA4": {
        "company": "Itaúsa",
        "sector": "Financeiro",
        "subsector": "Holding Financeira",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Concentrada em dividendos e valor do Itaú Unibanco.",
    },
    "BBDC3": {
        "company": "Bradesco ON",
        "sector": "Financeiro",
        "subsector": "Bancos",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Sensível à inadimplência de varejo e seguros.",
    },
    "BBDC4": {
        "company": "Bradesco PN",
        "sector": "Financeiro",
        "subsector": "Bancos",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Sensível à inadimplência de varejo e seguros.",
    },
    "SANB11": {
        "company": "Santander Brasil",
        "sector": "Financeiro",
        "subsector": "Bancos",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Sensível a crédito consignado e spread bancário.",
    },
    "BPAC11": {
        "company": "BTG Pactual",
        "sector": "Financeiro",
        "subsector": "Banco de Investimentos",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Sensível a volume de mercado de capitais (IPOs, M&A) e wealth management.",
    },
    "B3SA3": {
        "company": "B3",
        "sector": "Financeiro",
        "subsector": "Infraestrutura Financeira",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Sensível ao volume diário negociado (ADTV) na bolsa e juros.",
    },
    "BBSE3": {
        "company": "BB Seguridade",
        "sector": "Financeiro",
        "subsector": "Seguros e Previdência",
        "clusters": [CLUSTER_BANKS, CLUSTER_AGRO],
        "macro_risk_note": "Seguro agrícola e previdência no canal Banco do Brasil.",
    },
    "IRBR3": {
        "company": "IRB Brasil Resseguros",
        "sector": "Financeiro",
        "subsector": "Resseguros",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Sinistralidade de grandes riscos e resseguro agrícola/industrial.",
    },
    "WIZC3": {
        "company": "Wiz Co",
        "sector": "Financeiro",
        "subsector": "Corretagem de Seguros",
        "clusters": [CLUSTER_BANKS],
        "macro_risk_note": "Distribuição de seguros e consórcios bancários.",
    },

    # =========================================================================
    # PETRÓLEO, GÁS & COMBUSTÍVEIS
    # =========================================================================
    "PETR3": {
        "company": "Petrobras ON",
        "sector": "Petróleo e Gás",
        "subsector": "Exploração e Refino",
        "clusters": [CLUSTER_OIL_GAS],
        "macro_risk_note": "Sensível à cotação internacional do petróleo Brent e política de dividendos.",
    },
    "PETR4": {
        "company": "Petrobras PN",
        "sector": "Petróleo e Gás",
        "subsector": "Exploração e Refino",
        "clusters": [CLUSTER_OIL_GAS],
        "macro_risk_note": "Sensível à cotação internacional do petróleo Brent e dividendos.",
    },
    "PRIO3": {
        "company": "PRIO (PetroRio)",
        "sector": "Petróleo e Gás",
        "subsector": "Exploração Independente",
        "clusters": [CLUSTER_OIL_GAS],
        "macro_risk_note": "100% exposta à cotação do Brent e eficiência de campos maduros.",
    },
    "RECV3": {
        "company": "PetroReconcavo",
        "sector": "Petróleo e Gás",
        "subsector": "Exploração Onshore",
        "clusters": [CLUSTER_OIL_GAS],
        "macro_risk_note": "Exposta ao Brent e escoamento de gás natural em bacias terrestres.",
    },
    "UGPA3": {
        "company": "Ultrapar",
        "sector": "Petróleo e Gás",
        "subsector": "Distribuição de Combustíveis (Ipiranga)",
        "clusters": [CLUSTER_OIL_GAS],
        "macro_risk_note": "Margem de refino, preços de combustíveis e GLP.",
    },
    "VBBR3": {
        "company": "Vibra Energia",
        "sector": "Petróleo e Gás",
        "subsector": "Distribuição de Combustíveis (Postos BR)",
        "clusters": [CLUSTER_OIL_GAS],
        "macro_risk_note": "Volume de diesel/gasolina e concorrência no refino.",
    },
    "CSAN3": {
        "company": "Cosan",
        "sector": "Petróleo e Gás",
        "subsector": "Holding de Energia e Combustíveis",
        "clusters": [CLUSTER_OIL_GAS, CLUSTER_AGRO],
        "macro_risk_note": "Holding com Raízen (combustíveis/etanol), Rumo (ferrovias) e Compass (gás).",
    },

    # =========================================================================
    # MINERAÇÃO, SIDERURGIA & MATERIAIS BÁSICOS
    # =========================================================================
    "VALE3": {
        "company": "Vale",
        "sector": "Materiais Básicos",
        "subsector": "Mineração",
        "clusters": [CLUSTER_METALS],
        "macro_risk_note": "Sensível ao preço do minério de ferro em Qingdao e demanda de aço na China.",
    },
    "BRAP4": {
        "company": "Bradespar",
        "sector": "Materiais Básicos",
        "subsector": "Holding de Mineração",
        "clusters": [CLUSTER_METALS],
        "macro_risk_note": "Praticamente 100% espelho da cotação e proventos da Vale.",
    },
    "CSNA3": {
        "company": "CSN",
        "sector": "Materiais Básicos",
        "subsector": "Siderurgia e Mineração",
        "clusters": [CLUSTER_METALS],
        "macro_risk_note": "Alavancagem financeira, preço do aço e minério de ferro.",
    },
    "GGBR4": {
        "company": "Gerdau",
        "sector": "Materiais Básicos",
        "subsector": "Siderurgia de Aços Longos",
        "clusters": [CLUSTER_METALS],
        "macro_risk_note": "Demanda de aço para construção civil nos EUA e no Brasil.",
    },
    "USIM5": {
        "company": "Usiminas",
        "sector": "Materiais Básicos",
        "subsector": "Siderurgia de Aços Planos",
        "clusters": [CLUSTER_METALS],
        "macro_risk_note": "Fornecimento para montadoras automotivas e bens industriais.",
    },

    # =========================================================================
    # CONSTRUÇÃO CIVIL & INCORPORAÇÃO (Alta Sensibilidade a Juros)
    # =========================================================================
    "CYRE3": {
        "company": "Cyrela",
        "sector": "Construção Civil",
        "subsector": "Incorporação Residencial",
        "clusters": [CLUSTER_REAL_ESTATE],
        "macro_risk_note": "Sensível à taxa Selic, juros de financiamento habitacional e custo INCC.",
    },
    "DIRR3": {
        "company": "Direcional Engenharia",
        "sector": "Construção Civil",
        "subsector": "Habitação Popular e Média Renda",
        "clusters": [CLUSTER_REAL_ESTATE],
        "macro_risk_note": "Exposta a programas habitacionais governamentais e subsídios.",
    },
    "CURY3": {
        "company": "Cury Construtora",
        "sector": "Construção Civil",
        "subsector": "Habitação Econômica",
        "clusters": [CLUSTER_REAL_ESTATE],
        "macro_risk_note": "Sensível a custos de construção e programas de habitação popular.",
    },
    "TEND3": {
        "company": "Tenda",
        "sector": "Construção Civil",
        "subsector": "Habitação de Baixa Renda",
        "clusters": [CLUSTER_REAL_ESTATE],
        "macro_risk_note": "Margem operacional e custos de materiais (aço, cimento).",
    },
    "LAVV3": {
        "company": "Lavvi Incorporadora",
        "sector": "Construção Civil",
        "subsector": "Incorporação Médio e Alto Padrão",
        "clusters": [CLUSTER_REAL_ESTATE],
        "macro_risk_note": "Sensível a juros imobiliários em São Paulo.",
    },
    "PLPL3": {
        "company": "Plano&Plano",
        "sector": "Construção Civil",
        "subsector": "Habitação Econômica",
        "clusters": [CLUSTER_REAL_ESTATE],
        "macro_risk_note": "Sensível a funding habitacional e custo de mão de obra.",
    },

    # =========================================================================
    # VAREJO, SHOPPINGS & CONSUMO DISCRICIONÁRIO
    # =========================================================================
    "LREN3": {
        "company": "Lojas Renner",
        "sector": "Consumo Cíclico",
        "subsector": "Varejo de Moda",
        "clusters": [CLUSTER_RETAIL],
        "macro_risk_note": "Sensível ao poder de compra das famílias, crédito ao consumidor e clima de estação.",
    },
    "MGLU3": {
        "company": "Magazine Luiza",
        "sector": "Consumo Cíclico",
        "subsector": "E-commerce e Eletrodomésticos",
        "clusters": [CLUSTER_RETAIL],
        "macro_risk_note": "Altamente sensível a taxa Selic, carnê e demanda por bens duráveis.",
    },
    "CEAB3": {
        "company": "C&A Modas",
        "sector": "Consumo Cíclico",
        "subsector": "Varejo de Vestuário",
        "clusters": [CLUSTER_RETAIL],
        "macro_risk_note": "Sensível ao consumo de vestuário e serviços financeiros próprios.",
    },
    "ALOS3": {
        "company": "Allos",
        "sector": "Consumo Cíclico",
        "subsector": "Shopping Centers",
        "clusters": [CLUSTER_RETAIL],
        "macro_risk_note": "Vendas dos lojistas, fluxo de shopping e taxa de vacância.",
    },
    "MULT3": {
        "company": "Multiplan",
        "sector": "Consumo Cíclico",
        "subsector": "Shopping Centers Alto Padrão",
        "clusters": [CLUSTER_RETAIL],
        "macro_risk_note": "Fluxo e vendas em shoppings de alta renda.",
    },
    "VULC3": {
        "company": "Vulcabras",
        "sector": "Consumo Cíclico",
        "subsector": "Calçados Esportivos (Olympikus/Mizuno)",
        "clusters": [CLUSTER_RETAIL],
        "macro_risk_note": "Consumo esportivo e custos de matérias-primas sintéticas.",
    },

    # =========================================================================
    # ENERGIA ELÉTRICA & SANEAMENTO (UTILIDADE PÚBLICA - DEFENSIVOS)
    # =========================================================================
    "TAEE11": {
        "company": "Taesa",
        "sector": "Utilidade Pública",
        "subsector": "Transmissão de Energia",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Receita anual permitida (RAP) indexada à inflação (IGP-M/IPCA).",
    },
    "ALUP11": {
        "company": "Alupar",
        "sector": "Utilidade Pública",
        "subsector": "Transmissão e Geração de Energia",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Contratos de transmissão de longo prazo e juros reais longos (NTN-B).",
    },
    "CPLE3": {
        "company": "Copel",
        "sector": "Utilidade Pública",
        "subsector": "Geração, Transmissão e Distribuição",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Privatizada; sensível ao regime hídrico e tarifas de distribuição.",
    },
    "CPFE3": {
        "company": "CPFL Energia",
        "sector": "Utilidade Pública",
        "subsector": "Distribuição e Geração de Energia",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Mercado cativo de energia, perdas técnicas e reajustes Aneel.",
    },
    "CMIG4": {
        "company": "Cmig",
        "sector": "Utilidade Pública",
        "subsector": "Geração e Distribuição de Energia",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Risco regulatório estadual (Minas Gerais) e regime hídrico.",
    },
    "EGIE3": {
        "company": "Engie Brasil",
        "sector": "Utilidade Pública",
        "subsector": "Geração Renovável e Transmissão",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Preço de liquidação de diferenças (PLD) e recursos hídricos/eólicos.",
    },
    "ENGI11": {
        "company": "Energisa",
        "sector": "Utilidade Pública",
        "subsector": "Distribuição e Transmissão",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Concessões de distribuição no Centro-Oeste/Norte e expansão em transmissão.",
    },
    "EQTL3": {
        "company": "Equatorial Energia",
        "sector": "Utilidade Pública",
        "subsector": "Distribuição e Saneamento",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Turnaround de concessionárias adquiridas e taxa de desconto regulatória.",
    },
    "AURE3": {
        "company": "Auren Energia",
        "sector": "Utilidade Pública",
        "subsector": "Geração de Energia Renovável",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Comercialização de energia no mercado livre e eólica/solar.",
    },
    "ENEV3": {
        "company": "Eneva",
        "sector": "Utilidade Pública",
        "subsector": "Térmicas a Gás e Exploração",
        "clusters": [CLUSTER_UTILITIES, CLUSTER_OIL_GAS],
        "macro_risk_note": "Despacho térmico emergencial em períodos de seca e gás onshore.",
    },
    "SBSP3": {
        "company": "Sabesp",
        "sector": "Utilidade Pública",
        "subsector": "Água e Saneamento",
        "clusters": [CLUSTER_UTILITIES],
        "macro_risk_note": "Marco do saneamento, tarifas da Arsesp e investimentos em universalização.",
    },

    # =========================================================================
    # PAPEL E CELULOSE
    # =========================================================================
    "SUZB3": {
        "company": "Suzano",
        "sector": "Materiais Básicos",
        "subsector": "Papel e Celulose",
        "clusters": [CLUSTER_PULP_PAPER],
        "macro_risk_note": "Sensível ao preço global da tonelada de celulose BHKP e taxa de câmbio USD/BRL.",
    },
    "KLBN11": {
        "company": "Klabin",
        "sector": "Materiais Básicos",
        "subsector": "Papel, Embalagens e Celulose",
        "clusters": [CLUSTER_PULP_PAPER],
        "macro_risk_note": "Exposta a papelão ondulado, caixas para exportação e celulose.",
    },
    "DXCO3": {
        "company": "Dexco (Deca/Duratex)",
        "sector": "Materiais Básicos",
        "subsector": "Painéis de Madeira e Louças",
        "clusters": [CLUSTER_PULP_PAPER, CLUSTER_REAL_ESTATE],
        "macro_risk_note": "Reformas e acabamentos para construção civil.",
    },

    # =========================================================================
    # FRIGORÍFICOS / PROTEÍNA ANIMAL
    # =========================================================================
    "JBSS3": {
        "company": "JBS",
        "sector": "Consumo Não Cíclico",
        "subsector": "Carnes e Derivados (Global)",
        "clusters": [CLUSTER_PROTEIN],
        "macro_risk_note": "Ciclo do gado nos EUA, custos de grãos para ração e demanda global de proteína.",
    },
    "BRFS3": {
        "company": "BRF",
        "sector": "Consumo Não Cíclico",
        "subsector": "Aves e Suínos (Sadia/Perdigão)",
        "clusters": [CLUSTER_PROTEIN],
        "macro_risk_note": "Custo de milho/soja para ração, influenza aviária e exportações.",
    },

    # =========================================================================
    # SAÚDE & FARMÁCIA (DEFENSIVOS)
    # =========================================================================
    "RADL3": {
        "company": "RaiaDrogasil",
        "sector": "Saúde",
        "subsector": "Varejo Farmacêutico",
        "clusters": [CLUSTER_HEALTH],
        "macro_risk_note": "Reajuste anual de medicamentos pela CMED e expansão de lojas físicas.",
    },
    "PNVL3": {
        "company": "Dimed / Panvel",
        "sector": "Saúde",
        "subsector": "Varejo Farmacêutico",
        "clusters": [CLUSTER_HEALTH],
        "macro_risk_note": "Consumo de remédios e higiene no Sul e Sudeste.",
    },
    "HAPV3": {
        "company": "Hapvida",
        "sector": "Saúde",
        "subsector": "Planos de Saúde e Hospitais",
        "clusters": [CLUSTER_HEALTH],
        "macro_risk_note": "Taxa de sinistralidade médica (MLR), inflação médica e reajustes da ANS.",
    },
    "FLRY3": {
        "company": "Grupo Fleury",
        "sector": "Saúde",
        "subsector": "Medicina Diagnóstica e Exames",
        "clusters": [CLUSTER_HEALTH],
        "macro_risk_note": "Volume de procedimentos eletivos e parcerias com operadoras de saúde.",
    },
    "HYPE3": {
        "company": "Hypera Pharma",
        "sector": "Saúde",
        "subsector": "Medicamentos e Consumo",
        "clusters": [CLUSTER_HEALTH],
        "macro_risk_note": "Vendas de genéricos, medicamentos de prescrição e OTC.",
    },
    "BLAU3": {
        "company": "Blau Farmacêutica",
        "sector": "Saúde",
        "subsector": "Medicamentos Hospitalares",
        "clusters": [CLUSTER_HEALTH],
        "macro_risk_note": "Demanda hospitalar de medicamentos de alta complexidade e oncologia.",
    },
    "ODPV3": {
        "company": "Odontoprev",
        "sector": "Saúde",
        "subsector": "Planos Odontológicos",
        "clusters": [CLUSTER_HEALTH],
        "macro_risk_note": "Sinistralidade odontológica e planos corporativos de benefícios.",
    },

    # =========================================================================
    # BENS DE CAPITAL, TRANSPORTE & LOGÍSTICA
    # =========================================================================
    "WEGE3": {
        "company": "WEG",
        "sector": "Bens Industriais",
        "subsector": "Motores Elétricos e Equipamentos",
        "clusters": [CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Geração eólica/solar, motores industriais no exterior e taxa de câmbio.",
    },
    "EMBJ3": {
        "company": "Embraer",
        "sector": "Bens Industriais",
        "subsector": "Aeroespacial e Defesa",
        "clusters": [CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Entregas de jatos executivos/comerciais (E2) e contratos globais de defesa em dólar.",
    },
    "CCRO3": {
        "company": "Grupo CCR",
        "sector": "Bens Industriais",
        "subsector": "Concessões Rodoviárias e Mobilidade",
        "clusters": [CLUSTER_TRANSPORT],
        "macro_risk_note": "Tráfego de pedágios, transporte de cargas e passageiros em aeroportos/metrô.",
    },
    "RAIL3": {
        "company": "Rumo Logística",
        "sector": "Bens Industriais",
        "subsector": "Ferrovias de Carga",
        "clusters": [CLUSTER_TRANSPORT, CLUSTER_AGRO],
        "macro_risk_note": "Escoamento de safra agrícola do Centro-Oeste até o Porto de Santos.",
    },
    "RENT3": {
        "company": "Localiza",
        "sector": "Bens Industriais",
        "subsector": "Aluguel de Carros e Gestão de Frotas",
        "clusters": [CLUSTER_TRANSPORT],
        "macro_risk_note": "Preços de seminovos, juros para financiamento de frotas e demanda corporativa.",
    },
    "VAMO3": {
        "company": "Vamos",
        "sector": "Bens Industriais",
        "subsector": "Locação de Caminhões e Máquinas",
        "clusters": [CLUSTER_TRANSPORT, CLUSTER_AGRO],
        "macro_risk_note": "Locação de caminhões para agronegócio e renovação de maquinário pesado.",
    },
    "SIMH3": {
        "company": "Simpar",
        "sector": "Bens Industriais",
        "subsector": "Holding Logística (JSL/Vamos/Movida)",
        "clusters": [CLUSTER_TRANSPORT],
        "macro_risk_note": "Alavancagem consolidada e demanda por serviços logísticos dedicados.",
    },
    "TGMA3": {
        "company": "Tegma Gestão Logística",
        "sector": "Bens Industriais",
        "subsector": "Transporte de Veículos Novos",
        "clusters": [CLUSTER_TRANSPORT],
        "macro_risk_note": "Produção e venda de automóveis zero km no Brasil.",
    },
    "PORT3": {
        "company": "Wilson Sons",
        "sector": "Bens Industriais",
        "subsector": "Operações Portuárias e Rebocadores",
        "clusters": [CLUSTER_TRANSPORT],
        "macro_risk_note": "Comércio exterior, movimentação de contêineres e apoio marítimo offshore.",
    },
    "STBP3": {
        "company": "Santos Brasil",
        "sector": "Bens Industriais",
        "subsector": "Terminais Portuários de Contêineres",
        "clusters": [CLUSTER_TRANSPORT],
        "macro_risk_note": "Movimentação portuária de importação/exportação no Porto de Santos.",
    },
    "POMO4": {
        "company": "Marcopolo",
        "sector": "Bens Industriais",
        "subsector": "Carrocerias de Ônibus",
        "clusters": [CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Renovação de frotas de transporte público e programa Caminho da Escola.",
    },
    "RAPT4": {
        "company": "Randoncorp",
        "sector": "Bens Industriais",
        "subsector": "Implementos Rodoviários e Autopeças",
        "clusters": [CLUSTER_CAPITAL_GOODS, CLUSTER_AGRO],
        "macro_risk_note": "Vendas de reboques/semirreboques muito atreladas ao agronegócio.",
    },
    "FRAS3": {
        "company": "Fras-le",
        "sector": "Bens Industriais",
        "subsector": "Materiais de Fricção e Freios",
        "clusters": [CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Mercado de reposição automotiva global e montadoras.",
    },
    "MYPK3": {
        "company": "Iochpe-Maxion",
        "sector": "Bens Industriais",
        "subsector": "Rodas e Componentes Automotivos",
        "clusters": [CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Produção de veículos leves e pesados nas Américas e Europa.",
    },
    "LEVE3": {
        "company": "Mahle Metal Leve",
        "sector": "Bens Industriais",
        "subsector": "Componentes de Motores",
        "clusters": [CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Reposição de autopeças de motores a combustão.",
    },
    "SHUL4": {
        "company": "Schulz",
        "sector": "Bens Industriais",
        "subsector": "Compressores e Fundição Automotiva",
        "clusters": [CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Exportações de compressores de ar e peças automotivas.",
    },
    "TUPY3": {
        "company": "Tupy",
        "sector": "Bens Industriais",
        "subsector": "Fundição de Blocos e Cabeçotes",
        "clusters": [CLUSTER_CAPITAL_GOODS],
        "macro_risk_note": "Veículos comerciais pesados nos EUA e Europa.",
    },

    # =========================================================================
    # BEBIDAS E ALIMENTOS
    # =========================================================================
    "ABEV3": {
        "company": "Ambev",
        "sector": "Consumo Não Cíclico",
        "subsector": "Cervejas e Refrigerantes",
        "clusters": [CLUSTER_RETAIL],
        "macro_risk_note": "Custos de alumínio, cevada e poder de consumo da população.",
    },
    "MDIA3": {
        "company": "M. Dias Branco",
        "sector": "Consumo Não Cíclico",
        "subsector": "Massas e Biscoitos",
        "clusters": [CLUSTER_RETAIL, CLUSTER_AGRO],
        "macro_risk_note": "Custo de trigo em dólar e óleo de palma; consumo básico.",
    },

    # =========================================================================
    # TECNOLOGIA & TELECOMUNICAÇÕES
    # =========================================================================
    "TOTS3": {
        "company": "Totvs",
        "sector": "Tecnologia",
        "subsector": "Software Corporativo (ERP)",
        "clusters": [CLUSTER_TECH_TELCO],
        "macro_risk_note": "Receita recorrente contratada (SaaS) e investimentos de empresas de médio porte.",
    },
    "POSI3": {
        "company": "Positivo Tecnologia",
        "sector": "Tecnologia",
        "subsector": "Hardware e Soluções Governamentais",
        "clusters": [CLUSTER_TECH_TELCO],
        "macro_risk_note": "Licitações públicas de computadores/urnas e custos de semicondutores.",
    },
    "INTB3": {
        "company": "Intelbras",
        "sector": "Tecnologia",
        "subsector": "Segurança Eletrônica e Energia Solar",
        "clusters": [CLUSTER_TECH_TELCO],
        "macro_risk_note": "Vendas no varejo de construção civil e geração distribuída de energia solar.",
    },
    "BMOB3": {
        "company": "Bemobi Mobile Tech",
        "sector": "Tecnologia",
        "subsector": "Assinaturas e Pagamentos Móveis",
        "clusters": [CLUSTER_TECH_TELCO],
        "macro_risk_note": "Monetização de serviços digitais em telecom e mercados emergentes.",
    },
    "VLID3": {
        "company": "Valid",
        "sector": "Tecnologia",
        "subsector": "Identificação e Certificação Digital",
        "clusters": [CLUSTER_TECH_TELCO],
        "macro_risk_note": "Emissão de CNH/RG e cartões com chip.",
    },
    "TIMS3": {
        "company": "TIM Brasil",
        "sector": "Telecomunicações",
        "subsector": "Serviços Móveis e Banda Larga",
        "clusters": [CLUSTER_TECH_TELCO],
        "macro_risk_note": "Receita média por usuário (ARPU) pós-pago e investimentos em 5G.",
    },
    "VIVT3": {
        "company": "Telefônica Brasil (Vivo)",
        "sector": "Telecomunicações",
        "subsector": "Serviços Móveis e Fibra Óptica",
        "clusters": [CLUSTER_TECH_TELCO],
        "macro_risk_note": "Defensiva, com alta geração de caixa e dividendos sólidos.",
    },
    "FIQE3": {
        "company": "Unifique Telecom",
        "sector": "Telecomunicações",
        "subsector": "Provedor Regional de Fibra",
        "clusters": [CLUSTER_TECH_TELCO],
        "macro_risk_note": "Competição regional de banda larga e entrada em telefonia 5G.",
    },

    # =========================================================================
    # EDUCAÇÃO
    # =========================================================================
    "YDUQ3": {
        "company": "Yduqs",
        "sector": "Serviços Educacionais",
        "subsector": "Ensino Superior e Cursos de Medicina",
        "clusters": [CLUSTER_EDUCATION],
        "macro_risk_note": "Programas governamentais de bolsas/financiamento (FIES/Prouni) e tíquete de medicina.",
    },
    "SEER3": {
        "company": "Ser Educacional",
        "sector": "Serviços Educacionais",
        "subsector": "Ensino Superior Regional (Norte/Nordeste)",
        "clusters": [CLUSTER_EDUCATION],
        "macro_risk_note": "Captação de alunos presenciais e EaD no Norte/Nordeste.",
    },

    # =========================================================================
    # IMOBILIÁRIO (GALPÕES LOGÍSTICOS)
    # =========================================================================
    "LOGG3": {
        "company": "LOG Commercial Properties",
        "sector": "Imobiliário",
        "subsector": "Galpões Logísticos",
        "clusters": [CLUSTER_REAL_ESTATE, CLUSTER_TRANSPORT],
        "macro_risk_note": "Locação para e-commerce e reciclagem de portfólio de galpões.",
    },
}


def clean_ticker_key(ticker: str) -> str:
    """Normaliza o ticker removendo sufixos '.SA' ou 'F' de mercado fracionário."""
    t = ticker.upper().strip()
    if t.endswith(".SA"):
        t = t[:-3]
    if len(t) == 6 and t.endswith("F") and (t[:4].isalpha()):
        t = t[:-1]
    return t


def get_asset_sector_profile(ticker: str) -> Dict[str, Any]:
    """Retorna o perfil setorial completo e macro-clusters de risco de um ticker."""
    clean_tk = clean_ticker_key(ticker)
    if clean_tk in B3_SECTORS_DATA:
        info = B3_SECTORS_DATA[clean_tk].copy()
        info["ticker"] = clean_tk
        return info

    # Fallback para ativos fora do dicionário cadastrado
    return {
        "ticker": clean_tk,
        "company": clean_tk,
        "sector": "Outros",
        "subsector": "Geral",
        "clusters": ["OUTROS"],
        "macro_risk_note": "Ativo sem mapeamento setorial específico.",
    }


def are_clusters_correlated(cluster_a: str, cluster_b: str) -> bool:
    """Verifica se dois macro-clusters de risco se correspondem e tendem a oscilar juntos."""
    if cluster_a == cluster_b:
        return True
    corr_list = CORRELATED_CLUSTERS_MAP.get(cluster_a, [])
    return cluster_b in corr_list
