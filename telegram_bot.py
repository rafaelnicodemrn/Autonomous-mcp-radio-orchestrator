# telegram_bot.py
# Bot principal do Telegram para RadioIA Pessoal
# Rodar: python telegram_bot.py
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from datetime import time as dt_time
from datetime import timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

# Windows event loop fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv

load_dotenv()

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update  # noqa: E402
from telegram.ext import (  # noqa: E402
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Adiciona src/ ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from adaptive_engine import sync_youtube_signals  # noqa: E402
from adaptive_engine import calculate_dynamic_weights, format_learning_status  # noqa: E402
from adaptive_engine import load_state as load_adaptive_state  # noqa: E402
from adaptive_engine import record_command_usage, record_feedback, run_weekly_analysis  # noqa: E402
from adaptive_engine import save_state as save_adaptive_state  # noqa: E402
from content_enricher import _gemini_call_with_retry  # noqa: E402
from content_enricher import deduplicate, enrich_item, score_item  # noqa: E402
from data.versiculos import format_verse_of_day  # noqa: E402
from profile_filter import (  # noqa: E402
    filter_and_score_items,
    format_help,
    format_profile,
    load_profile,
    save_profile,
)
from telegram_sender import _escape_html  # noqa: E402
from telegram_sender import (  # noqa: E402
    send_audio,
    send_briefing_header,
    send_item_card,
    send_section_header,
    send_text,
)
from weather import get_exchange_rate, get_weather_summary  # noqa: E402

# Modelos Gemini — estratégia de dois níveis
MODEL_FILTER = "gemini/gemini-2.5-flash-lite"  # filtragem/scoring (barato, alto volume)
MODEL_GENERATE = "gemini/gemini-3.1-flash-lite"  # geração de roteiro (melhor qualidade PT-BR)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Configuração ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
STATE_FILE = "telegram_state.json"
MAX_SENT_IDS = 500
MAX_ITEMS_PER_CATEGORY = 3
BRIEFING_HOUR = 7
BRIEFING_MINUTE = 0
BRIEFING_TZ = ZoneInfo("America/Sao_Paulo")

BRIEFING_SOURCES = [
    "biblia",
    "utilidades",
    "catolicismo",
    "noticias",
    "tecnologia",
    "politica",
    "conservadorismo",
]

COMMANDS = {
    "/briefing": [
        "biblia",
        "utilidades",
        "catolicismo",
        "noticias",
        "tecnologia",
        "politica",
        "conservadorismo",
        "gdelt",
    ],
    "/noticias": ["noticias", "politica", "noticias-internacionais", "gdelt"],
    "/tech": ["tecnologia", "inteligencia-artificial", "tecnologia-internacional"],
    "/fe": ["biblia", "catolicismo", "conservadorismo"],
    "/gremio": ["gremio", "copa", "brasileirao", "libertadores"],
    "/filmes": ["filmes", "filmes-cartaz"],
    "/local": ["noticias-locais", "agronegocio"],
    "/youtube": ["youtube"],
}

# Keywords de busca no YouTube por comando (vídeos adicionais relacionados ao tema)
YOUTUBE_KEYWORDS = {
    "/noticias": ["notícias Brasil política hoje", "Brasil governo semana"],
    "/tech": ["inteligência artificial novidades", "tecnologia lançamento"],
    "/fe": ["catolicismo reflexão", "Padre Paulo Ricardo"],
    "/gremio": ["Grêmio futebol", "Brasileirão rodada resultado"],
    "/filmes": ["filmes lançamento 2026", "cinema estreia"],
    "/local": ["agronegócio Brasil", "soja milho mercado"],
    "/briefing": ["notícias Brasil hoje", "principais acontecimentos"],
}

# ── Estado persistente ────────────────────────────────────────────────────────


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "chat_id": None,
        "last_briefing": None,
        "sent_item_ids": [],
        "config": {
            "briefing_time": f"{BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d}",
            "include_audio": True,
            "max_items_per_category": MAX_ITEMS_PER_CATEGORY,
        },
    }


def save_state(state: dict):
    # Limita sent_item_ids a MAX_SENT_IDS (FIFO)
    if len(state.get("sent_item_ids", [])) > MAX_SENT_IDS:
        state["sent_item_ids"] = state["sent_item_ids"][-MAX_SENT_IDS:]
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[save_state] erro: {e}")


def item_hash(item: dict) -> str:
    key = f"{item.get('source_id','')}/{item.get('id', item.get('title',''))}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ── Coleta de conteúdo ────────────────────────────────────────────────────────


