#!/usr/bin/env python3
"""
Gerador Rápido de Configuração

Gera configuração de crawl baseada apenas nos domínios,
sem precisar acessar os sites. Útil para:
- Ter uma configuração inicial rápida
- Funcionar mesmo offline
- Classificar sites por plataforma conhecida

Uso:
    python generate_quick_config.py
    python generate_quick_config.py --input arquivo.csv --output config.json
"""

import argparse
import csv
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any

from analyzer.known_patterns import (
    detect_platform,
    get_platform_config,
    KNOWN_PLATFORMS,
    GENERIC_LOT_PATTERNS,
    GENERIC_CRAWL_PATHS
)


def load_sites(filepath: str) -> List[Dict[str, str]]:
    """Carrega sites do CSV"""
    sites = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = row.get('dominio', '').strip()
            if domain:
                sites.append({
                    'nome': row.get('nome', ''),
                    'dominio': domain
                })
    return sites


def classify_and_configure(sites: List[Dict[str, str]]) -> Dict[str, Any]:
    """Classifica sites e gera configuração"""
    groups = defaultdict(lambda: {"platform": "", "sites": [], "include_paths": []})

    for site in sites:
        domain = site['dominio']
        name = site['nome']

        # Detecta plataforma
        platform = detect_platform(domain)
        config = get_platform_config(platform)

        group_name = config.name

        if not groups[group_name]["platform"]:
            groups[group_name]["platform"] = platform
            groups[group_name]["include_paths"] = config.lot_include_paths

        # Normaliza URL
        if not domain.startswith(('http://', 'https://')):
            base_url = f"https://{domain}"
        else:
            base_url = domain

        base_url = base_url.rstrip('/')

        # Gera crawl URLs
        crawl_urls = [base_url]
        for path in config.default_crawl_paths[1:4]:  # Primeiros 3 paths adicionais
            crawl_urls.append(f"{base_url}{path}")

        groups[group_name]["sites"].append({
            "nome": name,
            "dominio": domain,
            "url_base": base_url,
            "crawl_urls": crawl_urls,
            "include_paths": config.lot_include_paths
        })

    return dict(groups)


def save_config_csv(groups: Dict[str, Any], filepath: str) -> None:
    """Salva configuração em CSV"""
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'grupo', 'nome', 'dominio', 'url_base',
            'crawl_urls', 'include_paths'
        ])

        for group_name, group_data in sorted(groups.items()):
            for site in group_data['sites']:
                writer.writerow([
                    group_name,
                    site['nome'],
                    site['dominio'],
                    site['url_base'],
                    '|'.join(site['crawl_urls']),
                    '|'.join(site['include_paths'])
                ])


def save_config_json(groups: Dict[str, Any], filepath: str) -> None:
    """Salva configuração em JSON"""
    output = {
        "gerado_em": __import__('datetime').datetime.now().isoformat(),
        "total_grupos": len(groups),
        "total_sites": sum(len(g['sites']) for g in groups.values()),
        "grupos": {}
    }

    for group_name, group_data in groups.items():
        output["grupos"][group_name] = {
            "platform": group_data['platform'],
            "quantidade": len(group_data['sites']),
            "include_paths_padrao": group_data['include_paths'],
            "sites": group_data['sites']
        }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def print_summary(groups: Dict[str, Any]) -> None:
    """Imprime resumo"""
    total_sites = sum(len(g['sites']) for g in groups.values())

    print("\n" + "="*60)
    print("CONFIGURAÇÃO RÁPIDA - BASEADA EM PADRÕES CONHECIDOS")
    print("="*60)
    print(f"\nTotal de sites: {total_sites}")
    print(f"Grupos identificados: {len(groups)}")

    print("\n" + "-"*60)
    print("GRUPOS:")
    print("-"*60)

    for group_name, group_data in sorted(groups.items(), key=lambda x: -len(x[1]['sites'])):
        print(f"\n{group_name}")
        print(f"  Quantidade: {len(group_data['sites'])} sites")
        print(f"  Plataforma: {group_data['platform']}")
        print(f"  Include paths: {', '.join(group_data['include_paths'])}")

        # Mostra alguns exemplos
        print("  Exemplos:")
        for site in group_data['sites'][:3]:
            print(f"    - {site['nome']}: {site['dominio']}")


def main():
    parser = argparse.ArgumentParser(
        description="Gerador rápido de configuração de crawl"
    )
    parser.add_argument(
        '--input', '-i',
        default='Dominios Leilões - Dominios.csv',
        help='Arquivo CSV com domínios'
    )
    parser.add_argument(
        '--output', '-o',
        default='output',
        help='Diretório de saída'
    )
    args = parser.parse_args()

    # Carrega sites
    print(f"Carregando sites de: {args.input}")
    sites = load_sites(args.input)
    print(f"Sites carregados: {len(sites)}")

    # Classifica e configura
    print("\nClassificando por plataforma...")
    groups = classify_and_configure(sites)

    # Cria diretório de saída
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    # Salva arquivos
    timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = output_dir / f"config_rapida_{timestamp}.csv"
    save_config_csv(groups, str(csv_path))
    print(f"\nSalvo: {csv_path}")

    json_path = output_dir / f"config_rapida_{timestamp}.json"
    save_config_json(groups, str(json_path))
    print(f"Salvo: {json_path}")

    # Imprime resumo
    print_summary(groups)

    print("\n" + "="*60)
    print("CONFIGURAÇÃO GERADA COM SUCESSO!")
    print("="*60)
    print("\nPróximos passos:")
    print("1. Use o arquivo CSV/JSON gerado para configurar seu crawler")
    print("2. Para cada site, use 'crawl_urls' como ponto de partida")
    print("3. Após o crawl, filtre URLs usando 'include_paths'")
    print("4. Apenas URLs que contém os include_paths são lotes")


if __name__ == "__main__":
    main()
