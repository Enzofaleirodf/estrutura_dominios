#!/usr/bin/env python3
"""
Script completo para análise de estrutura de sites de leilões.

Este script:
1. Carrega a lista de domínios do CSV
2. Analisa cada site para descobrir sua estrutura
3. Agrupa sites com estruturas similares
4. Gera configurações de crawl (url_base, include_paths)
5. Atualiza o CSV original com as informações

Uso:
    python run_full_analysis.py                    # Analisa todos
    python run_full_analysis.py --sample 100       # Analisa amostra
    python run_full_analysis.py --deep             # Análise profunda
"""

import asyncio
import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import asdict

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analisador completo de estrutura de sites de leilões"
    )
    parser.add_argument(
        '--input', '-i',
        default='Dominios Leilões - Dominios.csv',
        help='Arquivo CSV com os domínios'
    )
    parser.add_argument(
        '--output', '-o',
        default='output',
        help='Diretório para salvar resultados'
    )
    parser.add_argument(
        '--sample', '-s',
        type=int,
        default=0,
        help='Número de sites para analisar (0 = todos)'
    )
    parser.add_argument(
        '--concurrent', '-c',
        type=int,
        default=15,
        help='Número máximo de requisições simultâneas'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=30,
        help='Timeout em segundos para cada requisição'
    )
    parser.add_argument(
        '--deep',
        action='store_true',
        help='Fazer análise profunda (mais lenta, mais precisa)'
    )
    return parser.parse_args()


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


async def analyze_site_simple(
    session,
    domain: str,
    name: str,
    timeout: int = 30
) -> Dict[str, Any]:
    """Análise simples de um site"""
    import aiohttp
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse, urljoin
    import re

    result = {
        'name': name,
        'domain': domain,
        'status': 'pending',
        'base_url': '',
        'crawl_urls': [],
        'include_paths': [],
        'platform': 'unknown',
        'error_message': '',
        'lot_examples': []
    }

    # Normaliza URL
    if not domain.startswith(('http://', 'https://')):
        domain = f"https://{domain}"
    domain = domain.replace("https://www.www.", "https://www.")

    result['base_url'] = domain

    try:
        async with session.get(domain, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status != 200:
                result['status'] = 'error'
                result['error_message'] = f'HTTP {response.status}'
                return result

            final_url = str(response.url)
            result['base_url'] = final_url
            html = await response.text()

            # Detecta plataforma
            domain_lower = domain.lower()
            if '.lel.br' in domain_lower:
                result['platform'] = 'lel.br'
            elif '.leilao.br' in domain_lower:
                result['platform'] = 'leilao.br'
            elif 'superbid' in domain_lower:
                result['platform'] = 'superbid'
            elif 'bomvalor' in domain_lower:
                result['platform'] = 'bomvalor'
            else:
                result['platform'] = 'custom'

            # Extrai links
            soup = BeautifulSoup(html, 'lxml')
            base_domain = urlparse(final_url).netloc

            lot_patterns = [
                (r'/lotes?/(\d+)', '/lote/'),
                (r'/lotes?/([\w-]+)', '/lote/'),
                (r'/items?/(\d+)', '/item/'),
                (r'/produtos?/(\d+)', '/produto/'),
                (r'/imove[il]s?/', '/imovel/'),
                (r'/veiculos?/', '/veiculo/'),
                (r'/detalhe[s]?/', '/detalhe/'),
                (r'/bem/', '/bem/'),
            ]

            found_patterns = set()
            lot_examples = []

            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if href.startswith(('#', 'javascript:', 'mailto:')):
                    continue

                full_url = urljoin(final_url, href)
                path = urlparse(full_url).path.lower()

                for pattern, include_path in lot_patterns:
                    if re.search(pattern, path, re.IGNORECASE):
                        found_patterns.add(include_path)
                        if len(lot_examples) < 5:
                            lot_examples.append(full_url)
                        break

            result['include_paths'] = list(found_patterns) if found_patterns else ['/lote/', '/item/']
            result['lot_examples'] = lot_examples

            # Define crawl URLs
            crawl_urls = [final_url]
            common_paths = ['/leiloes', '/lotes', '/catalogo', '/imoveis', '/veiculos']
            base = final_url.rstrip('/')
            for path in common_paths:
                crawl_urls.append(f"{base}{path}")

            result['crawl_urls'] = crawl_urls[:5]
            result['status'] = 'success'

    except asyncio.TimeoutError:
        result['status'] = 'timeout'
        result['error_message'] = f'Timeout após {timeout}s'
    except Exception as e:
        result['status'] = 'error'
        result['error_message'] = str(e)[:100]

    return result


async def run_analysis(
    sites: List[Dict[str, str]],
    max_concurrent: int = 15,
    timeout: int = 30
) -> List[Dict[str, Any]]:
    """Executa análise de todos os sites"""
    import aiohttp

    results = []
    semaphore = asyncio.Semaphore(max_concurrent)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    async def analyze_with_semaphore(session, site):
        async with semaphore:
            result = await analyze_site_simple(
                session,
                site['dominio'],
                site['nome'],
                timeout
            )
            return result

    connector = aiohttp.TCPConnector(limit=max_concurrent, ssl=False)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"[cyan]Analisando sites...", total=len(sites))

        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            tasks = [analyze_with_semaphore(session, site) for site in sites]

            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                progress.update(task, advance=1)

    return results


