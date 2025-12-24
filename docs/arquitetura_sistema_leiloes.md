# Sistema de Descoberta e Agrupamento de Estrutura de Sites de Leilão

Documento de arquitetura completa e implementável (sem código final), cobrindo fluxo end-to-end, modelo de dados, pipeline de jobs, interface, regras de elegibilidade/agrupamento, endpoints REST e prompt do agente de IA.

---

## 📋 Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                        FLUXO END-TO-END                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CSV Upload    →  Import Sites   →  Fila de Jobs              │
│                                       ├─ map_site              │
│                                       ├─ extract_templates     │
│                                       ├─ build_signature       │
│                                       └─ group_sites           │
│                                              ↓                 │
│  Dashboard UI  ←  API REST        ←  template_groups           │
│  (Monitoramento)                         + ai_validate_group   │
│                                              ↓                 │
│                                     AGENTE IA (validador)      │
│                                              ↓                 │
│                                     Grupos Finais (validated)  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Modelo de Dados (Tabelas)

### **sites**
Registro imutável do site e seu ciclo de descoberta.

```sql
CREATE TABLE sites (
  id UUID PRIMARY KEY,
  nome VARCHAR(255) NOT NULL,
  dominio VARCHAR(255) NOT NULL UNIQUE,  -- canonical (sem www, sem /)
  dominio_original VARCHAR(255),         -- para auditoria

  -- Estados de descoberta
  discovery_status ENUM('pending', 'mapping', 'mapped', 'failed') DEFAULT 'pending',
  grouping_status ENUM('ungrouped', 'candidate_grouped', 'grouped', 'rejected') DEFAULT 'ungrouped',

  -- Referência
  group_id UUID NULLABLE,                -- foreign key → template_groups

  -- Rastreamento
  last_mapped_at TIMESTAMP NULLABLE,
  last_signature_at TIMESTAMP NULLABLE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),

  FOREIGN KEY (group_id) REFERENCES template_groups(id)
);

CREATE INDEX idx_sites_grouping_status ON sites(grouping_status);
CREATE INDEX idx_sites_discovery_status ON sites(discovery_status);
CREATE INDEX idx_sites_group_id ON sites(group_id);
```

### **site_map_runs**
Cada "execução" de map em lote.

```sql
CREATE TABLE site_map_runs (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL UNIQUE,            -- identificador único da run

  started_at TIMESTAMP DEFAULT NOW(),
  finished_at TIMESTAMP NULLABLE,

  -- Configuração
  concurrency INT DEFAULT 50,
  rate_limit INT DEFAULT 500,             -- requests/minute
  total_sites INT,

  -- Controle
  sites_success INT DEFAULT 0,
  sites_failed INT DEFAULT 0,
  status ENUM('running', 'done', 'failed') DEFAULT 'running',

  created_by UUID,                        -- user_id
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_site_map_runs_status ON site_map_runs(status);
```

### **site_maps**
URLs brutas extraídas de cada domínio.

```sql
CREATE TABLE site_maps (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL,
  site_id UUID NOT NULL,
  domain VARCHAR(255) NOT NULL,

  urls_raw JSONB NOT NULL,                -- array de strings
  total_urls INT NOT NULL,

  mapped_at TIMESTAMP,
  status ENUM('success', 'error', 'timeout') DEFAULT 'success',
  error_message VARCHAR(1024) NULLABLE,

  created_at TIMESTAMP DEFAULT NOW(),

  FOREIGN KEY (run_id) REFERENCES site_map_runs(id),
  FOREIGN KEY (site_id) REFERENCES sites(id)
);

CREATE INDEX idx_site_maps_site_id ON site_maps(site_id);
CREATE INDEX idx_site_maps_run_id ON site_maps(run_id);
```

### **site_templates**
Templates mecânicos extraídos de paths.

```sql
CREATE TABLE site_templates (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL,
  site_id UUID NOT NULL,

  template VARCHAR(512) NOT NULL,        -- ex: /item/{num}/detalhes
  count INT DEFAULT 1,                    -- quantas vezes apareceu
  sample_urls JSONB,                      -- array com 3 exemplos reais

  created_at TIMESTAMP DEFAULT NOW(),

  FOREIGN KEY (run_id) REFERENCES site_map_runs(id),
  FOREIGN KEY (site_id) REFERENCES sites(id),
  UNIQUE (site_id, run_id, template)
);

CREATE INDEX idx_site_templates_site_id ON site_templates(site_id);
CREATE INDEX idx_site_templates_template ON site_templates(template);
```

