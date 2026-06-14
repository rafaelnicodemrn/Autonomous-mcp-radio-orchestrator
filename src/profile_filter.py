# src/profile_filter.py
# Sistema de perfil personalizado para RadioIA Telegram Bot
import os
import json
import re
import logging
import yaml

logger = logging.getLogger(__name__)

# Modelo usado para filtragem/scoring (barato, alto volume)
MODEL_FILTER = os.getenv('TELEGRAM_LLM_MODEL', 'gemini/gemini-2.5-flash-lite')


def load_profile() -> dict:
    """Lê a seção telegram.perfil do config.yaml. Retorna perfil padrão se não existir."""
    config_path = 'config.yaml'
    if not os.path.exists(config_path):
        return _default_profile()

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Tenta ler seção telegram.perfil
        telegram_section = config.get('telegram', {})
        if isinstance(telegram_section, dict):
            perfil = telegram_section.get('perfil')
            if isinstance(perfil, dict):
                return _validate_profile(perfil)
    except Exception as e:
        logger.warning(f'[profile] erro ao ler config.yaml: {e}')

    return _default_profile()


def _default_profile() -> dict:
    """Retorna perfil padrão mínimo."""
    return {
        'nome': 'Rafael',
        'interesses_primarios': [
            'catolicismo tradicional',
            'filosofia conservadora',
            'tecnologia e inteligência artificial',
            'política brasileira',
            'política internacional',
        ],
        'fontes_vip': [
            'Padre Paulo Ricardo',
            'Vatican News',
            'Brasil Paralelo',
            'Gazeta do Povo',
        ],
        'ignorar_sempre': [
            'esportes olímpicos',
            'fofoca e celebridades',
            'loteria',
            'horóscopo',
            'reality show',
        ],
        'idioma_preferido': 'pt-BR',
        'score_minimo_enviar': 5,
        'max_cards_por_comando': 8,
    }


def _validate_profile(perfil: dict) -> dict:
    """Valida e completa campos faltantes do perfil."""
    default = _default_profile()
    for key in default:
        if key not in perfil:
            perfil[key] = default[key]
    return perfil


def save_profile(profile: dict):
    """Salva perfil de volta no config.yaml, preservando resto do arquivo."""
    config_path = 'config.yaml'
    if not os.path.exists(config_path):
        logger.warning('[profile] config.yaml não encontrado')
        return

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Garante que telegram.perfil existe
        if 'telegram' not in config or not isinstance(config['telegram'], dict):
            config['telegram'] = {}

        config['telegram']['perfil'] = profile

        # Salva mantendo unicode
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        logger.info('[profile] perfil salvo em config.yaml')
    except Exception as e:
        logger.error(f'[profile] erro ao salvar: {e}')


def should_block(item: dict, profile: dict) -> bool:
    """Verifica se o item deve ser bloqueado com base em ignorar_sempre."""
    ignorar = profile.get('ignorar_sempre', [])
    title = str(item.get('title', '')).lower()
    source = str(item.get('source_name', '')).lower()
    combined = f"{title} {source}"

    for palavra in ignorar:
        palavra_lower = palavra.lower()
        if palavra_lower in combined:
            logger.debug(f"[block] removido: {item.get('title','')[:60]} (palavra: {palavra})")
            return True

    return False


def score_batch_with_gemini(items: list, profile: dict) -> list:
    """
    Avalia relevância de até 5 itens em UMA chamada Gemini.
    Economiza ~80% dos tokens vs chamada individual.
    Usa MODEL_FILTER (modelo mais barato para filtragem).
    """
    if not items:
        return items

    interesses = ', '.join(profile.get('interesses_primarios', []))
    fontes_vip = ', '.join(profile.get('fontes_vip', []))

    itens_texto = []
    for i, item in enumerate(items):
        titulo = str(item.get('title', ''))[:100]
        fonte = str(item.get('source_name', ''))
        itens_texto.append(f"{i+1}. [{fonte}] {titulo}")

    lista = '\n'.join(itens_texto)

    prompt = (
        "Perfil do usuário:\n"
        f"- Interesses: {interesses}\n"
        f"- Fontes VIP (score +2): {fontes_vip}\n\n"
        "Avalie cada notícia de 0 a 10 para este usuário.\n"
        "Responda APENAS com JSON array sem texto adicional:\n"
        '[{"i":1,"score":8,"motivo":"catolicismo"},{"i":2,"score":3,"motivo":"irrelevante"}]\n\n'
        f"Notícias:\n{lista}"
    )

    try:
        from content_enricher import _gemini_call_with_retry
        from dotenv import load_dotenv
        load_dotenv()

        raw = _gemini_call_with_retry(prompt, MODEL_FILTER, 600)
        raw = raw.replace('```json', '').replace('```', '').strip()

        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            scores = json.loads(match.group())
            score_map = {s['i']: (int(s.get('score', 5)), str(s.get('motivo', '')))
                         for s in scores}
            for i, item in enumerate(items):
                score, motivo = score_map.get(i + 1, (5, 'padrão'))
                item['_score'] = min(max(score, 0), 10)
                item['_motivo'] = motivo

    except Exception as e:
        logger.warning(f'[batch_score] erro: {e}')

    for item in items:
        if '_score' not in item:
            item['_score'] = 5
            item['_motivo'] = 'fallback'

    return items


