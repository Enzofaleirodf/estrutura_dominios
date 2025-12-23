"""
Padrões Conhecidos de Plataformas de Leilões

Este módulo contém configurações pré-definidas para as plataformas
mais comuns de leilões no Brasil, permitindo classificação rápida
baseada apenas no domínio.
"""

from typing import Dict, List, Any
from dataclasses import dataclass, field


@dataclass
class PlatformConfig:
    """Configuração de uma plataforma de leilões"""
    name: str
    description: str
    domain_patterns: List[str]  # Padrões para identificar a plataforma
    default_crawl_paths: List[str]  # Caminhos padrão para começar o crawl
    lot_include_paths: List[str]  # Padrões de URL de lotes
    auction_include_paths: List[str]  # Padrões de URL de leilões


# Configurações conhecidas das principais plataformas
KNOWN_PLATFORMS: Dict[str, PlatformConfig] = {
    "lel.br": PlatformConfig(
        name="Plataforma LEL.BR",
        description="Plataforma unificada de leiloeiros oficiais (lel.br)",
        domain_patterns=[".lel.br"],
        default_crawl_paths=[
            "/",
            "/leiloes",
            "/leiloes/abertos",
            "/leiloes/proximos",
        ],
        lot_include_paths=[
            "/lote/",
            "/lotes/",
        ],
        auction_include_paths=[
            "/leilao/",
            "/leiloes/",
        ]
    ),

    "leilao.br": PlatformConfig(
        name="Plataforma LEILAO.BR",
        description="Plataforma leilao.br",
        domain_patterns=[".leilao.br"],
        default_crawl_paths=[
            "/",
            "/leiloes",
            "/catalogo",
        ],
        lot_include_paths=[
            "/lote/",
            "/item/",
        ],
        auction_include_paths=[
            "/leilao/",
        ]
    ),

    "superbid": PlatformConfig(
        name="Superbid",
        description="Plataforma Superbid para leilões online",
        domain_patterns=["superbid"],
        default_crawl_paths=[
            "/",
            "/leiloes",
        ],
        lot_include_paths=[
            "/lote/",
            "/lot/",
        ],
        auction_include_paths=[
            "/leilao/",
            "/auction/",
        ]
    ),

    "bomvalor": PlatformConfig(
        name="Bom Valor / Mercado Bomvalor",
        description="Plataforma Bom Valor para leilões judiciais",
        domain_patterns=["bomvalor"],
        default_crawl_paths=[
            "/",
            "/leiloes",
            "/imoveis",
            "/veiculos",
        ],
        lot_include_paths=[
            "/lote/",
            "/imoveis/",
            "/veiculos/",
        ],
        auction_include_paths=[
            "/leilao/",
            "/evento/",
        ]
    ),

    "zuk": PlatformConfig(
        name="Portal Zuk",
        description="Portal Zuk de leilões",
        domain_patterns=["zuk"],
        default_crawl_paths=[
            "/",
            "/imoveis",
            "/veiculos",
            "/bens",
        ],
        lot_include_paths=[
            "/imovel/",
            "/veiculo/",
            "/bem/",
        ],
        auction_include_paths=[
            "/leilao/",
        ]
    ),

    "copart": PlatformConfig(
        name="Copart",
        description="Copart Brasil - Leilões de veículos salvados",
        domain_patterns=["copart"],
        default_crawl_paths=[
            "/",
            "/leiloes",
            "/veiculos",
        ],
        lot_include_paths=[
            "/lot/",
            "/lote/",
            "/veiculo/",
        ],
        auction_include_paths=[
            "/leilao/",
            "/auction/",
        ]
    ),
}

# Padrões genéricos para sites próprios
GENERIC_LOT_PATTERNS = [
    "/lote/",
    "/lotes/",
    "/item/",
    "/produto/",
    "/bem/",
    "/imovel/",
    "/imoveis/",
    "/veiculo/",
    "/veiculos/",
    "/detalhe/",
]

GENERIC_CRAWL_PATHS = [
    "/",
    "/leiloes",
    "/leilao",
    "/catalogo",
    "/lotes",
    "/imoveis",
    "/veiculos",
    "/busca",
    "/proximos-leiloes",
    "/em-andamento",
]


def detect_platform(domain: str) -> str:
    """
    Detecta a plataforma baseado no domínio.

    Args:
        domain: URL ou domínio do site

    Returns:
        Nome da plataforma detectada ou 'custom'
    """
    domain_lower = domain.lower()

    for platform_key, config in KNOWN_PLATFORMS.items():
        for pattern in config.domain_patterns:
            if pattern in domain_lower:
                return platform_key

    return "custom"


def get_platform_config(platform: str) -> PlatformConfig:
    """
    Retorna a configuração de uma plataforma.

    Args:
        platform: Nome da plataforma

    Returns:
        Configuração da plataforma ou configuração genérica
    """
    if platform in KNOWN_PLATFORMS:
        return KNOWN_PLATFORMS[platform]

    # Retorna configuração genérica
    return PlatformConfig(
        name="Sites Próprios",
        description="Sites com plataforma própria",
        domain_patterns=[],
        default_crawl_paths=GENERIC_CRAWL_PATHS,
        lot_include_paths=GENERIC_LOT_PATTERNS,
        auction_include_paths=["/leilao/", "/leiloes/"]
    )


def classify_sites_by_domain(
    sites: List[Dict[str, str]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Classifica sites por plataforma baseado apenas no domínio.

    Útil para pré-classificação sem precisar acessar os sites.

    Args:
        sites: Lista de dicts com 'dominio' e 'nome'

    Returns:
        Dict com grupos e configurações
    """
    groups = {}

    for site in sites:
        domain = site.get('dominio', site.get('domain', ''))
        name = site.get('nome', site.get('name', ''))

        platform = detect_platform(domain)
        config = get_platform_config(platform)

        if config.name not in groups:
            groups[config.name] = {
                "platform": platform,
                "description": config.description,
                "default_crawl_paths": config.default_crawl_paths,
                "lot_include_paths": config.lot_include_paths,
                "sites": []
            }

        groups[config.name]["sites"].append({
            "nome": name,
            "dominio": domain,
            "crawl_urls": [f"{domain.rstrip('/')}{path}" for path in config.default_crawl_paths[:3]],
            "include_paths": config.lot_include_paths
        })

    return groups


def generate_quick_config(input_csv: str, output_json: str) -> None:
    """
    Gera configuração rápida baseada apenas nos domínios (sem acessar os sites).

    Útil para ter uma configuração inicial que pode ser refinada depois.

    Args:
        input_csv: Caminho do CSV com domínios
        output_json: Caminho para salvar o JSON de configuração
    """
    import csv
    import json

    sites = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('dominio'):
                sites.append(row)

    groups = classify_sites_by_domain(sites)

    # Adiciona estatísticas
    output = {
        "total_sites": len(sites),
        "total_groups": len(groups),
        "groups": groups
    }

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Configuração gerada: {output_json}")
    print(f"Total de sites: {len(sites)}")
    print(f"Grupos identificados: {len(groups)}")

    for group_name, group_data in sorted(groups.items(), key=lambda x: -len(x[1]['sites'])):
        print(f"  - {group_name}: {len(group_data['sites'])} sites")
