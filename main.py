import os
import sys
import shutil
import importlib.util
import yaml
from datetime import datetime
from dotenv import load_dotenv

from src.sources import youtube, rss, music as music_source, utility as utility_source
from src.script_generator import generate_script
from src.tts_generator import parse_script, generate_audio_files
from src.audio_mixer import mix_episode, save_episode_metadata
from src.vinheta import generate_vinhetas
from src.history import load_seen_ids, save_episode_to_history

load_dotenv()


def _load_plugins() -> dict:
    """Carrega dinamicamente os módulos de src/sources/plugins/."""
    plugins_dir = 'plugins'
    modules = {}
    if not os.path.isdir(plugins_dir):
        return modules
    for filename in sorted(os.listdir(plugins_dir)):
        if not filename.endswith('.py') or filename.startswith('_'):
            continue
        name = filename[:-3]
        try:
            spec   = importlib.util.spec_from_file_location(f'plugins.{name}',
                                                             os.path.join(plugins_dir, filename))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, 'fetch'):
                modules[name] = module
                print(f"  Plugin carregado: {name}")
            else:
                print(f"  [plugin/{name}] ignorado — sem função fetch()")
        except Exception as e:
            print(f"  [plugin/{name}] erro ao carregar: {e}")
    return modules


SOURCE_MODULES = {
    'youtube': youtube,
    'rss':     rss,
    'music':   music_source,
    'utility': utility_source,
}

SOURCE_MODULES.update(_load_plugins())


def load_config(path: str = 'config.yaml') -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _get_oauth_credentials():
    try:
        from src.auth import get_youtube_credentials
        return get_youtube_credentials()
    except Exception as e:
        print(f"  [aviso OAuth] {type(e).__name__}: {e}")
        return None


def _has_episodes_today() -> bool:
    today   = datetime.now().strftime('%Y-%m-%d')
    day_dir = os.path.join('output', today)
    if not os.path.exists(day_dir):
        return False
    return any(
        os.path.exists(os.path.join(day_dir, f, 'episode.mp3'))
        for f in os.listdir(day_dir)
        if os.path.isdir(os.path.join(day_dir, f))
    )


def _episode_output_dir(source_id: str) -> str:
    now = datetime.now()
    return os.path.join('output', now.strftime('%Y-%m-%d'), now.strftime('%H-%M') + f'_{source_id}')


def _run_replay_cli(partial: str, today: str | None = None) -> list[str]:
    """Cria replays dos episódios cujas pastas batem com o prefixo parcial.

    Retorna lista de caminhos para os episode.json criados.
    """
    import json as _json
    if not today:
        today = datetime.now().strftime('%Y-%m-%d')

    day_dir = os.path.join('output', today)
    if not os.path.isdir(day_dir):
        print(f"  Nenhum episodio encontrado para {today}.")
        return []

    matches = sorted([
        f for f in os.listdir(day_dir)
        if f.startswith(partial)
        and os.path.isdir(os.path.join(day_dir, f))
        and os.path.exists(os.path.join(day_dir, f, 'episode.mp3'))
    ])

    if not matches:
        print(f"  Nenhum episodio com prefixo '{partial}' em {today}.")
        available = sorted([
            f for f in os.listdir(day_dir)
            if os.path.isdir(os.path.join(day_dir, f))
        ])
        if available:
            print(f"  Disponiveis: {', '.join(available)}")
        return []

    now = datetime.now().strftime('%H-%M')
    created = []

    for folder in matches:
        orig_dir  = os.path.join(day_dir, folder)
        orig_mp3  = os.path.join(orig_dir, 'episode.mp3')
        orig_json = os.path.join(orig_dir, 'episode.json')

        source_id  = folder.split('_', 1)[1] if '_' in folder else folder
        output_dir = os.path.join(day_dir, f"{now}_{source_id}")

        os.makedirs(output_dir, exist_ok=True)

        meta = {}
        if os.path.exists(orig_json):
            with open(orig_json, 'r', encoding='utf-8') as f:
                meta = _json.load(f)

        meta['audio_path'] = os.path.abspath(orig_mp3)
        meta['replay_of']  = folder

        out_json = os.path.join(output_dir, 'episode.json')
        with open(out_json, 'w', encoding='utf-8') as f:
            _json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"  Replay: {folder} → {output_dir}")
        created.append(out_json)

    return created