### **site_signatures**
Classificação de templates em listagem/detalhe por domínio.

```sql
CREATE TABLE site_signatures (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL,
  site_id UUID NOT NULL,

  -- Arrays de templates classificados
  listagem_templates JSONB NOT NULL,      -- array de templates candidatos a listagem
  detalhe_templates JSONB NOT NULL,       -- array de templates candidatos a detalhe

  is_eligible BOOLEAN DEFAULT FALSE,      -- true se houver pelo menos 1 de cada
  reason_if_not VARCHAR(255) NULLABLE,    -- ex: "sem detalhe", "sem listagem"

  created_at TIMESTAMP DEFAULT NOW(),

  FOREIGN KEY (run_id) REFERENCES site_map_runs(id),
  FOREIGN KEY (site_id) REFERENCES sites(id)
);

CREATE INDEX idx_site_signatures_eligible ON site_signatures(is_eligible);
```

### **template_groups**
Grupos de domínios com mesma estrutura.

```sql
CREATE TABLE template_groups (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL,

  -- Assinatura estrutural (chave única do grupo)
  listagem_template VARCHAR(512) NOT NULL,
  detalhe_template VARCHAR(512) NOT NULL,
  signature_hash VARCHAR(64) NOT NULL UNIQUE,

  -- Domínio representante (para testes manuais)
  representative_site_id UUID,

  -- Validação
  status ENUM('candidate', 'validated', 'rejected') DEFAULT 'candidate',
  size INT DEFAULT 0,                     -- número de domínios

  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),

  FOREIGN KEY (run_id) REFERENCES site_map_runs(id),
  FOREIGN KEY (representative_site_id) REFERENCES sites(id)
);

CREATE INDEX idx_template_groups_status ON template_groups(status);
CREATE INDEX idx_template_groups_signature_hash ON template_groups(signature_hash);
```

### **template_group_members**
Associação many-to-many entre grupos e sites.

```sql
CREATE TABLE template_group_members (
  id UUID PRIMARY KEY,
  group_id UUID NOT NULL,
  site_id UUID NOT NULL,

  joined_at TIMESTAMP DEFAULT NOW(),

  FOREIGN KEY (group_id) REFERENCES template_groups(id),
  FOREIGN KEY (site_id) REFERENCES sites(id),
  UNIQUE (group_id, site_id)
);

CREATE INDEX idx_template_group_members_group_id ON template_group_members(group_id);
CREATE INDEX idx_template_group_members_site_id ON template_group_members(site_id);
```

### **ai_group_validations**
Histórico de validações com agente IA.

```sql
CREATE TABLE ai_group_validations (
  id UUID PRIMARY KEY,
  group_id UUID NOT NULL,

  -- Payloads
  input_payload JSONB NOT NULL,
  output_payload JSONB NOT NULL,

  -- Resultado
  is_valid_group BOOLEAN NOT NULL,
  confidence ENUM('low', 'medium', 'high') DEFAULT 'medium',
  raw_observations VARCHAR(1024) NULLABLE,

  created_at TIMESTAMP DEFAULT NOW(),

  FOREIGN KEY (group_id) REFERENCES template_groups(id)
);

CREATE INDEX idx_ai_group_validations_group_id ON template_groups(id);
```

---

## 🔄 Pipeline / Workers (Fila)

### **JOB A — `map_site(site_id, run_id)`**

**Entrada:**
- `site_id`: UUID do site
- `run_id`: UUID da execução

**Ações:**
1. Buscar domínio canônico do site
2. Chamar Firecrawl `/v2/map` com: 
   ```json
   {
     "url": "https://{domain}",
     "ignoreQueryParameters": true,
     "limit": 5000,
     "maxPages": 5000,
     "location": "BR",
     "language": ["pt-BR", "pt"],
     "timeout": 60000
   }
   ```
3. Se sucesso: 
   - Extrair `urls` do response
   - Salvar em `site_maps` com `status='success'`
   - Atualizar `sites.discovery_status = 'mapped'`
   - Atualizar `sites.last_mapped_at`