def filter_and_score_items(items: list, profile: dict) -> list:
    """
    Pipeline completo:
    1. Bloqueia itens com should_block()
    2. Avalia relevância em batch com score_batch_with_gemini()
    3. Traduz títulos em inglês se necessário
    4. Recalcula score com o motor adaptativo (se disponível)
    5. Filtra itens com score < score_minimo_enviar
    6. Ordena por score decrescente
    7. Aplica diversity_guard para evitar repetição de tópicos
    Retorna lista enriquecida com _score e _motivo.
    """
    from content_enricher import _is_english, translate_if_needed, diversity_guard

    # 1. Bloqueia
    filtered = [i for i in items if not should_block(i, profile)]

    # 2. Avalia em batch (5 itens por chamada) e enriquece
    enriched = [dict(item) for item in filtered]
    BATCH_SIZE = 5
    for i in range(0, len(enriched), BATCH_SIZE):
        score_batch_with_gemini(enriched[i:i + BATCH_SIZE], profile)

    # 3. Traduz títulos em inglês se preferência for pt-BR
    if profile.get('idioma_preferido') == 'pt-BR':
        for item in enriched:
            title = item.get('title', '')
            text = item.get('text', '')
            if _is_english(f"{title} {text}"):
                t_title, t_text = translate_if_needed(title, text)
                item['title'] = t_title
                item['text'] = t_text

    # 4. Recalcula score com o motor adaptativo, se disponível
    try:
        from adaptive_engine import load_state, save_state, compute_adaptive_score, update_source_reputation

        adaptive_state = load_state()
        for item in enriched:
            gemini_score = item.get('_score', 5)
            source_name = item.get('source_name', '')

            item['_score'] = compute_adaptive_score(item, gemini_score, adaptive_state)

            if source_name:
                update_source_reputation(source_name, gemini_score, adaptive_state)

        save_state(adaptive_state)
    except Exception as e:
        logger.debug(f'[adaptive] não foi possível recalcular score: {e}')

    # 5. Filtra por score mínimo
    min_score = profile.get('score_minimo_enviar', 5)
    filtered_by_score = [i for i in enriched if i['_score'] >= min_score]

    # 6. Ordena por score decrescente
    filtered_by_score.sort(key=lambda x: x['_score'], reverse=True)

    # 7. Garante diversidade de tópicos
    result = diversity_guard(filtered_by_score, max_per_topic=2)

    return result


def format_profile(profile: dict) -> str:
    """Formata perfil para exibição no Telegram."""
    nome = profile.get('nome', 'Rafael')
    interesses = profile.get('interesses_primarios', [])
    vips = profile.get('fontes_vip', [])
    ignorar = profile.get('ignorar_sempre', [])
    score_min = profile.get('score_minimo_enviar', 5)
    max_cards = profile.get('max_cards_por_comando', 8)

    lines = [
        f'👤 <b>Seu Perfil — RadioIA Pessoal</b>\n',
        f'🎯 <b>Interesses principais:</b>',
    ]

    for interesse in interesses:
        lines.append(f'• {interesse}')

    lines.append('')
    lines.append('<b>⭐ Fontes VIP (prioridade máxima):</b>')
    for vip in vips:
        lines.append(f'• {vip}')

    lines.append('')
    lines.append('<b>🚫 Sempre ignorar:</b>')
    for ig in ignorar:
        lines.append(f'• {ig}')

    lines.append('')
    lines.append('<b>⚙️ Configurações:</b>')
    lines.append(f'• Score mínimo: {score_min}/10')
    lines.append(f'• Máx. cards por comando: {max_cards}')
    lines.append(f'• Idioma: pt-BR')
    lines.append('')
    lines.append('<i>Use /perfil ajuda para ver como editar.</i>')

    return '\n'.join(lines)


def format_help() -> str:
    """Formata ajuda do comando /perfil."""
    lines = [
        '<b>📋 Como editar seu perfil:</b>\n',
        '/perfil add interesse &lt;texto&gt;',
        '/perfil rem interesse &lt;texto&gt;',
        '/perfil add ignorar &lt;texto&gt;',
        '/perfil rem ignorar &lt;texto&gt;',
        '/perfil add vip &lt;nome da fonte&gt;',
        '/perfil rem vip &lt;nome da fonte&gt;',
        '/perfil set score &lt;numero 0-10&gt;',
        '/perfil set cards &lt;numero 1-20&gt;',
        '',
        '<i>Exemplo: /perfil add interesse "economia austríaca"</i>',
    ]
    return '\n'.join(lines)
