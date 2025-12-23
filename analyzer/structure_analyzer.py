"""
Analisador de Estrutura de Sites de Leilões

Este módulo analisa sites de leilões para:
1. Descobrir URLs de listagem de lotes
2. Identificar padrões de URL para lotes individuais
3. Detectar a plataforma/framework utilizado
"""

import re
import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Set, Dict, Any
from urllib.parse import urlparse, urljoin
from collections import defaultdict

import aiohttp
from bs4 import BeautifulSoup


@dataclass
class SiteAnalysis:
    """Resultado da análise de um site"""
    domain: str
    name: str
    status: str = "pending"  # pending, success, error, timeout, redirect

    # URLs descobertas
    base_url: str = ""
    crawl_urls: List[str] = field(default_factory=list)
    include_paths: List[str] = field(default_factory=list)

    # Detecção de plataforma
    platform: str = "unknown"
    platform_version: str = ""

    # Padrões detectados
    lot_url_patterns: List[str] = field(default_factory=list)
    auction_url_patterns: List[str] = field(default_factory=list)

    # Metadados
    title: str = ""
    error_message: str = ""
    redirect_url: str = ""
    response_time_ms: float = 0

    # Links encontrados
    sample_lot_urls: List[str] = field(default_factory=list)
    sample_auction_urls: List[str] = field(default_factory=list)
    all_internal_links: List[str] = field(default_factory=list)


# Padrões conhecidos de plataformas de leilão
PLATFORM_SIGNATURES = {
    "lel.br": {
        "indicators": [".lel.br"],
        "lot_patterns": [r"/lote/\d+", r"/lotes/", r"/produto/\d+"],
        "auction_patterns": [r"/leilao/\d+", r"/leiloes/", r"/evento/\d+"],
    },
    "leilao.br": {
        "indicators": [".leilao.br"],
        "lot_patterns": [r"/lote/\d+", r"/lotes/", r"/item/\d+"],
        "auction_patterns": [r"/leilao/\d+", r"/leiloes/"],
    },
    "superbid": {
        "indicators": ["superbid", "superbidonline"],
        "lot_patterns": [r"/lote/\d+", r"/lot/\d+"],
        "auction_patterns": [r"/leilao/\d+", r"/auction/\d+"],
    },
    "bomvalor": {
        "indicators": ["bomvalor"],
        "lot_patterns": [r"/imoveis/", r"/veiculos/", r"/lote/"],
        "auction_patterns": [r"/leilao/", r"/evento/"],
    },
    "generic": {
        "indicators": [],
        "lot_patterns": [
            r"/lote[s]?/[\w-]+",
            r"/lote[s]?/\d+",
            r"/item[s]?/\d+",
            r"/produto[s]?/\d+",
            r"/bem[ns]?/\d+",
            r"/imovel[is]?/\d+",
            r"/veiculo[s]?/\d+",
            r"/lot/\d+",
            r"/auction-item/\d+",
        ],
        "auction_patterns": [
            r"/leilao[es]?/[\w-]+",
            r"/leilao[es]?/\d+",
            r"/leiloes[_-]?",
            r"/evento[s]?/\d+",
            r"/auction[s]?/\d+",
            r"/hasta[s]?/\d+",
        ],
    }
}

# Padrões comuns de URLs de lotes para diferentes estruturas
COMMON_LOT_PATTERNS = [
    # Padrão: /lote/{id} ou /lotes/{id}
    (r'/lotes?/(\d+)', '/lote/'),
    (r'/lotes?/([\w-]+)', '/lote/'),

    # Padrão: /item/{id}
    (r'/items?/(\d+)', '/item/'),

    # Padrão: /produto/{id}
    (r'/produtos?/(\d+)', '/produto/'),

    # Padrão: /bem/{id} ou /bens/{id}
    (r'/bens?/(\d+)', '/bem/'),

    # Padrão: /imovel/{id} ou /imoveis/{id}
    (r'/imove[il]s?/(\d+)', '/imovel/'),
    (r'/imove[il]s?/([\w-]+)', '/imovel/'),

    # Padrão: /veiculo/{id} ou /veiculos/{id}
    (r'/veiculos?/(\d+)', '/veiculo/'),
    (r'/veiculos?/([\w-]+)', '/veiculo/'),

    # Padrão: detalhes ou detalhe
    (r'/detalhe[s]?/(\d+)', '/detalhe/'),
    (r'/detalhe[s]?/([\w-]+)', '/detalhe/'),

    # Padrão: ver ou visualizar
    (r'/ver/(\d+)', '/ver/'),
    (r'/visualizar/(\d+)', '/visualizar/'),

    # Padrão com query string
    (r'\?.*lote[_-]?id=(\d+)', '?lote_id='),
    (r'\?.*id[_-]?lote=(\d+)', '?id_lote='),
]

