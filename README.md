# Analisador de Estrutura de Sites de Leilões

Sistema para descobrir automaticamente a estrutura de sites de leilões brasileiros, identificar padrões de URL de lotes e agrupar sites com estruturas similares.

## Funcionalidades

- **Análise automática** de ~1000 sites de leilões
- **Detecção de plataformas** (lel.br, leilao.br, Superbid, etc.)
- **Descoberta de padrões de URL** para lotes
- **Agrupamento automático** de sites com estruturas similares
- **Geração de configuração** para crawlers (url_base, include_paths)

## Instalação

```bash
# Instalar dependências
pip install -r requirements.txt
```

## Uso

### Análise Completa (todos os sites)

```bash
python run_full_analysis.py
```

### Análise com Amostra (para testes)

```bash
# Analisar apenas 50 sites
python run_full_analysis.py --sample 50

# Analisar 100 sites com mais concorrência
python run_full_analysis.py --sample 100 --concurrent 30
```

### Opções

| Opção | Descrição | Padrão |
|-------|-----------|--------|
| `--input`, `-i` | Arquivo CSV com domínios | `Dominios Leilões - Dominios.csv` |
| `--output`, `-o` | Diretório de saída | `output` |
| `--sample`, `-s` | Número de sites para analisar (0=todos) | 0 |
| `--concurrent`, `-c` | Requisições simultâneas | 15 |
| `--timeout`, `-t` | Timeout em segundos | 30 |

## Arquivos Gerados

### 1. `crawl_config_TIMESTAMP.csv`

CSV com configurações de crawl para cada site:

| Coluna | Descrição |
|--------|-----------|
| `grupo` | Grupo de sites similares |
| `nome` | Nome do leiloeiro |
| `dominio` | Domínio original |
| `url_base` | URL base após redirects |
| `crawl_urls` | URLs para iniciar o crawl (separadas por `\|`) |
| `include_paths` | Padrões de URL para filtrar lotes (separadas por `\|`) |
| `status` | Status da análise (success, error, timeout) |

### 2. `grupos_TIMESTAMP.json`

JSON com sites agrupados por estrutura:

```json
{
  "Plataforma LEL.BR": {
    "quantidade": 50,
    "include_paths_comum": ["/lote/", "/item/"],
    "sites": [
      {
        "nome": "Site A",
        "dominio": "https://...",
        "url_base": "https://...",
        "crawl_urls": ["..."],
        "include_paths": ["/lote/"]
      }
    ]
  }
}
```

### 3. `analise_completa_TIMESTAMP.json`

JSON com todos os detalhes da análise de cada site.

### 4. `resumo_TIMESTAMP.txt`

Arquivo texto com resumo legível.

## Estrutura de Grupos

O sistema identifica automaticamente os seguintes grupos:

| Grupo | Descrição |
|-------|-----------|
| **Plataforma LEL.BR** | Sites usando a plataforma lel.br |
| **Plataforma LEILAO.BR** | Sites usando a plataforma leilao.br |
| **Superbid** | Sites da Superbid |
| **Bom Valor** | Sites do Bom Valor |
| **Sites Próprios - Lotes Genéricos** | Sites com estrutura `/lote/` |
| **Sites Próprios - Imóveis** | Sites com estrutura `/imovel/` |
| **Sites Próprios - Veículos** | Sites com estrutura `/veiculo/` |

## Como Usar no Seu Crawler

### Exemplo de Uso

```python
import json

# Carrega configuração
with open('output/grupos_TIMESTAMP.json') as f:
    grupos = json.load(f)

# Para cada grupo
for grupo_nome, grupo_data in grupos.items():
    print(f"Grupo: {grupo_nome}")
    print(f"Include paths: {grupo_data['include_paths_comum']}")

    for site in grupo_data['sites']:
        # URL para iniciar o crawl
        start_url = site['crawl_urls'][0]

        # Padrões para filtrar apenas URLs de lotes
        include_paths = site['include_paths']

        # Exemplo: após o crawl, filtra URLs
        for url in crawled_urls:
            if any(pattern in url for pattern in include_paths):
                # Esta é uma URL de lote para scrape
                process_lot(url)
```

## Arquitetura

```
analyzer/
├── __init__.py
├── structure_analyzer.py   # Análise básica de estrutura
├── deep_analyzer.py        # Análise profunda (múltiplas páginas)
├── batch_analyzer.py       # Análise em lote com paralelismo
└── config_generator.py     # Geração de configurações

run_full_analysis.py        # Script principal
run_analysis.py            # Script alternativo
```

## Documento de Arquitetura

Para a especificação detalhada do sistema (modelo de dados, pipeline, UI e APIs), veja:

- `docs/arquitetura_sistema_leiloes.md`

## Limitações

- Alguns sites podem ter proteção contra bots (Cloudflare, etc.)
- Sites dinâmicos (SPA) podem não revelar todos os padrões
- A análise considera apenas a página inicial e links diretos

## Contribuindo

1. Fork o repositório
2. Crie uma branch para sua feature
3. Faça commit das mudanças
4. Abra um Pull Request
