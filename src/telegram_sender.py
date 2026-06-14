# src/telegram_sender.py
# Formatação e envio de mensagens para o Telegram
import os
import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Delay entre mensagens para respeitar rate limits do Telegram
MSG_DELAY = 1.0

# Emojis por categoria de fonte
SOURCE_EMOJIS = {
    'catolicismo': '✝️',
    'biblia': '📖',
    'conservadorismo': '🏛️',
    'noticias': '📰',
    'noticias-locais': '🌿',
    'noticias-internacionais': '🌐',
    'tecnologia': '💻',
    'inteligencia-artificial': '🤖',
    'tecnologia-internacional': '💡',
    'gremio': '⚽',
    'copa': '🏆',
    'brasileirao': '⚽',
    'libertadores': '🌎',
    'filmes': '🎬',
    'filmes-cartaz': '🎥',
    'efemerides': '📅',
    'quiz': '🧠',
    'receitas': '🍽️',
    'agronegocio': '🌾',
    'reddit': '💬',
    'europa': '🗺️',
    'youtube': '▶️',
    'politica': '🏛️',
}

CATEGORY_TITLES = {
    'catolicismo': '✝️ Fé e Reflexão',
    'biblia': '📖 Palavra do Dia',
    'conservadorismo': '🏛️ Filosofia e Conservadorismo',
    'noticias': '📰 Notícias',
    'noticias-locais': '🌿 Local — Medianeira/PR',
    'noticias-internacionais': '🌐 Internacional',
    'tecnologia': '💻 Tecnologia',
    'inteligencia-artificial': '🤖 Inteligência Artificial',
    'tecnologia-internacional': '💡 Tech Internacional',
    'gremio': '⚽ Grêmio',
    'copa': '🏆 Copa do Mundo',
    'brasileirao': '⚽ Brasileirão',
    'libertadores': '🌎 Libertadores',
    'filmes': '🎬 Filmes',
    'filmes-cartaz': '🎥 Em Cartaz',
    'efemerides': '📅 Hoje na História',
    'quiz': '🧠 Quiz',
    'receitas': '🍽️ Receita',
    'agronegocio': '🌾 Agronegócio',
    'reddit': '💬 Reddit',
    'europa': '🗺️ Europa e Viagens',
    'youtube': '▶️ YouTube',
    'politica': '🏛️ Política',
}


def _escape_html(text: str) -> str:
    """Escapa caracteres especiais do HTML do Telegram."""
    return (text or '').\
        replace('&', '&amp;').\
        replace('<', '&lt;').\
        replace('>', '&gt;')


def _stars(score: int) -> str:
    if score >= 8:
        return '⭐⭐'
    if score >= 5:
        return '⭐'
    return ''


def _extract_bullets(text: str, max_bullets: int = 3) -> list:
    """Extrai ou gera bullets a partir do texto do item."""
    if not text:
        return []

    # Se já tem bullets no texto
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    bullet_lines = [l for l in lines if l.startswith(('•', '-', '*', '–'))]
    if bullet_lines:
        return [re.sub(r'^[•\-\*–]\s*', '', b) for b in bullet_lines[:max_bullets]]

    # Divide em frases como bullets
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    bullets = []
    for s in sentences[:max_bullets]:
        s = s.strip()
        if len(s) > 20:
            bullets.append(s[:120] + ('...' if len(s) > 120 else ''))
    return bullets


def _source_tags(source_id: str, source_name: str) -> str:
    """Gera hashtags baseadas na fonte."""
    tags = []
    sid = source_id.lower().replace('-', '')
    if 'catolicismo' in sid or 'biblia' in sid:
        tags += ['#catolicismo']
    if 'conservador' in sid:
        tags += ['#conservadorismo']
    if 'gremio' in sid or 'brasileirao' in sid or 'copa' in sid or 'libertadores' in sid:
        tags += ['#futebol']
    if 'tech' in sid or 'tecnologia' in sid or 'ia' in sid or 'inteligencia' in sid:
        tags += ['#tecnologia']
    if 'noticias' in sid:
        tags += ['#noticias']
    if 'agronegocio' in sid:
        tags += ['#agro']
    return ' '.join(tags[:3])


