"""
Analisador Profundo de Sites de Leilões

Faz uma análise mais detalhada explorando múltiplas páginas
para descobrir padrões de URL com maior precisão.
"""

import re
import asyncio
from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional, Tuple
from urllib.parse import urlparse, urljoin, parse_qs
from collections import Counter

import aiohttp
from bs4 import BeautifulSoup


@dataclass
class DeepAnalysisResult:
    """Resultado da análise profunda de um site"""
    domain: str
    name: str
    status: str = "pending"

    # URLs descobertas
    base_url: str = ""
    final_url: str = ""  # Após redirects

    # Configuração para o crawler
    crawl_start_urls: List[str] = field(default_factory=list)
    lot_include_patterns: List[str] = field(default_factory=list)

    # Estatísticas
    pages_analyzed: int = 0
    total_links_found: int = 0
    lot_links_found: int = 0

    # Padrões detectados com confiança
    detected_patterns: Dict[str, float] = field(default_factory=dict)  # pattern -> confidence

    # Exemplos de URLs de lote
    lot_url_examples: List[str] = field(default_factory=list)

    # Metadados
    platform: str = "unknown"
    error_message: str = ""


# Padrões regex para detectar URLs de lotes
LOT_URL_PATTERNS = [
    # Padrão /lote/{id}
    (r'/lotes?/(\d+)', 'lote_numerico'),
    (r'/lotes?/([\w]+-[\w-]+)', 'lote_slug'),

    # Padrão /item/{id}
    (r'/items?/(\d+)', 'item_numerico'),

    # Padrão /produto/{id}
    (r'/produtos?/(\d+)', 'produto_numerico'),

    # Padrão /bem/{id}
    (r'/bens?/(\d+)', 'bem_numerico'),

    # Padrão /imovel/{id}
    (r'/imove[il]s?/(\d+)', 'imovel_numerico'),
    (r'/imove[il]s?/([\w]+-[\w-]+)', 'imovel_slug'),

    # Padrão /veiculo/{id}
    (r'/veiculos?/(\d+)', 'veiculo_numerico'),
    (r'/veiculos?/([\w]+-[\w-]+)', 'veiculo_slug'),

    # Padrão /detalhe/{id}
    (r'/detalhe[s]?/(\d+)', 'detalhe_numerico'),
    (r'/detalhe[s]?/([\w-]+)', 'detalhe_slug'),

    # Padrão /ver/{id}
    (r'/ver/(\d+)', 'ver_numerico'),

    # Padrão query string
    (r'\?.*(?:lote|item|id)[_-]?=(\d+)', 'query_id'),

    # Padrões específicos de plataformas
    (r'/auction-item/(\d+)', 'auction_item'),
    (r'/lot-detail/(\d+)', 'lot_detail'),
    (r'/property/(\d+)', 'property'),
]

# Padrões de páginas de listagem
LISTING_PATTERNS = [
    r'/leiloes?/?$',
    r'/leiloes?/[^/]+/?$',
    r'/lotes?/?$',
    r'/catalogo/?',
    r'/busca/?',
    r'/search/?',
    r'/produtos?/?$',
    r'/imove[il]s?/?$',
    r'/veiculos?/?$',
    r'/ativos?/?$',
    r'/hastas?/?$',
    r'/eventos?/?$',
    r'/proximos/?',
    r'/abertos?/?$',
    r'/em-andamento/?$',
]