def _collect_from_episode_json(source_ids: list) -> list:
    """Lê episódios já gerados hoje em output/ e extrai links/itens."""
    items = []
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join("output", today)
    if not os.path.exists(output_dir):
        return items

    for folder in sorted(os.listdir(output_dir)):
        ep_path = os.path.join(output_dir, folder, "episode.json")
        if not os.path.exists(ep_path):
            continue

        # Verifica se é uma das fontes solicitadas
        parts = folder.split("_", 1)
        source_id = parts[1] if len(parts) > 1 else folder
        if source_ids and source_id not in source_ids:
            continue

        try:
            with open(ep_path, "r", encoding="utf-8") as f:
                ep = json.load(f)

            mp3_path = os.path.join(output_dir, folder, "episode.mp3")
            audio_path = ep.get("audio_path", mp3_path if os.path.exists(mp3_path) else None)

            for link in ep.get("links", []):
                items.append(
                    {
                        "id": link.get("url", link.get("title", "")),
                        "title": link.get("title", ""),
                        "url": link.get("url", ""),
                        "text": link.get("text", link.get("title", "")),
                        "source_name": ep.get("source_name", source_id),
                        "source_id": source_id,
                        "source_type": ep.get("source_type", ""),
                        "published_at": today,
                        "views": link.get("views", 0),
                        "_audio_path": audio_path,
                        "_episode_folder": folder,
                    }
                )
        except Exception as e:
            logger.warning(f"[collect] erro em {ep_path}: {e}")

    return items


def _run_main_py(sources: list) -> Optional[str]:
    """Executa main.py com as sources e retorna None (roda em background)."""
    try:
        python = sys.executable
        args = [python, "main.py"] + sources
        proc = subprocess.Popen(
            args,
            cwd=os.path.abspath("."),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc
    except Exception as e:
        logger.error(f"[run_main] erro: {e}")
        return None


async def _wait_and_collect(proc, sources: list, timeout: int = 300) -> list:
    """Aguarda processo terminar (com timeout) e coleta resultados."""
    if proc is None:
        return []
    try:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, proc.wait),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("[wait_and_collect] timeout — processo encerrado")

    items = _collect_from_episode_json(sources)
    if not items:
        # Sem itens: loga a saída do main.py para diagnosticar a causa real
        # (ex: "Nenhum conteudo novo encontrado" por dedup, erro de fonte, etc.)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout, stderr = b"", b""
        if stdout:
            logger.warning(f"[wait_and_collect] main.py stdout:\n{stdout.decode(errors='replace')}")
        if stderr:
            logger.warning(f"[wait_and_collect] main.py stderr:\n{stderr.decode(errors='replace')}")
        logger.warning(f"[wait_and_collect] main.py exit code: {proc.returncode}")
    return items


def load_quotas(cmd_key: str = None) -> dict:
    """
    Lê telegram.quotas do config.yaml. Se cmd_key for informado, retorna
    apenas a quota daquele comando (sem a barra inicial). Retorna {} se
    não houver configuração (e o comando segue sem limite extra).
    """
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        return {}

    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        quotas = config.get("telegram", {}).get("quotas", {})
        if not isinstance(quotas, dict):
            return {}

        if cmd_key:
            return quotas.get(cmd_key.lstrip("/"), {})
        return quotas
    except Exception as e:
        logger.warning(f"[quotas] erro ao ler config.yaml: {e}")
        return {}


def _fetch_youtube_for_cmd(cmd_key: str) -> list:
    """Busca vídeos YouTube por keyword para o comando dado."""
    if cmd_key not in YOUTUBE_KEYWORDS:
        return []
    try:
        from googleapiclient.discovery import build

        from src.auth import get_youtube_credentials
        from src.sources.youtube import search_youtube_by_keyword

        creds = get_youtube_credentials()
        if not creds:
            return []
        yt_service = build("youtube", "v3", credentials=creds)

        items = []
        for keyword in YOUTUBE_KEYWORDS[cmd_key]:
            results = search_youtube_by_keyword(keyword, yt_service, max_results=2)
            items.extend(results)
        return items
    except Exception as e:
        logger.warning(f"[youtube_cmd] erro para {cmd_key}: {e}")
        return []


