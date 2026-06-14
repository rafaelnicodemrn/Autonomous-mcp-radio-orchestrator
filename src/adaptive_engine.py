# src/adaptive_engine.py
# Motor de aprendizado adaptativo do RadioIA Telegram Bot
import copy
import json
import logging
import os
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# Arquivo de estado fica na raiz do projeto, junto com config.yaml
STATE_FILE = "adaptive_state.json"

MAX_FEEDBACK_HISTORY = 500
MAX_ADJUSTMENTS_LOG = 20
FEEDBACK_WINDOW_DAYS = 30

DEFAULT_STATE = {
    # Reputação de fontes (Opção 2)
    "source_reputation": {},
    # Ex: {"Vatican News": {"total_score": 248, "count": 31, "avg": 8.0,
    #      "last_updated": "2026-06-13"}}
    # Histórico de feedback do Telegram (Opção 1)
    "feedback_history": [],
    # Ex: [{"item_hash": "abc123", "source_name": "Vatican News", "source_id": "catolicismo",
    #        "gemini_score": 8, "feedback": "+1", "date": "2026-06-13T10:30:00"}]
    # Vetor de interesses derivado do YouTube (Opção 8)
    "youtube_interest_vector": {},
    # Ex: {"catolicismo": 0.85, "tecnologia": 0.72, "futebol": 0.61}
    # Padrão de uso dos comandos
    "command_usage": {},
    # Ex: {"/fe": 12, "/tech": 8, "/gremio": 15, "/briefing": 6}
    # Pesos dinâmicos atuais (Opção 3)
    "signal_weights": {
        "llm": 0.70,
        "reputation": 0.00,
        "recency": 0.30,
        "feedback": 0.00,
        "youtube": 0.00,
    },
    # Metadados
    "last_youtube_sync": None,
    "last_auto_analysis": None,
    "total_items_processed": 0,
    "total_feedback_given": 0,
    # Ajustes automáticos aplicados pela IA
    "auto_adjustments_log": [],
}

_MESES_PT = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}


# ── Estado persistente ────────────────────────────────────────────────────────


def load_state() -> dict:
    """Carrega adaptive_state.json. Se não existir, cria com o estado padrão."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            # Completa campos faltantes (compatibilidade com versões antigas do arquivo)
            for key, default_value in DEFAULT_STATE.items():
                if key not in state:
                    state[key] = copy.deepcopy(default_value)
            return state
        except Exception as e:
            logger.warning(f"[adaptive_engine] erro ao ler estado: {e}")

    state = copy.deepcopy(DEFAULT_STATE)
    save_state(state)
    return state


def save_state(state: dict):
    """Salva o estado adaptativo em disco."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[adaptive_engine] erro ao salvar estado: {e}")


# ── Feedback e reputação ─────────────────────────────────────────────────────


def update_source_reputation(source_name: str, score: int, state: dict = None) -> dict:
    """
    Atualiza a reputação (média móvel) de uma fonte.
    Se `state` não for passado, carrega e salva o estado isoladamente.
    """
    standalone = state is None
    if standalone:
        state = load_state()

    reputation = state.setdefault("source_reputation", {})
    entry = reputation.get(
        source_name,
        {
            "total_score": 0,
            "count": 0,
            "avg": 5.0,
            "last_updated": None,
        },
    )

    old_avg = entry.get("avg", 5.0)
    count = entry.get("count", 0)
    new_avg = (old_avg * count + score) / (count + 1)

    entry["total_score"] = entry.get("total_score", 0) + score
    entry["count"] = count + 1
    entry["avg"] = round(new_avg, 2)
    entry["last_updated"] = date.today().isoformat()
    reputation[source_name] = entry

    if standalone:
        save_state(state)
    return state


def record_feedback(
    item_hash: str, source_name: str, source_id: str, gemini_score: int, feedback: str
):
    """Registra feedback do usuário (+1/-1), atualiza reputação e pesos."""
    state = load_state()

    entry = {
        "item_hash": item_hash,
        "source_name": source_name,
        "source_id": source_id,
        "gemini_score": gemini_score,
        "feedback": feedback,
        "date": datetime.now().isoformat(),
    }

    history = state.setdefault("feedback_history", [])
    history.append(entry)
    if len(history) > MAX_FEEDBACK_HISTORY:
        state["feedback_history"] = history[-MAX_FEEDBACK_HISTORY:]

    state["total_feedback_given"] = state.get("total_feedback_given", 0) + 1

    update_source_reputation(source_name, gemini_score, state)
    state["signal_weights"] = calculate_dynamic_weights(state)

    save_state(state)


def record_command_usage(command: str):
    """Incrementa o contador de uso de um comando."""
    state = load_state()
    usage = state.setdefault("command_usage", {})
    usage[command] = usage.get(command, 0) + 1
    save_state(state)


