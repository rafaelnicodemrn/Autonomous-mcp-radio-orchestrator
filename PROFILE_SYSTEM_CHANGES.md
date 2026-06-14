# Sistema de Perfil Personalizado — RadioIA Telegram Bot
## Resumo de Mudanças

Data: 2026-06-11
Versão: 1.0

---

## Arquivos Modificados

### 1. **config.yaml** (ATUALIZADO)
**Mudanças:**
- Adicionada nova seção `telegram.perfil` ao final do arquivo
- Contém 7 campos principais:
  - `nome`: "Rafael"
  - `interesses_primarios`: Lista de 5 interesses padrão
  - `fontes_vip`: Lista de 4 fontes de confiança máxima
  - `ignorar_sempre`: Lista de 5 tópicos a bloquear
  - `idioma_preferido`: "pt-BR"
  - `score_minimo_enviar`: 5 (default)
  - `max_cards_por_comando`: 8 (default)

**Por quê:**
- Centraliza todas as configurações de preferência do usuário
- Permite persistência entre restarts do bot
- Estrutura YAML permite fácil edição manual se necessário

---

### 2. **src/profile_filter.py** (NOVO)
**Módulo com 10 funções principais:**

1. **load_profile()** → dict
   - Lê seção `telegram.perfil` do config.yaml
   - Retorna perfil padrão se arquivo não existir
   - Valida e completa campos faltantes

2. **save_profile(profile: dict)** → None
   - Persiste perfil de volta ao config.yaml
   - Preserva resto do arquivo integralmente
   - Suporta unicode

3. **should_block(item: dict, profile: dict)** → bool
   - Verifica se item deve ser bloqueado
   - Checa contra lista `ignorar_sempre`
   - Match case-insensitive em título + source

4. **score_with_gemini(item: dict, profile: dict)** → Tuple[int, str]
   - Avalia relevância 0-10 via Gemini
   - Cache em memória para evitar chamadas repetidas
   - Retorna (score, motivo)
   - Timeout: 8 segundos, fallback: 5

5. **filter_and_score_items(items: list, profile: dict)** → list
   - Pipeline completo de filtragem:
     1. Bloqueia itens com `should_block()`
     2. Pontua com Gemini
     3. Traduz títulos em inglês
     4. Filtra por `score_minimo_enviar`
     5. Ordena por score decrescente

6. **format_profile(profile: dict)** → str
   - Formata perfil para exibição em Telegram
   - HTML formatado para leitura clara

7. **format_help()** → str
   - Formata ajuda do comando /perfil
   - Lista todos os subcomandos

8. **_default_profile()** → dict
   - Retorna perfil padrão se config.yaml não existir

9. **_validate_profile(perfil: dict)** → dict
   - Completa campos faltantes com padrões

10. **_is_english()** (importado de content_enricher.py)
    - Detecta se texto está em inglês

---

### 3. **telegram_bot.py** (MODIFICADO)
**Mudanças:**

#### Imports (linhas 30-35)
- Adicionado import de profile_filter:
  ```python
  from profile_filter import (
      load_profile, save_profile, filter_and_score_items,
      format_profile, format_help,
  )
  ```

#### Função _send_items() (linhas ~365-385)
- Adicionado filtro de perfil após deduplicação:
  ```python
  profile = load_profile()
  enriched_items = filter_and_score_items(enriched_items, profile)
  ```
- Items agora são filtrados por relevância antes de envio

#### Nova Função cmd_perfil() (linhas ~310-530)
- Handler completo para comando `/perfil` com subcomandos:
  - `/perfil` — mostra perfil atual
  - `/perfil ajuda` — mostra subcomandos
  - `/perfil add interesse <texto>` — adiciona interesse
  - `/perfil rem interesse <texto>` — remove interesse
  - `/perfil add ignorar <texto>` — adiciona bloqueio
  - `/perfil rem ignorar <texto>` — remove bloqueio
  - `/perfil add vip <fonte>` — adiciona fonte VIP
  - `/perfil rem vip <fonte>` — remove fonte VIP
  - `/perfil set score <0-10>` — altera score mínimo
  - `/perfil set cards <1-20>` — altera max cards

#### Handler em main() (linhas ~535+)
- Adicionado `app.add_handler(CommandHandler('perfil', cmd_perfil))`

#### Comando /start (linhas ~198-220)
- Adicionada linha: `/perfil — Ver e editar seu perfil de interesses`

---

## Fluxo de Funcionamento

### Quando usuário envia comando (ex: /tech)
1. `cmd_generate()` → `_send_items(bot, chat_id, items)`
2. Em `_send_items()`:
   - Items são enriquecidos (imagens, tradução, score básico)
   - Items são deduplicados
   - **NOVO:** Profile é carregado
   - **NOVO:** Items são filtrados por `filter_and_score_items()`:
     - Itens bloqueados são removidos
     - Cada item recebe score 0-10 via Gemini
     - Itens com score < `score_minimo_enviar` são removidos
     - Items são ordenados por relevância
   - Items são enviados para Telegram

### Quando usuário edita perfil (ex: /perfil add interesse "economia")
1. `cmd_perfil()` processa subcomando
2. Profile é carregado do config.yaml
3. Lista é modificada
4. `save_profile()` persiste mudanças
5. Próximas requisições usam novo perfil

---

## Configurações Padrão

```yaml
telegram:
  perfil:
    nome: Rafael
    interesses_primarios:
      - catolicismo tradicional
      - filosofia conservadora
      - tecnologia e inteligência artificial
      - política brasileira
      - política internacional
    fontes_vip:
      - Padre Paulo Ricardo
      - Vatican News
      - Brasil Paralelo
      - Gazeta do Povo
    ignorar_sempre:
      - esportes olímpicos
      - fofoca e celebridades
      - loteria
      - horóscopo
      - reality show
    idioma_preferido: pt-BR
    score_minimo_enviar: 5
    max_cards_por_comando: 8
```

---

## Cache e Performance

- **Cache Gemini**: Salvo em `_gemini_score_cache` dict em memória
  - Evita scores duplicados na mesma sessão
  - Limpo quando bot reinicia
  
- **Cache Tradução**: Já existente em `content_enricher.py`
  - Reutilizado para otimizar chamadas

- **Timeout**: 8 segundos para Gemini, fallback a score 5

---

## Requisitos

- Python 3.11+
- PyYAML (já no projeto)
- LiteLLM com Gemini 2.5 Flash-Lite (já configurado)
- python-telegram-bot 22.x (já no projeto)

---

## Testes Manuais Recomendados

1. `/perfil` — mostra perfil padrão
2. `/perfil add interesse "economia austríaca"` — adiciona interesse
3. `/perfil rem interesse "economia"` — remove por match parcial
4. `/perfil set score 6` — altera limiar mínimo
5. `/tech` — verifica se items são filtrados corretamente
6. `/perfil ajuda` — mostra menu de ajuda

---

## Notas Técnicas

- ✅ Compatível com Windows e Linux
- ✅ Sem f-strings com expressões complexas
- ✅ Uso correto de os.path.join() para paths
- ✅ Try/except em todas as chamadas ao Gemini
- ✅ Preservação integral do config.yaml ao salvar
- ✅ Unicode suportado em títulos e perfil

