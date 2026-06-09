"""
RadioIA MCP Server
Expoe ferramentas para que agentes de IA gerem e gerenciem episodios de radio.
"""

import contextlib
import io
import json
import os
import shutil
import sys
from datetime import datetime, date, timedelta

# Setup: project dir e path antes de qualquer import local
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

import nest_asyncio
nest_asyncio.apply()  # permite asyncio.run() aninhado dentro do loop do MCP

import yaml
from mcp.server.fastmcp import FastMCP

import main as radio_main
from src.history import load_seen_ids

mcp = FastMCP("RadioIA")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    with open(os.path.join(PROJECT_DIR, 'config.yaml'), 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _save_config(config: dict) -> None:
    """Salva config.yaml. Observacao: comentarios no arquivo serao perdidos apos salvar."""
    config_path = os.path.join(PROJECT_DIR, 'config.yaml')
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, indent=2)


def _capture(func, *args, **kwargs):
    """Executa func capturando stdout. Retorna (resultado, log)."""
    buf = io.StringIO()
    result = None
    error = None
    try:
        with contextlib.redirect_stdout(buf):
            result = func(*args, **kwargs)
    except Exception as e:
        error = str(e)
        buf.write(f"\nERRO: {e}")
    return result, buf.getvalue(), error


def _parse_fonte(arg: str) -> tuple[str, str | None]:
    """'musica:3' -> ('musica', '3') | 'youtube' -> ('youtube', None)"""
    if ':' in arg:
        sid, param = arg.split(':', 1)
        return sid.strip(), param.strip()
    return arg.strip(), None


def _fonte_info(s: dict, seen_ids: set) -> dict:
    return {
        'id':          s['id'],
        'nome':        s['name'],
        'tipo':        s['type'],
        'habilitada':  s.get('enabled', True),
    }


def _has_audio(ep_path: str) -> bool:
    """Verifica se a pasta tem episódio (mp3 direto ou replay via audio_path)."""
    if os.path.exists(os.path.join(ep_path, 'episode.mp3')):
        return True
    meta_path = os.path.join(ep_path, 'episode.json')
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return bool(json.load(f).get('audio_path'))
        except Exception:
            pass
    return False


