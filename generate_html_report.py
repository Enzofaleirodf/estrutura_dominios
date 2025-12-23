#!/usr/bin/env python3
"""
Gerador de Relatório HTML

Gera uma página HTML interativa com os resultados da análise.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from glob import glob


def find_latest_files():
    """Encontra os arquivos mais recentes de análise"""
    output_dir = Path("output")

    # Procura arquivos de configuração rápida
    quick_configs = sorted(glob(str(output_dir / "config_rapida_*.json")))
    quick_config = quick_configs[-1] if quick_configs else None

    # Procura arquivos de análise completa
    full_configs = sorted(glob(str(output_dir / "analise_completa_*.json")))
    full_config = full_configs[-1] if full_configs else None

    return quick_config, full_config


def load_data(quick_config_path, full_config_path):
    """Carrega os dados de análise"""
    data = {
        "quick": None,
        "full": None,
        "merged": None
    }

    if quick_config_path and os.path.exists(quick_config_path):
        with open(quick_config_path, 'r', encoding='utf-8') as f:
            data["quick"] = json.load(f)

    if full_config_path and os.path.exists(full_config_path):
        with open(full_config_path, 'r', encoding='utf-8') as f:
            data["full"] = json.load(f)

    return data


def generate_html(data):
    """Gera o HTML do relatório"""
    quick = data.get("quick", {})
    full = data.get("full", [])

    # Conta estatísticas da análise completa
    full_stats = {"success": 0, "error": 0, "timeout": 0}
    for site in full:
        status = site.get("status", "error")
        if status in full_stats:
            full_stats[status] += 1

    # Grupos da configuração rápida
    grupos = quick.get("grupos", {})
    total_sites = quick.get("total_sites", 0)

    html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Análise de Sites de Leilões</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.5rem;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 30px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        .stat-number {{
            font-size: 3rem;
            font-weight: bold;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .stat-label {{
            color: #888;
            margin-top: 5px;
        }}
        .groups-section {{
            margin-top: 40px;
        }}
        .section-title {{
            font-size: 1.5rem;
            margin-bottom: 20px;
            padding-left: 10px;
            border-left: 4px solid #00d4ff;
        }}
        .group-card {{
            background: rgba(255,255,255,0.03);
            border-radius: 15px;
            margin-bottom: 20px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .group-header {{
            background: rgba(255,255,255,0.05);
            padding: 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .group-header:hover {{
            background: rgba(255,255,255,0.08);
        }}
        .group-name {{
            font-size: 1.2rem;
            font-weight: 600;
        }}
        .group-count {{
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
        }}
        .group-content {{
            display: none;
            padding: 20px;
        }}
        .group-content.active {{
            display: block;
        }}
        .include-paths {{
            margin-bottom: 15px;
        }}
        .include-paths span {{
            display: inline-block;
            background: rgba(0, 212, 255, 0.2);
            padding: 5px 10px;
            border-radius: 5px;
            margin: 3px;
            font-family: monospace;
            font-size: 0.85rem;
        }}
        .sites-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .sites-table th {{
            text-align: left;
            padding: 12px;
            background: rgba(255,255,255,0.05);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .sites-table td {{
            padding: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .sites-table tr:hover {{
            background: rgba(255,255,255,0.02);
        }}
        .site-link {{
            color: #00d4ff;
            text-decoration: none;
        }}
        .site-link:hover {{
            text-decoration: underline;
        }}
        .crawl-urls {{
            font-family: monospace;
            font-size: 0.8rem;
            color: #888;
        }}
        .search-box {{
            width: 100%;
            padding: 15px 20px;
            border: none;
            border-radius: 10px;
            background: rgba(255,255,255,0.1);
            color: #fff;
            font-size: 1rem;
            margin-bottom: 30px;
        }}
        .search-box::placeholder {{
            color: #666;
        }}
        .search-box:focus {{
            outline: none;
            box-shadow: 0 0 0 2px #00d4ff;
        }}
        .download-section {{
            text-align: center;
            margin: 40px 0;
        }}
        .download-btn {{
            display: inline-block;
            padding: 15px 30px;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            color: #fff;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 600;
            margin: 10px;
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        .download-btn:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0, 212, 255, 0.3);
        }}
        .timestamp {{
            text-align: center;
            color: #666;
            margin-top: 40px;
            font-size: 0.9rem;
        }}
        .expand-icon {{
            transition: transform 0.3s;
        }}
        .group-header.active .expand-icon {{
            transform: rotate(180deg);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Análise de Sites de Leilões</h1>
        <p class="subtitle">Estrutura de URLs e configuração para crawlers</p>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{total_sites}</div>
                <div class="stat-label">Sites Analisados</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(grupos)}</div>
                <div class="stat-label">Grupos Identificados</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{full_stats["success"]}</div>
                <div class="stat-label">Análises com Sucesso</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{full_stats["error"] + full_stats["timeout"]}</div>
                <div class="stat-label">Sites com Erro/Timeout</div>
            </div>
        </div>

        <input type="text" class="search-box" id="searchBox" placeholder="Buscar site por nome ou domínio...">

        <div class="groups-section">
            <h2 class="section-title">Grupos por Estrutura</h2>
'''

    # Gera cards para cada grupo
    for group_name, group_data in sorted(grupos.items(), key=lambda x: -x[1]["quantidade"]):
        sites = group_data.get("sites", [])
        include_paths = group_data.get("include_paths_padrao", [])

        html += f'''
            <div class="group-card" data-group="{group_name.lower()}">
                <div class="group-header" onclick="toggleGroup(this)">
                    <span class="group-name">{group_name}</span>
                    <span class="group-count">{len(sites)} sites</span>
                    <span class="expand-icon">▼</span>
                </div>
                <div class="group-content">
                    <div class="include-paths">
                        <strong>Include Paths (filtrar lotes):</strong><br>
                        {''.join(f'<span>{p}</span>' for p in include_paths)}
                    </div>
                    <table class="sites-table">
                        <thead>
                            <tr>
                                <th>Nome</th>
                                <th>Domínio</th>
                                <th>Crawl URLs</th>
                            </tr>
                        </thead>
                        <tbody>
'''

        for site in sites[:100]:  # Limita a 100 por grupo para performance
            nome = site.get("nome", "")
            dominio = site.get("dominio", "")
            crawl_urls = site.get("crawl_urls", [])[:2]

            html += f'''
                            <tr class="site-row" data-name="{nome.lower()}" data-domain="{dominio.lower()}">
                                <td>{nome}</td>
                                <td><a href="{dominio}" target="_blank" class="site-link">{dominio}</a></td>
                                <td class="crawl-urls">{', '.join(crawl_urls)}</td>
                            </tr>
'''

        if len(sites) > 100:
            html += f'''
                            <tr>
                                <td colspan="3" style="text-align: center; color: #888;">
                                    ... e mais {len(sites) - 100} sites. Baixe o JSON para ver todos.
                                </td>
                            </tr>
'''

        html += '''
                        </tbody>
                    </table>
                </div>
            </div>
'''

    html += f'''
        </div>

        <div class="download-section">
            <h2 class="section-title" style="text-align: center; border: none;">Download dos Dados</h2>
            <a href="config_rapida.json" download class="download-btn">📦 Baixar JSON Completo</a>
            <a href="config_rapida.csv" download class="download-btn">📊 Baixar CSV</a>
        </div>

        <p class="timestamp">Gerado em: {datetime.now().strftime("%d/%m/%Y às %H:%M")}</p>
    </div>

    <script>
        function toggleGroup(header) {{
            header.classList.toggle('active');
            const content = header.nextElementSibling;
            content.classList.toggle('active');
        }}

        document.getElementById('searchBox').addEventListener('input', function(e) {{
            const query = e.target.value.toLowerCase();
            const rows = document.querySelectorAll('.site-row');
            const groups = document.querySelectorAll('.group-card');

            if (query.length < 2) {{
                rows.forEach(row => row.style.display = '');
                groups.forEach(group => group.style.display = '');
                return;
            }}

            groups.forEach(group => {{
                let hasVisibleRows = false;
                const groupRows = group.querySelectorAll('.site-row');

                groupRows.forEach(row => {{
                    const name = row.dataset.name || '';
                    const domain = row.dataset.domain || '';

                    if (name.includes(query) || domain.includes(query)) {{
                        row.style.display = '';
                        hasVisibleRows = true;
                    }} else {{
                        row.style.display = 'none';
                    }}
                }});

                group.style.display = hasVisibleRows ? '' : 'none';

                if (hasVisibleRows && query.length > 0) {{
                    group.querySelector('.group-header').classList.add('active');
                    group.querySelector('.group-content').classList.add('active');
                }}
            }});
        }});
    </script>
</body>
</html>
'''

    return html


def main():
    # Cria diretório docs para GitHub Pages
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    # Encontra arquivos mais recentes
    quick_config, full_config = find_latest_files()

    print(f"Configuração rápida: {quick_config}")
    print(f"Análise completa: {full_config}")

    # Carrega dados
    data = load_data(quick_config, full_config)

    # Gera HTML
    html = generate_html(data)

    # Salva HTML
    html_path = docs_dir / "index.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML gerado: {html_path}")

    # Copia JSON e CSV para docs
    if quick_config:
        import shutil
        shutil.copy(quick_config, docs_dir / "config_rapida.json")

        # Também procura o CSV correspondente
        csv_path = quick_config.replace('.json', '.csv')
        if os.path.exists(csv_path):
            shutil.copy(csv_path, docs_dir / "config_rapida.csv")

    print("Relatório HTML gerado com sucesso!")


if __name__ == "__main__":
    main()