4. Se erro (timeout, rate limit, 4xx/5xx):
   - Salvar erro em `site_maps` com `status='error'`
   - Atualizar `sites.discovery_status = 'failed'`
   - Enfileirar retry com backoff exponencial (max 3 tentativas)

**Saída:**
- `site_maps` preenchida

---

### **JOB B — `extract_templates(site_id, run_id)`**

**Entrada:**
- `site_id`, `run_id` (já com site_maps preenchida)

**Ações:**
1. Buscar todas as URLs em `site_maps.urls_raw`
2. Para cada URL:
   - Extrair apenas pathname (remover domínio, www, querystring)
   - Tokenizar por `/`
   - Aplicar transformações mecânicas: 
     ```
     /item/6186/detalhes
     tokenize → ["item", "6186", "detalhes"]
     apply rules: 
     - "6186" é numérico?  → {num}
     resultado: /item/{num}/detalhes
     ```
   - Regras de tokenização:
     - Segmento `^\d+$` → `{num}`
     - Segmento `^[a-f0-9]{32}$` (MD5) ou `^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$` (UUID) → `{id}`
     - Tudo mais → mantém literal

3. Agrupar templates por frequência
4. Para cada template único:
   - Contar ocorrências
   - Coletar 3 URLs de exemplo
5. Salvar em `site_templates` com `(site_id, run_id, template, count, sample_urls)`

**Saída:**
- `site_templates` preenchida

---

### **JOB C — `build_signature(site_id, run_id)`**

**Entrada:**
- `site_id`, `run_id` (já com site_templates preenchida)

**Ações:**
1. Buscar todos os templates do site em `site_templates`
2. Classificar templates em 2 conjuntos usando regras MECÂNICAS (sem semântica):

   **DETALHE candidato:**
   - Template termina com `/detalhes` OU `/show` E contém `{num}` ou `{id}`
   - Exemplos:
     - `/item/{num}/detalhes` ✓
     - `/lote/{num}/show` ✓
     - `/bem/{id}/info` ✓

   **LISTAGEM candidato:**
   - Template contém `/leilao/{num}/lotes` OU
   - Template começa com `/lotes` OU
   - Template termina com `/lotes` E contém `{num}`
   - Exemplos: 
     - `/leilao/{num}/lotes` ✓
     - `/lotes/categoria/{slug}` ✓
     - `/lotes/search` ✓

3. Determinar elegibilidade:
   ```
   is_eligible = 
     (listagem_templates.length > 0) AND 
     (detalhe_templates.length > 0)
   ```

4. Se NÃO elegível:
   - Determinar motivo: 
     - `"sem_listagem"` se detalhe_templates.length > 0 mas listagem vazio
     - `"sem_detalhe"` se listagem_templates.length > 0 mas detalhe vazio
     - `"sem_padroes"` se ambos vazios
     - `"map_vazio"` se site_templates vazio

5. Salvar em `site_signatures`:
   ```json
   {
     "site_id": ".. .",
     "run_id":  "...",
     "listagem_templates": ["...", "..."],
     "detalhe_templates": ["... "],
     "is_eligible":  true/false,
     "reason_if_not": "..."
   }
   ```

**Saída:**
- `site_signatures` preenchida
- `sites.grouping_status` = "ungrouped" (padrão)
- `sites.last_signature_at` atualizado

---

### **JOB D — `group_sites(run_id)`**

**Entrada:**
- `run_id` (toda a run completa)

**Ações:**
1. Buscar todos os sites com: 
   ```sql
   SELECT s.*, sig.*
   FROM sites s
   JOIN site_signatures sig ON s.id = sig.site_id
   WHERE sig.run_id = {run_id} AND sig.is_eligible = true
   ```

2. Para cada site elegível:
   - Escolher: 
     - **um** template de listagem (o de maior `count`)
     - **um** template de detalhe (o de maior `count`)
   - Criar assinatura de grupo: 
     ```
     signature_hash = SHA256(listagem_template + "|" + detalhe_template)
     ```

3. Agrupar sites por signature_hash:
   ```
   GROUP BY (listagem_template, detalhe_template)
   ```

4. Para cada grupo único:
   - Criar `template_group`:
     - `listagem_template`
     - `detalhe_template`
     - `signature_hash`
     - `representative_site_id` = site com mais URLs
     - `status = 'candidate'`
     - `size` = número de sites no grupo
   - Criar `template_group_members` para cada site
   - Atualizar `sites`:
     - `sites.group_id = group_id`
     - `sites.grouping_status = 'candidate_grouped'`