def _scan_day(date_str: str) -> list[dict]:
    day_dir = os.path.join(PROJECT_DIR, 'output', date_str)
    episodes = []
    if not os.path.isdir(day_dir):
        return episodes
    for ep_folder in sorted(os.listdir(day_dir)):
        ep_path = os.path.join(day_dir, ep_folder)
        if not os.path.isdir(ep_path) or not _has_audio(ep_path):
            continue
        meta = {}
        meta_path = os.path.join(ep_path, 'episode.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        parts = ep_folder.split('_', 1)
        ep = {
            'pasta':       ep_folder,
            'horario':     parts[0],
            'fonte':       parts[1] if len(parts) > 1 else ep_folder,
            'nome':        meta.get('source_name', ''),
            'duracao_seg': meta.get('duration_seconds', 0),
            'itens':       meta.get('videos_covered', 0),
            'arquivo':     os.path.join(day_dir, ep_folder, 'episode.mp3'),
        }
        if meta.get('replay_of'):
            ep['replay_de'] = meta['replay_of']
        episodes.append(ep)
    return episodes


def _schedule_entry_key(entry: dict) -> str:
    """Chave unica de uma entrada da grade (espelha logica do scheduler.py)."""
    d    = entry.get('date', 'daily')
    t    = entry.get('time', '')
    days = ','.join(sorted(str(x) for x in entry.get('days', [])))
    if entry.get('replay_of') is not None:
        s = f"replay:{entry['replay_of']}"
    else:
        s = '+'.join(sorted(str(x) for x in entry.get('sources', [])))
    return f"{d}|{t}|{s}|{days}"


def _parse_value(s: str):
    """Converte string para bool, int, float ou mantém como str."""
    if isinstance(s, bool):
        return s
    if not isinstance(s, str):
        return s
    if s.lower() in ('true', 'yes', 'sim', '1'):
        return True
    if s.lower() in ('false', 'no', 'nao', 'não', '0'):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _set_nested(d: dict, keys: list[str], value):
    """Define d[k1][k2]...[kn] = value criando dicts intermediarios."""
    for key in keys[:-1]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


# ── Tools — Geração de conteúdo ───────────────────────────────────────────────

@mcp.tool()
def listar_fontes() -> str:
    """
    Lista todas as fontes de conteudo configuradas no RadioIA.
    Mostra id, nome, tipo, se esta habilitada e quantos itens ja foram citados no historico.
    """
    config   = _load_config()
    seen_ids = load_seen_ids()

    fontes = [_fonte_info(s, seen_ids) for s in config.get('sources', [])]

    history_path = os.path.join(PROJECT_DIR, 'history.json')
    episodios_gerados = 0
    if os.path.exists(history_path):
        with open(history_path, 'r', encoding='utf-8') as f:
            h = json.load(f)
        episodios_gerados = len(h.get('episodes', []))

    return json.dumps({
        'fontes': fontes,
        'historico': {
            'itens_ja_citados': len(seen_ids),
            'episodios_gerados': episodios_gerados,
        },
        'dica': 'Use gerar_episodios(["youtube", "musica:2", "noticias"]) para gerar episodios.'
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def gerar_episodios(fontes: list[str]) -> str:
    """
    Gera episodios de audio para as fontes especificadas.

    Args:
        fontes: Lista de IDs de fontes a gerar. Exemplos:
                ["youtube"] — so o feed do YouTube
                ["utilidades", "youtube", "noticias"] — grade completa
                ["musica:1"] — 1 musica
                ["musica:3"] — 3 musicas
                ["url:https://exemplo.com/artigo"] — episodio a partir de URL avulsa

    Fontes disponiveis: youtube, noticias, noticias-locais, tecnologia, horoscopo,
    utilidades, loteria, copa, brasileirao, champions, efemerides, quiz, reddit,
    receitas, filmes, filmes-cartaz, musica, musica-local, concursos, biblia.
    Para musica, use musica:N onde N e o numero de faixas (ex: musica:3).
    Para URL avulsa, use url:https://... — nao requer configuracao previa.
    """
    config      = _load_config()
    all_sources = config.get('sources', [])
    seen_ids    = load_seen_ids()
    credentials = radio_main._get_oauth_credentials()
    first_of_day = not radio_main._has_episodes_today()

    results  = []
    logs_all = []

    for arg in fontes:
        source_id, param = _parse_fonte(arg)

        # Fonte de URL avulsa: sintética, sem entrada no config
        if source_id == 'url' and param:
            source_cfg = {
                'id': 'url', 'type': 'url',
                'name': 'Conteudo da Web',
                'settings': {'url': param},
            }
        else:
            source_cfg = next((s for s in all_sources if s['id'] == source_id), None)
            if not source_cfg:
                results.append({'fonte': source_id, 'status': 'erro', 'mensagem': f"Fonte '{source_id}' nao encontrada."})
                continue

        source_type = source_cfg.get('type')

        # Aplicar override de param (ex: musica:3)
        if param and source_type == 'music':
            try:
                n = int(param)
                source_cfg = {**source_cfg, 'settings': {**source_cfg.get('settings', {}), 'num_tracks': n}}
            except ValueError:
                pass

        # Executar fonte com captura de stdout
        if source_type == 'music':
            path, log, err = _capture(radio_main._run_music_source, source_cfg, config, first_of_day)
        elif source_type == 'utility':
            path, log, err = _capture(radio_main._run_utility_source, source_cfg, config, first_of_day)
        else:
            path, log, err = _capture(radio_main._run_source, source_cfg, config, credentials, seen_ids, first_of_day)

        logs_all.append(f"[{source_id}]\n{log.strip()}")

        if path and os.path.exists(path):
            # Ler metadados do episodio gerado
            meta_path = os.path.join(os.path.dirname(path), 'episode.json')
            meta = {}
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)

            dur = meta.get('duration_seconds', 0)
            mins, secs = dur // 60, dur % 60
            results.append({
                'fonte':    source_id,
                'status':   'ok',
                'nome':     meta.get('source_name', source_id),
                'duracao':  f"{mins}m {secs}s",
                'itens':    meta.get('videos_covered', 0),
                'arquivo':  path,
            })
            first_of_day = False
            seen_ids = load_seen_ids()
        else:
            results.append({
                'fonte':    source_id,
                'status':   'erro',
                'mensagem': err or 'Nenhum episodio gerado.',
            })

    gerados = [r for r in results if r['status'] == 'ok']
    falhas  = [r for r in results if r['status'] == 'erro']

    return json.dumps({
        'resumo': {
            'gerados':    len(gerados),
            'falhas':     len(falhas),
            'player_url': 'http://localhost:5000',
        },
        'episodios': results,
        'log':       '\n\n'.join(logs_all),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def listar_episodios(data: str = '') -> str:
    """
    Lista os episodios gerados para uma data especifica.

    Args:
        data: Data no formato YYYY-MM-DD. Se vazio, usa a data de hoje.
    """
    if not data:
        data = datetime.now().strftime('%Y-%m-%d')

    episodes = _scan_day(data)

    if not episodes:
        output_dir = os.path.join(PROJECT_DIR, 'output')
        datas = []
        if os.path.exists(output_dir):
            datas = sorted([
                d for d in os.listdir(output_dir)
                if os.path.isdir(os.path.join(output_dir, d)) and d[:4].isdigit()
            ], reverse=True)
        return json.dumps({
            'data':     data,
            'episodios': [],
            'mensagem': f"Nenhum episodio encontrado para {data}.",
            'datas_disponiveis': datas[:10],
        }, ensure_ascii=False, indent=2)

    total_dur = sum(e['duracao_seg'] for e in episodes)
    mins, secs = total_dur // 60, total_dur % 60

    return json.dumps({
        'data':              data,
        'total_episodios':   len(episodes),
        'duracao_total':     f"{mins}m {secs}s",
        'player_url':        'http://localhost:5000',
        'episodios':         episodes,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def ler_episodio(pasta: str, data: str = '') -> str:
    """
    Le o conteudo completo de um episodio: roteiro (script.txt) e metadados (episode.json).
    Util para revisar o que foi gerado, verificar qualidade ou depurar problemas.

    Args:
        pasta: Nome ou prefixo parcial da pasta do episodio. Exemplos:
               "09-30_youtube"  — episodio exato
               "09-30"          — qualquer episodio das 09:30
               "youtube"        — qualquer episodio de youtube
               "noticias"       — qualquer episodio de noticias
        data: Data no formato YYYY-MM-DD. Se vazio, usa hoje.
    """
    if not data:
        data = datetime.now().strftime('%Y-%m-%d')

    day_dir = os.path.join(PROJECT_DIR, 'output', data)
    if not os.path.isdir(day_dir):
        return json.dumps({'status': 'erro', 'mensagem': f"Nenhum episodio encontrado para {data}."}, ensure_ascii=False)

    # Encontrar pasta que bate com o parcial
    candidatos = [
        f for f in sorted(os.listdir(day_dir))
        if pasta.lower() in f.lower() and os.path.isdir(os.path.join(day_dir, f))
    ]

    if not candidatos:
        return json.dumps({
            'status':   'erro',
            'mensagem': f"Nenhuma pasta com '{pasta}' em {data}.",
            'pastas_disponiveis': [
                f for f in sorted(os.listdir(day_dir))
                if os.path.isdir(os.path.join(day_dir, f))
            ],
        }, ensure_ascii=False, indent=2)

    resultados = []
    for folder in candidatos:
        ep_path = os.path.join(day_dir, folder)

        meta = {}
        meta_path = os.path.join(ep_path, 'episode.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

        script = ''
        script_path = os.path.join(ep_path, 'script.txt')
        if os.path.exists(script_path):
            with open(script_path, 'r', encoding='utf-8') as f:
                script = f.read()

        dur = meta.get('duration_seconds', 0)
        resultados.append({
            'pasta':    folder,
            'data':     data,
            'nome':     meta.get('source_name', ''),
            'duracao':  f"{dur // 60}m {dur % 60}s",
            'itens':    meta.get('videos_covered', 0),
            'metadados': meta,
            'script':   script,
        })

    if len(resultados) == 1:
        return json.dumps({'status': 'ok', **resultados[0]}, ensure_ascii=False, indent=2)

    return json.dumps({
        'status':     'ok',
        'encontrados': len(resultados),
        'episodios':  resultados,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def status_historico() -> str:
    """
    Mostra o status do historico de episodios gerados.
    O historico controla quais itens ja foram citados para evitar repeticao.
    """
    history_path = os.path.join(PROJECT_DIR, 'history.json')
    if not os.path.exists(history_path):
        return json.dumps({'itens_vistos': 0, 'episodios': 0, 'mensagem': 'Historico vazio.'}, ensure_ascii=False)

    with open(history_path, 'r', encoding='utf-8') as f:
        h = json.load(f)

    episodios = h.get('episodes', [])
    ultimo = episodios[-1] if episodios else None

    return json.dumps({
        'itens_vistos':    len(h.get('seen_ids', [])),
        'episodios_total': len(episodios),
        'ultimo_episodio': ultimo['episode_id'] if ultimo else None,
        'dica': 'Use limpar_historico() para resetar e permitir repeticao de conteudos.',
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def limpar_historico() -> str:
    """
    Limpa o historico de episodios gerados.
    Apos limpar, todos os conteudos ficam elegiveis novamente para novos episodios.
    """
    history_path = os.path.join(PROJECT_DIR, 'history.json')
    dados_anteriores = {'seen_ids': [], 'episodes': []}

    if os.path.exists(history_path):
        with open(history_path, 'r', encoding='utf-8') as f:
            dados_anteriores = json.load(f)

    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump({'seen_ids': [], 'episodes': []}, f, ensure_ascii=False, indent=2)

    return json.dumps({
        'status':           'ok',
        'itens_removidos':  len(dados_anteriores.get('seen_ids', [])),
        'episodios_removidos': len(dados_anteriores.get('episodes', [])),
        'mensagem':         'Historico limpo. Todos os conteudos estao elegiveis novamente.',
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def replay_episodio(parcial: str, data: str = '') -> str:
    """
    Cria um replay de episodios cujas pastas batem com o prefixo parcial.
    Nao regera o audio — apenas registra o episodio original no horario atual
    para que o player o exiba e reproduza.

    Args:
        parcial: Prefixo parcial do nome da pasta do episodio. Exemplos:
                 "12-15"       — todos os episodios gerados as 12:15
                 "12-15_not"   — episodio das 12:15 cuja pasta comeca com "12-15_not"
                 "noticias"    — qualquer episodio de noticias (sem filtro de horario)
        data: Data no formato YYYY-MM-DD. Se vazio, usa hoje.

    Equivalente a: python main.py replay:12-15_not
    """
    if not data:
        data = datetime.now().strftime('%Y-%m-%d')

    import contextlib, io as _io
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        paths = radio_main._run_replay_cli(parcial, today=data)
    log = buf.getvalue()

    if not paths:
        return json.dumps({
            'status':   'erro',
            'mensagem': f"Nenhum episodio encontrado com prefixo '{parcial}' em {data}.",
            'log':      log,
        }, ensure_ascii=False, indent=2)

    replays = []
    for p in paths:
        meta = {}
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        replays.append({
            'pasta':      os.path.basename(os.path.dirname(p)),
            'replay_de':  meta.get('replay_of', ''),
            'nome':       meta.get('source_name', ''),
        })

    return json.dumps({
        'status':          'ok',
        'data':            data,
        'replays_criados': len(replays),
        'replays':         replays,
        'player_url':      'http://localhost:5000',
        'log':             log,
    }, ensure_ascii=False, indent=2)


# ── Tools — Grade e configuração ──────────────────────────────────────────────

@mcp.tool()
def ver_grade() -> str:
    """
    Exibe a grade completa de programacao da radio.
    Mostra todos os horarios agendados, fontes, labels, slot_ids, replays e status de execucao.
    Util para entender o que esta programado e planejar adicoes ou remocoes.
    """
    config  = _load_config()
    entries = config.get('schedule', [])
    today   = datetime.now().strftime('%Y-%m-%d')
    now_time = datetime.now().strftime('%H:%M')

    state_path = os.path.join(PROJECT_DIR, 'scheduler_state.json')
    state = {}
    if os.path.exists(state_path):
        with open(state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)

    completed_today = set(state.get('completed_today', {}).keys())
    completed_once  = set(state.get('completed_once', []))

    grade = []
    proximo_idx = None

    for i, entry in enumerate(entries):
        e = {
            'time':  entry.get('time', ''),
            'label': entry.get('label', ''),
            'tipo':  'pontual' if entry.get('date') else 'diario',
        }

        if entry.get('date'):
            e['date'] = entry['date']

        if entry.get('replay_of') is not None:
            e['replay_of'] = entry['replay_of']
        elif entry.get('sources'):
            e['sources'] = entry['sources']

        if entry.get('slot_id') is not None:
            e['slot_id'] = entry['slot_id']

        if entry.get('days'):
            e['days'] = entry['days']

        key = _schedule_entry_key(entry)
        run_key = f"{today}|{key}"

        if entry.get('date'):
            e['executado'] = key in completed_once
        else:
            e['executado_hoje'] = run_key in completed_today

        # Marcar proximo a executar (diario, nao executado, horario >= agora)
        if (proximo_idx is None
                and not entry.get('date')
                and entry.get('time', '') >= now_time
                and run_key not in completed_today):
            e['proximo'] = True
            proximo_idx = i

        grade.append(e)

    proximo_time = entries[proximo_idx].get('time') if proximo_idx is not None else None

    return json.dumps({
        'total_entradas': len(grade),
        'proximo_horario': proximo_time,
        'hora_atual':      now_time,
        'grade':           grade,
        'dica':            'Use adicionar_grade() e remover_grade() para modificar a programacao.',
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def ler_config(secao: str = '') -> str:
    """
    Le uma secao do config.yaml e retorna como JSON.
    Util para inspecionar configuracoes antes de alterar.

    Args:
        secao: Nome da secao a ler. Opcoes: sources, narrators, llm, radio,
               vinheta, schedule, tts, spots, spots_config, announcements.
               Se vazio, retorna o config completo (exceto schedule — use ver_grade() para a grade).
    """
    config = _load_config()

    if secao:
        if secao not in config:
            return json.dumps({
                'status':  'erro',
                'mensagem': f"Secao '{secao}' nao encontrada.",
                'secoes_disponiveis': list(config.keys()),
            }, ensure_ascii=False, indent=2)
        return json.dumps({
            'secao':  secao,
            'conteudo': config[secao],
        }, ensure_ascii=False, indent=2)

    # Retorna tudo exceto schedule (muito grande — use ver_grade())
    resumo = {k: v for k, v in config.items() if k != 'schedule'}
    resumo['schedule_entradas'] = len(config.get('schedule', []))
    return json.dumps(resumo, ensure_ascii=False, indent=2)


@mcp.tool()
def configurar_fonte(id_fonte: str, campo: str, valor: str) -> str:
    """
    Altera um campo de uma fonte de conteudo no config.yaml.
    Operacao mais comum: habilitar ou desabilitar uma fonte.

    ATENCAO: salvar o config reformata o YAML e perde os comentarios do arquivo.

    Args:
        id_fonte: ID da fonte a alterar (ex: youtube, noticias, musica, horoscopo).
        campo:    Campo a alterar. Exemplos:
                  "enabled"  — true/false para habilitar/desabilitar
                  "name"     — nome exibido na programacao
                  "model"    — modelo LLM a usar (ex: claude-haiku-4-5-20251001)
        valor:    Novo valor (string — sera convertido para bool/int se aplicavel).
                  Para enabled: "true" ou "false".

    Exemplos:
        configurar_fonte("musica", "enabled", "true")
        configurar_fonte("youtube", "model", "claude-haiku-4-5-20251001")
        configurar_fonte("noticias", "name", "Noticias Gerais")
    """
    config  = _load_config()
    sources = config.get('sources', [])
    idx     = next((i for i, s in enumerate(sources) if s['id'] == id_fonte), None)

    if idx is None:
        ids = [s['id'] for s in sources]
        return json.dumps({
            'status':   'erro',
            'mensagem': f"Fonte '{id_fonte}' nao encontrada.",
            'fontes_disponiveis': ids,
        }, ensure_ascii=False, indent=2)

    valor_convertido = _parse_value(valor)
    valor_anterior   = sources[idx].get(campo, '<nao definido>')

    sources[idx][campo] = valor_convertido
    config['sources']   = sources
    _save_config(config)

    return json.dumps({
        'status':         'ok',
        'fonte':          id_fonte,
        'campo':          campo,
        'valor_anterior': valor_anterior,
        'valor_novo':     valor_convertido,
        'aviso':          'config.yaml foi reformatado — comentarios originais foram perdidos.',
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def atualizar_config(caminho: str, valor: str) -> str:
    """
    Atualiza qualquer valor no config.yaml usando notacao de ponto.
    Para alterar fontes, prefira configurar_fonte() que e mais seguro e especifico.

    ATENCAO: salvar o config reformata o YAML e perde os comentarios do arquivo.

    Args:
        caminho: Caminho com pontos ate o valor. Exemplos:
                 "radio.name"          — nome da radio
                 "llm.model"           — modelo LLM padrao
                 "vinheta.voice"       — voz das vinhetas
                 "vinheta.rate"        — velocidade das vinhetas (ex: +20%)
                 "announcements.enabled" — avisos entre musicas (true/false)
                 "radio.background_volume_db" — volume da musica de fundo
        valor:  Novo valor como string (convertido automaticamente para bool/int se aplicavel).

    Exemplos:
        atualizar_config("radio.name", "Minha Radio Genial")
        atualizar_config("llm.model", "claude-haiku-4-5-20251001")
        atualizar_config("vinheta.voice", "pt-BR-AntonioNeural")
    """
    config = _load_config()
    chaves = caminho.split('.')

    # Navegar ate o penultimo nivel para verificar existencia
    cursor = config
    for k in chaves[:-1]:
        if not isinstance(cursor, dict) or k not in cursor:
            return json.dumps({
                'status':   'erro',
                'mensagem': f"Caminho '{caminho}' invalido — '{k}' nao encontrado.",
            }, ensure_ascii=False, indent=2)
        cursor = cursor[k]

    valor_anterior = cursor.get(chaves[-1], '<nao definido>') if isinstance(cursor, dict) else '<nao definido>'
    valor_convertido = _parse_value(valor)

    _set_nested(config, chaves, valor_convertido)
    _save_config(config)

    return json.dumps({
        'status':         'ok',
        'caminho':        caminho,
        'valor_anterior': valor_anterior,
        'valor_novo':     valor_convertido,
        'aviso':          'config.yaml foi reformatado — comentarios originais foram perdidos.',
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def adicionar_grade(
    time: str,
    sources: list[str] = None,
    label: str = '',
    slot_id: int = None,
    date: str = '',
    days: list[str] = None,
    replay_of: int = None,
) -> str:
    """
    Adiciona uma nova entrada na grade de programacao do config.yaml.

    ATENCAO: salvar o config reformata o YAML e perde os comentarios do arquivo.

    Args:
        time:      Horario no formato HH:MM (ex: "14:30").
        sources:   Lista de IDs de fontes (ex: ["noticias", "tecnologia"]).
                   Obrigatorio se replay_of nao for informado.
        label:     Descricao da entrada (ex: "Noticias da tarde").
        slot_id:   ID numerico para permitir replay posterior deste episodio.
        date:      Data no formato YYYY-MM-DD para entrada pontual (so roda nessa data).
                   Omitir = entrada diaria.
        days:      Lista de dias da semana (ex: ["mon","tue","wed","thu","fri"]).
                   Omitir = todos os dias.
        replay_of: ID do slot a repetir (em vez de gerar novo episodio).

    Exemplos:
        adicionar_grade("16:00", ["noticias"], "Noticias da tarde")
        adicionar_grade("09:00", ["copa"], "Copa do Mundo", date="2026-07-14")
        adicionar_grade("18:00", replay_of=3, label="Quiz (noite)")
    """
    if not time:
        return json.dumps({'status': 'erro', 'mensagem': 'Parametro time e obrigatorio.'}, ensure_ascii=False)

    if sources is None and replay_of is None:
        return json.dumps({'status': 'erro', 'mensagem': 'Informe sources ou replay_of.'}, ensure_ascii=False)

    entry: dict = {'time': time}
    if label:
        entry['label'] = label
    if date:
        entry['date'] = date
    if days:
        entry['days'] = days
    if replay_of is not None:
        entry['replay_of'] = replay_of
    elif sources:
        entry['sources'] = sources
        if slot_id is not None:
            entry['slot_id'] = slot_id

    config   = _load_config()
    schedule = config.get('schedule', [])
    schedule.append(entry)
    # Ordenar por time para manter a grade organizada
    schedule.sort(key=lambda e: (e.get('date', '9999'), e.get('time', '')))
    config['schedule'] = schedule
    _save_config(config)

    return json.dumps({
        'status':  'ok',
        'entrada': entry,
        'total_entradas': len(schedule),
        'aviso':   'config.yaml foi reformatado — comentarios originais foram perdidos.',
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def remover_grade(time: str, label: str = '') -> str:
    """
    Remove entradas da grade de programacao do config.yaml.

    ATENCAO: salvar o config reformata o YAML e perde os comentarios do arquivo.

    Args:
        time:  Horario da entrada a remover (formato HH:MM).
               Se houver multiplas entradas no mesmo horario, todas serao removidas
               a menos que 'label' seja informado para filtrar.
        label: Label para filtrar quando ha multiplas entradas no mesmo horario.
               Se vazio, remove todas as entradas do horario informado.

    Exemplos:
        remover_grade("16:00")                     — remove todas as entradas das 16:00
        remover_grade("09:30", "Noticias da manha") — remove so a entrada especifica
    """
    config   = _load_config()
    schedule = config.get('schedule', [])

    antes = len(schedule)
    removidas = [
        e for e in schedule
        if e.get('time') == time and (not label or e.get('label', '') == label)
    ]
    schedule = [
        e for e in schedule
        if not (e.get('time') == time and (not label or e.get('label', '') == label))
    ]

    if not removidas:
        entradas_no_horario = [e for e in config.get('schedule', []) if e.get('time') == time]
        return json.dumps({
            'status':   'erro',
            'mensagem': f"Nenhuma entrada encontrada para time='{time}'" + (f" label='{label}'" if label else '') + '.',
            'entradas_no_horario': entradas_no_horario,
        }, ensure_ascii=False, indent=2)

    config['schedule'] = schedule
    _save_config(config)

    return json.dumps({
        'status':         'ok',
        'removidas':      removidas,
        'total_removidas': len(removidas),
        'total_restantes': len(schedule),
        'aviso':          'config.yaml foi reformatado — comentarios originais foram perdidos.',
    }, ensure_ascii=False, indent=2)


# ── Tools — Sistema e manutenção ─────────────────────────────────────────────

@mcp.tool()
def status_sistema() -> str:
    """
    Retorna o status geral do sistema RadioIA.
    Verifica: scheduler, player web, API keys configuradas, disco e ultimo episodio gerado.
    """
    resultado = {}

    # ── Scheduler ─────────────────────────────────────────────────────────────
    state_path = os.path.join(PROJECT_DIR, 'scheduler_state.json')
    if os.path.exists(state_path):
        mtime = os.path.getmtime(state_path)
        age_s = datetime.now().timestamp() - mtime
        resultado['scheduler'] = {
            'estado':          'provavelmente ativo' if age_s < 120 else 'inativo ou pausado',
            'ultimo_tick_seg': int(age_s),
            'dica':            'python scheduler.py para iniciar | scheduler_state.json atualizado a cada 30s',
        }
    else:
        resultado['scheduler'] = {'estado': 'nunca iniciado', 'dica': 'python scheduler.py para iniciar'}

    # ── Player web ────────────────────────────────────────────────────────────
    import urllib.request
    player_ativo = False
    try:
        urllib.request.urlopen('http://localhost:5000', timeout=2)
        player_ativo = True
    except Exception:
        pass
    resultado['player'] = {
        'ativo':   player_ativo,
        'url':     'http://localhost:5000',
        'dica':    'python serve.py para iniciar',
    }

    # ── API keys ──────────────────────────────────────────────────────────────
    keys_check = {
        'ANTHROPIC_API_KEY':       ('obrigatorio', 'Claude API — geracao de roteiros'),
        'YOUTUBE_API_KEY':         ('obrigatorio', 'YouTube Data API — fonte youtube'),
        'OPENWEATHER_API_KEY':     ('opcional',    'Clima — fonte utilidades'),
        'FOOTBALL_DATA_API_KEY':   ('opcional',    'Futebol — fontes copa/brasileirao/champions'),
        'TMDB_API_KEY':            ('opcional',    'Filmes — fontes filmes/filmes-cartaz'),
        'JAMENDO_CLIENT_ID':       ('opcional',    'Musica streaming — fonte musica'),
        'ABIBLIADIGITAL_TOKEN':    ('opcional',    'Biblia — fonte biblia'),
        'ELEVENLABS_API_KEY':      ('opcional',    'ElevenLabs TTS'),
        'OPENAI_API_KEY':          ('opcional',    'OpenAI TTS ou LLM'),
    }
    api_keys = {}
    for key, (tipo, desc) in keys_check.items():
        val = os.environ.get(key, '')
        api_keys[key] = {
            'configurada': bool(val),
            'tipo':        tipo,
            'descricao':   desc,
        }
    resultado['api_keys'] = api_keys

    # ── Disco ─────────────────────────────────────────────────────────────────
    output_dir = os.path.join(PROJECT_DIR, 'output')
    if os.path.exists(output_dir):
        total_bytes = sum(
            os.path.getsize(os.path.join(root, f))
            for root, _, files in os.walk(output_dir)
            for f in files
        )
        datas_output = sorted([
            d for d in os.listdir(output_dir)
            if os.path.isdir(os.path.join(output_dir, d)) and d[:4].isdigit()
        ], reverse=True)
        resultado['output'] = {
            'tamanho_mb':    round(total_bytes / 1024 / 1024, 1),
            'dias_com_data': len(datas_output),
            'datas_recentes': datas_output[:5],
            'dica':          'Use limpar_output(dias_manter=7) para liberar espaco.',
        }
    else:
        resultado['output'] = {'tamanho_mb': 0, 'dias_com_data': 0}

    # ── Ultimo episodio ───────────────────────────────────────────────────────
    history_path = os.path.join(PROJECT_DIR, 'history.json')
    if os.path.exists(history_path):
        with open(history_path, 'r', encoding='utf-8') as f:
            h = json.load(f)
        eps = h.get('episodes', [])
        resultado['historico'] = {
            'itens_vistos':    len(h.get('seen_ids', [])),
            'episodios_total': len(eps),
            'ultimo':          eps[-1]['episode_id'] if eps else None,
        }

    # ── Config ────────────────────────────────────────────────────────────────
    config = _load_config()
    resultado['radio'] = {
        'nome':          config.get('radio', {}).get('name', 'RadioIA'),
        'llm_model':     config.get('llm', {}).get('model', ''),
        'tts_provider':  config.get('tts', {}).get('provider', 'edge_tts'),
        'narradores':    [n.get('name') for n in config.get('narrators', [])],
        'fontes_ativas': [s['id'] for s in config.get('sources', []) if s.get('enabled', True)],
    }

    return json.dumps(resultado, ensure_ascii=False, indent=2)


@mcp.tool()
def limpar_output(dias_manter: int = 7, preview: bool = True) -> str:
    """
    Remove episodios antigos da pasta output para liberar espaco em disco.

    Args:
        dias_manter: Numero de dias recentes a manter. Default: 7.
                     Pastas com datas mais antigas serao removidas.
        preview:     Se True (padrao), apenas lista o que seria removido sem deletar.
                     Use preview=False para realmente deletar os arquivos.

    Exemplos:
        limpar_output()                    — lista o que seria removido (seguro)
        limpar_output(dias_manter=30)      — lista pastas mais antigas que 30 dias
        limpar_output(dias_manter=7, preview=False) — deleta de verdade
    """
    output_dir = os.path.join(PROJECT_DIR, 'output')
    if not os.path.exists(output_dir):
        return json.dumps({'status': 'ok', 'mensagem': 'Pasta output nao existe.'}, ensure_ascii=False)

    cutoff = (datetime.now() - timedelta(days=dias_manter)).strftime('%Y-%m-%d')

    datas = sorted([
        d for d in os.listdir(output_dir)
        if os.path.isdir(os.path.join(output_dir, d)) and len(d) == 10 and d[:4].isdigit()
    ])

    para_remover = [d for d in datas if d < cutoff]
    para_manter  = [d for d in datas if d >= cutoff]

    # Calcular tamanho das pastas a remover
    def _dir_size(path: str) -> int:
        return sum(
            os.path.getsize(os.path.join(root, f))
            for root, _, files in os.walk(path)
            for f in files
        )

    detalhes = []
    total_bytes = 0
    for d in para_remover:
        p = os.path.join(output_dir, d)
        sz = _dir_size(p)
        total_bytes += sz
        detalhes.append({'data': d, 'tamanho_mb': round(sz / 1024 / 1024, 1)})

    if preview:
        return json.dumps({
            'status':        'preview',
            'cutoff':        cutoff,
            'dias_manter':   dias_manter,
            'para_remover':  detalhes,
            'para_manter':   para_manter,
            'espaco_mb':     round(total_bytes / 1024 / 1024, 1),
            'mensagem':      f"Simulacao: {len(para_remover)} pasta(s) seriam removidas ({round(total_bytes/1024/1024,1)} MB). "
                             f"Use preview=False para confirmar.",
        }, ensure_ascii=False, indent=2)

    # Deletar de verdade
    removidas = []
    erros = []
    for d in para_remover:
        p = os.path.join(output_dir, d)
        try:
            shutil.rmtree(p)
            removidas.append(d)
        except Exception as e:
            erros.append({'data': d, 'erro': str(e)})

    return json.dumps({
        'status':       'ok',
        'removidas':    removidas,
        'total_removidas': len(removidas),
        'espaco_liberado_mb': round(total_bytes / 1024 / 1024, 1),
        'mantidas':     para_manter,
        'erros':        erros,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def testar_tts(texto: str, voz: str = '') -> str:
    """
    Gera um arquivo de audio de teste usando o TTS configurado (edge-tts por padrao).
    Util para verificar se o TTS esta funcionando e ouvir como uma voz soa.

    Args:
        texto: Texto a sintetizar (ex: "Bem-vindos a RadioIA, sua radio personalizada!").
        voz:   Nome da voz edge-tts a usar. Se vazio, usa a voz da vinheta configurada.
               Vozes pt-BR disponiveis:
               - pt-BR-ThalitaMultilingualNeural (feminina, padrao narradora Ana)
               - pt-BR-AntonioNeural (masculina, narrador Carlos)
               - pt-BR-FranciscaNeural (feminina, vinhetas)

    O arquivo gerado e salvo em output/tts_test.mp3.
    """
    import asyncio
    import edge_tts

    config = _load_config()

    if not voz:
        voz = config.get('vinheta', {}).get('voice', 'pt-BR-FranciscaNeural')

    output_path = os.path.join(PROJECT_DIR, 'output', 'tts_test.mp3')
    os.makedirs(os.path.join(PROJECT_DIR, 'output'), exist_ok=True)

    async def _synth():
        comm = edge_tts.Communicate(texto, voz)
        await comm.save(output_path)

    try:
        asyncio.run(_synth())
    except RuntimeError:
        # Em contextos onde event loop ja existe (ex: Jupyter)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_synth())
        loop.close()

    if not os.path.exists(output_path):
        return json.dumps({'status': 'erro', 'mensagem': 'Arquivo nao gerado.'}, ensure_ascii=False)

    size_kb = round(os.path.getsize(output_path) / 1024, 1)

    return json.dumps({
        'status':   'ok',
        'voz':      voz,
        'texto':    texto,
        'arquivo':  output_path,
        'tamanho_kb': size_kb,
        'mensagem': f"Audio gerado com sucesso. Acesse em http://localhost:5000 ou abra o arquivo diretamente.",
    }, ensure_ascii=False, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    mcp.run()
