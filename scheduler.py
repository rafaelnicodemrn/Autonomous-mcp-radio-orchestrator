"""
RadioIA Scheduler

Modos de agendamento (config.yaml, seção 'schedule'):

  Diário (sem 'date'):
    - time: "07:00"
      sources: [utilidades, noticias]
      label: "Manhã"
      # days: [mon,tue,wed,thu,fri]  # opcional — omitir = todos os dias

  Pontual (com 'date'):
    - time: "11:00"
      date: "2026-06-11"
      sources: [copa]
      label: "Abertura da Copa"

  Com slot_id (para replay posterior):
    - time: "08:00"
      slot_id: 10
      sources: [filmes]
      label: "Cine Indica Manhã"

  Replay (reaproveita episódio já gerado):
    - time: "14:00"
      replay_of: 10
      label: "Cine Indica (tarde)"

Uso:
  python scheduler.py          — inicia o agendador
  python scheduler.py --list   — exibe a grade sem rodar
"""

import json
import os
import sys
import time
import argparse
from datetime import date, datetime

import yaml

CONFIG_FILE = 'config.yaml'
STATE_FILE  = 'scheduler_state.json'

DAYS_MAP = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}


# ── Config & State ────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _entry_key(entry: dict) -> str:
    d    = entry.get('date', 'daily')
    t    = entry.get('time', '')
    days = ','.join(sorted(entry.get('days', [])))
    if entry.get('replay_of') is not None:
        s = f"replay:{entry['replay_of']}"
    else:
        s = '+'.join(sorted(entry.get('sources', [])))
    return f"{d}|{t}|{s}|{days}"


def _entry_active_today(entry: dict) -> bool:
    days = entry.get('days')
    if not days:
        return True
    today_wd = datetime.now().weekday()
    return any(DAYS_MAP.get(str(d).lower(), -1) == today_wd for d in days)


# ── Execution ─────────────────────────────────────────────────────────────────

def _run(sources: list[str], label: str = ''):
    tag = f"[{label}] " if label else ''
    ts  = datetime.now().strftime('%H:%M:%S')
    src = ' '.join(sources)
    print(f"\n{'='*50}")
    print(f"[{ts}] {tag}python main.py {src}")
    print(f"{'='*50}")
    import subprocess
    result = subprocess.run([sys.executable, 'main.py'] + sources)
    status = 'Concluido' if result.returncode == 0 else f'Erro (code {result.returncode})'
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {tag}{status}\n")


def _find_latest_episode(source_id: str, today: str) -> str | None:
    """Retorna o ep_id mais recente para o source_id no dia de hoje."""
    day_dir = os.path.join('output', today)
    if not os.path.exists(day_dir):
        return None
    candidates = [
        f for f in sorted(os.listdir(day_dir))
        if '_' in f and f.split('_', 1)[1] == source_id
        and os.path.exists(os.path.join(day_dir, f, 'episode.mp3'))
    ]
    return f"{today}/{candidates[-1]}" if candidates else None


def _save_slot(slot_id, sources: list[str], today: str, programacao_map: dict):
    """Registra o episódio gerado no programacao_map para uso futuro por replay."""
    if today not in programacao_map:
        programacao_map[today] = {}
    for source_arg in sources:
        source_id = source_arg.split(':')[0]  # remove parâmetros como "horoscopo:0"
        ep_id = _find_latest_episode(source_id, today)
        if ep_id:
            programacao_map[today][str(slot_id)] = ep_id
            print(f"  [slot:{slot_id}] registrado -> {ep_id}")
            return
    print(f"  [slot:{slot_id}] nenhum episodio encontrado para registrar.")