def _run_spot_source(source_config: dict, config: dict, is_first_of_day: bool) -> str | None:
    import json as _json
    from src.spots import get_next_spot
    from pydub import AudioSegment as _AS
    import io as _io

    source_name = source_config.get('name', 'Comunicado')
    output_dir  = _episode_output_dir(source_config['id'])

    print(f"\n{'='*50}")
    print(f"Fonte: {source_name} (spot)")
    print(f"{'='*50}")

    result = get_next_spot()
    if not result:
        print("  Nenhum spot disponivel ou todos atingiram o limite diario.")
        return None

    spot, audio_bytes = result
    os.makedirs(output_dir, exist_ok=True)
    episode_path = os.path.join(output_dir, 'episode.mp3')

    with open(episode_path, 'wb') as f:
        f.write(audio_bytes)

    try:
        duration = len(_AS.from_mp3(_io.BytesIO(audio_bytes))) / 1000
    except Exception:
        duration = len(audio_bytes) / 16000

    metadata = {
        'source_name':      source_name,
        'duration_seconds': int(duration),
        'videos_covered':   1,
        'links': [{'title': spot.get('id', ''), 'url': '', 'channel': 'Spots',
                   'views': 0, 'published_at': '', 'top_comments': []}],
        'spot_id':   spot['id'],
        'spot_type': spot.get('type', 'file'),
    }
    with open(os.path.join(output_dir, 'episode.json'), 'w', encoding='utf-8') as f:
        _json.dump(metadata, f, ensure_ascii=False, indent=2)

    mins, secs = int(duration // 60), int(duration % 60)
    print(f"\nSpot gerado: {episode_path}")
    print(f"Duracao: {mins}m {secs}s | ID: {spot['id']} ({spot.get('type', 'file')})")
    return episode_path


def _run_music_source(source_config: dict, config: dict, is_first_of_day: bool) -> str | None:
    source_name = source_config.get('name', 'Selecao Musical')
    output_dir  = _episode_output_dir(source_config['id'])
    radio_name  = config.get('radio', {}).get('name', 'RadioIA')

    print(f"\n{'='*50}")
    print(f"Fonte: {source_name} (music)")
    print(f"{'='*50}")

    narrators = config['narrators'][:1]
    try:
        duration = music_source.generate_episode(
            source_config, output_dir, narrators, is_first_of_day, station_name=radio_name
        )
    except FileNotFoundError as e:
        print(f"  Erro: {e}")
        return None

    episode_path = os.path.join(output_dir, 'episode.mp3')
    mins, secs = int(duration // 60), int(duration % 60)
    print(f"\nBloco musical gerado: {episode_path}")
    print(f"Duracao: {mins}m {secs}s")
    return episode_path


def _run_utility_source(source_config: dict, config: dict, is_first_of_day: bool) -> str | None:
    source_name = source_config.get('name', 'Resumo do Dia')
    output_dir  = _episode_output_dir(source_config['id'])
    radio_name  = config.get('radio', {}).get('name', 'RadioIA')

    print(f"\n{'='*50}")
    print(f"Fonte: {source_name} (utility)")
    print(f"{'='*50}")

    narrators = config['narrators'][:2]
    try:
        duration = utility_source.generate_episode(
            source_config, output_dir, narrators, is_first_of_day, station_name=radio_name
        )
    except Exception as e:
        print(f"  Erro: {e}")
        return None

    episode_path = os.path.join(output_dir, 'episode.mp3')
    mins, secs = int(duration // 60), int(duration % 60)
    print(f"\nBloco de utilidades gerado: {episode_path}")
    print(f"Duracao: {mins}m {secs}s")
    return episode_path


def _run_source(source_config: dict, config: dict, credentials, seen_ids: set,
                is_first_of_day: bool = True) -> str | None:
    source_type = source_config['type']
    source_id = source_config['id']
    source_name = source_config['name']
    module = SOURCE_MODULES.get(source_type)

    if not module:
        print(f"  Tipo desconhecido: {source_type}")
        return None

    youtube_api_key = os.getenv('YOUTUBE_API_KEY')

    output_dir = _episode_output_dir(source_id)
    temp_dir   = os.path.join(output_dir, 'temp')
    episode_id = '/'.join(output_dir.replace('\\', '/').split('/')[-2:])

    print(f"\n{'='*50}")
    print(f"Fonte: {source_name} ({source_type})")
    print(f"{'='*50}")

    # Inject API key for YouTube source
    if source_type == 'youtube':
        source_config = {**source_config, '_api_key': youtube_api_key}
        items = module.fetch(source_config, credentials)
    else:
        items = module.fetch(source_config)

    before = len(items)
    items = [v for v in items if v['id'] not in seen_ids]
    skipped = before - len(items)
    if skipped:
        print(f"  {skipped} item(s) ignorado(s) — ja citados anteriormente.")

    # Se poucos itens novos, expande o periodo de busca e complementa
    # (não se aplica a fontes com número fixo de itens como horoscopo/trivia)
    settings = source_config.get('settings') or {}
    max_total = settings.get('max_videos_total', settings.get('max_items_total', 10))
    min_items = max(3, max_total // 3)

    if 0 < len(items) < min_items and source_type not in ('horoscopo', 'trivia', 'efemerides'):
        lookback = settings.get('days_lookback', 7)
        print(f"  Poucos itens novos ({len(items)}), expandindo busca para {lookback * 3} dias...")
        expanded_settings = {**settings, 'days_lookback': lookback * 3}
        expanded_config = {**source_config, 'settings': expanded_settings}

        already_ids = seen_ids | {v['id'] for v in items}
        if source_type == 'youtube':
            extra = module.fetch(expanded_config, credentials)
        else:
            extra = module.fetch(expanded_config)

        extra_new = [v for v in extra if v['id'] not in already_ids]
        needed = max_total - len(items)
        items.extend(extra_new[:needed])
        if extra_new:
            print(f"  +{min(len(extra_new), needed)} item(s) encontrado(s) na busca expandida.")

    if not items:
        print("  Nenhum conteudo novo encontrado.")
        return None

    print(f"  {len(items)} item(s) novo(s).\n")

    narrators = config['narrators'][:3]
    radio_name = config.get('radio', {}).get('name', 'RadioIA')
    llm_cfg = config.get('llm', config.get('claude', {}))
    default_model = llm_cfg.get('model', 'claude-sonnet-4-6')
    api_base = llm_cfg.get('api_base')
    model = source_config.get('model') or default_model

    print(f"Gerando roteiro ({model})...")
    script = generate_script(items, narrators, source_config,
                             is_first_of_day=is_first_of_day, station_name=radio_name,
                             model=model, api_base=api_base)
    print(f"  {len(script.split())} palavras.\n")

    print("Gerando audio...")
    lines = parse_script(script)
    if not lines:
        print("  Roteiro sem falas no formato esperado.")
        print(script[:400])
        return None

    locutor_keys = ['LOCUTOR_A', 'LOCUTOR_B', 'LOCUTOR_C']
    voices = {locutor_keys[i]: n['voice'] for i, n in enumerate(narrators)}
    tts_config = config.get('tts', {})
    audio_files = generate_audio_files(lines, voices, temp_dir, tts_config)

    vinheta_config = {**config.get('vinheta', {}), 'station_name': radio_name}
    vinhetas = generate_vinhetas(vinheta_config, temp_dir, tts_config)
    print(f"  {len(lines)} falas + vinhetas geradas.\n")

    print("Montando episodio...")
    episode_path = os.path.join(output_dir, 'episode.mp3')
    links_text = ' | '.join(f"[{i}] {v['title']} {v['url']}" for i, v in enumerate(items, 1))

    duration = mix_episode(
        audio_files=audio_files,
        lines=lines,
        output_path=episode_path,
        metadata={'title': f'{source_name} - {episode_id}', 'links_text': links_text},
        radio_config=config.get('radio', {}),
        vinhetas=vinhetas,
        station_name=radio_name,
    )

    save_episode_metadata(items, script, output_dir, duration, source_name=source_name)
    save_episode_to_history(episode_id, items)
    shutil.rmtree(temp_dir)

    mins, secs = int(duration // 60), int(duration % 60)
    print(f"\nEpisodio pronto: {episode_path}")
    print(f"Duracao: {mins}m {secs}s | Itens: {len(items)}")
    for i, item in enumerate(items, 1):
        print(f"  [{i}] {item['title'][:60]}")
        print(f"      {item['url']}")

    return episode_path


def _cmd_gen_time_clips():
    from src.time_clips import generate_atomic_clips
    config = load_config()
    vinheta = config.get('vinheta', {})
    voice   = vinheta.get('voice', 'pt-BR-FranciscaNeural')
    rate    = vinheta.get('rate',  '+15%')
    print(f"Gerando clips de hora/minuto (voz: {voice}, rate: {rate})...")
    force = '--force' in sys.argv
    n = generate_atomic_clips(voice=voice, rate=rate, force=force)
    if n:
        print(f"  {n} clip(s) gerado(s) em output/_time_clips/atomic/")
    else:
        print("  Todos os clips já existem. Use --gen-time-clips --force para regenerar.")


def _cmd_download_musica():
    config = load_config()
    from src.sources import music as music_source
    jamendo_sources = [
        s for s in config.get('sources', [])
        if s.get('type') == 'music'
        and (s.get('settings') or {}).get('source') == 'jamendo'
    ]
    if not jamendo_sources:
        print("Nenhuma fonte de música Jamendo configurada no config.yaml.")
        return
    for src in jamendo_sources:
        print(f"Baixando músicas — {src.get('name', src['id'])}...")
        n = music_source.download_cache(src)
        print(f"  {n} faixa(s) nova(s) baixada(s).\n")


def main():
    if '--gen-time-clips' in sys.argv:
        _cmd_gen_time_clips()
        sys.exit(0)

    if 'download-musica' in sys.argv:
        _cmd_download_musica()
        sys.exit(0)

    config = load_config()
    radio_name = config.get('radio', {}).get('name', 'RadioIA')
    print(f"{radio_name}\n")
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')

    if not youtube_api_key:
        print("Erro: configure YOUTUBE_API_KEY no arquivo .env")
        sys.exit(1)

    # CLI: python main.py [source_id[:param] ...]
    # Exemplos: youtube  |  musica  |  musica:3  |  musica:1
    def _parse_cli(args: list[str]) -> dict[str, str | None]:
        result = {}
        for arg in args:
            if ':' in arg:
                sid, param = arg.split(':', 1)
                result[sid] = param
            else:
                result[arg] = None
        return result

    cli = _parse_cli(sys.argv[1:]) if len(sys.argv) > 1 else {}

    # Extrai replay: direto do argv para suportar múltiplos (replay:X replay:Y)
    replay_targets = [a.split(':', 1)[1] for a in sys.argv[1:] if a.startswith('replay:')]
    # Extrai URLs avulsas: url:https://... → fonte sintética, sem precisar de config
    url_targets     = [v for k, v in cli.items() if k == 'url' and v]
    # Extrai clippings: clipping:tema → fonte sintética, sem precisar de config
    clipping_targets = [v for k, v in cli.items() if k == 'clipping' and v]
    cli_clean   = {k: v for k, v in cli.items() if k not in ('url', 'replay', 'clipping')}
    requested   = set(cli_clean.keys())

    all_sources = config.get('sources', [])
    if requested:
        sources = [s for s in all_sources if s['id'] in requested]
        unknown = requested - {s['id'] for s in all_sources}
        if unknown:
            available = ', '.join(s['id'] for s in all_sources)
            print(f"Fonte(s) desconhecida(s): {', '.join(unknown)}")
            print(f"Disponiveis: {available}")
            sys.exit(1)
    elif not url_targets and not clipping_targets and not replay_targets:
        # Sem args: roda tudo habilitado
        sources = [s for s in all_sources if s.get('enabled', True)]
    else:
        sources = []

    for target_url in url_targets:
        sources.append({
            'id':       'url',
            'type':     'url',
            'name':     'Conteúdo da Web',
            'enabled':  True,
            'settings': {'url': target_url},
        })

    for topic in clipping_targets:
        # Mescla defaults do config (se existir fonte id=clipping) com o tópico CLI
        base = next((s for s in all_sources if s['id'] == 'clipping'), {})
        sources.append({
            **base,
            'id':      'clipping',
            'type':    'clipping',
            'name':    f"Clipping — {topic[:60]}",
            'enabled': True,
            'settings': {**(base.get('settings') or {}), 'topic': topic},
        })

    if not sources and not replay_targets:
        print("Nenhuma fonte selecionada ou habilitada.")
        sys.exit(0)

    credentials = _get_oauth_credentials()
    if credentials:
        print("OAuth ativo — inscricoes do YouTube disponiveis.\n")
    else:
        print("Sem OAuth — usando canais configurados.\n")

    seen_ids = load_seen_ids()
    generated = []
    first_of_day = not _has_episodes_today()

    for source_config in sources:
        # Apply CLI param overrides
        param = cli.get(source_config['id'])
        if param is not None and source_config.get('type') == 'music':
            try:
                n = int(param)
                source_config = {
                    **source_config,
                    'settings': {**source_config.get('settings', {}), 'num_tracks': n}
                }
                print(f"  Parametro CLI: {n} musica(s)")
            except ValueError:
                print(f"  Parametro invalido '{param}' — usando config padrao.")

        if param is not None and source_config.get('type') == 'clipping':
            source_config = {
                **source_config,
                'settings': {**(source_config.get('settings') or {}), 'topic': param},
                'name': f"Clipping — {param[:60]}",
            }
            print(f"  Tópico: {param}")

        if param is not None and source_config.get('type') == 'horoscopo':
            try:
                from plugins.horoscopo import SIGN_PAIRS, SIGN_PT
                n = int(param) % 6
                pair = SIGN_PAIRS[n]
                label = f"{SIGN_PT[pair[0]]} e {SIGN_PT[pair[1]]}"
                source_config = {
                    **source_config,
                    'settings': {**(source_config.get('settings') or {}), 'pair_index': n},
                    'name': f"Horóscopo — {label}",
                }
                print(f"  Parametro CLI: par {n} ({label})")
            except ValueError:
                print(f"  Parametro invalido '{param}' — usando rotacao automatica.")

        if source_config.get('type') in ('music', 'utility', 'spot'):
            fn = {'music': _run_music_source,
                  'utility': _run_utility_source,
                  'spot': _run_spot_source}[source_config['type']]
            path = fn(source_config, config, first_of_day)
            if path:
                generated.append(path)
                first_of_day = False
            continue

        path = _run_source(source_config, config, credentials, seen_ids,
                           is_first_of_day=first_of_day)
        if path:
            generated.append(path)
            first_of_day = False  # subsequent sources are mid-day segments
            seen_ids = load_seen_ids()

    for partial in replay_targets:
        print(f"\n{'='*50}")
        print(f"Replay: '{partial}'")
        print(f"{'='*50}")
        paths = _run_replay_cli(partial)
        generated.extend(paths)

    print(f"\n{'='*50}")
    print(f"Concluido. {len(generated)} episodio(s) gerado(s).")
    for p in generated:
        print(f"  {p}")


if __name__ == '__main__':
    main()
