import os
import json
import webbrowser
import threading
from flask import Flask, jsonify, send_from_directory, render_template_string

app = Flask(__name__)
OUTPUT_DIR = 'output'
MUSIC_DIR  = 'music'

POLL_INTERVAL_SECONDS = 20   # frequencia de verificacao de novos episodios

FALLBACK_INTRO_PATH  = os.path.join('output', '_fallback_intro.mp3')
FALLBACK_INTRO_TEXT  = 'Enquanto aguardamos novos episódios, fiquem com algumas músicas selecionadas para você.'
FALLBACK_INTRO_VOICE = 'pt-BR-ThalitaMultilingualNeural'


def _jamendo_cache_empty() -> bool:
    catalog_path = os.path.join('music', 'cache', 'jamendo', 'catalog.json')
    if not os.path.exists(catalog_path):
        return True
    try:
        with open(catalog_path, 'r', encoding='utf-8') as f:
            return len(json.load(f)) == 0
    except Exception:
        return True


def _auto_download_jamendo():
    """Se o cache do Jamendo estiver vazio e houver fonte configurada, baixa automaticamente."""
    if not _jamendo_cache_empty():
        return
    try:
        import yaml
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
    except Exception:
        return
    jamendo_sources = [
        s for s in cfg.get('sources', [])
        if s.get('type') == 'music'
        and (s.get('settings') or {}).get('source') == 'jamendo'
    ]
    if not jamendo_sources:
        return
    print("Cache do Jamendo vazio — baixando músicas para o fallback...")
    from src.sources import music as music_source
    for src in jamendo_sources:
        n = music_source.download_cache(src)
        print(f"  {n} faixa(s) baixada(s) ({src.get('name', src['id'])}).")


def _generate_fallback_intro():
    if os.path.exists(FALLBACK_INTRO_PATH):
        return
    try:
        import sys
        import asyncio
        import edge_tts
        os.makedirs('output', exist_ok=True)
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        async def _gen():
            await edge_tts.Communicate(FALLBACK_INTRO_TEXT, FALLBACK_INTRO_VOICE).save(FALLBACK_INTRO_PATH)
        asyncio.run(_gen())
        print('Intro de fallback gerada.')
    except Exception as e:
        print(f'[aviso] Intro de fallback nao gerada: {e}')

HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>{{ radio_name }}</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #111827; color: #f3f4f6; height: 100vh; display: flex; flex-direction: column; }