def _run_replay(replay_of, current_time: str, label: str, state: dict, today: str) -> bool:
    """Cria um episódio de replay apontando para o MP3 original (sem copiar o arquivo)."""
    pmap   = state.get('programacao_map', {}).get(today, {})
    ep_id  = pmap.get(str(replay_of))

    if not ep_id:
        print(f"  [replay:{replay_of}] Slot nao encontrado — episodio original ainda nao foi gerado hoje.")
        return False

    orig_dir  = os.path.join('output', ep_id)
    orig_mp3  = os.path.join(orig_dir, 'episode.mp3')
    orig_json = os.path.join(orig_dir, 'episode.json')

    if not os.path.exists(orig_mp3):
        print(f"  [replay:{replay_of}] MP3 original nao encontrado: {orig_mp3}")
        return False

    # Usa o mesmo source_id do original para nomear a pasta de forma consistente no player
    folder     = ep_id.split('/')[-1]                          # "08-00_filmes"
    source_id  = folder.split('_', 1)[1] if '_' in folder else folder
    output_dir = os.path.join('output', today, f"{current_time.replace(':', '-')}_{source_id}")

    os.makedirs(output_dir, exist_ok=True)

    meta = {}
    if os.path.exists(orig_json):
        with open(orig_json, 'r', encoding='utf-8') as f:
            meta = json.load(f)

    meta['audio_path']     = os.path.abspath(orig_mp3)
    meta['replay_of_slot'] = replay_of

    with open(os.path.join(output_dir, 'episode.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"  [replay:{replay_of}] {label} -> {ep_id}")
    return True


# ── Display ───────────────────────────────────────────────────────────────────

def _days_str(entry: dict) -> str:
    days = entry.get('days')
    if not days:
        return ''
    return f"[{','.join(str(d).lower() for d in days)}]"


def _sources_str(entry: dict) -> str:
    if entry.get('replay_of') is not None:
        return f"replay:{entry['replay_of']}"
    sources = ' '.join(entry.get('sources', []))
    slot_id = entry.get('slot_id')
    return f"{sources} [slot:{slot_id}]" if slot_id is not None else sources


def _next_entry_key(entries: list[dict], today: str, state: dict) -> str | None:
    now_time        = datetime.now().strftime('%H:%M')
    completed_today = set(state.get('completed_today', {}).keys())
    upcoming = [
        e for e in entries
        if not e.get('date')
        and e.get('time', '') >= now_time
        and f"{today}|{_entry_key(e)}" not in completed_today
        and _entry_active_today(e)
    ]
    if not upcoming:
        return None
    return _entry_key(min(upcoming, key=lambda e: e.get('time', '')))


def _print_next(entries: list[dict]):
    today = date.today().isoformat()
    state = load_state()
    key   = _next_entry_key(entries, today, state)
    if not key:
        print("Aguardando... (sem proximos agendamentos para hoje)\n")
        return
    nxt = next((e for e in entries if _entry_key(e) == key), None)
    if nxt:
        label = f" — {nxt['label']}" if nxt.get('label') else ''
        print(f"Aguardando... Proximo: {nxt['time']}  {_sources_str(nxt)}{label}\n")
    else:
        print("Aguardando...\n")


def print_schedule(entries: list[dict]):
    if not entries:
        print("  (nenhuma entrada configurada)")
        return
    today          = date.today().isoformat()
    state          = load_state()
    completed_once = set(state.get('completed_once', []))
    next_key       = _next_entry_key(entries, today, state)

    for e in entries:
        label  = e.get('label', '')
        edate  = e.get('date', '')
        key    = _entry_key(e)
        src    = _sources_str(e)

        if edate:
            past   = edate < today
            done   = key in completed_once
            mode   = f"pontual {edate}"
            status = ' [ja executado]' if done else (' [data passada]' if past else '')
        else:
            mode   = 'diario'
            status = ''

        marker   = '*' if key == next_key else ' '
        tag      = f" — {label}" if label else ''
        days_tag = f" {_days_str(e)}" if e.get('days') else ''
        print(f"{marker} {e['time']}  {mode:<20}  {src}{days_tag}{tag}{status}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_loop():
    config  = load_config()
    radio_name = config.get('radio', {}).get('name', 'RadioIA')
    print(f"{radio_name} Scheduler iniciado — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    entries = config.get('schedule', [])
    print(f"\nGrade ({len(entries)} entrada(s)):")
    print_schedule(entries)
    _print_next(entries)

    while True:
        now          = datetime.now()
        today        = date.today().isoformat()
        current_time = now.strftime('%H:%M')

        config  = load_config()  # recarrega a cada tick (permite editar sem reiniciar)
        entries = config.get('schedule', [])
        state   = load_state()

        completed_once  = set(state.get('completed_once', []))
        completed_today = {k: v for k, v in state.get('completed_today', {}).items()
                           if k.startswith(today)}
        # Mantém programacao_map só para hoje
        programacao_map = {d: m for d, m in state.get('programacao_map', {}).items()
                           if d == today}

        ran = False
        for entry in entries:
            if entry.get('time') != current_time:
                continue
            if not _entry_active_today(entry):
                continue

            key       = _entry_key(entry)
            sources   = entry.get('sources', [])
            label     = entry.get('label', '')
            edate     = entry.get('date', '')
            slot_id   = entry.get('slot_id')
            replay_of = entry.get('replay_of')

            if edate:
                # Pontual: só roda na data certa, uma única vez
                if edate != today or key in completed_once:
                    continue
                if replay_of is not None:
                    _run_replay(replay_of, current_time, label, state, today)
                else:
                    _run(sources, label)
                    if slot_id is not None:
                        _save_slot(slot_id, sources, today, programacao_map)
                completed_once.add(key)
                ran = True
            else:
                # Diário: roda todo dia, uma vez por minuto
                run_key = f"{today}|{key}"
                if run_key in completed_today:
                    continue
                if replay_of is not None:
                    _run_replay(replay_of, current_time, label, state, today)
                else:
                    _run(sources, label)
                    if slot_id is not None:
                        _save_slot(slot_id, sources, today, programacao_map)
                completed_today[run_key] = current_time
                ran = True

        state['completed_once']  = list(completed_once)
        state['completed_today'] = completed_today
        state['programacao_map'] = programacao_map
        save_state(state)

        if ran:
            print(f"\nGrade ({len(entries)} entrada(s)):")
            print_schedule(entries)
            _print_next(entries)

        time.sleep(30)


# ── PID guard ────────────────────────────────────────────────────────────────

PID_FILE = 'scheduler.pid'


def _process_alive(pid: int) -> bool:
    try:
        if sys.platform == 'win32':
            import subprocess as _sp
            r = _sp.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                        capture_output=True, text=True)
            return str(pid) in r.stdout
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _acquire_pid_lock() -> bool:
    """Verifica se ja ha instancia rodando. Retorna True se pode prosseguir."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                existing_pid = int(f.read().strip())
            if _process_alive(existing_pid):
                print(f"ERRO: Scheduler ja esta rodando (PID {existing_pid}).")
                print(f"      Encerre a instancia existente antes de iniciar outra.")
                print(f"      Para forcar, remova o arquivo: {os.path.abspath(PID_FILE)}")
                return False
        except (ValueError, OSError):
            pass  # arquivo corrompido — sobrescreve

    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True


def _release_pid_lock():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(PID_FILE)
        except (ValueError, OSError):
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RadioIA Scheduler')
    parser.add_argument('--list', action='store_true', help='Exibe a grade e sai')
    args = parser.parse_args()

    if args.list:
        config  = load_config()
        entries = config.get('schedule', [])
        radio_name = config.get('radio', {}).get('name', 'RadioIA')
        print(f"Grade {radio_name} ({date.today()}):")
        print_schedule(entries)
    else:
        if not _acquire_pid_lock():
            sys.exit(1)
        try:
            run_loop()
        finally:
            _release_pid_lock()
