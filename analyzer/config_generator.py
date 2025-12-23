"""
Gerador de Configuração para Crawler de Leilões

Gera configurações de crawl baseadas na análise dos sites.
Produz CSV atualizado e JSON com grupos de sites similares.
"""

import csv
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path
from collections import defaultdict


@dataclass
class CrawlConfig:
    """Configuração de crawl para um site"""
    grupo: str = ""
    nome: str = ""
    dominio: str = ""
    url_base: str = ""
    crawl_urls: List[str] = field(default_factory=list)
    include_paths: List[str] = field(default_factory=list)
    platform: str = ""
    status: str = ""


@dataclass
class SiteGroup:
    """Grupo de sites com estrutura similar"""
    group_id: str
    group_name: str
    platform: str
    include_paths: List[str]
    sites: List[CrawlConfig] = field(default_factory=list)
    description: str = ""


class ConfigGenerator:
    """Gera configurações de crawl a partir de resultados de análise"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.groups: Dict[str, SiteGroup] = {}
        self.configs: List[CrawlConfig] = []

    def process_analysis_results(self, results: List[Dict[str, Any]]) -> None:
        """Processa resultados de análise e gera configurações"""
        for result in results:
            config = self._create_config(result)
            self.configs.append(config)

        self._group_sites()

    def _create_config(self, result: Dict[str, Any]) -> CrawlConfig:
        """Cria configuração de crawl a partir de resultado de análise"""
        config = CrawlConfig(
            nome=result.get('name', ''),
            dominio=result.get('domain', ''),
            url_base=result.get('base_url', result.get('final_url', '')),
            platform=result.get('platform', 'unknown'),
            status=result.get('status', 'unknown')
        )

        # Extrai crawl_urls
        if 'crawl_urls' in result:
            config.crawl_urls = result['crawl_urls']
        elif 'crawl_start_urls' in result:
            config.crawl_urls = result['crawl_start_urls']
        else:
            config.crawl_urls = [config.url_base] if config.url_base else []

        # Extrai include_paths
        if 'include_paths' in result:
            config.include_paths = result['include_paths']
        elif 'lot_include_patterns' in result:
            config.include_paths = result['lot_include_patterns']
        else:
            config.include_paths = ['/lote/', '/item/']

        return config

    def _group_sites(self) -> None:
        """Agrupa sites por estrutura similar"""
        platform_groups = defaultdict(list)

        for config in self.configs:
            # Cria chave de grupo baseada em plataforma + include_paths
            include_key = ','.join(sorted(config.include_paths))
            group_key = f"{config.platform}::{include_key}"

            platform_groups[group_key].append(config)

        # Cria grupos
        for group_key, sites in platform_groups.items():
            parts = group_key.split('::')
            platform = parts[0]
            include_paths = parts[1].split(',') if len(parts) > 1 else []

            group = SiteGroup(
                group_id=group_key,
                group_name=self._generate_group_name(platform, include_paths),
                platform=platform,
                include_paths=include_paths,
                sites=sites
            )

            # Atualiza o grupo de cada config
            for config in sites:
                config.grupo = group.group_name

            self.groups[group_key] = group

    def _generate_group_name(self, platform: str, include_paths: List[str]) -> str:
        """Gera um nome legível para o grupo"""
        if platform == 'lel.br':
            name = "Plataforma LEL.BR"
        elif platform == 'leilao.br':
            name = "Plataforma LEILAO.BR"
        elif platform == 'superbid':
            name = "Superbid"
        elif platform == 'bomvalor':
            name = "Bom Valor"
        elif platform == 'zuk':
            name = "Portal Zuk"
        else:
            name = "Sites Próprios"

        # Adiciona tipo de lote
        if '/imovel/' in include_paths or '/imoveis/' in include_paths:
            name += " - Imóveis"
        elif '/veiculo/' in include_paths or '/veiculos/' in include_paths:
            name += " - Veículos"

        return name

    def export_updated_csv(self, filepath: str) -> None:
        """Exporta CSV atualizado com configurações"""
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'grupo', 'nome', 'dominio', 'url_base',
                'crawl_urls', 'include_paths', 'status'
            ])

            for config in sorted(self.configs, key=lambda x: x.grupo):
                writer.writerow([
                    config.grupo,
                    config.nome,
                    config.dominio,
                    config.url_base,
                    '|'.join(config.crawl_urls),
                    '|'.join(config.include_paths),
                    config.status
                ])

    def export_groups_json(self, filepath: str) -> None:
        """Exporta JSON com grupos de sites"""
        groups_data = {}

        for group_id, group in self.groups.items():
            groups_data[group.group_name] = {
                "id": group.group_id,
                "platform": group.platform,
                "include_paths": group.include_paths,
                "site_count": len(group.sites),
                "sites": [
                    {
                        "nome": s.nome,
                        "dominio": s.dominio,
                        "url_base": s.url_base,
                        "crawl_urls": s.crawl_urls,
                        "include_paths": s.include_paths
                    }
                    for s in group.sites
                ]
            }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(groups_data, f, ensure_ascii=False, indent=2)

    def export_crawler_config(self, filepath: str) -> None:
        """Exporta configuração pronta para uso no crawler"""
        config = {
            "sites": [],
            "groups": {}
        }

        for c in self.configs:
            if c.status == "success":
                site_config = {
                    "name": c.nome,
                    "domain": c.dominio,
                    "start_urls": c.crawl_urls,
                    "include_patterns": c.include_paths,
                    "group": c.grupo
                }
                config["sites"].append(site_config)

        for group_name, group in self.groups.items():
            config["groups"][group.group_name] = {
                "platform": group.platform,
                "common_include_paths": group.include_paths,
                "site_count": len([s for s in group.sites if s.status == "success"])
            }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def print_summary(self) -> None:
        """Imprime resumo das configurações geradas"""
        print("\n" + "="*60)
        print("RESUMO DAS CONFIGURAÇÕES GERADAS")
        print("="*60)

        print(f"\nTotal de sites: {len(self.configs)}")
        print(f"Grupos identificados: {len(self.groups)}")

        print("\n" + "-"*40)
        print("GRUPOS:")
        print("-"*40)

        for group_name, group in sorted(self.groups.items(), key=lambda x: -len(x[1].sites)):
            success_count = sum(1 for s in group.sites if s.status == "success")
            print(f"\n{group.group_name}:")
            print(f"  Sites: {len(group.sites)} (success: {success_count})")
            print(f"  Plataforma: {group.platform}")
            print(f"  Include paths: {', '.join(group.include_paths)}")


def generate_configs_from_analysis(
    analysis_file: str,
    output_dir: str = "output"
) -> ConfigGenerator:
    """
    Gera configurações a partir de arquivo de análise JSON

    Args:
        analysis_file: Caminho para arquivo JSON com resultados de análise
        output_dir: Diretório para salvar configurações

    Returns:
        ConfigGenerator com configurações processadas
    """
    with open(analysis_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    generator = ConfigGenerator(output_dir=output_dir)
    generator.process_analysis_results(results)

    return generator