5. Salvar metadados:
   - Total de grupos criados
   - Total de sites elegíveis
   - Total de sites agrupados

**Saída:**
- `template_groups` preenchida
- `template_group_members` preenchida
- `sites.group_id` atualizado

---

### **JOB E — `ai_validate_group(group_id)`**

**Entrada:**
- `group_id` (UUID do grupo)

**Ações:**
1. Buscar grupo: 
   ```sql
   SELECT * FROM template_groups WHERE id = {group_id}
   ```

2. Buscar 2–3 domínios representantes do grupo:
   ```sql
   SELECT s.dominio, s.id
   FROM template_group_members tm
   JOIN sites s ON tm.site_id = s.id
   WHERE tm.group_id = {group_id}
   ORDER BY s.last_mapped_at DESC
   LIMIT 3
   ```

3. Para cada domínio, buscar 2 URLs de exemplo de listagem + 2 de detalhe: 
   ```sql
   SELECT sample_urls FROM site_templates
   WHERE site_id = {site_id} AND template = {listagem_template}
   LIMIT 1

   SELECT sample_urls FROM site_templates
   WHERE site_id = {site_id} AND template = {detalhe_template}
   LIMIT 1
   ```

4. Montar payload de input para agente IA:
   ```json
   {
     "group_id": "...",
     "listagem_template": "/leilao/{num}/lotes",
     "detalhe_template": "/item/{num}/detalhes",
     "domains_count": 12,
     "examples":  [
       {
         "domain": "3torres.com.br",
         "listagem_urls": [
           "https://3torres.com.br/leilao/1240/lotes",
           "https://3torres.com.br/leilao/868/lotes"
         ],
         "detalhe_urls":  [
           "https://3torres.com.br/item/9173/detalhes",
           "https://3torres.com.br/item/6186/detalhes"
         ]
       },
       {
         "domain":  "agencialeilao.com.br",
         "listagem_urls": [...],
         "detalhe_urls": [...]
       }
     ]
   }
   ```

5. Chamar AGENTE IA com prompt estruturado:
   ```
   Você é um validador de estruturas de site de leilão. 

   Dado um grupo de domínios que compartilham a mesma estrutura de URLs: 
   - Padrão de listagem de lotes: {listagem_template}
   - Padrão de detalhe de lote: {detalhe_template}

   Exemplos reais de URLs de {domains_count} domínios: 
   {examples formatado}

   Pergunta: Esses padrões realmente representam uma estrutura coerente? 
   Existem inconsistências entre os domínios?  O padrão é consistente?

   Responda APENAS em JSON: 
   {
     "is_valid_group": true/false,
     "confidence": "low|medium|high",
     "reasoning": "explicação breve"
   }
   ```

6. Parsear response:
   ```json
   {
     "is_valid_group": true,
     "confidence":  "high",
     "reasoning": "Padrão idêntico em todos os domínios.  Provavelmente mesmo CMS."
   }
   ```

7. Salvar em `ai_group_validations`:
   ```json
   {
     "group_id": ".. .",
     "input_payload": {... },
     "output_payload":  {...},
     "is_valid_group": true,
     "confidence": "high"
   }
   ```

8. Se `is_valid_group = true`:
   - Atualizar `template_groups`:
     - `status = 'validated'`
   - Atualizar `sites`:
     - `grouping_status = 'grouped'`
   Senão:
   - Atualizar `template_groups`:
     - `status = 'rejected'`
   - Atualizar `sites`:
     - `grouping_status = 'rejected'`
     - `group_id = NULL`
   - Remover registros em `template_group_members`

**Saída:**
- `ai_group_validations` preenchida
- `template_groups.status` e `sites.grouping_status` atualizados

---

## 🖼️ Interface / Dashboard — Telas

### **Tela 1: "Importar Sites"**

