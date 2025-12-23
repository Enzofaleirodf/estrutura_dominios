#!/usr/bin/env python3
"""
Analisador Inteligente com Firecrawl

Usa a API do Firecrawl para scraping profissional com:
- Proxy automático
- Renderização JavaScript
- Localização BR
- Bypass de proteções
"""

import asyncio
import aiohttp
import json
import csv
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Optional, Tuple


FIRECRAWL_API_KEY = "fc-19e8c1585f334b02bdbc0ee89d9c9386"
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"


# Padrões de URL que indicam lotes
LOT_URL_PATTERNS = [
    r'/lotes?[/-]',
    r'/items?[/-]',
    r'/produtos?[/-]',
    r'/bens?[/-]',
    r'/imove[il]s?[/-]',
    r'/imoveis[/-]',
    r'/veiculos?[/-]',
    r'/detalhes?[/-]',
    r'/auction[/-]?item',
    r'/lot[/-]',
    r'/property[/-]',
    r'/vehicle[/-]',
    r'\?.*id[_-]?(lote|item|produto)',
    r'/\d{3,}',  # IDs numéricos
]

# Keywords para identificar links de lotes
LOT_KEYWORDS = [
    'lote', 'lance', 'arremate', 'detalhe', 'ver mais',
    'saiba mais', 'acessar', 'visualizar'
]

# Keywords para páginas de listagem
LISTING_KEYWORDS = [
    'leilão', 'leilao', 'leilões', 'leiloes',
    'catálogo', 'catalogo', 'busca', 'buscar',
    'imóveis', 'imoveis', 'veículos', 'veiculos',
    'em andamento', 'abertos', 'próximos', 'proximos'
]


@dataclass
class SmartAnalysisResult:
    """Resultado da análise"""
    nome: str
    dominio: str
    status: str = "pending"
    url_base: str = ""
    url_final: str = ""
    listing_pages: List[str] = field(default_factory=list)
    lot_patterns: List[Dict] = field(default_factory=list)
    lot_examples: List[str] = field(default_factory=list)
    crawl_start_urls: List[str] = field(default_factory=list)
    include_paths: List[str] = field(default_factory=list)
    pages_visited: int = 0
    links_analyzed: int = 0
    error_message: str = ""
    analysis_time_ms: float = 0
    raw_links: List[str] = field(default_factory=list)