def group_sites(results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Agrupa sites por estrutura similar"""
    from collections import defaultdict

    groups = defaultdict(list)

    for result in results:
        if result['status'] != 'success':
            groups['ERRO - Sites com problema'].append(result)
            continue

        platform = result['platform']
        include_paths = tuple(sorted(result['include_paths']))

        # Cria nome do grupo
        if platform == 'lel.br':
            group_name = 'Plataforma LEL.BR'
        elif platform == 'leilao.br':
            group_name = 'Plataforma LEILAO.BR'
        elif platform == 'superbid':
            group_name = 'Superbid'
        elif platform == 'bomvalor':
            group_name = 'Bom Valor'
        else:
            # Agrupa por include_paths
            if '/imovel/' in include_paths:
                group_name = 'Sites Próprios - Imóveis'
            elif '/veiculo/' in include_paths:
                group_name = 'Sites Próprios - Veículos'
            elif '/lote/' in include_paths:
                group_name = 'Sites Próprios - Lotes Genéricos'
            elif '/produto/' in include_paths:
                group_name = 'Sites Próprios - Produtos'
            else:
                group_name = 'Sites Próprios - Outros'

        result['grupo'] = group_name
        groups[group_name].append(result)

    return dict(groups)


def save_results(
    results: List[Dict[str, Any]],
    groups: Dict[str, List[Dict[str, Any]]],
    output_dir: str
):
    """Salva todos os resultados"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. CSV com configurações de crawl
    csv_file = output_path / f"crawl_config_{timestamp}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'grupo', 'nome', 'dominio', 'url_base',
            'crawl_urls', 'include_paths', 'status'
        ])

        for result in sorted(results, key=lambda x: x.get('grupo', 'ZZZ')):
            writer.writerow([
                result.get('grupo', ''),
                result['name'],
                result['domain'],
                result['base_url'],
                '|'.join(result['crawl_urls']),
                '|'.join(result['include_paths']),
                result['status']
            ])

    console.print(f"[green]Salvo:[/green] {csv_file}")

    # 2. JSON com grupos
    groups_file = output_path / f"grupos_{timestamp}.json"
    groups_data = {}
    for group_name, sites in groups.items():
        groups_data[group_name] = {
            "quantidade": len(sites),
            "include_paths_comum": list(set(
                path for site in sites
                for path in site.get('include_paths', [])
            )),
            "sites": [
                {
                    "nome": s['name'],
                    "dominio": s['domain'],
                    "url_base": s['base_url'],
                    "crawl_urls": s['crawl_urls'],
                    "include_paths": s['include_paths']
                }
                for s in sites
            ]
        }

    with open(groups_file, 'w', encoding='utf-8') as f:
        json.dump(groups_data, f, ensure_ascii=False, indent=2)

    console.print(f"[green]Salvo:[/green] {groups_file}")

    # 3. JSON detalhado
    detailed_file = output_path / f"analise_completa_{timestamp}.json"
    with open(detailed_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    console.print(f"[green]Salvo:[/green] {detailed_file}")

    # 4. Resumo em texto
    summary_file = output_path / f"resumo_{timestamp}.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("RESUMO DA ANÁLISE DE SITES DE LEILÕES\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total de sites: {len(results)}\n")
        f.write(f"Sucesso: {sum(1 for r in results if r['status'] == 'success')}\n")
        f.write(f"Erros: {sum(1 for r in results if r['status'] == 'error')}\n")
        f.write(f"Timeouts: {sum(1 for r in results if r['status'] == 'timeout')}\n\n")

        f.write("GRUPOS IDENTIFICADOS:\n")
        f.write("-" * 50 + "\n\n")

        for group_name, sites in sorted(groups.items(), key=lambda x: -len(x[1])):
            f.write(f"{group_name}: {len(sites)} sites\n")
            include_paths = list(set(
                path for site in sites
                for path in site.get('include_paths', [])
            ))
            f.write(f"  Include paths: {', '.join(include_paths)}\n\n")

    console.print(f"[green]Salvo:[/green] {summary_file}")

    return {
        'csv': str(csv_file),
        'groups': str(groups_file),
        'detailed': str(detailed_file),
        'summary': str(summary_file)
    }


def print_summary(results: List[Dict[str, Any]], groups: Dict[str, List[Dict[str, Any]]]):
    """Imprime resumo no console"""
    # Tabela de resumo geral
    table = Table(title="Resumo da Análise")
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", style="green")

    total = len(results)
    success = sum(1 for r in results if r['status'] == 'success')
    errors = sum(1 for r in results if r['status'] == 'error')
    timeouts = sum(1 for r in results if r['status'] == 'timeout')

    table.add_row("Total de sites", str(total))
    table.add_row("Sucesso", str(success))
    table.add_row("Erros", str(errors))
    table.add_row("Timeouts", str(timeouts))
    table.add_row("Taxa de sucesso", f"{(success/total)*100:.1f}%" if total > 0 else "0%")
    table.add_row("Grupos identificados", str(len(groups)))

    console.print(table)

    # Tabela de grupos
    groups_table = Table(title="Sites por Grupo")
    groups_table.add_column("Grupo", style="cyan")
    groups_table.add_column("Quantidade", style="green")
    groups_table.add_column("Include Paths", style="yellow")

    for group_name, sites in sorted(groups.items(), key=lambda x: -len(x[1])):
        include_paths = list(set(
            path for site in sites[:5]  # Apenas primeiros 5 para amostra
            for path in site.get('include_paths', [])
        ))
        groups_table.add_row(
            group_name,
            str(len(sites)),
            ', '.join(include_paths[:3])
        )

    console.print(groups_table)


async def main():
    args = parse_args()

    console.print(Panel.fit(
        "[bold cyan]Analisador de Estrutura de Sites de Leilões[/bold cyan]\n"
        "Descobre URLs base, padrões de lotes e agrupa sites similares",
        border_style="cyan"
    ))

    # Carrega sites
    input_file = Path(args.input)
    if not input_file.exists():
        console.print(f"[red]Erro: Arquivo não encontrado: {input_file}[/red]")
        sys.exit(1)

    console.print(f"\n[cyan]Carregando sites de:[/cyan] {input_file}")
    sites = load_sites(str(input_file))
    console.print(f"[green]Sites carregados:[/green] {len(sites)}")

    # Amostragem
    if args.sample > 0 and args.sample < len(sites):
        import random
        sites = random.sample(sites, args.sample)
        console.print(f"[yellow]Usando amostra de:[/yellow] {args.sample} sites")

    # Configuração
    console.print(f"\n[cyan]Configuração:[/cyan]")
    console.print(f"  Concorrência: {args.concurrent}")
    console.print(f"  Timeout: {args.timeout}s")
    console.print(f"  Saída: {args.output}")

    # Executa análise
    console.print("\n[bold]Iniciando análise...[/bold]\n")

    results = await run_analysis(
        sites,
        max_concurrent=args.concurrent,
        timeout=args.timeout
    )

    # Agrupa sites
    console.print("\n[bold]Agrupando sites por estrutura...[/bold]")
    groups = group_sites(results)

    # Imprime resumo
    console.print("\n")
    print_summary(results, groups)

    # Salva resultados
    console.print("\n[bold]Salvando resultados...[/bold]")
    files = save_results(results, groups, args.output)

    console.print("\n[bold green]Análise concluída![/bold green]")
    console.print("\n[cyan]Próximos passos:[/cyan]")
    console.print("1. Revise o arquivo CSV gerado para ajustar configurações")
    console.print("2. Use o JSON de grupos para configurar seu crawler")
    console.print("3. Os include_paths indicam os padrões de URL para filtrar lotes")


if __name__ == "__main__":
    asyncio.run(main())
