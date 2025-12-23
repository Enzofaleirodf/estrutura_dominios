#!/usr/bin/env python3
"""
Analisador Inteligente de Sites de Leilões

Este analisador descobre os padrões REAIS de cada site:
1. Acessa a home e encontra links de navegação
2. Identifica páginas de listagem de lotes
3. Extrai URLs que parecem ser de lotes individuais
4. Analisa e extrai o padrão de URL específico do site
"""

import asyncio
import aiohttp
import re
import json
import csv
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Optional, Tuple
from bs4 import BeautifulSoup

# Palavras-chave para identificar links de navegação para leilões
NAVIGATION_KEYWORDS = [
    'leilão', 'leilao', 'leilões', 'leiloes',
    'catálogo', 'catalogo', 'catalog',
    'em andamento', 'andamento', 'aberto', 'abertos',
    'próximo', 'proximo', 'próximos', 'proximos',
    'agenda', 'eventos', 'evento',
    'busca', 'buscar', 'search',
    'imóveis', 'imoveis', 'imóvel', 'imovel',
    'veículos', 'veiculos', 'veículo', 'veiculo',
    'todos', 'ver todos', 'ver mais',
]

# Palavras-chave que indicam um link para lote individual
LOT_KEYWORDS = [
    'ver lote', 'ver detalhes', 'detalhe', 'detalhes',
    'dar lance', 'lance', 'lançar', 'lancar',
    'ver mais', 'saiba mais', 'mais info',
    'acessar', 'visualizar', 'abrir',
]

# Padrões de texto que indicam preço (sugere que é um lote)
PRICE_PATTERNS = [
    r'R\$\s*[\d.,]+',
    r'lance\s*(mínimo|minimo|atual|inicial)',
    r'avaliação', r'avaliacao',
    r'valor\s*(mínimo|minimo|inicial)',
]

# Padrões de URL que geralmente indicam lotes
LOT_URL_INDICATORS = [
    r'/lote[s]?[/-]',
    r'/item[s]?[/-]',
    r'/produto[s]?[/-]',
    r'/bem[/-]',
    r'/bens[/-]',
    r'/imovel[/-]', r'/imoveis[/-]', r'/imóvel[/-]', r'/imóveis[/-]',
    r'/veiculo[/-]', r'/veiculos[/-]', r'/veículo[/-]', r'/veículos[/-]',
    r'/detalhe[s]?[/-]',
    r'/auction[/-]item',
    r'/lot[/-]',
    r'/property[/-]',
    r'/vehicle[/-]',
    r'\?.*id[_-]?(lote|item|produto)',
    r'/\d{4,}',  # IDs numéricos longos
]


@dataclass
class LotPattern:
    """Padrão de URL de lote descoberto"""
    pattern: str  # Regex pattern
    example_urls: List[str] = field(default_factory=list)
    confidence: float = 0.0
    count: int = 0


@dataclass
class SmartAnalysisResult:
    """Resultado da análise inteligente de um site"""
    nome: str
    dominio: str
    status: str = "pending"

    # URLs descobertas
    url_base: str = ""
    url_final: str = ""  # Após redirects

    # Páginas de listagem encontradas
    listing_pages: List[str] = field(default_factory=list)

    # Padrões de lotes descobertos
    lot_patterns: List[Dict] = field(default_factory=list)

    # URLs de exemplo de lotes
    lot_examples: List[str] = field(default_factory=list)

    # Configuração final para crawler
    crawl_start_urls: List[str] = field(default_factory=list)
    include_paths: List[str] = field(default_factory=list)

    # Metadados
    pages_visited: int = 0
    links_analyzed: int = 0
    error_message: str = ""
    analysis_time_ms: float = 0


