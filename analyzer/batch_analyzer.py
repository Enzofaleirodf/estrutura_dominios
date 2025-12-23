"""
Analisador em Batch de Sites de Leilões

Executa análise paralela de múltiplos sites e agrupa por estrutura similar.
"""

import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict
from dataclasses import asdict

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from .structure_analyzer import SiteStructureAnalyzer, SiteAnalysis


console = Console()


class BatchAnalyzer:
    """Executa análise em batch de múltiplos sites"""

    def __init__(
        self,
        max_concurrent: int = 20,
        timeout: int = 30,
        output_dir: str = "output"
    ):
        self.max_concurrent = max_concurrent
        self.analyzer = SiteStructureAnalyzer(timeout=timeout)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results: List[SiteAnalysis] = []

    async def analyze_sites(self, sites: List[Dict[str, str]]) -> List[SiteAnalysis]:
        """Analisa múltiplos sites em paralelo"""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def analyze_with_semaphore(site: Dict[str, str]) -> SiteAnalysis:
            async with semaphore:
                return await self.analyzer.analyze_site(
                    domain=site.get('dominio', site.get('domain', '')),
                    name=site.get('nome', site.get('name', ''))
                )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Analisando {len(sites)} sites...",
                total=len(sites)
            )

            tasks = []
            for site in sites:
                task_coro = analyze_with_semaphore(site)
                tasks.append(task_coro)

            results = []
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                progress.update(task, advance=1)

        self.results = results
        return results

    def group_by_platform(self) -> Dict[str, List[SiteAnalysis]]:
        """Agrupa sites por plataforma detectada"""
        groups = defaultdict(list)
        for result in self.results:
            groups[result.platform].append(result)
        return dict(groups)

    def group_by_domain_suffix(self) -> Dict[str, List[SiteAnalysis]]:
        """Agrupa sites por sufixo de domínio (lel.br, leilao.br, etc.)"""
        groups = defaultdict(list)

        for result in self.results:
            domain = result.domain.lower()

            if '.lel.br' in domain:
                groups['lel.br'].append(result)
            elif '.leilao.br' in domain:
                groups['leilao.br'].append(result)
            elif 'superbid' in domain:
                groups['superbid'].append(result)
            elif 'bomvalor' in domain:
                groups['bomvalor'].append(result)
            else:
                groups['outros'].append(result)

        return dict(groups)

    def group_by_url_structure(self) -> Dict[str, List[SiteAnalysis]]:
        """Agrupa sites por estrutura de URL similar"""
        groups = defaultdict(list)

        for result in self.results:
            if result.status != "success":
                groups['error'].append(result)
                continue

            # Cria uma chave baseada nos padrões encontrados
            patterns_key = self._create_pattern_key(result)
            groups[patterns_key].append(result)

        return dict(groups)

    def _create_pattern_key(self, analysis: SiteAnalysis) -> str:
        """Cria uma chave única baseada nos padrões de URL"""
        lot_patterns = sorted(analysis.lot_url_patterns)
        auction_patterns = sorted(analysis.auction_url_patterns)

        # Simplifica os padrões para agrupamento
        simplified_lot = []
        for p in lot_patterns:
            if '/lote' in p.lower():
                simplified_lot.append('lote')
            elif '/item' in p.lower():
                simplified_lot.append('item')
            elif '/produto' in p.lower():
                simplified_lot.append('produto')
            elif '/imovel' in p.lower() or '/imoveis' in p.lower():
                simplified_lot.append('imovel')
            elif '/veiculo' in p.lower():
                simplified_lot.append('veiculo')
            else:
                simplified_lot.append('outro')

        if not simplified_lot:
            simplified_lot = ['indefinido']

        # Adiciona a plataforma à chave
        key = f"{analysis.platform}::{','.join(sorted(set(simplified_lot)))}"
        return key

    def generate_report(self) -> Dict[str, Any]:
        """Gera um relatório completo da análise"""
        total = len(self.results)
        success = sum(1 for r in self.results if r.status == "success")
        errors = sum(1 for r in self.results if r.status == "error")
        timeouts = sum(1 for r in self.results if r.status == "timeout")

        platform_groups = self.group_by_platform()
        domain_groups = self.group_by_domain_suffix()
        structure_groups = self.group_by_url_structure()

        return {
            "summary": {
                "total_sites": total,
                "success": success,
                "errors": errors,
                "timeouts": timeouts,
                "success_rate": f"{(success/total)*100:.1f}%" if total > 0 else "0%"
            },
            "by_platform": {k: len(v) for k, v in platform_groups.items()},
            "by_domain": {k: len(v) for k, v in domain_groups.items()},
            "by_structure": {k: len(v) for k, v in structure_groups.items()},
            "generated_at": datetime.now().isoformat()
        }

    def save_results(self, prefix: str = "analysis") -> Dict[str, str]:
        """Salva os resultados em múltiplos formatos"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        files_saved = {}

        # 1. Salva resultados detalhados em JSON
        json_file = self.output_dir / f"{prefix}_{timestamp}_detailed.json"
        detailed_results = [asdict(r) for r in self.results]
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=2)
        files_saved['detailed_json'] = str(json_file)

        # 2. Salva CSV com configurações de crawl
        csv_file = self.output_dir / f"{prefix}_{timestamp}_config.csv"
        self._save_crawl_config_csv(csv_file)
        files_saved['config_csv'] = str(csv_file)

        # 3. Salva grupos por estrutura
        groups_file = self.output_dir / f"{prefix}_{timestamp}_groups.json"
        self._save_groups_json(groups_file)
        files_saved['groups_json'] = str(groups_file)

        # 4. Salva relatório resumido
        report_file = self.output_dir / f"{prefix}_{timestamp}_report.json"
        report = self.generate_report()
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        files_saved['report_json'] = str(report_file)

        return files_saved

    def _save_crawl_config_csv(self, filepath: Path) -> None:
        """Salva CSV com configurações de crawl para cada site"""
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'grupo', 'nome', 'dominio', 'url_base',
                'crawl_urls', 'include_paths', 'status',
                'platform', 'error_message'
            ])

            # Agrupa para identificar o grupo de cada site
            structure_groups = self.group_by_url_structure()
            site_to_group = {}
            for group_name, sites in structure_groups.items():
                for site in sites:
                    site_to_group[site.domain] = group_name

            for result in sorted(self.results, key=lambda x: site_to_group.get(x.domain, '')):
                writer.writerow([
                    site_to_group.get(result.domain, 'unknown'),
                    result.name,
                    result.domain,
                    result.base_url,
                    '|'.join(result.crawl_urls),
                    '|'.join(result.include_paths),
                    result.status,
                    result.platform,
                    result.error_message
                ])

    def _save_groups_json(self, filepath: Path) -> None:
        """Salva JSON com sites agrupados por estrutura"""
        structure_groups = self.group_by_url_structure()

        groups_data = {}
        for group_name, sites in structure_groups.items():
            groups_data[group_name] = {
                "count": len(sites),
                "sites": [
                    {
                        "name": s.name,
                        "domain": s.domain,
                        "base_url": s.base_url,
                        "crawl_urls": s.crawl_urls,
                        "include_paths": s.include_paths,
                        "sample_lot_urls": s.sample_lot_urls[:3],
                        "status": s.status
                    }
                    for s in sites
                ]
            }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(groups_data, f, ensure_ascii=False, indent=2)

    def print_summary(self) -> None:
        """Imprime um resumo da análise no console"""
        report = self.generate_report()

        # Tabela de resumo
        table = Table(title="Resumo da Análise")
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="green")

        for key, value in report["summary"].items():
            table.add_row(key.replace("_", " ").title(), str(value))

        console.print(table)

        # Tabela de plataformas
        platform_table = Table(title="Sites por Plataforma")
        platform_table.add_column("Plataforma", style="cyan")
        platform_table.add_column("Quantidade", style="green")

        for platform, count in sorted(report["by_platform"].items(), key=lambda x: -x[1]):
            platform_table.add_row(platform, str(count))

        console.print(platform_table)

        # Tabela de domínios
        domain_table = Table(title="Sites por Tipo de Domínio")
        domain_table.add_column("Tipo", style="cyan")
        domain_table.add_column("Quantidade", style="green")

        for domain, count in sorted(report["by_domain"].items(), key=lambda x: -x[1]):
            domain_table.add_row(domain, str(count))

        console.print(domain_table)

        # Top estruturas
        console.print("\n[bold]Top 10 Grupos por Estrutura:[/bold]")
        structure_sorted = sorted(report["by_structure"].items(), key=lambda x: -x[1])[:10]
        for i, (structure, count) in enumerate(structure_sorted, 1):
            console.print(f"  {i}. [cyan]{structure}[/cyan]: {count} sites")


def load_sites_from_csv(filepath: str) -> List[Dict[str, str]]:
    """Carrega lista de sites de um arquivo CSV"""
    sites = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('dominio') or row.get('domain'):
                sites.append(row)
    return sites