# ── Handlers ──────────────────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = load_state()
    state["chat_id"] = chat_id
    save_state(state)

    # Atualiza também o .env (apenas se não estiver preenchido)
    _set_env_chat_id(chat_id)

    text = (
        "📻 <b>RadioIA Pessoal</b>\n"
        "Seu briefing diário de notícias, fé e futebol.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>Comandos disponíveis:</b>\n\n"
        "/briefing — Briefing completo agora\n"
        "/noticias — Notícias + política + GDELT\n"
        "/tech — Tecnologia + IA + YouTube\n"
        "/fe — Fé, filosofia e catolicismo\n"
        "/gremio — Grêmio, Copa e futebol\n"
        "/filmes — Filmes em cartaz\n"
        "/local — Notícias locais + agro\n"
        "/youtube — Vídeos do YouTube (canais configurados)\n\n"
        "/perfil — Ver e editar seu perfil de interesses\n"
        "/url &lt;link&gt; — Episódio de URL avulsa\n"
        "/resumo — Resumo executivo do dia em uma mensagem\n"
        "/historico — Episódios de hoje\n"
        "/status — Status e próximo briefing\n"
        "/aprendizado — Status do aprendizado adaptativo\n"
        "/analise — Análise de dados sob demanda\n"
        "/sincronia — Sincronizar interesses do YouTube\n"
        "/config — Ver quotas e pesos do sistema\n"
        "/ajuda — Esta mensagem\n\n"
        f"⏰ Briefing automático às {BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d} todos os dias."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    last = state.get("last_briefing", "Nunca enviado")
    sent = len(state.get("sent_item_ids", []))
    chat = state.get("chat_id", "não registrado")

    text = (
        f"📊 <b>Status do RadioIA Bot</b>\n\n"
        f"💬 Chat ID: <code>{chat}</code>\n"
        f"📅 Último briefing: {last}\n"
        f"📦 Itens no histórico: {sent}\n"
        f"⏰ Próximo briefing: {BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d}\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_historico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join("output", today)

    if not os.path.exists(output_dir):
        await update.message.reply_text("Nenhum episódio gerado hoje.")
        return

    episodes = []
    for folder in sorted(os.listdir(output_dir)):
        ep_json = os.path.join(output_dir, folder, "episode.json")
        ep_mp3 = os.path.join(output_dir, folder, "episode.mp3")
        if os.path.exists(ep_json):
            try:
                with open(ep_json, "r", encoding="utf-8") as f:
                    ep = json.load(f)
                parts = folder.split("_", 1)
                time_str = parts[0].replace("-", "h") if len(parts) > 1 else ""
                name = ep.get("source_name", parts[1] if len(parts) > 1 else folder)
                dur = ep.get("duration_seconds", 0)
                dur_str = f"{dur//60}:{dur%60:02d}" if dur else ""
                has_mp3 = os.path.exists(ep_mp3)
                episodes.append((time_str, name, dur_str, folder, has_mp3))
            except Exception:
                pass

    if not episodes:
        await update.message.reply_text("Nenhum episódio encontrado hoje.")
        return

    lines = ["📋 <b>Episódios de hoje:</b>\n"]
    keyboard = []
    for i, (t, name, dur, folder, has_mp3) in enumerate(episodes):
        meta = f" · {dur}" if dur else ""
        lines.append(f"{i+1}. {t} — {name}{meta}")
        if has_mp3:
            keyboard.append([InlineKeyboardButton(f"🎵 {name}", callback_data=f"play:{folder}")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


async def callback_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    folder = query.data.replace("play:", "")
    today = datetime.now().strftime("%Y-%m-%d")
    mp3_path = os.path.join("output", today, folder, "episode.mp3")

    if not os.path.exists(mp3_path):
        await query.message.reply_text("Arquivo de áudio não encontrado.")
        return

    await query.message.reply_text("⏳ Enviando áudio...")
    await send_audio(context.bot, query.message.chat_id, mp3_path, caption=f"🎵 {folder}")


async def callback_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa feedback (👍/👎) dado pelo usuário em um item."""
    query = update.callback_query
    await query.answer()

    try:
        # formato: fb:<+1|-1>:<hash>:<src_short>:<sid_short>:<score>
        parts = query.data.split(":")
        _, feedback, item_hash_short, src_short, sid_short, score_str = parts[:6]
        gemini_score = int(score_str)
    except Exception as e:
        logger.warning(f"[callback_feedback] payload inválido: {e}")
        return

    record_feedback(item_hash_short, src_short, sid_short, gemini_score, feedback)

    emoji = "👍" if feedback == "+1" else "👎"
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await query.message.reply_text(
        f"{emoji} Obrigado pelo feedback! Isso ajuda a melhorar suas recomendações."
    )


async def cmd_aprendizado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /aprendizado — mostra status do motor de aprendizado adaptativo."""
    adaptive_state = load_adaptive_state()
    text = format_learning_status(adaptive_state)
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_analise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /analise — roda análise sob demanda com Gemini."""
    await update.message.reply_text("🧠 Analisando seus dados de uso...")
    adaptive_state = load_adaptive_state()
    report = run_weekly_analysis(adaptive_state)
    await update.message.reply_text(report, parse_mode="HTML")


async def cmd_sincronia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /sincronia — força sincronização de sinais do YouTube."""
    await update.message.reply_text("▶️ Sincronizando preferências do YouTube...")

    try:
        from googleapiclient.discovery import build

        from src.auth import get_youtube_credentials

        creds = get_youtube_credentials()
        if not creds:
            await update.message.reply_text("⚠️ Credenciais do YouTube não configuradas.")
            return

        yt_service = build("youtube", "v3", credentials=creds)
        vector = sync_youtube_signals(yt_service)

        adaptive_state = load_adaptive_state()
        if vector:
            adaptive_state["youtube_interest_vector"] = vector
        adaptive_state["last_youtube_sync"] = datetime.now().strftime("%Y-%m-%d")
        adaptive_state["signal_weights"] = calculate_dynamic_weights(adaptive_state)
        save_adaptive_state(adaptive_state)

        if vector:
            interesses = ", ".join(f"{k} ({v:.2f})" for k, v in vector.items())
            await update.message.reply_text(f"✅ Interesses identificados: {interesses}")
        else:
            await update.message.reply_text("ℹ️ Nenhum interesse novo identificado.")
    except Exception as e:
        logger.warning(f"[sincronia] erro: {e}")
        await update.message.reply_text(f"⚠️ Erro ao sincronizar: {e}")


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /config — mostra quotas e pesos atuais do sistema."""
    quotas = load_quotas()
    adaptive_state = load_adaptive_state()
    weights = adaptive_state.get("signal_weights", {})

    lines = ["⚙️ <b>Configurações — RadioIA</b>\n"]

    lines.append("📦 <b>Quotas por comando:</b>")
    if quotas:
        for cmd, q in quotas.items():
            por_fonte = q.get("max_por_fonte", "-")
            total = q.get("max_total", "-")
            lines.append(f"• /{cmd}: até {por_fonte}/fonte, máx {total} total")
    else:
        lines.append("• Nenhuma quota configurada")

    lines.append("")
    lines.append("🧠 <b>Pesos do motor adaptativo:</b>")
    for nome, peso in weights.items():
        lines.append(f"• {nome}: {round(peso * 100)}%")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


def _build_resumo_prompt(items: list, profile: dict) -> str:
    interesses = ", ".join(profile.get("interesses_primarios", []))
    linhas = []
    for item in items[:25]:
        titulo = str(item.get("title", ""))[:120]
        fonte = str(item.get("source_name", ""))
        linhas.append(f"- [{fonte}] {titulo}")
    lista = "\n".join(linhas)

    return (
        "Você é o assistente pessoal de notícias do Rafael.\n"
        f"Perfil de interesses dele: {interesses}.\n\n"
        "Com base nos itens abaixo, escreva um resumo executivo do dia em "
        "5 a 8 linhas, tom direto, em português do Brasil, cobrindo os "
        "principais pontos relevantes ao perfil dele. Não use markdown, "
        "apenas texto corrido em parágrafos curtos.\n\n"
        f"Itens do dia:\n{lista}"
    )


async def cmd_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /resumo — resumo executivo do dia em uma única mensagem."""
    record_command_usage("/resumo")

    items = _collect_from_episode_json([])
    if not items:
        await update.message.reply_text(
            "⏳ Nenhum conteúdo gerado hoje ainda — coletando agora...\nAguarde alguns instantes."
        )
        proc = _run_main_py(BRIEFING_SOURCES)
        items = await _wait_and_collect(proc, BRIEFING_SOURCES, timeout=360)

    data_str = datetime.now().strftime("%d/%m/%Y")

    if not items:
        await update.message.reply_text(
            f"📋 <b>Resumo do dia — {data_str}</b>\n\n"
            "⚠️ Nenhum conteúdo disponível hoje para resumir.",
            parse_mode="HTML",
        )
        return

    profile = load_profile()
    prompt = _build_resumo_prompt(items, profile)

    try:
        resumo = _gemini_call_with_retry(prompt, MODEL_GENERATE, 500).strip()
    except Exception as e:
        logger.warning(f"[resumo] erro ao gerar resumo: {e}")
        resumo = "⚠️ Não foi possível gerar o resumo agora. Tente novamente em alguns instantes."

    text = f"📋 <b>Resumo do dia — {data_str}</b>\n\n{_escape_html(resumo)}"
    await update.message.reply_text(text, parse_mode="HTML")


async def weekly_analysis_job(context: ContextTypes.DEFAULT_TYPE):
    """Job semanal — analisa dados acumulados e envia relatório ao usuário."""
    state = load_state()
    chat_id = state.get("chat_id")
    if not chat_id:
        return

    adaptive_state = load_adaptive_state()
    report = run_weekly_analysis(adaptive_state)

    await send_text(
        context.bot,
        chat_id,
        "🧠 <b>Análise Semanal — RadioIA</b>\n\n" + report,
        parse_mode="HTML",
    )


async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /perfil — ver e editar perfil de interesses."""
    args = context.args
    profile = load_profile()

    if not args:
        text = format_profile(profile)
        await update.message.reply_text(text, parse_mode="HTML")
        return

    cmd = args[0].lower()

    if cmd == "ajuda":
        text = format_help()
        await update.message.reply_text(text, parse_mode="HTML")
        return

    # Comandos que modificam o perfil
    if cmd == "add":
        if len(args) < 3:
            await update.message.reply_text(
                "❌ Uso: /perfil add &lt;tipo&gt; &lt;valor&gt;\n" "Tipos: interesse, ignorar, vip",
                parse_mode="HTML",
            )
            return

        tipo = args[1].lower()
        valor = " ".join(args[2:])

        if tipo == "interesse":
            if valor not in profile["interesses_primarios"]:
                profile["interesses_primarios"].append(valor)
                save_profile(profile)
                await update.message.reply_text(
                    f"✅ Adicionado aos seus interesses: <b>{valor}</b>", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"ℹ️ Você já tem esse interesse: <b>{valor}</b>", parse_mode="HTML"
                )

        elif tipo == "ignorar":
            if valor not in profile["ignorar_sempre"]:
                profile["ignorar_sempre"].append(valor)
                save_profile(profile)
                await update.message.reply_text(
                    f"✅ Adicionado à sua lista de ignorar: <b>{valor}</b>", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"ℹ️ Você já ignora isso: <b>{valor}</b>", parse_mode="HTML"
                )

        elif tipo == "vip":
            if valor not in profile["fontes_vip"]:
                profile["fontes_vip"].append(valor)
                save_profile(profile)
                await update.message.reply_text(
                    f"⭐ Adicionado às suas fontes VIP: <b>{valor}</b>", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"ℹ️ Essa fonte já é VIP: <b>{valor}</b>", parse_mode="HTML"
                )

    elif cmd == "rem":
        if len(args) < 3:
            await update.message.reply_text(
                "❌ Uso: /perfil rem &lt;tipo&gt; &lt;valor&gt;\n" "Tipos: interesse, ignorar, vip",
                parse_mode="HTML",
            )
            return

        tipo = args[1].lower()
        valor = " ".join(args[2:])

        if tipo == "interesse":
            encontrado = None
            for i in profile["interesses_primarios"]:
                if valor.lower() in i.lower():
                    encontrado = i
                    break
            if encontrado:
                profile["interesses_primarios"].remove(encontrado)
                save_profile(profile)
                await update.message.reply_text(
                    f"✅ Removido dos seus interesses: <b>{encontrado}</b>", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"❌ Interesse não encontrado: {valor}", parse_mode="HTML"
                )

        elif tipo == "ignorar":
            encontrado = None
            for i in profile["ignorar_sempre"]:
                if valor.lower() in i.lower():
                    encontrado = i
                    break
            if encontrado:
                profile["ignorar_sempre"].remove(encontrado)
                save_profile(profile)
                await update.message.reply_text(
                    f"✅ Removido da sua lista de ignorar: <b>{encontrado}</b>", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"❌ Palavra-chave não encontrada: {valor}", parse_mode="HTML"
                )

        elif tipo == "vip":
            encontrado = None
            for i in profile["fontes_vip"]:
                if valor.lower() in i.lower():
                    encontrado = i
                    break
            if encontrado:
                profile["fontes_vip"].remove(encontrado)
                save_profile(profile)
                await update.message.reply_text(
                    f"✅ Removido das suas fontes VIP: <b>{encontrado}</b>", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"❌ Fonte VIP não encontrada: {valor}", parse_mode="HTML"
                )

    elif cmd == "set":
        if len(args) < 3:
            await update.message.reply_text(
                "❌ Uso: /perfil set &lt;tipo&gt; &lt;valor&gt;\n"
                "Tipos: score (0-10), cards (1-20)",
                parse_mode="HTML",
            )
            return

        tipo = args[1].lower()
        try:
            valor = int(args[2])
        except ValueError:
            await update.message.reply_text("❌ Valor deve ser um número.", parse_mode="HTML")
            return

        if tipo == "score":
            if 0 <= valor <= 10:
                profile["score_minimo_enviar"] = valor
                save_profile(profile)
                await update.message.reply_text(
                    f"✅ Score mínimo alterado para <b>{valor}/10</b>\n"
                    f"<i>Notícias com score abaixo de {valor} não serão enviadas.</i>",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(
                    "❌ Score deve estar entre 0 e 10.", parse_mode="HTML"
                )

        elif tipo == "cards":
            if 1 <= valor <= 20:
                profile["max_cards_por_comando"] = valor
                save_profile(profile)
                await update.message.reply_text(
                    f"✅ Máx. cards por comando alterado para <b>{valor}</b>", parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    "❌ Número de cards deve estar entre 1 e 20.", parse_mode="HTML"
                )

    else:
        text = format_help()
        await update.message.reply_text(text, parse_mode="HTML")


async def cmd_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Uso: /url https://site.com/artigo")
        return

    url = args[0]
    await update.message.reply_text(
        f"⏳ Gerando episódio a partir de:\n{url}\n\nAguarde alguns minutos..."
    )

    proc = _run_main_py([f"url:{url}"])
    items = await _wait_and_collect(proc, [])

    if not items:
        # Tenta coletar qualquer episódio novo
        items = _collect_from_episode_json([])

    if not items:
        await update.message.reply_text(
            "⚠️ Nenhum conteúdo gerado. Verifique se a URL é acessível."
        )  # noqa: E501
        return

    record_command_usage("/url")
    await _send_items(context.bot, update.effective_chat.id, items[:3])


async def cmd_generate(
    update: Update, context: ContextTypes.DEFAULT_TYPE, sources: list, label: str, cmd_key: str = ""
):
    """Handler genérico para comandos de geração."""
    chat_id = update.effective_chat.id
    state = load_state()
    state["chat_id"] = chat_id
    save_state(state)

    record_command_usage(cmd_key if cmd_key else f"/{sources[0]}" if sources else "/unknown")

    await update.message.reply_text(
        f"⏳ Gerando <b>{label}</b>...\nAguarde alguns minutos.",
        parse_mode="HTML",
    )

    proc = _run_main_py(sources)
    items = await _wait_and_collect(proc, sources, timeout=360)

    # Adiciona vídeos YouTube relacionados ao tema
    yt_items = _fetch_youtube_for_cmd(cmd_key)
    if yt_items:
        items.extend(yt_items)
        logger.info(f"[youtube] {len(yt_items)} vídeos adicionados via keyword")

    if not items:
        await update.message.reply_text(
            f"⚠️ Nenhum conteúdo encontrado para <b>{label}</b>.\n"
            "Tente novamente em alguns instantes.",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(
        f"✅ <b>{label}</b> — {len(items)} item(s) encontrado(s)",
        parse_mode="HTML",
    )
    await _send_items(context.bot, chat_id, items, cmd_key)


def _build_feedback_keyboard(item: dict) -> InlineKeyboardMarkup:
    """Monta teclado inline com botões de feedback (👍/👎) para um item."""
    source_name = str(item.get("source_name", ""))
    source_id = str(item.get("source_id", ""))
    title = str(item.get("title", ""))
    score = int(item.get("_score", 5))

    h = hashlib.md5(f"{source_name}{title}".encode()).hexdigest()[:8]
    src_short = source_name.replace(" ", "")[:10]
    sid_short = source_id[:8]

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👍 Relevante", callback_data=f"fb:+1:{h}:{src_short}:{sid_short}:{score}"
                ),
                InlineKeyboardButton(
                    "👎 Não curto", callback_data=f"fb:-1:{h}:{src_short}:{sid_short}:{score}"
                ),
            ]
        ]
    )


def _apply_quotas(items: list, cmd_key: str) -> list:
    """Aplica limites de quota (por fonte e total) configurados para o comando."""
    quotas = load_quotas(cmd_key)
    if not quotas:
        return items

    max_por_fonte = quotas.get("max_por_fonte")
    max_total = quotas.get("max_total")

    result = []
    per_source_count = {}

    for item in items:
        if max_total is not None and len(result) >= max_total:
            break

        source_name = item.get("source_name", "")
        if max_por_fonte is not None:
            count = per_source_count.get(source_name, 0)
            if count >= max_por_fonte:
                continue
            per_source_count[source_name] = count + 1

        result.append(item)

    return result


async def _send_items(bot, chat_id: int, items: list, cmd_key: str = ""):
    """Enriquece, deduplica, filtra por perfil e envia lista de items."""
    state = load_state()
    sent_ids = set(state.get("sent_item_ids", []))
    max_items = state["config"].get("max_items_per_category", MAX_ITEMS_PER_CATEGORY)

    # Enriquece
    enriched_items = []
    for item in items:
        try:
            enriched = enrich_item(item)
            enriched_items.append(enriched)
        except Exception as e:
            logger.warning(f"[enrich] erro: {e}")
            item["_score"] = score_item(item)
            item["_image_url"] = None
            enriched_items.append(item)

    # Deduplica e ordena por score
    enriched_items = deduplicate(enriched_items)
    enriched_items.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # Filtra por perfil de interesses
    profile = load_profile()
    enriched_items = filter_and_score_items(enriched_items, profile)

    # Aplica quotas do comando (se configuradas)
    enriched_items = _apply_quotas(enriched_items, cmd_key)

    # Envia
    sent = 0
    audio_sent = False
    last_audio_path = None

    for enriched in enriched_items[: max_items * 3]:
        ih = item_hash(enriched)
        try:
            keyboard = _build_feedback_keyboard(enriched)
            await send_item_card(bot, chat_id, enriched, enriched, reply_markup=keyboard)
            sent_ids.add(ih)
            sent += 1

            # Guarda o último mp3 disponível para oferecer
            if enriched.get("_audio_path") and not audio_sent:
                last_audio_path = enriched["_audio_path"]

        except Exception as e:
            logger.error(f"[send_items] erro: {e}")

    # Botão para ouvir MP3 se disponível
    if last_audio_path and os.path.exists(last_audio_path):
        folder = os.path.basename(os.path.dirname(last_audio_path))
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🎵 Ouvir episódio completo", callback_data=f"play:{folder}")]]
        )
        await bot.send_message(
            chat_id=chat_id,
            text=f"🎧 <b>{sent} item(s) enviado(s)</b>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    # Salva IDs enviados
    state["sent_item_ids"] = list(sent_ids)
    save_state(state)


# ── Briefing matinal ──────────────────────────────────────────────────────────


async def send_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    """Enviado automaticamente às 07:00."""
    state = load_state()
    chat_id = state.get("chat_id")
    if not chat_id:
        logger.warning("[briefing] chat_id não configurado. Envie /start ao bot.")
        return

    logger.info("[briefing] iniciando briefing matinal...")

    # Sincroniza sinais do YouTube uma vez por dia (curtidos/histórico)
    try:
        adaptive_state = load_adaptive_state()
        today_str = datetime.now().strftime("%Y-%m-%d")
        if adaptive_state.get("last_youtube_sync") != today_str:
            from googleapiclient.discovery import build

            from src.auth import get_youtube_credentials

            creds = get_youtube_credentials()
            if creds:
                yt_service = build("youtube", "v3", credentials=creds)
                vector = sync_youtube_signals(yt_service)
                if vector:
                    adaptive_state["youtube_interest_vector"] = vector
                adaptive_state["last_youtube_sync"] = today_str
                adaptive_state["signal_weights"] = calculate_dynamic_weights(adaptive_state)
                save_adaptive_state(adaptive_state)
                logger.info("[briefing] sinais do YouTube sincronizados")
    except Exception as e:
        logger.warning(f"[briefing] sincronização YouTube falhou: {e}")

    # Gera conteúdo
    proc = _run_main_py(BRIEFING_SOURCES)

    # Envia header enquanto gera (clima/cotação/versículo nunca bloqueiam o
    # briefing — qualquer falha já é tratada dentro de cada função, retornando
    # string vazia, e send_briefing_header simplesmente omite a linha)
    weather_text = get_weather_summary()
    finance_text = get_exchange_rate()
    verse_text = format_verse_of_day()
    await send_briefing_header(
        context.bot, chat_id, weather_text=weather_text, finance_text=finance_text, verse=verse_text
    )

    # Aguarda geração
    items = await _wait_and_collect(proc, BRIEFING_SOURCES, timeout=600)

    if not items:
        await send_text(
            context.bot,
            chat_id,
            "⚠️ Nenhum conteúdo gerado no briefing matinal. Verifique os logs.",
        )
        return

    # Agrupa por source_id
    by_source = {}
    for item in items:
        sid = item.get("source_id", "outros")
        by_source.setdefault(sid, []).append(item)

    # Envia por seção
    max_items = state["config"].get("max_items_per_category", MAX_ITEMS_PER_CATEGORY)
    for source_id, source_items in by_source.items():
        await send_section_header(context.bot, chat_id, source_id)

        enriched_list = [enrich_item(i) for i in source_items]
        enriched_list = deduplicate(enriched_list)
        enriched_list.sort(key=lambda x: x.get("_score", 0), reverse=True)

        for enriched in enriched_list[:max_items]:
            keyboard = _build_feedback_keyboard(enriched)
            await send_item_card(context.bot, chat_id, enriched, enriched, reply_markup=keyboard)

    # Atualiza last_briefing
    state["last_briefing"] = datetime.now().isoformat()
    save_state(state)

    await send_text(
        context.bot,
        chat_id,
        "━" * 20 + "\n☀️ <b>Bom dia! Esse foi seu briefing matinal.</b>",
        parse_mode="HTML",
    )

    logger.info("[briefing] concluído.")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _set_env_chat_id(chat_id: int):
    """Atualiza TELEGRAM_CHAT_ID no .env se ainda não estiver preenchido."""
    env_path = ".env"
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        if f"TELEGRAM_CHAT_ID={chat_id}" in content:
            return
        if "TELEGRAM_CHAT_ID=" in content:
            import re

            content = re.sub(r"TELEGRAM_CHAT_ID=.*", f"TELEGRAM_CHAT_ID={chat_id}", content)
        else:
            content += f"\nTELEGRAM_CHAT_ID={chat_id}\n"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[env] TELEGRAM_CHAT_ID={chat_id} salvo no .env")
    except Exception as e:
        logger.warning(f"[env] não foi possível salvar chat_id: {e}")


def _make_command_handler(sources, label, cmd_key=""):
    """Factory para handlers de comandos de geração."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await cmd_generate(update, context, sources, label, cmd_key)

    return handler


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN não configurado no .env")
        print("   Adicione: TELEGRAM_BOT_TOKEN=seu_token")
        sys.exit(1)

    print("🤖 RadioIA Telegram Bot iniciando...")
    print(f"⏰ Briefing automático: {BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d} (horário local)")

    state = load_state()
    if state.get("chat_id"):
        print(f'💬 Chat ID registrado: {state["chat_id"]}')
    else:
        print("💬 Chat ID não registrado. Envie /start ao bot @radiobootbot")

    app = Application.builder().token(BOT_TOKEN).build()

    # Comandos estáticos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("historico", cmd_historico))
    app.add_handler(CommandHandler("perfil", cmd_perfil))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("aprendizado", cmd_aprendizado))
    app.add_handler(CommandHandler("analise", cmd_analise))
    app.add_handler(CommandHandler("sincronia", cmd_sincronia))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("resumo", cmd_resumo))

    # Comandos de geração dinâmicos
    for cmd, sources in COMMANDS.items():
        label = cmd.replace("/", "").capitalize()
        app.add_handler(
            CommandHandler(cmd.replace("/", ""), _make_command_handler(sources, label, cmd))
        )

    # Callback para botões inline
    app.add_handler(CallbackQueryHandler(callback_play, pattern="^play:"))
    app.add_handler(CallbackQueryHandler(callback_feedback, pattern="^fb:"))

    # Agendamento do briefing matinal
    job_queue = app.job_queue
    job_queue.run_daily(
        send_morning_briefing,
        time=dt_time(BRIEFING_HOUR, BRIEFING_MINUTE, 0, tzinfo=BRIEFING_TZ),
        name="briefing_matinal",
    )

    # Agendamento da análise semanal de aprendizado (run_weekly removido no PTB v20+)
    _now = datetime.now(timezone.utc)
    _days_to_sunday = (6 - _now.weekday()) % 7
    _next_sunday = _now.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(
        days=_days_to_sunday
    )
    if _next_sunday <= _now:
        _next_sunday += timedelta(weeks=1)
    job_queue.run_repeating(
        weekly_analysis_job,
        interval=timedelta(weeks=1),
        first=_next_sunday,
        name="analise_semanal",
    )

    print("✅ Bot rodando. Pressione Ctrl+C para parar.\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