class SmartSiteAnalyzer:
    """Analisador inteligente de sites de leilão"""

    def __init__(self, timeout: int = 30, max_pages: int = 10):
        self.timeout = aiohttp.ClientTimeout(total=timeout, connect=15)
        self.max_pages = max_pages
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.95,en-BR;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.google.com.br/",
        }

    async def analyze_site(self, dominio: str, nome: str) -> SmartAnalysisResult:
        """Analisa um site de forma inteligente"""
        import time
        start_time = time.time()

        result = SmartAnalysisResult(nome=nome, dominio=dominio)

        # Normaliza URL
        if not dominio.startswith(('http://', 'https://')):
            dominio = f"https://{dominio}"
        dominio = dominio.replace("https://www.www.", "https://www.")
        result.url_base = dominio

        try:
            connector = aiohttp.TCPConnector(ssl=False, limit=10)
            async with aiohttp.ClientSession(
                timeout=self.timeout,
                headers=self.headers,
                connector=connector
            ) as session:

                # 1. Acessa página inicial
                print(f"  [1/4] Acessando {dominio}...")
                home_html, final_url, error_msg = await self._fetch_page(session, dominio)

                if not home_html:
                    result.status = "error"
                    result.error_message = error_msg or "Não foi possível acessar a página inicial"
                    print(f"  ❌ ERRO: {result.error_message}")
                    return result

                print(f"  ✓ Página carregada: {final_url}")

                result.url_final = final_url
                result.pages_visited = 1
                base_domain = urlparse(final_url).netloc

                # 2. Encontra links de navegação para leilões
                print(f"  [2/4] Procurando páginas de listagem...")
                nav_links = self._find_navigation_links(home_html, final_url, base_domain)

                # Adiciona URLs comuns de listagem
                common_paths = ['/leiloes', '/leilao', '/catalogo', '/imoveis', '/veiculos', '/lotes', '/busca']
                for path in common_paths:
                    potential = f"{final_url.rstrip('/')}{path}"
                    if potential not in nav_links:
                        nav_links.append(potential)

                # 3. Visita páginas de listagem e coleta links de lotes
                print(f"  [3/4] Analisando {len(nav_links[:self.max_pages])} páginas de listagem...")
                all_lot_candidates = []
                visited = {final_url}

                # Também analisa links da home
                home_lot_candidates = self._find_lot_links(home_html, final_url, base_domain)
                all_lot_candidates.extend(home_lot_candidates)

                for nav_url in nav_links[:self.max_pages]:
                    if nav_url in visited:
                        continue
                    visited.add(nav_url)

                    page_html, _, _ = await self._fetch_page(session, nav_url, retries=1)
                    if page_html:
                        result.pages_visited += 1
                        lot_candidates = self._find_lot_links(page_html, nav_url, base_domain)
                        all_lot_candidates.extend(lot_candidates)

                        if lot_candidates:
                            result.listing_pages.append(nav_url)
                            print(f"  ✓ Encontrados {len(lot_candidates)} lotes em {nav_url}")

                    await asyncio.sleep(0.5)  # Rate limiting

                result.links_analyzed = len(all_lot_candidates)

                # 4. Analisa padrões das URLs de lotes
                print(f"  [4/4] Extraindo padrões de {len(all_lot_candidates)} URLs...")
                patterns = self._extract_patterns(all_lot_candidates, base_domain)

                result.lot_patterns = [asdict(p) for p in patterns]
                result.lot_examples = list(set(all_lot_candidates))[:20]

                # 5. Gera configuração final
                self._generate_config(result, patterns)

                result.status = "success" if patterns else "no_patterns"

        except asyncio.TimeoutError:
            result.status = "timeout"
            result.error_message = f"Timeout após {self.timeout.total}s"
        except Exception as e:
            result.status = "error"
            result.error_message = f"{type(e).__name__}: {str(e)[:100]}"

        result.analysis_time_ms = (time.time() - start_time) * 1000
        return result

    async def _fetch_page(self, session: aiohttp.ClientSession, url: str, retries: int = 2) -> Tuple[Optional[str], str, str]:
        """Busca uma página e retorna o HTML + erro detalhado"""
        last_error = ""

        for attempt in range(retries + 1):
            try:
                async with session.get(url, allow_redirects=True, ssl=False) as response:
                    if response.status == 200:
                        html = await response.text()
                        return html, str(response.url), ""
                    elif response.status == 403:
                        last_error = f"HTTP 403 Forbidden - Site bloqueou acesso"
                    elif response.status == 503:
                        last_error = f"HTTP 503 - Cloudflare/proteção ativa"
                    else:
                        last_error = f"HTTP {response.status}"

            except aiohttp.ClientConnectorError as e:
                last_error = f"Conexão falhou: {str(e)[:80]}"
            except aiohttp.ServerTimeoutError:
                last_error = "Timeout - servidor não respondeu"
            except aiohttp.ClientSSLError as e:
                last_error = f"Erro SSL: {str(e)[:80]}"
            except asyncio.TimeoutError:
                last_error = "Timeout na requisição"
            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)[:80]}"

            if attempt < retries:
                await asyncio.sleep(1)  # Espera antes de retry

        return None, url, last_error

    def _find_navigation_links(self, html: str, base_url: str, base_domain: str) -> List[str]:
        """Encontra links de navegação que levam a páginas de listagem"""
        soup = BeautifulSoup(html, 'lxml')
        nav_links = []

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            text = a_tag.get_text(strip=True).lower()

            # Verifica se o texto do link indica navegação para leilões
            is_nav_link = any(kw in text for kw in NAVIGATION_KEYWORDS)

            # Também verifica o href
            href_lower = href.lower()
            is_nav_href = any(kw in href_lower for kw in ['leilao', 'leiloe', 'catalogo', 'busca', 'imovel', 'imoveis', 'veiculo', 'veiculos'])

            if is_nav_link or is_nav_href:
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)

                # Verifica se é link interno
                if self._is_same_domain(parsed.netloc, base_domain):
                    if full_url not in nav_links:
                        nav_links.append(full_url)

        return nav_links

    def _find_lot_links(self, html: str, base_url: str, base_domain: str) -> List[str]:
        """Encontra links que parecem ser de lotes individuais"""
        soup = BeautifulSoup(html, 'lxml')
        lot_links = []

        # Estratégia 1: Links com palavras-chave de lote
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            text = a_tag.get_text(strip=True).lower()

            # Pula links de navegação
            if any(kw in text for kw in ['home', 'início', 'contato', 'sobre', 'login', 'cadastro', 'entrar']):
                continue

            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            if not self._is_same_domain(parsed.netloc, base_domain):
                continue

            path = parsed.path.lower()

            # Verifica indicadores de URL de lote
            is_lot_url = any(re.search(pattern, path) for pattern in LOT_URL_INDICATORS)

            # Verifica texto do link
            is_lot_text = any(kw in text for kw in LOT_KEYWORDS)

            # Verifica contexto (preço próximo)
            parent = a_tag.parent
            parent_text = parent.get_text() if parent else ""
            has_price = any(re.search(p, parent_text, re.IGNORECASE) for p in PRICE_PATTERNS)

            if is_lot_url or is_lot_text or has_price:
                if full_url not in lot_links:
                    lot_links.append(full_url)

        # Estratégia 2: Procura por cards/grids de produtos
        card_selectors = [
            '.card', '.item', '.product', '.lote', '.lot',
            '[class*="card"]', '[class*="item"]', '[class*="product"]',
            '[class*="lote"]', '[class*="lot"]', '[class*="grid"]',
        ]

        for selector in card_selectors:
            try:
                cards = soup.select(selector)
                for card in cards:
                    link = card.find('a', href=True)
                    if link:
                        full_url = urljoin(base_url, link['href'])
                        parsed = urlparse(full_url)
                        if self._is_same_domain(parsed.netloc, base_domain):
                            if full_url not in lot_links:
                                lot_links.append(full_url)
            except:
                pass

        return lot_links

    def _extract_patterns(self, urls: List[str], base_domain: str) -> List[LotPattern]:
        """Extrai padrões das URLs de lotes"""
        if not urls:
            return []

        # Agrupa URLs por estrutura de path
        path_structures = defaultdict(list)

        for url in urls:
            parsed = urlparse(url)
            path = parsed.path

            # Normaliza o path substituindo números e slugs
            normalized = re.sub(r'/\d+', '/{id}', path)
            normalized = re.sub(r'/[a-f0-9]{8,}', '/{hash}', normalized)  # Hashes
            normalized = re.sub(r'/[a-z0-9]+-[a-z0-9-]+', '/{slug}', normalized)  # Slugs

            path_structures[normalized].append(url)

        # Cria padrões ordenados por frequência
        patterns = []
        for structure, urls_list in sorted(path_structures.items(), key=lambda x: -len(x[1])):
            if len(urls_list) >= 1:  # Aceita mesmo com 1 ocorrência
                # Converte estrutura em include_path
                include_path = structure.split('/{')[0]
                if include_path and include_path != '/':
                    include_path = include_path.rstrip('/') + '/'

                    pattern = LotPattern(
                        pattern=include_path,
                        example_urls=urls_list[:5],
                        count=len(urls_list),
                        confidence=min(len(urls_list) / 10, 1.0)
                    )
                    patterns.append(pattern)

        return patterns[:10]  # Top 10 padrões

    def _generate_config(self, result: SmartAnalysisResult, patterns: List[LotPattern]) -> None:
        """Gera configuração final para o crawler"""
        base = result.url_final or result.url_base

        # URLs de início do crawl
        crawl_urls = [base]
        for page in result.listing_pages[:5]:
            if page not in crawl_urls:
                crawl_urls.append(page)

        result.crawl_start_urls = crawl_urls

        # Include paths
        include_paths = []
        for pattern in patterns:
            if pattern.pattern and pattern.pattern not in include_paths:
                include_paths.append(pattern.pattern)

        # Fallback se não encontrou nada
        if not include_paths:
            include_paths = ['/lote/', '/item/', '/detalhe/']

        result.include_paths = include_paths

    def _is_same_domain(self, domain1: str, domain2: str) -> bool:
        """Verifica se dois domínios são equivalentes"""
        d1 = domain1.replace('www.', '').lower()
        d2 = domain2.replace('www.', '').lower()
        return d1 == d2