def format_item_html(item: dict, enriched: dict) -> str:
    """Formata item como HTML para Telegram."""
    source_id = enriched.get('source_id', '')
    source_name = _escape_html(enriched.get('source_name', source_id))
    title = _escape_html(enriched.get('title', ''))
    url = enriched.get('url', '')
    score = enriched.get('_score', 0)
    text = enriched.get('text', '')
    is_youtube = enriched.get('source_type') == 'youtube'

    emoji = SOURCE_EMOJIS.get(source_id, '📌')
    stars = _stars(score)
    bullets = _extract_bullets(text)
    tags = _source_tags(source_id, source_name)

    lines = []

    # Cabeçalho
    if is_youtube:
        lines.append(f'▶️ <b>{source_name}</b>  {stars}')
    else:
        lines.append(f'{emoji} <b>{source_name}</b>  {stars}')

    # Título
    if url:
        lines.append(f'📌 <b><a href="{url}">{title}</a></b>')
    else:
        lines.append(f'📌 <b>{title}</b>')

    # Bullets
    if bullets:
        lines.append('')
        for b in bullets:
            lines.append(f'• {_escape_html(b)}')

    # Link
    if url and not is_youtube:
        lines.append('')
        lines.append(f'🔗 <a href="{url}">Ler artigo completo</a>')
    elif url and is_youtube:
        lines.append('')
        lines.append(f'🎬 <a href="{url}">Assistir no YouTube</a>')

    # Hashtags
    if tags:
        lines.append('')
        lines.append(tags)

    return '\n'.join(lines)


async def send_item_card(bot, chat_id: int, item: dict, enriched: dict, reply_markup=None) -> None:
    """Envia item como card formatado com imagem opcional."""
    from telegram import InputMediaPhoto
    from telegram.error import TelegramError

    html = format_item_html(item, enriched)
    image_url = enriched.get('_image_url')

    try:
        if image_url:
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=html,
                    parse_mode='HTML',
                    reply_markup=reply_markup,
                )
            except TelegramError:
                # Foto falhou — envia só texto
                await bot.send_message(
                    chat_id=chat_id,
                    text=html,
                    parse_mode='HTML',
                    disable_web_page_preview=False,
                    reply_markup=reply_markup,
                )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=html,
                parse_mode='HTML',
                disable_web_page_preview=False,
                reply_markup=reply_markup,
            )
        await asyncio.sleep(MSG_DELAY)
    except TelegramError as e:
        logger.error(f'[send_item_card] erro: {e}')


async def send_audio(bot, chat_id: int, mp3_path: str, caption: str) -> None:
    """Envia arquivo MP3 como mensagem de áudio."""
    from telegram.error import TelegramError

    if not os.path.exists(mp3_path):
        return
    try:
        with open(mp3_path, 'rb') as f:
            await bot.send_audio(
                chat_id=chat_id,
                audio=f,
                caption=caption[:1024],
                title='RadioIA Pessoal',
                performer='RadioIA',
            )
        await asyncio.sleep(MSG_DELAY)
    except TelegramError as e:
        logger.error(f'[send_audio] erro: {e}')


async def send_section_header(bot, chat_id: int, source_id: str) -> None:
    """Envia cabeçalho de seção para o briefing."""
    title = CATEGORY_TITLES.get(source_id, f'📌 {source_id}')
    sep = '\u2501' * 20
    text = f'\n<b>{sep}</b>\n{title}\n'
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='HTML',
        )
        await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f'[send_section_header] erro: {e}')


async def send_briefing_header(bot, chat_id: int, weather_text: str = '',
                                finance_text: str = '', verse: str = '') -> None:
    """Envia cabeçalho do briefing matinal."""
    from datetime import datetime
    import locale

    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except Exception:
        pass

    now = datetime.now()
    try:
        date_str = now.strftime('%A, %d de %B de %Y').capitalize()
    except Exception:
        date_str = now.strftime('%d/%m/%Y')

    lines = [
        f'☀️ <b>Bom dia, Rafael!</b>',
        f'<i>RadioIA Pessoal · {date_str}</i>',
        '━' * 20,
    ]

    if weather_text:
        lines.append(f'🌡️ {_escape_html(weather_text)}')

    if finance_text:
        lines.append(f'💵 {_escape_html(finance_text)}')

    if verse:
        lines.append('')
        lines.append(f'✝️ <b>Palavra do Dia</b>')
        lines.append(f'<i>{_escape_html(verse)}</i>')

    text = '\n'.join(lines)

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='HTML',
        )
        await asyncio.sleep(MSG_DELAY)
    except Exception as e:
        logger.error(f'[send_briefing_header] erro: {e}')


async def send_text(bot, chat_id: int, text: str,
                    parse_mode: str = 'HTML',
                    disable_preview: bool = True) -> None:
    """Envia mensagem de texto simples."""
    from telegram.error import TelegramError
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_preview,
        )
        await asyncio.sleep(0.3)
    except TelegramError as e:
        logger.error(f'[send_text] erro: {e}')
