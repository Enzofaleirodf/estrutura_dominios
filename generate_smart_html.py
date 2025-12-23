#!/usr/bin/env python3
"""
Gerador de HTML para Análise Inteligente
"""

import json
import os
from datetime import datetime
from pathlib import Path
from glob import glob


def find_latest_smart_analysis():
    """Encontra o arquivo mais recente de análise inteligente"""
    files = sorted(glob("output/smart_analysis_*.json"))
    return files[-1] if files else None


def generate_html(results):
    """Gera HTML interativo com os resultados"""

    success = [r for r in results if r['status'] == 'success']
    no_patterns = [r for r in results if r['status'] in ['no_patterns', 'no_lots_found']]
    errors = [r for r in results if r['status'] in ['error', 'timeout', 'pending']]

    html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Análise Inteligente - Sites de Leilões</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f1a;
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}

        h1 {{
            text-align: center;
            font-size: 2rem;
            margin-bottom: 5px;
            background: linear-gradient(90deg, #00ff88, #00d4ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{ text-align: center; color: #666; margin-bottom: 30px; }}

        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .stat {{
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .stat-value {{
            font-size: 2.5rem;
            font-weight: bold;
            color: #00ff88;
        }}
        .stat-value.warning {{ color: #ffaa00; }}
        .stat-value.error {{ color: #ff4444; }}
        .stat-label {{ color: #888; font-size: 0.9rem; }}

        .site-card {{
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            margin-bottom: 15px;
            border: 1px solid rgba(255,255,255,0.1);
            overflow: hidden;
        }}
        .site-header {{
            padding: 15px 20px;
            background: rgba(255,255,255,0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }}
        .site-header:hover {{ background: rgba(255,255,255,0.08); }}

        .site-name {{ font-weight: 600; font-size: 1.1rem; }}
        .site-domain {{ color: #00d4ff; font-size: 0.85rem; }}

        .status {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .status.success {{ background: rgba(0,255,136,0.2); color: #00ff88; }}
        .status.no_patterns, .status.no_lots_found {{ background: rgba(255,170,0,0.2); color: #ffaa00; }}
        .status.error, .status.timeout, .status.pending {{ background: rgba(255,68,68,0.2); color: #ff4444; }}

        .site-content {{
            padding: 20px;
            display: none;
            border-top: 1px solid rgba(255,255,255,0.1);
        }}
        .site-content.active {{ display: block; }}

        .section-title {{
            font-size: 0.9rem;
            color: #888;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .paths {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 20px;
        }}
        .path {{
            background: rgba(0,212,255,0.15);
            color: #00d4ff;
            padding: 6px 12px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 0.9rem;
        }}

        .examples {{
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        }}
        .example-url {{
            font-family: monospace;
            font-size: 0.85rem;
            color: #aaa;
            padding: 5px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            word-break: break-all;
        }}
        .example-url:last-child {{ border-bottom: none; }}
        .example-url a {{ color: #00d4ff; text-decoration: none; }}
        .example-url a:hover {{ text-decoration: underline; }}

        .crawl-config {{
            background: rgba(0,255,136,0.1);
            border-radius: 8px;
            padding: 15px;
            border: 1px solid rgba(0,255,136,0.2);
        }}
        .crawl-config h4 {{ color: #00ff88; margin-bottom: 10px; }}
        .crawl-config code {{
            display: block;
            background: rgba(0,0,0,0.3);
            padding: 10px;
            border-radius: 5px;
            font-size: 0.85rem;
            overflow-x: auto;
        }}

        .timestamp {{
            text-align: center;
            color: #444;
            margin-top: 30px;
            font-size: 0.85rem;
        }}

        .filter-buttons {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            padding: 8px 16px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            background: rgba(255,255,255,0.1);
            color: #fff;
            transition: all 0.2s;
        }}
        .filter-btn:hover {{ background: rgba(255,255,255,0.2); }}
        .filter-btn.active {{ background: #00d4ff; color: #000; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Análise Inteligente</h1>
        <p class="subtitle">Padrões reais descobertos em cada site de leilão</p>

        <div class="stats">
            <div class="stat">
                <div class="stat-value">{len(results)}</div>
                <div class="stat-label">Sites Analisados</div>
            </div>
            <div class="stat">
                <div class="stat-value">{len(success)}</div>
                <div class="stat-label">Padrões Encontrados</div>
            </div>
            <div class="stat">
                <div class="stat-value warning">{len(no_patterns)}</div>
                <div class="stat-label">Sem Padrões</div>
            </div>
            <div class="stat">
                <div class="stat-value error">{len(errors)}</div>
                <div class="stat-label">Erros</div>
            </div>
        </div>

        <div class="filter-buttons">
            <button class="filter-btn active" onclick="filterSites('all')">Todos</button>
            <button class="filter-btn" onclick="filterSites('success')">Com Padrões</button>
            <button class="filter-btn" onclick="filterSites('no_patterns')">Sem Padrões</button>
            <button class="filter-btn" onclick="filterSites('error')">Erros</button>
        </div>

        <div id="sites-container">
'''

    for r in results:
        status_class = 'success' if r['status'] == 'success' else 'no_patterns' if r['status'] in ['no_patterns', 'no_lots_found'] else 'error'
        platform = r.get('platform_detected', '')
        link_structure = r.get('link_structure', {})

        html += f'''
            <div class="site-card" data-status="{r['status']}">
                <div class="site-header" onclick="toggleSite(this)">
                    <div>
                        <div class="site-name">{r['nome']}</div>
                        <div class="site-domain">{r['dominio']}</div>
                        {f'<div style="font-size:0.75rem;color:#00ff88;margin-top:3px;">📦 {platform}</div>' if platform else ''}
                    </div>
                    <span class="status {status_class}">{r['status']}</span>
                </div>
                <div class="site-content">
'''

        # Mostra estrutura de links descoberta
        if link_structure:
            html += '''
                    <div class="section-title">🔗 Estrutura de Links Descoberta</div>
                    <div class="examples" style="margin-bottom:20px;">
'''
            for path, info in list(link_structure.items())[:8]:
                count = info.get('count', 0) if isinstance(info, dict) else info
                examples = info.get('examples', [])[:2] if isinstance(info, dict) else []
                html += f'''
                        <div style="margin-bottom:10px;">
                            <span class="path">{path}</span>
                            <span style="color:#888;margin-left:10px;">{count} links</span>
                            {''.join(f'<div style="font-size:0.75rem;color:#666;margin-left:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{ex[:80]}...</div>' for ex in examples)}
                        </div>
'''
            html += '''
                    </div>
'''

        if r['status'] == 'success' or r.get('include_paths'):
            html += f'''
                    <div class="section-title">✅ Include Paths (usar no crawler)</div>
                    <div class="paths">
                        {''.join(f'<span class="path">{p}</span>' for p in r.get('include_paths', []))}
                    </div>
'''

        if r.get('lot_examples'):
            html += f'''
                    <div class="section-title">📋 Exemplos de URLs de Lotes</div>
                    <div class="examples">
                        {''.join(f'<div class="example-url"><a href="{url}" target="_blank">{url}</a></div>' for url in r['lot_examples'][:10])}
                    </div>
'''

        if r.get('crawl_start_urls'):
            html += f'''
                    <div class="crawl-config">
                        <h4>🚀 Configuração para Crawler</h4>
                        <code>{{
    "start_urls": {json.dumps(r['crawl_start_urls'][:3], ensure_ascii=False)},
    "include_paths": {json.dumps(r.get('include_paths', []), ensure_ascii=False)}
}}</code>
                    </div>
'''

        # Raw links para debugging
        raw_links = r.get('raw_links', [])
        if raw_links:
            html += f'''
                    <details style="margin-top:15px;">
                        <summary style="cursor:pointer;color:#888;">🔍 Ver todos os links ({len(raw_links)} encontrados)</summary>
                        <div class="examples" style="margin-top:10px;max-height:300px;overflow-y:auto;">
                            {''.join(f'<div class="example-url" style="font-size:0.75rem;"><a href="{url}" target="_blank">{url}</a></div>' for url in raw_links[:50])}
                        </div>
                    </details>
'''

        if r.get('error_message'):
            html += f'''
                    <div class="section-title">❌ Erro</div>
                    <div class="examples" style="color: #ff4444;">{r['error_message']}</div>
'''

        html += '''
                </div>
            </div>
'''

    html += f'''
        </div>

        <p class="timestamp">Gerado em: {datetime.now().strftime("%d/%m/%Y às %H:%M")}</p>
    </div>

    <script>
        function toggleSite(header) {{
            const content = header.nextElementSibling;
            content.classList.toggle('active');
        }}

        function filterSites(status) {{
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            document.querySelectorAll('.site-card').forEach(card => {{
                if (status === 'all') {{
                    card.style.display = '';
                }} else if (status === 'error') {{
                    card.style.display = ['error', 'timeout', 'pending'].includes(card.dataset.status) ? '' : 'none';
                }} else if (status === 'no_patterns') {{
                    card.style.display = ['no_patterns', 'no_lots_found'].includes(card.dataset.status) ? '' : 'none';
                }} else {{
                    card.style.display = card.dataset.status === status ? '' : 'none';
                }}
            }});
        }}
    </script>
</body>
</html>
'''

    return html


def main():
    # Cria diretório docs
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    # Encontra arquivo de análise
    analysis_file = find_latest_smart_analysis()

    if not analysis_file:
        print("Nenhum arquivo de análise encontrado!")
        return

    print(f"Usando: {analysis_file}")

    # Carrega resultados
    with open(analysis_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    # Gera HTML
    html = generate_html(results)

    # Salva
    html_path = docs_dir / "index.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"HTML gerado: {html_path}")

    # Copia JSON para docs
    import shutil
    shutil.copy(analysis_file, docs_dir / "smart_analysis.json")


if __name__ == "__main__":
    main()