**Layout:**
```
┌──────────────────────────────────────────────────────┐
│ Importar Sites de Leilão                             │
├──────────────────────────────────────────────────────┤
│                                                      │
│ [Drag & drop CSV aqui ou clique para selecionar]     │
│                                                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│ Validação:                                           │
│ ✓ Arquivo selecionado:  sites.csv (145 linhas)       │
│ ✓ Colunas encontradas: nome, dominio                 │
│ ⚠ Duplicados detectados: 3 por dominio              │
│                                                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│ PREVIEW (primeiras 10 linhas):                       │
│                                                      │
│ nome               | dominio                         │
│ ──────────────────┼───────────────────────           │
│ 3 Torres           | 3torres.com.br                  │
│ Agência Leilão     | agencialeilao.com.br            │
│ ...                                                  │
│                                                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│ [Baixar template CSV]  [Importar]  [Cancelar]        │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Funcionalidade:**
- Upload drag-and-drop
- Validação de colunas (obrigatórias: `nome`, `dominio`)
- Detecção de duplicados por domínio canônico (remover www, trailing slash, lowercase)
- Preview paginado
- Botão "Baixar template CSV"
- Ao clicar "Importar": 
  - Criar/atualizar registros em `sites`
  - Mostrar relatório final

---

### **Tela 2: "Sites"**

**Layout:**
```
┌──────────────────────────────────────────────────────────┐
│ Gerenciar Sites (1.000 total)                            │
├──────────────────────────────────────────────────────────┤
│                                                          │
│ Filtros:                                                 │
│ [Todos v] [Discovery: mapped ▼] [Grouping: ungrouped ▼]  │
│ [Sem grupo] [Apenas com erro]                            │
│                                                          │
│ Ações em massa:                                          │
│ □ (check-all)  [Rodar Map] [Validar Grupos] [Exportar]    │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│ □ | Nome        | Domínio          | Discovery | Group    │
│───┼─────────────┼──────────────────┼───────────┼──────    │
│ □ | 3 Torres    | 3torres.com.br   | mapped    | 7        │
│ □ | Agência     | agencialeilao... | mapped    | 7        │
│ □ | Site X      | sitex.com.br     | failed    | —        │
│ □ | ...         | ...              | ...       | ...      │
│                                                          │
│                            [< 1 2 3 ... >]               │
│                                                          │
├──────────────────────────────────────────────────────────┤
│ Legenda:                                                 │
│ mapped ✓  | mapping ⟳ | failed ✗ | pending ○             │
│ grouped | candidate | ungrouped | rejected               │
└──────────────────────────────────────────────────────────┘
```

---

### **Tela 3: "Execuções (Runs)"**

**Layout:**
```
┌───────────────────────────────────────────────────────┐
│ Histórico de Execuções (Map Runs)                    │
├───────────────────────────────────────────────────────┤
│                                                       │
│ Run ID | Status | Sites | Sucesso | Erro | Duração     │
│────────┼────────┼──────┼─────────┼──────┼─────────     │
│ run-001| done   | 1000 | 980     | 20   | 45 min       │
│ run-002| done   | 850  | 820     | 30   | 38 min       │
│ run-003| running| 1000 | 650     | 12   | 12 min       │
│                                                       │
└───────────────────────────────────────────────────────┘
```

---

### **Tela 4: "Detalhes do Site"**

**Abas:** Map, Templates, Assinatura, Logs (conforme layout detalhado do documento original).

---

### **Tela 5: "Grupos"**

**Dados exibidos (list):**
- `group_id`, `listagem_template`, `detalhe_template`, `size`, `status`, `representative_site_id`

**Ao abrir um grupo:**
- Mostrar todos os domínios membros
- Para cada domínio, 2 URLs listagem + 2 URLs detalhe
- Resultado da validação IA (se existir)
- Botões: "Validar com IA" (se status=candidate), "Aprovar", "Rejeitar"

---

### **Tela 6: "Domínios Sem Grupo"**

**Motivos possíveis:**
- `sem_listagem`
- `sem_detalhe`
- `sem_padroes`
- `map_vazio`
- `map_erro`

**Ações:**
- "Rodar Map" (JOB A novamente)
- "Marcar como Ignorar" (sites.grouping_status = 'ignored')

---

## 🎯 Regras de Elegibilidade e Agrupamento

### **Regra 1: Elegibilidade de Domínio**

Um domínio é elegível para agrupamento se:
```
is_eligible = 
  (listagem_templates.length ≥ 1) AND
  (detalhe_templates.length ≥ 1)
