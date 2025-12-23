#!/usr/bin/env python3
"""
Script principal para análise de estrutura de sites de leilões.

Uso:
    python run_analysis.py                    # Analisa todos os sites do CSV
    python run_analysis.py --sample 50        # Analisa apenas 50 sites (amostra)
    python run_analysis.py --concurrent 30    # Define concorrência máxima
    python run_analysis.py --timeout 60       # Define timeout em segundos
"""

import asyncio
import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from analyzer.batch_analyzer import BatchAnalyzer, load_sites_from_csv


console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analisador de estrutura de sites de leilões"
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
        default=20,
        help='Número máximo de requisições simultâneas'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=30,
        help='Timeout em segundos para cada requisição'
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    console.print(Panel.fit(
        "[bold cyan]Analisador de Estrutura de Sites de Leilões[/bold cyan]\n"
        "Descobre URLs base, padrões de lotes e agrupa sites similares",
        border_style="cyan"
    ))

    # Carrega sites do CSV
    input_file = Path(args.input)
    if not input_file.exists():
        console.print(f"[red]Erro: Arquivo não encontrado: {input_file}[/red]")
        sys.exit(1)

    console.print(f"\n[cyan]Carregando sites de:[/cyan] {input_file}")
    sites = load_sites_from_csv(str(input_file))
    console.print(f"[green]Sites carregados:[/green] {len(sites)}")

    # Aplica amostragem se solicitado
    if args.sample > 0 and args.sample < len(sites):
        import random
        sites = random.sample(sites, args.sample)
        console.print(f"[yellow]Usando amostra de:[/yellow] {args.sample} sites")

    # Configura e executa o analisador
    console.print(f"\n[cyan]Configuração:[/cyan]")
    console.print(f"  - Concorrência máxima: {args.concurrent}")
    console.print(f"  - Timeout: {args.timeout}s")
    console.print(f"  - Diretório de saída: {args.output}")

    analyzer = BatchAnalyzer(
        max_concurrent=args.concurrent,
        timeout=args.timeout,
        output_dir=args.output
    )

    console.print("\n[bold]Iniciando análise...[/bold]\n")

    # Executa análise
    await analyzer.analyze_sites(sites)

    # Imprime resumo
    console.print("\n")
    analyzer.print_summary()

    # Salva resultados
    console.print("\n[bold]Salvando resultados...[/bold]")
    files = analyzer.save_results()

    console.print("\n[green]Arquivos gerados:[/green]")
    for desc, path in files.items():
        console.print(f"  - {desc}: {path}")

    console.print("\n[bold green]Análise concluída![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