header { background: #1f2937; border-bottom: 1px solid #374151;
         padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
header h1 { font-size: 18px; font-weight: 700; color: #f9fafb; }
.header-right { display: flex; align-items: center; gap: 12px; }
.header-sub { font-size: 12px; color: #6b7280; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; display: none; }
.live-dot.active { display: block; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

/* Toast notification */
.toast { position: fixed; top: 16px; right: 16px; background: #1e3a2f; border: 1px solid #10b981;
         color: #6ee7b7; padding: 12px 16px; border-radius: 8px; font-size: 13px;
         display: none; z-index: 100; max-width: 320px; box-shadow: 0 4px 12px #0008; }
.toast.show { display: flex; align-items: center; gap: 10px; }
.toast-btn { background: #10b981; color: #fff; border: none; padding: 4px 10px;
             border-radius: 4px; cursor: pointer; font-size: 12px; white-space: nowrap; }

.player-bar { background: #1f2937; border-bottom: 1px solid #374151; padding: 14px 24px; flex-shrink: 0;
              display: flex; align-items: center; gap: 12px; }
.player-info { flex: 1; min-width: 0; }
.music-mode-btn {
  flex-shrink: 0; background: #374151; border: 1px solid #4b5563;
  color: #9ca3af; width: 38px; height: 38px; border-radius: 8px;
  font-size: 18px; cursor: pointer; transition: background .15s, color .15s;
  display: flex; align-items: center; justify-content: center;
}
.music-mode-btn:hover { background: #4b5563; color: #e5e7eb; }
.music-mode-btn.active { background: #064e3b; border-color: #10b981; color: #6ee7b7; }
.player-badge { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em;
                padding: 2px 8px; border-radius: 4px; display: inline-block; margin-bottom: 4px; }
.badge-content { background: #312e81; color: #a5b4fc; }
.badge-music   { background: #064e3b; color: #6ee7b7; }
.badge-news    { background: #431407; color: #fdba74; }
.badge-fallback{ background: #1c1917; color: #a8a29e; }
.player-name   { font-size: 16px; font-weight: 600; color: #f9fafb; margin-bottom: 2px; }
.player-track  { font-size: 12px; color: #6b7280; margin-bottom: 10px; min-height: 16px; }
audio { width: 100%; height: 36px; accent-color: #6366f1; }

.body { flex: 1; display: flex; overflow: hidden; }

.sidebar { width: 140px; background: #1f2937; border-right: 1px solid #374151;
           overflow-y: auto; flex-shrink: 0; }
.sidebar-header { font-size: 10px; color: #6b7280; text-transform: uppercase;
                  letter-spacing: .05em; padding: 14px 16px 8px; }
.day-item { padding: 12px 16px; cursor: pointer; border-left: 3px solid transparent; transition: background .15s; }
.day-item:hover { background: #374151; }
.day-item.active { background: #312e81; border-color: #6366f1; }
.day-num   { font-size: 22px; font-weight: 700; line-height: 1; }
.day-month { font-size: 11px; color: #9ca3af; margin-top: 2px; }

.playlist { width: 240px; border-right: 1px solid #374151; overflow-y: auto; flex-shrink: 0; }
.section-header { font-size: 10px; color: #6b7280; text-transform: uppercase; letter-spacing: .05em;
                  padding: 14px 16px 8px; position: sticky; top: 0; background: #111827; }
.ep-item { padding: 12px 16px; cursor: pointer; display: flex; align-items: center;
           gap: 10px; border-left: 3px solid transparent; transition: background .15s; }
.ep-item:hover { background: #1f2937; }
.ep-item.active { background: #1e1b4b; border-color: #6366f1; }
.ep-item.played { opacity: .5; }
.ep-item.new-ep { border-left-color: #10b981; background: #064e3b22; }
.ep-dot  { width: 8px; height: 8px; border-radius: 50%; background: #4b5563; flex-shrink: 0; }
.ep-item.active .ep-dot { background: #6366f1; }
.ep-item.played .ep-dot { background: #374151; }
.ep-item.new-ep .ep-dot { background: #10b981; }
.ep-label { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ep-meta  { font-size: 11px; color: #6b7280; margin-top: 2px; }
.ep-next  { cursor: default; opacity: .55; border-left-style: dashed; }
.ep-next:hover { background: transparent !important; }
.ep-next .ep-dot { background: transparent; border: 1px dashed #4b5563; }

.notes { flex: 1; overflow-y: auto; padding: 20px 24px; }
.notes-header { font-size: 10px; color: #6b7280; text-transform: uppercase;
                letter-spacing: .05em; margin-bottom: 14px; }
.link-card { background: #1f2937; border: 1px solid #374151; border-radius: 10px;
             padding: 14px 16px; margin-bottom: 10px; }
.link-num    { font-size: 11px; color: #818cf8; font-weight: 700; margin-bottom: 4px; }
.link-title  { font-size: 14px; font-weight: 600; margin-bottom: 6px; line-height: 1.4; }
.link-meta   { font-size: 12px; color: #9ca3af; margin-bottom: 8px; }
.link-url    { font-size: 12px; color: #60a5fa; text-decoration: none; word-break: break-all; display: block; }
.link-url:hover { text-decoration: underline; }
.comment-block  { margin-top: 10px; padding-top: 10px; border-top: 1px solid #374151; }
.comment-label  { font-size: 10px; color: #6b7280; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
.comment-item   { font-size: 12px; color: #d1d5db; margin-bottom: 4px; }
.comment-author { color: #818cf8; font-weight: 600; }
.empty { color: #4b5563; text-align: center; padding: 48px 0; font-size: 14px; }

.fallback-card { background: #1c1917; border: 1px solid #44403c; border-radius: 10px;
                 padding: 24px; text-align: center; }
.fallback-icon { font-size: 36px; margin-bottom: 10px; }
.fallback-name { font-size: 15px; font-weight: 600; color: #d6d3d1; margin-bottom: 4px; }
.fallback-hint { font-size: 12px; color: #78716c; }

/* ── Mobile nav bar ───────────────────────────────────────────────────────── */
.mobile-nav { display: none; }
.mobile-days-bar { display: none; }

@media (max-width: 768px) {
  body { height: 100vh; height: 100dvh; } /* dvh com fallback vh */

  header { padding: 10px 16px; }
  header h1 { font-size: 16px; }
  .header-sub { display: none; }

  .player-bar { padding: 10px 16px; }
  .player-name { font-size: 15px; }

  .body { flex-direction: column; overflow: hidden; }

  /* Dias: barra horizontal acima do player */
  .sidebar { display: none !important; }
  .mobile-days-bar {
    display: flex; overflow-x: auto; overflow-y: hidden;
    background: #1f2937; border-bottom: 1px solid #374151;
    padding: 6px 8px; flex-shrink: 0;
  }
  .mobile-days-bar > div {
    display: flex; flex-direction: row; gap: 6px;
  }
  .day-item {
    flex-shrink: 0; border-radius: 10px; border-left: none;
    border-bottom: 3px solid transparent; min-width: 54px;
    padding: 8px 10px; text-align: center;
  }
  .day-item.active { border-bottom-color: #6366f1; }
  .day-num { font-size: 18px; }

  .playlist {
    width: 100%; border-right: none; display: none;
    flex: 1; overflow-y: auto;
  }
  .playlist.tab-active { display: block; }
  .ep-item { padding: 14px 16px; }

  .notes { display: none; flex: 1; padding: 16px; overflow-y: auto; }
  .notes.tab-active { display: block; }

  /* Bottom nav — sempre visível */
  .mobile-nav {
    display: flex !important; background: #1f2937;
    border-top: 1px solid #374151; flex-shrink: 0;
    padding-bottom: env(safe-area-inset-bottom, 0);
  }
  .mobile-nav-btn {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 3px;
    padding: 10px 4px; cursor: pointer; background: none; border: none;
    color: #6b7280; font-size: 10px; font-family: inherit;
    -webkit-tap-highlight-color: transparent; transition: color .15s;
  }
  .mobile-nav-btn.active { color: #6366f1; }
  .mobile-nav-icon { font-size: 18px; line-height: 1; }
}

@media (min-width: 769px) {
  .sidebar { display: block !important; }
  .playlist { display: block !important; }
  .notes { display: block !important; }
}
</style>
</head>
<body>

<div class="toast" id="toast">
  <span id="toast-msg"></span>
  <button class="toast-btn" id="toast-btn" onclick="onToastAction()">Ouvir agora</button>
</div>

<header>
  <h1>{{ radio_name }}</h1>
  <div class="header-right">
    <div class="live-dot" id="live-dot" title="Verificando novos episódios..."></div>
    <span class="header-sub" id="header-sub">Selecione um dia para começar</span>
  </div>
</header>

<div class="mobile-days-bar"><div id="days-mobile"></div></div>

<div class="player-bar">
  <div class="player-info">
    <span class="player-badge badge-content" id="player-badge">Conteúdo</span>
    <div class="player-name"  id="player-name">Nenhum episódio selecionado</div>
    <div class="player-track" id="player-track"></div>
    <audio id="audio" controls></audio>
  </div>
  <button class="music-mode-btn" id="music-mode-btn" onclick="onMusicModeClick()" title="Modo musical">♫</button>
</div>

<div class="body">
  <div class="sidebar">
    <div class="sidebar-header">Dias</div>
    <div id="days"></div>
  </div>
  <div class="playlist">
    <div class="section-header">Playlist</div>
    <div id="playlist"></div>
  </div>
  <div class="notes">
    <div class="notes-header">Fontes do episódio</div>
    <div id="notes"><div class="empty">Selecione um episódio para ver as fontes.</div></div>
  </div>
</div>

<nav class="mobile-nav">
  <button class="mobile-nav-btn active" id="tab-playlist" onclick="setTab('playlist')">
    <span class="mobile-nav-icon">▶</span>Playlist
  </button>
  <button class="mobile-nav-btn" id="tab-fontes" onclick="setTab('fontes')">
    <span class="mobile-nav-icon">ℹ</span>Fontes
  </button>
</nav>

<script src="https://cdnjs.cloudflare.com/ajax/libs/nosleep/0.12.0/NoSleep.min.js"></script>
<script>
const POLL_MS = """ + str(POLL_INTERVAL_SECONDS * 1000) + r""";

let allEpisodes   = [];
let musicFiles    = [];
let currentDate   = null;
const ANNOUNCEMENT_EVERY         = 3;   // break de grade a cada N músicas no modo fallback
const SPOT_EVERY                 = {{ spots_fallback_every }};   // spot a cada N músicas (0 = desativado)
const BETWEEN_EPISODES_EVERY     = {{ between_episodes_every }}; // break entre episódios a cada N transições (0 = desativado)
let currentEp     = null;
let fallbackMode  = false;
let fallbackIdx   = 0;
let _fallbackTrackCount      = 0;
let _episodeTransitionCount  = 0;
let _playingAnnouncement     = false;   // suprime ended global durante qualquer break

const S_EP   = 'radioIA_ep';
const S_TIME = 'radioIA_time';
const S_VOL  = 'radioIA_vol';

// Salva posição a cada 5 segundos enquanto toca
let _lastSave = 0;
document.addEventListener('DOMContentLoaded', () => {
  const audio = document.getElementById('audio');

  audio.addEventListener('timeupdate', () => {
    if (!currentEp || fallbackMode) return;
    const t = audio.currentTime;
    if (t - _lastSave >= 5) {
      _lastSave = t;
      localStorage.setItem(S_EP,   currentEp.id);
      localStorage.setItem(S_TIME, t);
    }
  });

  audio.addEventListener('play',  () => acquireWakeLock());
  audio.addEventListener('pause', () => releaseWakeLock());
  audio.addEventListener('volumechange', () => {
    localStorage.setItem(S_VOL, audio.volume);
  });

  // Restaura volume salvo
  const savedVol = localStorage.getItem(S_VOL);
  if (savedVol !== null) audio.volume = parseFloat(savedVol);
});

const months = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];


// ── Screen Wake Lock (NoSleep.js — funciona em HTTP e HTTPS) ─────────────────
const noSleep = new NoSleep();

function acquireWakeLock() {
  noSleep.enable().catch(() => {});
}

function releaseWakeLock() {
  noSleep.disable();
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    const audio = document.getElementById('audio');
    if (!audio.paused) acquireWakeLock();
  }
});

// ── Mobile tabs ───────────────────────────────────────────────────────────────
function isMobile() { return window.innerWidth <= 768; }

function setTab(tab) {
  if (!isMobile()) return;
  document.querySelector('.playlist').classList.toggle('tab-active', tab === 'playlist');
  document.querySelector('.notes').classList.toggle('tab-active', tab === 'fontes');
  document.getElementById('tab-playlist').classList.toggle('active', tab === 'playlist');
  document.getElementById('tab-fontes').classList.toggle('active', tab === 'fontes');
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  const [epsRes, musRes] = await Promise.all([
    fetch('/api/episodes'),
    fetch('/api/music-files')
  ]);
  allEpisodes = await epsRes.json();
  musicFiles  = await musRes.json();
  shuffle(musicFiles);
  renderDays();

  const today     = new Date().toISOString().slice(0, 10);
  const savedId   = localStorage.getItem(S_EP);
  const savedTime = parseFloat(localStorage.getItem(S_TIME) || '0');
  const savedEp   = savedId && allEpisodes.find(e => e.id === savedId);
  const todayEps  = groupByDate(allEpisodes)[today] || [];

  if (savedEp && savedEp.date === today) {
    // Retoma episódio de hoje de onde parou
    selectDate(today, false);
    playEpisode(savedEp);
    if (savedTime > 3) {
      const audio = document.getElementById('audio');
      audio.addEventListener('canplay', () => { audio.currentTime = savedTime; }, { once: true });
    }
  } else {
    // Novo dia ou sem histórico — abre hoje direto
    selectDate(today, false);
    if (todayEps.length) playEpisode(todayEps[0]);
    else enterFallback();
  }

  if (isMobile()) setTab('playlist');
  startPolling();
}

// ── Polling ───────────────────────────────────────────────────────────────────
function startPolling() {
  document.getElementById('live-dot').classList.add('active');
  setInterval(pollEpisodes, POLL_MS);
}

async function pollEpisodes() {
  try {
    const res  = await fetch('/api/episodes');
    const fresh = await res.json();
    const knownIds = new Set(allEpisodes.map(e => e.id));
    const newOnes  = fresh.filter(e => !knownIds.has(e.id));

    if (!newOnes.length) return;

    allEpisodes = fresh;
    rerenderCurrentDay();

    const todayNew = newOnes.filter(e => e.date === currentDate);
    if (!todayNew.length) return;

    if (fallbackMode) {
      showToast(`Novo episódio: ${todayNew[0].source_name || todayNew[0].source_id}`, false);
      exitFallback(todayNew[0]);
    } else {
      showToast(`Novo episódio: ${todayNew[0].source_name || todayNew[0].source_id}`, false);
      markNewEpisodes(todayNew.map(e => e.id));
    }
  } catch (_) {}
}

function rerenderCurrentDay() {
  renderDays();
  if (currentDate) {
    const eps = groupByDate(allEpisodes)[currentDate] || [];
    const {day, month} = fmt(currentDate);
    document.getElementById('header-sub').textContent = `${day} de ${month} · ${eps.length} episódio(s)`;
    renderPlaylist(eps);
    appendNextScheduled();
  }
}

function markNewEpisodes(ids) {
  ids.forEach(id => {
    const el = document.querySelector(`.ep-item[data-id="${id}"]`);
    if (el) el.classList.add('new-ep');
  });
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let toastTimer = null;
function showToast(msg, showBtn) {
  const toast = document.getElementById('toast');
  document.getElementById('toast-msg').textContent = msg;
  document.getElementById('toast-btn').style.display = showBtn ? 'block' : 'none';
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), showBtn ? 8000 : 4000);
}

function onToastAction() {
  document.getElementById('toast').classList.remove('show');
}

// ── Fallback music ─────────────────────────────────────────────────────────────
async function enterFallback() {
  if (!musicFiles.length) return;

  // Navega ANTES de setar fallbackMode — selectDate() faz fallbackMode=false
  // e causaria dupla reprodução do intro se chamada depois
  const today  = new Date().toISOString().slice(0, 10);
  const groups = groupByDate(allEpisodes);
  const latest = Object.keys(groups).sort().reverse()[0];
  if (currentDate !== today && latest && latest !== currentDate) {
    // Só navega para o último dia com episódios se não estamos em hoje
    selectDate(latest, false);
  } else {
    // Já estamos no lugar certo — apenas rola a playlist para o fim
    // para que o item "próximo na grade" fique visível
    setTimeout(() => {
      const pl = document.getElementById('playlist');
      if (pl) pl.scrollTop = pl.scrollHeight;
    }, 200);
  }

  fallbackMode = true;
  document.getElementById('music-mode-btn').classList.add('active');

  try {
    const res = await fetch('/api/fallback-intro', { method: 'HEAD' });
    if (res.ok) {
      const badge = document.getElementById('player-badge');
      badge.className = 'player-badge badge-fallback';
      badge.textContent = '🎵 Modo Musical';
      document.getElementById('player-name').textContent = 'Seleção Musical';
      document.getElementById('player-track').textContent = '';
      document.getElementById('notes').innerHTML = `
        <div class="fallback-card">
          <div class="fallback-icon">🎵</div>
          <div class="fallback-name">Seleção Musical</div>
          <div class="fallback-hint">Aguardando novos episódios...</div>
        </div>`;
      const audio = document.getElementById('audio');
      audio.src = '/api/fallback-intro';
      audio.play().catch(() => playFallbackTrack());
      return;
    }
  } catch (_) {}

  playFallbackTrack();
}

function _playTrack(track) {
  const badge = document.getElementById('player-badge');
  badge.className = 'player-badge badge-fallback';
  badge.textContent = '🎵 Modo Musical';
  document.getElementById('player-name').textContent = track.title || track.name.replace(/\.[^.]+$/, '');
  document.getElementById('player-track').textContent = track.artist || 'Tocando músicas enquanto aguarda novos episódios...';
  const audio = document.getElementById('audio');
  audio.src = track.url;
  audio.play().catch(() => {});
  document.getElementById('notes').innerHTML = `
    <div class="fallback-card">
      <div class="fallback-icon">🎵</div>
      <div class="fallback-name">${track.title || track.name.replace(/\.[^.]+$/, '')}</div>
      <div class="fallback-hint">${track.artist ? track.artist + ' · ' : ''}Aguardando novos episódios...</div>
    </div>`;
}

const S_SPOTS = 'radioIA_spots';

function _spotsToday() {
  const today = new Date().toISOString().slice(0, 10);
  try {
    const d = JSON.parse(localStorage.getItem(S_SPOTS) || '{}');
    if (d.day !== today) return {day: today, counts: {}};
    return d;
  } catch (_) { return {day: today, counts: {}}; }
}

function _incSpot(id) {
  const d = _spotsToday();
  d.counts[id] = (d.counts[id] || 0) + 1;
  localStorage.setItem(S_SPOTS, JSON.stringify(d));
}

function _playSpot(onEnd) {
  fetch('/api/spot', { method: 'HEAD' })
    .then(r => {
      if (!r.ok) { onEnd(); return; }
      const spotId    = r.headers.get('X-Spot-Id') || '';
      const maxPerDay = parseInt(r.headers.get('X-Spot-Max-Per-Day') || '9999');
      const count     = _spotsToday().counts[spotId] || 0;
      if (count >= maxPerDay) { onEnd(); return; }   // limite do cliente atingido

      _playingAnnouncement = true;
      _incSpot(spotId);
      const audio = document.getElementById('audio');
      audio.src = '/api/spot?t=' + Date.now();
      audio.addEventListener('ended', function handler() {
        audio.removeEventListener('ended', handler);
        _playingAnnouncement = false;
        onEnd();
      });
      audio.play().catch(() => { _playingAnnouncement = false; onEnd(); });
    })
    .catch(onEnd);
}

function _playAnnouncement(onEnd) {
  fetch('/api/announcement', { method: 'HEAD' })
    .then(r => {
      if (!r.ok) { onEnd(); return; }
      _playingAnnouncement = true;
      const audio = document.getElementById('audio');
      audio.src = '/api/announcement?t=' + Date.now();
      audio.addEventListener('ended', function handler() {
        audio.removeEventListener('ended', handler);
        _playingAnnouncement = false;
        onEnd();
      });
      audio.play().catch(() => { _playingAnnouncement = false; onEnd(); });
    })
    .catch(onEnd);
}

function playFallbackTrack() {
  if (!fallbackMode) return;
  _fallbackTrackCount++;
  const track = musicFiles[fallbackIdx % musicFiles.length];
  fallbackIdx++;

  const doAnnouncement = _fallbackTrackCount % ANNOUNCEMENT_EVERY === 0;
  const doSpot = SPOT_EVERY > 0 && _fallbackTrackCount % SPOT_EVERY === 0;

  if (doSpot && doAnnouncement) {
    _playSpot(() => _playAnnouncement(() => _playTrack(track)));
  } else if (doSpot) {
    _playSpot(() => _playTrack(track));
  } else if (doAnnouncement) {
    _playAnnouncement(() => _playTrack(track));
  } else {
    _playTrack(track);
  }
}

function exitFallback(ep) {
  fallbackMode = false;
  document.getElementById('music-mode-btn').classList.remove('active');
  playEpisode(ep);
}

function onMusicModeClick() {
  if (fallbackMode) {
    // já em modo musical: volta para o primeiro episódio do dia
    const eps = groupByDate(allEpisodes)[currentDate] || [];
    if (eps.length) exitFallback(eps[0]);
  } else {
    enterFallback();
    document.getElementById('music-mode-btn').classList.add('active');
  }
}

// ── Playback ──────────────────────────────────────────────────────────────────
document.getElementById('audio').addEventListener('ended', () => {
  if (_playingAnnouncement) return;   // break em andamento — handler próprio cuida do encadeamento
  const eps = groupByDate(allEpisodes)[currentDate] || [];

  if (fallbackMode) {
    playFallbackTrack();
    return;
  }

  const idx = eps.findIndex(e => e.id === currentEp?.id);
  const el  = document.querySelector(`.ep-item[data-id="${currentEp?.id}"]`);
  if (el) el.classList.add('played');

  if (idx >= 0 && idx < eps.length - 1) {
    const nextEp = eps[idx + 1];
    _episodeTransitionCount++;
    const doBreak = BETWEEN_EPISODES_EVERY > 0
                    && _episodeTransitionCount % BETWEEN_EPISODES_EVERY === 0;
    if (doBreak) {
      const doSpot         = SPOT_EVERY > 0;
      const doAnnouncement = true;
      if (doSpot && doAnnouncement)
        _playSpot(() => _playAnnouncement(() => playEpisode(nextEp)));
      else if (doSpot)
        _playSpot(() => playEpisode(nextEp));
      else
        _playAnnouncement(() => playEpisode(nextEp));
    } else {
      playEpisode(nextEp);
    }
  } else {
    enterFallback();
  }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
}

function groupByDate(eps) {
  const g = {};
  eps.forEach(ep => { (g[ep.date] = g[ep.date] || []).push(ep); });
  return g;
}

function fmt(d) {
  const [y, m, day] = d.split('-');
  return { day, month: months[+m-1] + '/' + y };
}

function fmtDur(s) {
  return s ? `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}` : '';
}

function fmtViews(v) {
  if (!v) return '';
  if (v >= 1e6) return (v/1e6).toFixed(1) + 'M views';
  if (v >= 1e3) return Math.floor(v/1e3) + 'k views';
  return v + ' views';
}

function episodeType(ep) {
  const id = (ep.source_id || '').toLowerCase();
  if (id.includes('music') || id === 'musica' || id === 'musica-local') return 'music';
  if (id.includes('noticia') || id.includes('rss') || id.includes('tech') || id.includes('economia')) return 'news';
  return 'content';
}

function badgeLabel(type) {
  if (type === 'music') return ['badge-music',   '🎵 Música'];
  if (type === 'news')  return ['badge-news',    '📰 Notícias'];
  return                       ['badge-content', '▶ Conteúdo'];
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderDays() {
  const groups = groupByDate(allEpisodes);
  const today  = new Date().toISOString().slice(0, 10);
  if (!groups[today]) groups[today] = [];
  const dates  = Object.keys(groups).sort().reverse().slice(0, 5);
  const html   = dates.map(d => {
    const {day, month} = fmt(d);
    return `<div class="day-item" data-date="${d}" onclick="selectDate('${d}')">
      <div class="day-num">${day}</div>
      <div class="day-month">${month}</div>
    </div>`;
  }).join('');
  document.getElementById('days').innerHTML = html;
  document.getElementById('days-mobile').innerHTML = html;
  document.querySelectorAll('.day-item').forEach(el =>
    el.classList.toggle('active', el.dataset.date === currentDate));
}

function appendNextScheduled() {
  const today = new Date().toISOString().slice(0, 10);
  if (currentDate !== today) return;
  fetch('/api/next-scheduled')
    .then(r => r.json())
    .then(next => {
      if (!next) return;
      const el = document.createElement('div');
      el.className = 'ep-item ep-next';
      el.innerHTML =
        `<div class="ep-dot"></div>` +
        `<div style="min-width:0">` +
          `<div class="ep-label">${next.time_display} &mdash; ${next.label}</div>` +
          `<div class="ep-meta">próximo na grade</div>` +
        `</div>`;
      document.getElementById('playlist').appendChild(el);
    })
    .catch(() => {});
}

function selectDate(date, autoplay = true) {
  currentDate = date;
  fallbackMode = false;
  document.querySelectorAll('.day-item').forEach(el =>
    el.classList.toggle('active', el.dataset.date === date));
  const eps = groupByDate(allEpisodes)[date] || [];
  const {day, month} = fmt(date);
  document.getElementById('header-sub').textContent =
    `${day} de ${month} · ${eps.length} episódio(s)`;
  renderPlaylist(eps);
  appendNextScheduled();
  if (autoplay && eps.length) playEpisode(eps[0]);
  if (isMobile()) setTab('playlist');
}

function renderPlaylist(eps) {
  document.getElementById('playlist').innerHTML = eps.map(ep => {
    const name = ep.source_name || ep.source_id;
    const dur  = fmtDur(ep.duration);
    const cnt  = ep.videos_covered ? ep.videos_covered + ' itens' : '';
    const meta = [ep.time, dur, cnt].filter(Boolean).join(' · ');
    return `<div class="ep-item" data-id="${ep.id}" onclick="onEpClick('${ep.id}')">
      <div class="ep-dot"></div>
      <div style="min-width:0">
        <div class="ep-label">${name}</div>
        <div class="ep-meta">${meta}</div>
      </div>
    </div>`;
  }).join('');
  // re-apply active / played
  if (currentEp) {
    const el = document.querySelector(`.ep-item[data-id="${currentEp.id}"]`);
    if (el) el.classList.add('active');
  }
}

function onEpClick(epId) {
  fallbackMode = false;
  const ep = allEpisodes.find(e => e.id === epId);
  if (ep) playEpisode(ep);
}

function playEpisode(ep) {
  if (!ep) return;
  fallbackMode = false;
  currentEp = ep;
  _lastSave = 0;
  localStorage.setItem(S_EP,   ep.id);
  localStorage.setItem(S_TIME, '0');
  const name = ep.source_name || ep.source_id;
  const type = episodeType(ep);
  const [badgeClass, badgeText] = badgeLabel(type);

  const badge = document.getElementById('player-badge');
  badge.className = 'player-badge ' + badgeClass;
  badge.textContent = badgeText;
  document.getElementById('player-name').textContent = name;
  document.getElementById('player-track').textContent = '';

  const audio = document.getElementById('audio');
  audio.src = `/audio/${ep.id}`;
  audio.play().catch(() => {});

  document.querySelectorAll('.ep-item').forEach(el => {
    el.classList.remove('active', 'new-ep');
    el.classList.toggle('active', el.dataset.id === ep.id);
  });

  renderNotes(ep);
  if (isMobile()) setTab('fontes');
}

function renderNotes(ep) {
  const el = document.getElementById('notes');
  if (!ep.links || !ep.links.length) {
    el.innerHTML = '<div class="empty">Sem fontes registradas.</div>';
    return;
  }
  const isMusic = episodeType(ep) === 'music';
  el.innerHTML = ep.links.map((lk, i) => {
    const meta = isMusic
      ? [lk.channel, lk.album].filter(Boolean).join(' · ')
      : [lk.channel, fmtViews(lk.views)].filter(Boolean).join(' · ');
    const urlHtml = lk.url ? `<a class="link-url" href="${lk.url}" target="_blank">${lk.url}</a>` : '';
    const comments = (lk.top_comments || []).filter(c => c.likes > 0);
    const commentsHtml = comments.length ? `
      <div class="comment-block">
        <div class="comment-label">Comentários em destaque</div>
        ${comments.map(c => `<div class="comment-item">
          <span class="comment-author">${c.author}</span>: "${c.text}"
          <span style="color:#4b5563"> · ${c.likes} curtidas</span>
        </div>`).join('')}
      </div>` : '';
    return `<div class="link-card">
      <div class="link-num">${isMusic ? '🎵' : '#' + (i+1)}</div>
      <div class="link-title">${lk.title}</div>
      ${meta ? `<div class="link-meta">${meta}</div>` : ''}
      ${urlHtml}${commentsHtml}
    </div>`;
  }).join('');
}

init();
</script>
</body>
</html>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_date(s: str) -> bool:
    parts = s.split('-')
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def _has_audio(ep_path: str) -> bool:
    """Aceita episódios com episode.mp3 ou episódios de replay com audio_path em episode.json."""
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


def _add_episode(episodes: list, ep_path: str, ep_id: str, date: str, source_id: str, time: str = ''):
    meta = {}
    meta_path = os.path.join(ep_path, 'episode.json')
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
    episodes.append({
        'id':             ep_id,
        'date':           date,
        'time':           time,
        'source_id':      source_id,
        'source_name':    meta.get('source_name', source_id),
        'duration':       meta.get('duration_seconds', 0),
        'videos_covered': meta.get('videos_covered', 0),
        'links':          meta.get('links', []),
    })


def scan_episodes():
    episodes = []
    if not os.path.exists(OUTPUT_DIR):
        return episodes

    for entry in sorted(os.listdir(OUTPUT_DIR)):
        entry_path = os.path.join(OUTPUT_DIR, entry)
        if not os.path.isdir(entry_path):
            continue

        if _is_date(entry):
            date = entry
            for ep_folder in sorted(os.listdir(entry_path)):
                ep_path = os.path.join(entry_path, ep_folder)
                if not os.path.isdir(ep_path):
                    continue
                if not _has_audio(ep_path):
                    continue
                parts     = ep_folder.split('_', 1)
                source_id = parts[1] if len(parts) > 1 else ep_folder
                time      = parts[0].replace('-', 'h') if len(parts) > 1 else ''
                _add_episode(episodes, ep_path, f"{date}/{ep_folder}", date, source_id, time)
        else:
            if not _has_audio(entry_path):
                continue
            parts     = entry.split('_')
            date      = parts[0] if parts else ''
            source_id = '_'.join(parts[2:]) if len(parts) > 2 else entry
            _add_episode(episodes, entry_path, entry, date, source_id)

    return episodes


def _extra_music_paths() -> list[str]:
    try:
        import yaml
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        paths = []
        for src in cfg.get('sources', []):
            if src.get('type') == 'music' and (src.get('settings') or {}).get('source') == 'local':
                paths += (src.get('settings') or {}).get('paths', [])
        return list(dict.fromkeys(paths))  # deduplica mantendo ordem
    except Exception:
        return []


def scan_music_files():
    files = []
    audio_exts = {'.mp3', '.m4a', '.ogg', '.wav', '.flac'}

    # Músicas locais — recursivo (exclui cache do Jamendo)
    jamendo_cache = os.path.abspath(os.path.join(MUSIC_DIR, 'cache', 'jamendo'))
    if os.path.exists(MUSIC_DIR):
        for dirpath, _, filenames in os.walk(MUSIC_DIR):
            if os.path.abspath(dirpath).startswith(jamendo_cache):
                continue
            for f in sorted(filenames):
                if os.path.splitext(f)[1].lower() in audio_exts:
                    rel = os.path.relpath(os.path.join(dirpath, f), MUSIC_DIR).replace(os.sep, '/')
                    files.append({'name': f, 'url': f'/music/{rel}',
                                   'title': os.path.splitext(f)[0], 'artist': ''})

    # Paths extras configurados em musica-local
    seen_abs = set()
    for fi in files:
        seen_abs.add(os.path.abspath(os.path.join(MUSIC_DIR, fi['name'])))
    for extra in _extra_music_paths():
        if not os.path.isdir(extra):
            continue
        for dirpath, _, filenames in os.walk(extra):
            for f in sorted(filenames):
                if os.path.splitext(f)[1].lower() in audio_exts:
                    full = os.path.abspath(os.path.join(dirpath, f))
                    if full not in seen_abs:
                        seen_abs.add(full)
                        files.append({'name': f, 'url': f'/music-extra/{full.replace(os.sep, "/")}',
                                       'title': os.path.splitext(f)[0], 'artist': ''})

    # Cache Jamendo
    catalog_path = os.path.join(MUSIC_DIR, 'cache', 'jamendo', 'catalog.json')
    if os.path.exists(catalog_path):
        with open(catalog_path, 'r', encoding='utf-8') as f:
            catalog = json.load(f)
        for meta in catalog.values():
            fpath = os.path.join(MUSIC_DIR, 'cache', 'jamendo', meta['file'])
            if os.path.exists(fpath):
                files.append({'name':   meta['file'],
                               'url':    f'/music-cache/{meta["file"]}',
                               'title':  meta.get('title', ''),
                               'artist': meta.get('artist', '')})
    return files


# ── Announcement (break musical) ─────────────────────────────────────────────

_ANNOUNCEMENT_DAYS = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
_announcement_cache: dict = {'audio': None, 'valid_until': '', 'radio_name': ''}
_announcement_generating = False


def _build_announcement() -> bytes | None:
    """Gera TTS com os próximos itens da grade. Retorna bytes MP3 ou None."""
    import asyncio, sys, os, tempfile, yaml, edge_tts
    from datetime import datetime as _dt

    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
    except Exception:
        return None

    if not cfg.get('announcements', {}).get('enabled', True):
        return None

    schedule   = cfg.get('schedule', [])
    radio_name = cfg.get('radio', {}).get('name', 'RadioIA')
    vinheta    = cfg.get('vinheta', {})
    voice      = vinheta.get('voice', 'pt-BR-FranciscaNeural')
    rate       = vinheta.get('rate', '+15%')

    now        = _dt.now()
    today_str  = now.strftime('%Y-%m-%d')
    now_time   = now.strftime('%H:%M')
    today_wd   = now.weekday()

    upcoming = []
    for entry in schedule:
        entry_date = entry.get('date')
        if entry_date and str(entry_date) != today_str:
            continue
        t = entry.get('time', '')
        if t <= now_time:
            continue
        days = entry.get('days')
        if days and not any(_ANNOUNCEMENT_DAYS.get(str(d).lower(), -1) == today_wd for d in days):
            continue
        label = entry.get('label', '')
        if not label:
            srcs = entry.get('sources', [])
            label = 'Replay' if entry.get('replay_of') else ', '.join(str(s) for s in srcs)
        h, m = t.split(':')
        upcoming.append({'time': t, 'display': f"{int(h)}h{m}", 'label': label})

    upcoming.sort(key=lambda x: x['time'])
    upcoming = upcoming[:3]

    if not upcoming:
        return None

    cache = _announcement_cache
    valid_until = upcoming[0]['time']
    if cache['audio'] and cache['valid_until'] == valid_until and cache['radio_name'] == radio_name:
        return cache['audio']

    # Monta texto do break
    parts = [f"{u['label']} às {u['display']}" for u in upcoming]
    if len(parts) == 1:
        items_text = parts[0]
    else:
        items_text = ', '.join(parts[:-1]) + ' e ' + parts[-1]
    text = f"Você está na {radio_name}. Em breve: {items_text}."

    tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    tmp.close()
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        async def _gen():
            await edge_tts.Communicate(text, voice, rate=rate).save(tmp.name)

        asyncio.run(_gen())
        with open(tmp.name, 'rb') as f:
            audio = f.read()
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    cache['audio']       = audio
    cache['valid_until'] = valid_until
    cache['radio_name']  = radio_name
    return audio


# ── Routes ────────────────────────────────────────────────────────────────────

def _get_radio_name() -> str:
    try:
        import yaml
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        return cfg.get('radio', {}).get('name', 'RadioIA')
    except Exception:
        return 'RadioIA'


def _get_spots_config() -> dict:
    try:
        import yaml
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        sc = cfg.get('spots_config', {})
        return {
            'fallback_every':          int(sc.get('fallback_every', 0)),
            'between_episodes_every':  int(sc.get('between_episodes_every', 0)),
        }
    except Exception:
        return {'fallback_every': 0, 'between_episodes_every': 0}

@app.route('/')
def index():
    sc = _get_spots_config()
    return render_template_string(
        HTML,
        radio_name=_get_radio_name(),
        spots_fallback_every=sc['fallback_every'],
        between_episodes_every=sc['between_episodes_every'],
    )

@app.route('/api/episodes')
def api_episodes():
    return jsonify(scan_episodes())

def _warm_announcement():
    """Gera o anúncio em background para que a próxima requisição seja imediata."""
    global _announcement_generating
    if _announcement_generating:
        return
    _announcement_generating = True
    try:
        _build_announcement()
    finally:
        _announcement_generating = False


_spot_cache: dict = {'spot': None, 'audio': None, 'expires': 0}

@app.route('/api/spot', methods=['GET', 'HEAD'])
def api_spot():
    import time
    from flask import Response as _Resp, request as _req
    from src.spots import get_next_spot

    now = time.time()
    if _spot_cache['spot'] and now < _spot_cache['expires']:
        spot, audio = _spot_cache['spot'], _spot_cache['audio']
    else:
        result = get_next_spot()
        if not result:
            return '', 204
        spot, audio = result
        _spot_cache.update({'spot': spot, 'audio': audio, 'expires': now + 10})

    headers = {
        'Cache-Control':      'no-cache',
        'X-Spot-Id':          spot['id'],
        'X-Spot-Max-Per-Day': str(spot.get('max_per_day', 9999)),
    }
    if _req.method == 'HEAD':
        return _Resp('', headers=headers)
    return _Resp(audio, mimetype='audio/mpeg', headers=headers)

@app.route('/api/announcement')
def api_announcement():
    import io, threading
    from datetime import datetime as _dt
    from flask import Response as _Resp

    cache = _announcement_cache
    sched_bytes = None
    if cache['audio'] and cache['valid_until']:
        if _dt.now().strftime('%H:%M') < cache['valid_until']:
            sched_bytes = cache['audio']

    if not sched_bytes:
        threading.Thread(target=_warm_announcement, daemon=True).start()
        return '', 204

    # Tenta prepender o clip de hora atual
    try:
        from src.time_clips import get_time_clip
        from pydub import AudioSegment
        now = _dt.now()
        time_bytes = get_time_clip(now.hour, now.minute)
        if time_bytes:
            t_audio = AudioSegment.from_mp3(io.BytesIO(time_bytes))
            s_audio = AudioSegment.from_mp3(io.BytesIO(sched_bytes))
            combined = t_audio + AudioSegment.silent(250) + s_audio
            buf = io.BytesIO()
            combined.export(buf, format='mp3', bitrate='128k')
            audio = buf.getvalue()
        else:
            audio = sched_bytes
    except Exception:
        audio = sched_bytes

    return _Resp(audio, mimetype='audio/mpeg', headers={'Cache-Control': 'no-cache'})

@app.route('/api/next-scheduled')
def api_next_scheduled():
    _DAYS = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
    try:
        import yaml
        from datetime import datetime as _dt
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        schedule = cfg.get('schedule', [])
        now        = _dt.now()
        today_str  = now.strftime('%Y-%m-%d')
        now_time   = now.strftime('%H:%M')
        today_wd   = now.weekday()

        upcoming = []
        for entry in schedule:
            entry_date = entry.get('date')
            if entry_date and str(entry_date) != today_str:
                continue
            t = entry.get('time', '')
            if t <= now_time:
                continue
            days = entry.get('days')
            if days and not any(_DAYS.get(str(d).lower(), -1) == today_wd for d in days):
                continue
            label = entry.get('label', '')
            if not label:
                sources = entry.get('sources', [])
                label = 'Replay' if entry.get('replay_of') else ', '.join(str(s) for s in sources)
            h, m = t.split(':')
            upcoming.append({'time': t, 'time_display': f"{int(h)}h{m}", 'label': label})

        if not upcoming:
            return jsonify(None)
        upcoming.sort(key=lambda x: x['time'])
        return jsonify(upcoming[0])
    except Exception:
        return jsonify(None)

@app.route('/api/music-files')
def api_music_files():
    return jsonify(scan_music_files())

@app.route('/audio/<path:episode_id>')
def serve_audio(episode_id):
    ep_path   = os.path.join(OUTPUT_DIR, episode_id)
    meta_path = os.path.join(ep_path, 'episode.json')
    if os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                audio_path = json.load(f).get('audio_path')
            if audio_path and os.path.exists(audio_path):
                return send_from_directory(
                    os.path.dirname(audio_path),
                    os.path.basename(audio_path),
                    mimetype='audio/mpeg'
                )
        except Exception:
            pass
    return send_from_directory(ep_path, 'episode.mp3', mimetype='audio/mpeg')

@app.route('/music/<path:filename>')
def serve_music(filename):
    return send_from_directory(MUSIC_DIR, filename)

@app.route('/music-cache/<path:filename>')
def serve_music_cache(filename):
    return send_from_directory(os.path.join(MUSIC_DIR, 'cache', 'jamendo'), filename)

@app.route('/music-extra/<path:filepath>')
def serve_music_extra(filepath):
    # filepath é o caminho absoluto com / como separador
    abs_path = filepath if os.path.isabs(filepath) else '/' + filepath
    abs_path = abs_path.replace('/', os.sep)
    return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path))

@app.route('/api/fallback-intro')
def api_fallback_intro():
    if os.path.exists(FALLBACK_INTRO_PATH):
        return send_from_directory('output', '_fallback_intro.mp3', mimetype='audio/mpeg')
    return '', 404


def open_browser():
    webbrowser.open('http://localhost:5000')


if __name__ == '__main__':
    try:
        import yaml as _yaml
        with open('config.yaml', 'r', encoding='utf-8') as _f:
            _cfg = _yaml.safe_load(_f)
        _vinheta = _cfg.get('vinheta', {})
        _tc_voice = _vinheta.get('voice', 'pt-BR-FranciscaNeural')
        _tc_rate  = _vinheta.get('rate', '+15%')
    except Exception:
        _tc_voice, _tc_rate = 'pt-BR-FranciscaNeural', '+15%'

    from src.time_clips import generate_atomic_clips as _gen_clips
    from src.spots import warmup as _warm_spots
    threading.Thread(target=_generate_fallback_intro, daemon=True).start()
    threading.Thread(target=lambda: _gen_clips(_tc_voice, _tc_rate), daemon=True).start()
    threading.Thread(target=_warm_announcement, daemon=True).start()
    threading.Thread(target=_warm_spots, daemon=True).start()
    threading.Thread(target=_auto_download_jamendo, daemon=True).start()
    threading.Timer(1.0, open_browser).start()
    n_music = len(scan_music_files())
    print(f"{_get_radio_name()} rodando em http://localhost:5000")
    print(f"Musicas no fallback: {n_music} | Polling: {POLL_INTERVAL_SECONDS}s")
    app.run(host='0.0.0.0', port=5000, debug=False)