```

#### **Classificação de LISTAGEM (JOB C)**
Candidato a listagem é um template que:
- Contém `/leilao/{num}/lotes` OU
- Começa com `/lotes` OU
- Termina com `/lotes` E contém `{num}`

#### **Classificação de DETALHE (JOB C)**
Candidato a detalhe é um template que:
- Termina com `/detalhes` OU `/show` OU `/info`
- E contém `{num}` OU `{id}`

**Motivos de NÃO elegibilidade:**
- `sem_listagem`
- `sem_detalhe`
- `sem_padroes`
- `map_vazio`
- `map_erro`

---

### **Regra 2: Assinatura de Grupo (JOB D)**

Cada site elegível tem:
```
signature = 
  SHA256(
    listagem_template_chosen |
    detalhe_template_chosen
  )
```

---

### **Regra 3: Agrupamento (JOB D)**

Dois domínios pertencem ao mesmo grupo se e somente se:
```
GROUP BY (listagem_template_chosen, detalhe_template_chosen)
```

---

### **Regra 4: Validação IA (JOB E)**

O agente IA recebe:
```json
{
  "group_id": ".. .",
  "listagem_template": "...",
  "detalhe_template": "...",
  "domains_count": 12,
  "examples": [
    {
      "domain": ".. .",
      "listagem_urls": [".. .", "..."],
      "detalhe_urls": ["...", "..."]
    }
  ]
}
```

O agente responde:
```json
{
  "is_valid_group": true/false,
  "confidence": "low|medium|high",
  "reasoning": "..."
}
```

---

## 📊 API Endpoints (REST)

### **Domínios**
```
POST   /api/sites/import
GET    /api/sites
GET    /api/sites/{site_id}
POST   /api/sites/{site_id}/map
```

### **Execuções**
```
GET    /api/runs
GET    /api/runs/{run_id}
POST   /api/sites/batch/map
```

### **Grupos**
```
GET    /api/groups
GET    /api/groups/{group_id}
POST   /api/groups/{group_id}/validate
POST   /api/groups/{group_id}/approve
POST   /api/groups/{group_id}/reject
```

### **Sem Grupo**
```
GET    /api/sites/ungrouped
```

---

## 🧠 Prompt do Agente IA

```
Você é um validador de estruturas de sites de leilão brasileiros. 

Seu objetivo é responder uma pergunta simples:
"O padrão de URLs proposto realmente representa uma estrutura coerente 
compartilhada por múltiplos domínios?"

─────────────────────────────────────────────────────────────

DADO:
- Um padrão de LISTAGEM de lotes:  {listagem_template}
- Um padrão de DETALHE de lote: {detalhe_template}
- {domains_count} domínios que compartilham esses padrões
- Exemplos REAIS de URLs de {min(3, domains_count)} desses domínios

PERGUNTA: 
1. Os padrões são consistentes entre os domínios?
2. Não há contradições estruturais?
3. Parecem ser da mesma plataforma/CMS ou seguir o mesmo padrão?

─────────────────────────────────────────────────────────────

EXEMPLOS: 

{examples_formatted}

─────────────────────────────────────────────────────────────

CRITÉRIOS DE VALIDAÇÃO: 

✓ VÁLIDO se:
  - Todos os domínios seguem exatamente o padrão proposto
  - Os templates realmente representam listagem (múltiplos lotes) e detalhe (um lote)
  - A estrutura é coerente e reconhecível

✗ INVÁLIDO se:
  - Alguns domínios desviam do padrão
  - Os templates não fazem sentido estruturalmente
  - Existem inconsistências entre os exemplos
  - O padrão parece forçado ou artificial

─────────────────────────────────────────────────────────────

RESPONDA UNICAMENTE EM JSON (sem markdown, sem explicações extras):

{
  "is_valid_group": true ou false,
  "confidence": "low" ou "medium" ou "high",
  "reasoning": "explicação breve (1-2 frases) do porquê"
}
```

---

## 📦 Entrega Final

Este documento cobre:
- Arquitetura: componentes, fluxo, estados
- Banco de dados: 9 tabelas, índices, relacionamentos
- Pipeline: 5 jobs (A–E) com lógica exata
- Interface: 6 telas + componentes
- Regras: elegibilidade, agrupamento, validação IA
- API: 11 endpoints REST
- Prompts: instrução do agente IA

Pronto para ser implementado por um engenheiro sênior de full-stack.