# Padrões de URLs de listagem/catálogo
CATALOG_PATTERNS = [
    r'/leiloes/?$',
    r'/leilao/?$',
    r'/catalogo/?',
    r'/lotes/?$',
    r'/produtos/?$',
    r'/busca/?',
    r'/search/?',
    r'/imoveis/?$',
    r'/veiculos/?$',
    r'/ativos/?$',
    r'/hastas?/?$',
    r'/eventos?/?$',
]


class SiteStructureAnalyzer:
    """Analisador de estrutura de sites de leilão"""

    def __init__(self, timeout: int = 30, max_links_to_check: int = 100):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_links_to_check = max_links_to_check
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def analyze_site(self, domain: str, name: str) -> SiteAnalysis:
        """Analisa um site e retorna a estrutura descoberta"""
        import time

        analysis = SiteAnalysis(domain=domain, name=name)

        # Normaliza a URL
        if not domain.startswith(('http://', 'https://')):
            domain = f"https://{domain}"

        # Remove www. duplicado ou corrige URLs mal formadas
        domain = domain.replace("https://www.www.", "https://www.")

        analysis.base_url = domain
        start_time = time.time()

        try:
            async with aiohttp.ClientSession(
                timeout=self.timeout,
                headers=self.headers,
                connector=aiohttp.TCPConnector(ssl=False)
            ) as session:
                # Primeira requisição - página inicial
                async with session.get(domain, allow_redirects=True) as response:
                    analysis.response_time_ms = (time.time() - start_time) * 1000

                    # Verifica redirect
                    if str(response.url) != domain:
                        analysis.redirect_url = str(response.url)
                        analysis.base_url = str(response.url)

                    if response.status != 200:
                        analysis.status = "error"
                        analysis.error_message = f"HTTP {response.status}"
                        return analysis

                    html = await response.text()

                # Analisa o HTML
                soup = BeautifulSoup(html, 'lxml')

                # Extrai título
                title_tag = soup.find('title')
                analysis.title = title_tag.get_text(strip=True) if title_tag else ""

                # Detecta plataforma
                analysis.platform = self._detect_platform(domain, html)

                # Extrai todos os links internos
                base_domain = urlparse(analysis.base_url).netloc
                internal_links = self._extract_internal_links(soup, analysis.base_url, base_domain)
                analysis.all_internal_links = list(internal_links)[:self.max_links_to_check]

                # Analisa padrões de URLs
                self._analyze_url_patterns(analysis, internal_links)

                # Define as URLs de crawl e include paths
                self._define_crawl_config(analysis)

                analysis.status = "success"

        except asyncio.TimeoutError:
            analysis.status = "timeout"
            analysis.error_message = f"Timeout após {self.timeout.total}s"
        except aiohttp.ClientError as e:
            analysis.status = "error"
            analysis.error_message = str(e)
        except Exception as e:
            analysis.status = "error"
            analysis.error_message = f"{type(e).__name__}: {str(e)}"

        return analysis

    def _detect_platform(self, domain: str, html: str) -> str:
        """Detecta a plataforma/framework do site"""
        domain_lower = domain.lower()
        html_lower = html.lower()

        for platform_name, config in PLATFORM_SIGNATURES.items():
            if platform_name == "generic":
                continue
            for indicator in config["indicators"]:
                if indicator in domain_lower or indicator in html_lower:
                    return platform_name

        # Detecta por meta tags ou scripts
        if "angular" in html_lower:
            return "angular-based"
        if "react" in html_lower or "__next" in html_lower:
            return "react-based"
        if "vue" in html_lower:
            return "vue-based"
        if "wordpress" in html_lower or "wp-content" in html_lower:
            return "wordpress"

        return "generic"

    def _extract_internal_links(self, soup: BeautifulSoup, base_url: str, base_domain: str) -> Set[str]:
        """Extrai todos os links internos da página"""
        links = set()

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']

            # Ignora links especiais
            if href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'whatsapp:')):
                continue

            # Converte para URL absoluta
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Verifica se é link interno
            if parsed.netloc == base_domain or parsed.netloc == f"www.{base_domain}" or base_domain == f"www.{parsed.netloc}":
                # Remove fragmentos e normaliza
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.query:
                    clean_url += f"?{parsed.query}"
                links.add(clean_url)

        return links

    def _analyze_url_patterns(self, analysis: SiteAnalysis, links: Set[str]) -> None:
        """Analisa os padrões de URLs encontrados"""
        lot_urls = []
        auction_urls = []
        catalog_urls = []

        for link in links:
            parsed = urlparse(link)
            path = parsed.path.lower()

            # Verifica padrões de lote
            for pattern, _ in COMMON_LOT_PATTERNS:
                if re.search(pattern, path, re.IGNORECASE):
                    lot_urls.append(link)
                    break

            # Verifica padrões de leilão/catálogo
            for pattern in CATALOG_PATTERNS:
                if re.search(pattern, path, re.IGNORECASE):
                    catalog_urls.append(link)
                    break

            # Verifica padrões de leilão específico
            auction_patterns = [r'/leilao/\d+', r'/leilao/[\w-]+', r'/evento/\d+', r'/auction/\d+']
            for pattern in auction_patterns:
                if re.search(pattern, path, re.IGNORECASE):
                    auction_urls.append(link)
                    break

        # Armazena amostras
        analysis.sample_lot_urls = lot_urls[:10]
        analysis.sample_auction_urls = list(set(auction_urls + catalog_urls))[:10]

        # Identifica padrões únicos
        analysis.lot_url_patterns = self._extract_unique_patterns(lot_urls)
        analysis.auction_url_patterns = self._extract_unique_patterns(auction_urls + catalog_urls)

    def _extract_unique_patterns(self, urls: List[str]) -> List[str]:
        """Extrai padrões únicos de uma lista de URLs"""
        patterns = set()

        for url in urls:
            parsed = urlparse(url)
            path = parsed.path

            # Substitui IDs numéricos por {id}
            pattern = re.sub(r'/\d+', '/{id}', path)
            # Substitui slugs por {slug}
            pattern = re.sub(r'/[a-z0-9-]{20,}', '/{slug}', pattern)

            patterns.add(pattern)

        return list(patterns)[:5]

    def _define_crawl_config(self, analysis: SiteAnalysis) -> None:
        """Define as configurações de crawl baseado na análise"""
        base_url = analysis.base_url

        # Define URLs de crawl (onde o crawler deve começar)
        crawl_urls = [base_url]

        # Adiciona URLs de catálogo encontradas
        for url in analysis.sample_auction_urls:
            if url not in crawl_urls:
                crawl_urls.append(url)

        # Adiciona URLs comuns de listagem
        common_listing_paths = [
            "/leiloes",
            "/leilao",
            "/lotes",
            "/catalogo",
            "/imoveis",
            "/veiculos",
            "/busca",
        ]

        for path in common_listing_paths:
            potential_url = f"{base_url.rstrip('/')}{path}"
            if potential_url not in crawl_urls:
                crawl_urls.append(potential_url)

        analysis.crawl_urls = crawl_urls[:5]  # Limita a 5 URLs

        # Define include paths (padrões para filtrar lotes)
        include_paths = []

        # Baseado nos padrões encontrados
        for pattern in analysis.lot_url_patterns:
            # Converte padrão em include path
            include = pattern.replace('/{id}', '/').replace('/{slug}', '/')
            include = re.sub(r'/+', '/', include)  # Remove barras duplicadas
            if include and include != '/':
                include_paths.append(include)

        # Adiciona padrões comuns se nenhum foi encontrado
        if not include_paths:
            include_paths = ["/lote/", "/lotes/", "/item/", "/produto/"]

        analysis.include_paths = list(set(include_paths))[:5]