# ── Pesos dinâmicos ──────────────────────────────────────────────────────────


def calculate_dynamic_weights(state: dict) -> dict:
    """
    Calcula pesos dinamicamente baseado nos sinais disponíveis.
    Sinais ausentes têm peso 0, os demais são redistribuídos.
    """
    feedback_count = len(state.get("feedback_history", []))
    reputation_count = len(state.get("source_reputation", {}))
    youtube_count = len(state.get("youtube_interest_vector", {}))

    # Determina quais sinais estão disponíveis
    tem_feedback = feedback_count >= 5  # pelo menos 5 feedbacks
    tem_reputacao = reputation_count >= 3  # pelo menos 3 fontes avaliadas
    tem_youtube = youtube_count >= 3  # pelo menos 3 interesses do YouTube

    # Configura pesos baseado no que está disponível
    if tem_feedback and tem_reputacao and tem_youtube:
        return {"llm": 0.35, "reputation": 0.20, "recency": 0.15, "feedback": 0.20, "youtube": 0.10}
    elif tem_feedback and tem_reputacao:
        return {"llm": 0.40, "reputation": 0.25, "recency": 0.20, "feedback": 0.15, "youtube": 0.00}
    elif tem_reputacao and tem_youtube:
        return {"llm": 0.45, "reputation": 0.25, "recency": 0.20, "feedback": 0.00, "youtube": 0.10}
    elif tem_reputacao:
        return {"llm": 0.55, "reputation": 0.25, "recency": 0.20, "feedback": 0.00, "youtube": 0.00}
    else:
        # Estado inicial: só LLM e recência
        return {"llm": 0.70, "reputation": 0.00, "recency": 0.30, "feedback": 0.00, "youtube": 0.00}


# ── Score adaptativo ──────────────────────────────────────────────────────────


def _calc_recency(published_at: str) -> float:
    """Hoje = 10, ontem = 7, 2 dias = 5, 3+ dias = 2. Sem data válida = 5."""
    if not published_at:
        return 5.0
    try:
        pub_date = datetime.fromisoformat(str(published_at)[:10]).date()
        delta = (date.today() - pub_date).days
        if delta <= 0:
            return 10.0
        elif delta == 1:
            return 7.0
        elif delta == 2:
            return 5.0
        else:
            return 2.0
    except Exception:
        return 5.0


def _calc_feedback_score(source_name: str, state: dict) -> float:
    """
    Calcula score de feedback (0-10) para uma fonte com base nos
    feedbacks dos últimos 30 dias. Neutro = 5, sem dados = 5.
    """
    history = state.get("feedback_history", [])
    if not history:
        return 5.0

    cutoff = datetime.now() - timedelta(days=FEEDBACK_WINDOW_DAYS)
    relevant = []
    for f in history:
        if f.get("source_name") != source_name:
            continue
        try:
            f_date = datetime.fromisoformat(f.get("date", ""))
        except Exception:
            continue
        if f_date >= cutoff:
            relevant.append(f)

    if not relevant:
        return 5.0

    total = 0
    for f in relevant:
        if f.get("feedback") == "+1":
            total += 1
        elif f.get("feedback") == "-1":
            total -= 1

    ratio = total / len(relevant)  # entre -1 e 1
    score = 5 + ratio * 5
    return round(min(max(score, 0.0), 10.0), 1)


def _calc_youtube_alignment(item: dict, state: dict) -> float:
    """
    Verifica alinhamento do item com o vetor de interesses do YouTube.
    Vetor vazio = 5 (neutro). Sem correspondências = 0.
    """
    vector = state.get("youtube_interest_vector", {})
    if not vector:
        return 5.0

    text = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("source_name", "")),
        ]
    ).lower()

    matched_weights = [
        weight for interest, weight in vector.items() if str(interest).lower() in text
    ]

    if not matched_weights:
        return 0.0

    avg_weight = sum(matched_weights) / len(matched_weights)
    return round(min(max(avg_weight * 10, 0.0), 10.0), 1)


def compute_adaptive_score(item: dict, gemini_score: int, state: dict) -> float:
    """Calcula score final ponderado com todos os sinais disponíveis."""
    weights = state.get("signal_weights", {"llm": 0.70, "recency": 0.30})

    llm_score = gemini_score

    source_name = item.get("source_name", "")
    reputation = state.get("source_reputation", {})
    source_avg = reputation.get(source_name, {}).get("avg", 5.0)

    recency_score = _calc_recency(item.get("published_at", ""))
    feedback_score = _calc_feedback_score(source_name, state)
    youtube_score = _calc_youtube_alignment(item, state)

    final = (
        weights.get("llm", 0.70) * llm_score
        + weights.get("reputation", 0.00) * source_avg
        + weights.get("recency", 0.30) * recency_score
        + weights.get("feedback", 0.00) * feedback_score
        + weights.get("youtube", 0.00) * youtube_score
    )

    return min(max(round(final, 1), 0.0), 10.0)