class FirecrawlAnalyzer:
    """Analisador usando Firecrawl API"""

    def __init__(self, api_key: str = FIRECRAWL_API_KEY, timeout: int = 60):
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def scrape_page(self, session: aiohttp.ClientSession, url: str) -> Tuple[Optional[Dict], str]:
        """Faz scrape de uma página usando Firecrawl"""
        payload = {
            "url": url,
            "formats": ["html", "links"],
            "onlyMainContent": False,
            "waitFor": 3000,
            "timeout": 30000,
            "location": {
                "country": "BR",
                "languages": ["pt-BR", "pt"]
            }
        }

        try:
            async with session.post(
                FIRECRAWL_API_URL,
                json=payload,
                headers=self.headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        return data.get("data", {}), ""
                    else:
                        return None, data.get("error", "Erro desconhecido do Firecrawl")
                else:
                    error_text = await response.text()
                    return None, f"HTTP {response.status}: {error_text[:100]}"

        except asyncio.TimeoutError:
            return None, "Timeout na requisição ao Firecrawl"
        except Exception as e:
            return None, f"{type(e).__name__}: {str(e)[:100]}"

    async def analyze_site(self, dominio: str, nome: str) -> SmartAnalysisResult:
        """Analisa um site usando Firecrawl"""
        import time
        start_time = time.time()

        result = SmartAnalysisResult(nome=nome, dominio=dominio)

        # Normaliza URL
        if not dominio.startswith(('http://', 'https://')):
            dominio = f"https://{dominio}"
        dominio = dominio.replace("https://www.www.", "https://www.")
        result.url_base = dominio

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:

                # 1. Scrape da página inicial
                print(f"  [1/3] Acessando {dominio} via Firecrawl...")
                data, error = await self.scrape_page(session, dominio)

                if not data:
                    result.status = "error"
                    result.error_message = error
                    print(f"  ❌ ERRO: {error}")
                    return result

                result.pages_visited = 1
                result.url_final = data.get("metadata", {}).get("url", dominio)
                print(f"  ✓ Página carregada: {result.url_final}")

                # Extrai links
                all_links = data.get("links", [])
                html_content = data.get("html", "")

                # Se links não veio, tenta extrair do HTML
                if not all_links and html_content:
                    all_links = self._extract_links_from_html(html_content, result.url_final)

                result.raw_links = all_links[:100]
                print(f"  ✓ Encontrados {len(all_links)} links")

                # 2. Filtra links de listagem e lotes
                print(f"  [2/3] Analisando links...")
                base_domain = urlparse(result.url_final).netloc

                listing_links = []
                lot_links = []

                for link in all_links:
                    if not isinstance(link, str):
                        continue

                    # Verifica se é link interno
                    try:
                        parsed = urlparse(link)
                        link_domain = parsed.netloc
                        if link_domain and not self._is_same_domain(link_domain, base_domain):
                            continue
                    except:
                        continue

                    link_lower = link.lower()
                    path = urlparse(link).path.lower()

                    # Verifica se é link de listagem
                    if any(kw in link_lower for kw in LISTING_KEYWORDS):
                        listing_links.append(link)

                    # Verifica se é link de lote
                    is_lot = any(re.search(p, path) for p in LOT_URL_PATTERNS)
                    if is_lot:
                        lot_links.append(link)

                result.listing_pages = list(set(listing_links))[:10]
                result.lot_examples = list(set(lot_links))[:30]
                result.links_analyzed = len(all_links)

                print(f"  ✓ Páginas de listagem: {len(result.listing_pages)}")
                print(f"  ✓ Links de lotes: {len(result.lot_examples)}")

                # 3. Extrai padrões
                print(f"  [3/3] Extraindo padrões...")
                patterns = self._extract_patterns(result.lot_examples)
                result.lot_patterns = patterns
                result.include_paths = [p["pattern"] for p in patterns]

                # Gera config de crawl
                crawl_urls = [result.url_final]
                for listing in result.listing_pages[:3]:
                    if listing not in crawl_urls:
                        crawl_urls.append(listing)
                result.crawl_start_urls = crawl_urls

                # Fallback se não encontrou padrões
                if not result.include_paths:
                    result.include_paths = ["/lote/", "/item/", "/detalhe/", "/imovel/", "/veiculo/"]

                result.status = "success" if result.lot_examples else "no_lots_found"
                print(f"  ✓ Padrões encontrados: {result.include_paths}")

        except Exception as e:
            result.status = "error"
            result.error_message = f"{type(e).__name__}: {str(e)[:100]}"
            print(f"  ❌ ERRO: {result.error_message}")

        result.analysis_time_ms = (time.time() - start_time) * 1000
        return result

    def _extract_links_from_html(self, html: str, base_url: str) -> List[str]:
        """Extrai links do HTML"""
        from bs4 import BeautifulSoup

        links = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith(('http://', 'https://')):
                    links.append(href)
                elif href.startswith('/'):
                    links.append(urljoin(base_url, href))
        except:
            pass
        return links

    def _is_same_domain(self, domain1: str, domain2: str) -> bool:
        """Verifica se dois domínios são iguais"""
        d1 = domain1.replace('www.', '').lower()
        d2 = domain2.replace('www.', '').lower()
        return d1 == d2 or d1.endswith('.' + d2) or d2.endswith('.' + d1)

    def _extract_patterns(self, urls: List[str]) -> List[Dict]:
        """Extrai padrões das URLs"""
        if not urls:
            return []

        path_counts = defaultdict(int)

        for url in urls:
            try:
                path = urlparse(url).path

                # Normaliza removendo IDs
                normalized = re.sub(r'/\d+', '/{id}', path)
                normalized = re.sub(r'/[a-f0-9-]{8,}', '/{hash}', normalized)
                normalized = re.sub(r'/[a-z0-9]+-[a-z0-9-]+', '/{slug}', normalized)

                # Extrai o prefixo do padrão
                parts = normalized.split('/{')[0]
                if parts and parts != '/':
                    path_counts[parts + '/'] += 1
            except:
                pass

        # Ordena por frequência
        patterns = []
        for pattern, count in sorted(path_counts.items(), key=lambda x: -x[1]):
            patterns.append({
                "pattern": pattern,
                "count": count,
                "confidence": min(count / 5, 1.0)
            })

        return patterns[:10]


async def run_analysis(sites: List[Dict], max_concurrent: int = 2) -> List[SmartAnalysisResult]:
    """Executa análise em múltiplos sites"""
    analyzer = FirecrawlAnalyzer()
    results = []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_with_limit(site: Dict, idx: int) -> SmartAnalysisResult:
        async with semaphore:
            print(f"\n[{idx+1}/{len(sites)}] {site['nome']}")
            result = await analyzer.analyze_site(site['dominio'], site['nome'])
            await asyncio.sleep(1)  # Rate limiting
            return result

    tasks = [analyze_with_limit(site, i) for i, site in enumerate(sites)]
    results = await asyncio.gather(*tasks)

    return results


def save_results(results: List[SmartAnalysisResult], output_dir: str = "output"):
    """Salva resultados"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON
    json_file = output_path / f"smart_analysis_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
    print(f"\n✓ Salvo: {json_file}")

    # CSV
    csv_file = output_path / f"smart_config_{timestamp}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['nome', 'dominio', 'status', 'url_base', 'crawl_urls', 'include_paths', 'exemplos_lotes', 'erro'])
        for r in results:
            writer.writerow([
                r.nome, r.dominio, r.status, r.url_final or r.url_base,
                '|'.join(r.crawl_start_urls), '|'.join(r.include_paths),
                '|'.join(r.lot_examples[:5]), r.error_message
            ])
    print(f"✓ Salvo: {csv_file}")

    # Resumo
    success = sum(1 for r in results if r.status == "success")
    no_lots = sum(1 for r in results if r.status == "no_lots_found")
    errors = sum(1 for r in results if r.status == "error")

    print(f"\n{'='*50}")
    print("RESUMO")
    print(f"{'='*50}")
    print(f"Total: {len(results)}")
    print(f"Sucesso: {success}")
    print(f"Sem lotes encontrados: {no_lots}")
    print(f"Erros: {errors}")

    for r in results:
        icon = "✓" if r.status == "success" else "⚠" if r.status == "no_lots_found" else "✗"
        print(f"\n{icon} {r.nome}")
        print(f"  URL: {r.dominio}")
        print(f"  Status: {r.status}")
        if r.include_paths:
            print(f"  Include paths: {', '.join(r.include_paths[:5])}")
        if r.lot_examples:
            print(f"  Exemplos: {len(r.lot_examples)} lotes encontrados")
        if r.error_message:
            print(f"  Erro: {r.error_message}")


def load_sites(filepath: str, limit: int = 0) -> List[Dict]:
    """Carrega sites do CSV"""
    sites = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('dominio'):
                sites.append({'nome': row.get('nome', ''), 'dominio': row['dominio']})
                if limit > 0 and len(sites) >= limit:
                    break
    return sites


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', default='Dominios Leilões - Dominios.csv')
    parser.add_argument('--limit', '-l', type=int, default=10)
    parser.add_argument('--concurrent', '-c', type=int, default=2)
    args = parser.parse_args()

    print("="*50)
    print("ANALISADOR COM FIRECRAWL")
    print("="*50)
    print(f"Localização: BR | Idioma: pt-BR, pt | Proxy: auto")

    sites = load_sites(args.input, args.limit)
    print(f"\nSites a analisar: {len(sites)}")

    results = await run_analysis(sites, args.concurrent)
    save_results(results)


if __name__ == "__main__":
    asyncio.run(main())