async def run_smart_analysis(sites: List[Dict], max_concurrent: int = 5) -> List[SmartAnalysisResult]:
    """Executa análise inteligente em múltiplos sites"""
    analyzer = SmartSiteAnalyzer(timeout=45, max_pages=8)
    results = []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_with_semaphore(site: Dict, index: int) -> SmartAnalysisResult:
        async with semaphore:
            print(f"\n[{index+1}/{len(sites)}] Analisando: {site['nome']}")
            result = await analyzer.analyze_site(site['dominio'], site['nome'])
            print(f"  → Status: {result.status} | Padrões: {len(result.lot_patterns)} | Exemplos: {len(result.lot_examples)}")
            return result

    tasks = [analyze_with_semaphore(site, i) for i, site in enumerate(sites)]
    results = await asyncio.gather(*tasks)

    return results


def save_results(results: List[SmartAnalysisResult], output_dir: str = "output"):
    """Salva os resultados da análise"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON detalhado
    json_file = output_path / f"smart_analysis_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
    print(f"\nSalvo: {json_file}")

    # CSV simplificado
    csv_file = output_path / f"smart_config_{timestamp}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['nome', 'dominio', 'status', 'url_base', 'crawl_urls', 'include_paths', 'exemplos_lotes'])

        for r in results:
            writer.writerow([
                r.nome,
                r.dominio,
                r.status,
                r.url_final or r.url_base,
                '|'.join(r.crawl_start_urls),
                '|'.join(r.include_paths),
                '|'.join(r.lot_examples[:5])
            ])
    print(f"Salvo: {csv_file}")

    # Resumo
    success = sum(1 for r in results if r.status == "success")
    no_patterns = sum(1 for r in results if r.status == "no_patterns")
    errors = sum(1 for r in results if r.status in ["error", "timeout"])

    print(f"\n{'='*50}")
    print(f"RESUMO DA ANÁLISE INTELIGENTE")
    print(f"{'='*50}")
    print(f"Total de sites: {len(results)}")
    print(f"Sucesso: {success}")
    print(f"Sem padrões: {no_patterns}")
    print(f"Erros/Timeout: {errors}")

    print(f"\n{'='*50}")
    print(f"RESULTADOS POR SITE")
    print(f"{'='*50}")

    for r in results:
        print(f"\n{r.nome} ({r.dominio})")
        print(f"  Status: {r.status}")
        if r.include_paths:
            print(f"  Include paths: {', '.join(r.include_paths)}")
        if r.lot_examples:
            print(f"  Exemplos de lotes:")
            for ex in r.lot_examples[:3]:
                print(f"    - {ex}")

    return json_file, csv_file


def load_sites_from_csv(filepath: str, limit: int = 0) -> List[Dict]:
    """Carrega sites do CSV"""
    sites = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('dominio'):
                sites.append({
                    'nome': row.get('nome', ''),
                    'dominio': row['dominio']
                })
                if limit > 0 and len(sites) >= limit:
                    break
    return sites


async def main():
    import argparse

    parser = argparse.ArgumentParser(description='Analisador Inteligente de Sites de Leilões')
    parser.add_argument('--input', '-i', default='Dominios Leilões - Dominios.csv', help='CSV com domínios')
    parser.add_argument('--limit', '-l', type=int, default=10, help='Limite de sites (0=todos)')
    parser.add_argument('--concurrent', '-c', type=int, default=3, help='Requisições simultâneas')
    args = parser.parse_args()

    print(f"{'='*50}")
    print("ANALISADOR INTELIGENTE DE SITES DE LEILÕES")
    print(f"{'='*50}")

    # Carrega sites
    sites = load_sites_from_csv(args.input, args.limit)
    print(f"\nSites carregados: {len(sites)}")

    # Executa análise
    results = await run_smart_analysis(sites, max_concurrent=args.concurrent)

    # Salva resultados
    save_results(results)


if __name__ == "__main__":
    asyncio.run(main())