# ── Sincronização de sinais do YouTube ────────────────────────────────────────


def sync_youtube_signals(youtube_service) -> dict:
    """
    Busca vídeos curtidos e histórico do YouTube para extrair padrões de interesse.
    Usa Gemini para analisar e gerar vetor de interesses.
    Retorna vetor atualizado ou {} se falhar.
    """
    liked_videos = []
    channel_resp = {}

    try:
        # 1. Buscar playlist de liked videos
        channel_resp = (
            youtube_service.channels()
            .list(
                part="contentDetails",
                mine=True,
            )
            .execute()
        )

        liked_playlist_id = (
            channel_resp.get("items", [{}])[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("likes", "")
        )

        if liked_playlist_id:
            items_resp = (
                youtube_service.playlistItems()
                .list(
                    part="snippet",
                    playlistId=liked_playlist_id,
                    maxResults=30,
                )
                .execute()
            )

            for item in items_resp.get("items", []):
                snippet = item.get("snippet", {})
                liked_videos.append(
                    {
                        "title": snippet.get("title", ""),
                        "channel": snippet.get("videoOwnerChannelTitle", ""),
                    }
                )

    except Exception as e:
        logger.warning(f"[youtube_sync] liked videos falhou: {e}")

    # Tenta watch history (pode falhar por privacidade)
    try:
        watch_history_id = (
            channel_resp.get("items", [{}])[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("watchHistory", "")
        )
        if watch_history_id:
            hist_resp = (
                youtube_service.playlistItems()
                .list(
                    part="snippet",
                    playlistId=watch_history_id,
                    maxResults=20,
                )
                .execute()
            )
            for item in hist_resp.get("items", []):
                snippet = item.get("snippet", {})
                liked_videos.append(
                    {
                        "title": snippet.get("title", ""),
                        "channel": snippet.get("videoOwnerChannelTitle", ""),
                    }
                )
    except Exception as e:
        logger.debug(f"[youtube_sync] watch history indisponível: {e}")

    if not liked_videos:
        return {}

    # Usar Gemini para analisar padrões
    try:
        import re

        from dotenv import load_dotenv

        from content_enricher import _gemini_call_with_retry

        load_dotenv()

        titulos_list = [f"- [{v['channel']}] {v['title']}" for v in liked_videos[:30]]
        titulos = "\n".join(titulos_list)

        prompt = (
            "Analise estes vídeos curtidos/assistidos pelo usuário e identifique "
            "seus principais interesses com scores de 0.0 a 1.0.\n"
            "Responda APENAS com JSON. Exemplo:\n"
            '{"catolicismo": 0.85, "tecnologia": 0.72, "futebol": 0.61}\n\n'
            f"Vídeos:\n{titulos}"
        )

        raw = _gemini_call_with_retry(
            prompt,
            os.getenv("TELEGRAM_LLM_MODEL", "gemini/gemini-2.5-flash-lite"),
            300,
        )
        raw = raw.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            vector = json.loads(match.group())
            logger.info(f"[youtube_sync] vetor extraído: {vector}")
            return {k: float(v) for k, v in vector.items()}

    except Exception as e:
        logger.warning(f"[youtube_sync] análise Gemini falhou: {e}")

    return {}


# ── Análise semanal ────────────────────────────────────────────────────────────


def run_weekly_analysis(state: dict) -> str:
    """
    Gemini analisa todos os dados acumulados e gera relatório de aprendizado.
    Retorna texto do relatório para enviar ao usuário.
    """
    feedback = state.get("feedback_history", [])
    reputation = state.get("source_reputation", {})
    usage = state.get("command_usage", {})
    weights = state.get("signal_weights", {})

    if len(feedback) < 3 and not reputation:
        return "Ainda sem dados suficientes para análise. Continue usando o bot!"

    top_sources = sorted(reputation.items(), key=lambda x: x[1].get("avg", 0), reverse=True)[:5]
    bottom_sources = sorted(reputation.items(), key=lambda x: x[1].get("avg", 0))[:3]
    positive_fb = [f for f in feedback if f.get("feedback") == "+1"]
    negative_fb = [f for f in feedback if f.get("feedback") == "-1"]
    top_commands = sorted(usage.items(), key=lambda x: x[1], reverse=True)[:5]

    top_sources_names = [s[0] for s in top_sources]
    bottom_sources_names = [s[0] for s in bottom_sources]

    prompt = (
        "Você é o motor de aprendizado da RadioIA. Analise os dados abaixo e gere "
        "um relatório em português com insights e recomendações.\n\n"
        "Dados (últimos 30 dias):\n"
        f"- Feedbacks positivos: {len(positive_fb)}\n"
        f"- Feedbacks negativos: {len(negative_fb)}\n"
        f"- Melhores fontes: {top_sources_names}\n"
        f"- Piores fontes: {bottom_sources_names}\n"
        f"- Comandos mais usados: {top_commands}\n"
        f"- Pesos atuais: {weights}\n\n"
        "Gere um relatório curto (máximo 10 linhas) com:\n"
        "1. O que o usuário mais gosta\n"
        "2. O que deve ser reduzido\n"
        "3. Uma sugestão de ajuste automático\n"
        "Use emojis e seja direto."
    )

    try:
        from dotenv import load_dotenv

        from content_enricher import _gemini_call_with_retry

        load_dotenv()

        report = _gemini_call_with_retry(
            prompt,
            os.getenv("TELEGRAM_LLM_MODEL", "gemini/gemini-2.5-flash-lite"),
            400,
        )

        state["last_auto_analysis"] = datetime.now().isoformat()
        adjustments = state.setdefault("auto_adjustments_log", [])
        adjustments.append(
            {
                "date": state["last_auto_analysis"],
                "report_preview": report[:100],
            }
        )
        if len(adjustments) > MAX_ADJUSTMENTS_LOG:
            state["auto_adjustments_log"] = adjustments[-MAX_ADJUSTMENTS_LOG:]
        save_state(state)

        return report

    except Exception as e:
        return f"Erro na análise: {e}"


# ── Formatação ─────────────────────────────────────────────────────────────────


def _format_date_pt(iso_str) -> str:
    if not iso_str:
        return "nunca"
    try:
        dt = datetime.fromisoformat(iso_str)
        mes = _MESES_PT.get(dt.month, "")
        return f"{dt.day:02d} {mes} {dt.year}"
    except Exception:
        return "nunca"


def format_learning_status(state: dict) -> str:
    """Formata o estado atual do aprendizado para o comando /aprendizado."""
    feedback_history = state.get("feedback_history", [])
    positivos = sum(1 for f in feedback_history if f.get("feedback") == "+1")
    negativos = sum(1 for f in feedback_history if f.get("feedback") == "-1")

    reputation = state.get("source_reputation", {})
    youtube_vector = state.get("youtube_interest_vector", {})
    command_usage = state.get("command_usage", {})
    weights = state.get("signal_weights", {})
    total_comandos = sum(command_usage.values())

    lines = [
        "🧠 <b>Status de Aprendizado — RadioIA</b>\n",
        "📊 <b>Dados acumulados:</b>",
        f"• Feedbacks dados: {len(feedback_history)} ({positivos} 👍 / {negativos} 👎)",
        f"• Fontes avaliadas: {len(reputation)}",
        f"• Interesses mapeados (YouTube): {len(youtube_vector)}",
        f"• Comandos usados: {total_comandos}",
    ]

    if reputation:
        ranked = sorted(reputation.items(), key=lambda x: x[1].get("avg", 0), reverse=True)
        top = ranked[:3]
        worst = [s for s in ranked[::-1][:3] if s[1].get("avg", 0) < 5]

        lines.append("")
        lines.append("⭐ <b>Melhores fontes (por você):</b>")
        for nome, dados in top:
            avg = dados.get("avg", 0)
            lines.append(f"• {nome} — {avg:.1f}/10")

        if worst:
            lines.append("")
            lines.append("⚠️ <b>Fontes com baixo desempenho:</b>")
            for nome, dados in worst:
                avg = dados.get("avg", 0)
                lines.append(f"• {nome} — {avg:.1f}/10")

    lines.append("")
    lines.append("⚙️ <b>Pesos ativos:</b>")
    llm_pct = round(weights.get("llm", 0.70) * 100)
    rep_pct = round(weights.get("reputation", 0.00) * 100)
    rec_pct = round(weights.get("recency", 0.30) * 100)
    fb_pct = round(weights.get("feedback", 0.00) * 100)
    yt_pct = round(weights.get("youtube", 0.00) * 100)

    lines.append(f"• LLM: {llm_pct}% | Reputação: {rep_pct}% | Recência: {rec_pct}%")

    sufixo = ""
    if rep_pct > 0 and fb_pct > 0 and yt_pct > 0:
        sufixo = " (TODOS ATIVOS)"
    lines.append(f"• Feedback: {fb_pct}% | YouTube: {yt_pct}%{sufixo}")

    lines.append("")
    data_analise = _format_date_pt(state.get("last_auto_analysis"))
    lines.append(f"📅 Última análise automática: {data_analise}")

    return "\n".join(lines)