class DeepSiteAnalyzer:
    """Analisador profundo de sites de leilão"""

    def __init__(
        self,
        timeout: int = 30,
        max_pages_per_site: int = 10,
        max_links_per_page: int = 200
    ):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_pages = max_pages_per_site
        self.max_links = max_links_per_page
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }

    async def analyze_site(self, domain: str, name: str) -> DeepAnalysisResult:
        """Analisa um site em profundidade"""
        result = DeepAnalysisResult(domain=domain, name=name)

        # Normaliza URL
        if not domain.startswith(('http://', 'https://')):
            domain = f"https://{domain}"
        domain = domain.replace("https://www.www.", "https://www.")

        result.base_url = domain

        try:
            async with aiohttp.ClientSession(
                timeout=self.timeout,
                headers=self.headers,
                connector=aiohttp.TCPConnector(ssl=False)
            ) as session:
                # Analisa página inicial
                initial_links, final_url = await self._analyze_page(session, domain)

                if not initial_links:
                    result.status = "error"
                    result.error_message = "Não foi possível acessar a página inicial"
                    return result

                result.final_url = final_url
                result.platform = self._detect_platform(domain)

                # Coleta todas as URLs para análise
                all_links = set(initial_links)
                pages_to_visit = self._find_listing_pages(initial_links, domain)
                visited = {domain, final_url}

                # Visita páginas de listagem para encontrar mais lotes
                for page_url in pages_to_visit[:self.max_pages - 1]:
                    if page_url in visited:
                        continue

                    visited.add(page_url)
                    page_links, _ = await self._analyze_page(session, page_url)

                    if page_links:
                        all_links.update(page_links)
                        result.pages_analyzed += 1

                    await asyncio.sleep(0.5)  # Delay entre requisições

                result.pages_analyzed += 1
                result.total_links_found = len(all_links)

                # Analisa padrões de lotes
                lot_links, patterns = self._analyze_lot_patterns(all_links, domain)
                result.lot_links_found = len(lot_links)
                result.lot_url_examples = list(lot_links)[:10]
                result.detected_patterns = patterns

                # Define configuração de crawl
                self._define_crawl_config(result, pages_to_visit, patterns)

                result.status = "success"

        except asyncio.TimeoutError:
            result.status = "timeout"
            result.error_message = f"Timeout após {self.timeout.total}s"
        except aiohttp.ClientError as e:
            result.status = "error"
            result.error_message = str(e)
        except Exception as e:
            result.status = "error"
            result.error_message = f"{type(e).__name__}: {str(e)}"

        return result

    async def _analyze_page(
        self,
        session: aiohttp.ClientSession,
        url: str
    ) -> Tuple[Set[str], str]:
        """Analisa uma página e retorna os links encontrados"""
        try:
            async with session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    return set(), url

                final_url = str(response.url)
                html = await response.text()

                soup = BeautifulSoup(html, 'lxml')
                base_domain = urlparse(final_url).netloc

                links = set()
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']

                    if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                        continue

                    full_url = urljoin(final_url, href)
                    parsed = urlparse(full_url)

                    # Verifica se é link interno
                    if self._is_same_domain(parsed.netloc, base_domain):
                        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                        if parsed.query:
                            clean_url += f"?{parsed.query}"
                        links.add(clean_url)

                return links, final_url

        except Exception:
            return set(), url

    def _is_same_domain(self, domain1: str, domain2: str) -> bool:
        """Verifica se dois domínios são equivalentes"""
        d1 = domain1.replace('www.', '')
        d2 = domain2.replace('www.', '')
        return d1 == d2

    def _detect_platform(self, domain: str) -> str:
        """Detecta a plataforma do site"""
        domain_lower = domain.lower()

        if '.lel.br' in domain_lower:
            return 'lel.br'
        elif '.leilao.br' in domain_lower:
            return 'leilao.br'
        elif 'superbid' in domain_lower:
            return 'superbid'
        elif 'bomvalor' in domain_lower:
            return 'bomvalor'
        elif 'zuk' in domain_lower:
            return 'zuk'
        else:
            return 'custom'

    def _find_listing_pages(self, links: Set[str], base_url: str) -> List[str]:
        """Encontra páginas de listagem para visitar"""
        listing_pages = []

        for link in links:
            parsed = urlparse(link)
            path = parsed.path.lower()

            for pattern in LISTING_PATTERNS:
                if re.search(pattern, path):
                    listing_pages.append(link)
                    break

        # Adiciona URLs comuns de listagem
        base = base_url.rstrip('/')
        common_paths = [
            '/leiloes', '/leilao', '/lotes', '/catalogo',
            '/imoveis', '/veiculos', '/busca', '/proximos-leiloes'
        ]

        for path in common_paths:
            potential = f"{base}{path}"
            if potential not in listing_pages:
                listing_pages.append(potential)

        return listing_pages

    def _analyze_lot_patterns(
        self,
        links: Set[str],
        base_url: str
    ) -> Tuple[Set[str], Dict[str, float]]:
        """Analisa padrões de URLs de lotes"""
        lot_links = set()
        pattern_counts = Counter()

        for link in links:
            parsed = urlparse(link)
            path = parsed.path + ('?' + parsed.query if parsed.query else '')

            for regex, pattern_name in LOT_URL_PATTERNS:
                if re.search(regex, path, re.IGNORECASE):
                    lot_links.add(link)
                    pattern_counts[pattern_name] += 1
                    break

        # Calcula confiança para cada padrão
        total = sum(pattern_counts.values()) if pattern_counts else 1
        patterns = {
            name: count / total
            for name, count in pattern_counts.items()
        }

        return lot_links, patterns

    def _define_crawl_config(
        self,
        result: DeepAnalysisResult,
        listing_pages: List[str],
        patterns: Dict[str, float]
    ) -> None:
        """Define as configurações de crawl baseado na análise"""
        base = result.final_url or result.base_url

        # URLs de início do crawl
        crawl_urls = [base]

        # Adiciona páginas de listagem encontradas
        for page in listing_pages[:3]:
            if page not in crawl_urls:
                crawl_urls.append(page)

        result.crawl_start_urls = crawl_urls[:5]

        # Define include patterns baseado nos padrões detectados
        include_patterns = []

        # Mapeia padrões para include paths
        pattern_to_include = {
            'lote_numerico': '/lote/',
            'lote_slug': '/lote/',
            'item_numerico': '/item/',
            'produto_numerico': '/produto/',
            'bem_numerico': '/bem/',
            'imovel_numerico': '/imovel/',
            'imovel_slug': '/imovel/',
            'veiculo_numerico': '/veiculo/',
            'veiculo_slug': '/veiculo/',
            'detalhe_numerico': '/detalhe/',
            'detalhe_slug': '/detalhe/',
            'ver_numerico': '/ver/',
            'query_id': '?',
            'auction_item': '/auction-item/',
            'lot_detail': '/lot-detail/',
            'property': '/property/',
        }

        for pattern_name, confidence in sorted(patterns.items(), key=lambda x: -x[1]):
            if pattern_name in pattern_to_include and confidence > 0.1:
                include = pattern_to_include[pattern_name]
                if include not in include_patterns:
                    include_patterns.append(include)

        # Se nenhum padrão foi detectado, usa padrões comuns
        if not include_patterns:
            include_patterns = ['/lote/', '/item/', '/detalhe/']

        result.lot_include_patterns = include_patterns[:5]


async def analyze_sites_deep(
    sites: List[Dict[str, str]],
    max_concurrent: int = 10,
    timeout: int = 30,
    max_pages: int = 5
) -> List[DeepAnalysisResult]:
    """Analisa múltiplos sites em profundidade"""
    analyzer = DeepSiteAnalyzer(
        timeout=timeout,
        max_pages_per_site=max_pages
    )

    semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_with_semaphore(site: Dict[str, str]) -> DeepAnalysisResult:
        async with semaphore:
            result = await analyzer.analyze_site(
                domain=site.get('dominio', site.get('domain', '')),
                name=site.get('nome', site.get('name', ''))
            )
            await asyncio.sleep(1)  # Rate limiting entre sites
            return result

    tasks = [analyze_with_semaphore(site) for site in sites]
    results = await asyncio.gather(*tasks)

    return results
