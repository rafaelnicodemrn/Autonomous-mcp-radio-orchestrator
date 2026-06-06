import litellm
from datetime import datetime, timezone

litellm.suppress_debug_info = True

LOCUTOR_KEYS = ['LOCUTOR_A', 'LOCUTOR_B', 'LOCUTOR_C']


def _format_views(views: int) -> str:
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f} milhoes de visualizacoes"
    if views >= 1_000:
        return f"{int(views / 1_000)} mil visualizacoes"
    return f"{views} visualizacoes" if views else ''


def _format_age(published_at: str) -> str:
    try:
        dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days == 0:
            hours = delta.seconds // 3600
            return f"ha {hours}h" if hours > 0 else "agora"
        if days == 1:
            return "ontem"
        if days <= 6:
            return f"ha {days} dias"
        return f"ha {days // 7} semana(s)"
    except Exception:
        return ''


def _narrator_block(narrators: list[dict]) -> str:
    lines = []
    for i, n in enumerate(narrators):
        key = LOCUTOR_KEYS[i]
        lines.append(f"- {n['name']} ({key}): {n.get('personality', '')}")
    return '\n'.join(lines)


def _format_block(narrators: list[dict]) -> str:
    lines = ['FORMATO OBRIGATORIO (uma fala por linha):']
    for i, n in enumerate(narrators):
        key = LOCUTOR_KEYS[i]
        lines.append(f"[{key}]: fala de {n['name']}")
    return '\n'.join(lines)


def _build_video_card(i: int, item: dict) -> str:
    views_str = _format_views(item.get('views', 0))
    age_str = _format_age(item.get('published_at', ''))
    meta = ', '.join(filter(None, [views_str, age_str]))
    context = item.get('text', '') or item.get('description', '')
    context_hint = f"\nContexto: {context}" if context else ''
    comments = item.get('comments', [])
    comments_hint = ''
    if comments:
        lines = [f'  - {c["author"]}: "{c["text"]}" ({c["likes"]} curtidas)' for c in comments]
        comments_hint = '\nComentarios:\n' + '\n'.join(lines)
    return (
        f"[Video {i}]\n"
        f"Titulo: {item['title']}\n"
        f"Canal: {item.get('channel', item.get('source_name', ''))}\n"
        f"Dados: {meta}"
        f"{context_hint}{comments_hint}"
    )


def _build_news_card(i: int, item: dict) -> str:
    age_str = _format_age(item.get('published_at', ''))
    return (
        f"[Noticia {i}]\n"
        f"Titulo: {item['title']}\n"
        f"Fonte: {item.get('source_name', '')}\n"
        f"Publicada: {age_str}\n"
        f"Conteudo: {item.get('text', '')}"
    )


def _build_receita_card(i: int, item: dict) -> str:
    return (
        f"[Receita: {item['title']}]\n"
        f"Culinária: {item.get('channel', '')}\n"
        f"{item.get('text', '')}"
    )


def _build_horoscopo_card(i: int, item: dict) -> str:
    return (
        f"[Signo {i}: {item['title']}]\n"
        f"Previsao: {item.get('text', '')}"
    )


def _build_reddit_card(i: int, item: dict) -> str:
    score    = item.get('views', 0)
    comments = item.get('num_comments', 0)
    age_str  = _format_age(item.get('published_at', ''))
    score_str = _format_views(score) if score >= 1000 else f"{score} upvotes"
    meta = ', '.join(filter(None, [
        score_str,
        f"{comments} comentários" if comments else '',
        age_str,
    ]))
    context = item.get('text', '')
    context_hint = f"\nConteudo: {context}" if context else ''
    return (
        f"[Post {i}]\n"
        f"Titulo: {item['title']}\n"
        f"Subreddit: {item.get('channel', '')}\n"
        f"Dados: {meta}"
        f"{context_hint}"
    )


def _build_trivia_card(i: int, item: dict) -> str:
    return (
        f"[Pergunta {i}]\n"
        f"Pergunta: {item['title']}\n"
        f"{item.get('text', '')}"
    )


DEFAULT_MODEL = 'claude-sonnet-4-6'


def generate_script(items: list[dict], narrators: list[dict], source_config: dict,
                    is_first_of_day: bool = True,
                    station_name: str = 'RadioIA',
                    model: str = DEFAULT_MODEL,
                    api_base: str | None = None) -> str:

    n = min(len(narrators), 3)
    active = narrators[:n]
    source_type = source_config.get('type', 'youtube')
    source_name = source_config.get('name', station_name)
    names = [nr['name'] for nr in active]

    if source_type == 'whatsapp':
        cards = [_build_whatsapp_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _whatsapp_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    elif source_type == 'biblia':
        cards = [_build_biblia_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _biblia_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    elif source_type == 'filmes':
        cards = [_build_filmes_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _filmes_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    elif source_type == 'url':
        cards = [_build_news_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _url_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    elif source_type == 'receitas':
        cards = [_build_receita_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _receitas_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    elif source_type == 'horoscopo':
        cards = [_build_horoscopo_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _horoscopo_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    elif source_type == 'rss' or source_type == 'efemerides':
        cards = [_build_news_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _news_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    elif source_type == 'reddit':
        cards = [_build_reddit_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _reddit_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    elif source_type == 'trivia':
        cards = [_build_trivia_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _trivia_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)
    else:
        cards = [_build_video_card(i, item) for i, item in enumerate(items, 1)]
        prompt = _radio_prompt(active, names, source_name, '\n\n'.join(cards), is_first_of_day, station_name)

    kwargs = {'api_base': api_base} if api_base else {}
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        **kwargs
    )
    return response.choices[0].message.content


def _radio_prompt(narrators: list[dict], names: list[str], station: str,
                  content: str, is_first_of_day: bool = True,
                  station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]
    falas_por_video = 3 + n

    solo_note = (
        "- E um programa solo: use so [LOCUTOR_A], tom envolvente e direto ao ouvinte"
        if n == 1 else
        f"- Distribua as falas entre os {n} apresentadores de forma equilibrada"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA DO DIA: {names_str} dao bom dia, se apresentam pelo nome, "
            f'dizem que os ouvintes estao na {station_name}, '
            f'apresentam o segmento "{station}" e antecipam os destaques com energia (4-5 falas)'
        )
        encerramento = "4. Encerramento: convide o ouvinte a continuar ouvindo a programacao do dia (2-3 falas)"
    else:
        abertura = (
            f'1. ENTRADA DE SEGMENTO: entre como continuacao da programacao — algo como '
            f'"E chegou a hora do {station}!", "Voltamos com {station}..." ou similar. '
            f'SEM bom dia, SEM apresentacao de nomes. (2-3 falas)'
        )
        encerramento = "4. Encerramento rapido sinalizando que a programacao continua (1-2 falas)"

    return f"""Voce e um roteirista de radio FM brasileira.
Crie o roteiro do segmento "{station}".

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite estritamente o perfil de cada apresentador em todas as falas.

ESTRUTURA:
{abertura}
2. Para cada video: {falas_por_video} falas — o que e, canal, popularidade, quando, por que vale ver
3. Transicoes variadas entre videos ("Proximo!", "E tem mais!", "Olha so...", "Mudando de assunto...")
{encerramento}

REGRAS:
- Cada fala: maximo 2 sentencas — radio e velocidade
- Mencione canal, visualizacoes e data em cada video
- Diga "link do video [numero] nas notas do episodio"
- Use energia: exclamacoes, reacoes naturais de cada perfil
- Varie quem abre cada bloco de video
- Comentarios de inscritos: cite apenas se genuinamente interessante, maximo 1 por video, nomeie o autor
{solo_note}
- NAO invente informacoes

VIDEOS DO DIA:
{content}

Roteiro:"""


def _news_prompt(narrators: list[dict], names: list[str], source_name: str,
                 content: str, is_first_of_day: bool = True,
                 station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Apresentacao solo: fale diretamente com o ouvinte, tom jornalistico e preciso"
        if n == 1 else
        f"- Distribua as falas de forma equilibrada entre os {n} apresentadores"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA DO DIA: {names_str} dao bom dia, se apresentam, "
            f'dizem que os ouvintes estao na {station_name} e anunciam '
            f'o boletim "{source_name}" com os principais temas (3-4 falas)'
        )
        encerramento = "4. Encerramento: convide o ouvinte a continuar na programacao (2-3 falas)"
    else:
        abertura = (
            f'1. ENTRADA DE BOLETIM: entre direto como um novo bloco — '
            f'"Agora, {source_name}...", "E nas noticias..." ou similar. '
            f'SEM bom dia, SEM reapresentacao. (2 falas)'
        )
        encerramento = "4. Encerramento curto indicando que a programacao segue (1-2 falas)"

    return f"""Voce e um roteirista de boletim de noticias de radio brasileiro.
Crie o roteiro do "{source_name}".

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador mesmo no tom jornalistico.

ESTRUTURA:
{abertura}
2. Para cada noticia: 2-3 falas — o que aconteceu, fonte, contexto rapido
3. Transicoes jornalisticas ("Em outras noticias...", "Tambem nesta edicao...", "No cenario de...")
{encerramento}

REGRAS:
- Cada fala: maximo 2 sentencas
- Mencione sempre a fonte (G1, Folha, etc.)
- Diga "materia completa nas notas, noticia [numero]"
- Tom informativo — pode ter leveza mas sem exageros
{solo_note}
- NAO invente informacoes

NOTICIAS:
{content}

Roteiro:"""


def _trivia_prompt(narrators: list[dict], names: list[str], source_name: str,
                   content: str, is_first_of_day: bool = True,
                   station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block   = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Programa solo: alterne entre apresentar a pergunta e revelar a resposta, tom animado"
        if n == 1 else
        f"- Distribua: um apresentador lê a pergunta, outro revela a resposta — alterne a cada pergunta"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA: {names_str} dao bom dia, dizem que os ouvintes estao na {station_name}, "
            f"apresentam o quiz \"{source_name}\" "
            f"com energia de game show e convidam o ouvinte a participar (3-4 falas)"
        )
        encerramento = "5. Encerramento: pontuacao imaginaria, elogio ao ouvinte, convide a ficar na programacao (2-3 falas)"
    else:
        abertura = (
            f'1. ENTRADA: entre como um novo bloco animado — "E hora do {source_name}!", '
            f'"Bora testar seus conhecimentos!" ou similar. SEM bom dia. (2 falas)'
        )
        encerramento = "5. Encerramento rapido celebrando o quiz e sinalizando que a programacao continua (1-2 falas)"

    return f"""Voce e um roteirista de programa de quiz para radio FM brasileira.
Crie o roteiro do segmento "{source_name}" — um quiz divertido e interativo.

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador mesmo no tom de game show.

ESTRUTURA:
{abertura}
2. Para cada pergunta:
   - Apresente com energia (traduza para portugues se necessario)
   - Leia as alternativas A, B, C e D
   - Convide o ouvinte a pensar: "pense ai...", "voce sabe?", "nao vale pesquisar!" etc. (1 fala curta)
   - Revele a resposta correta com reacao
   - Acrescente 1 frase de curiosidade ou contexto sobre a resposta
3. Transicoes animadas entre perguntas: "Proxima!", "Ficou facil? Vamos dificultar!", "Essa e para os experts!", etc.
4. Reaja a perguntas dificeis ou categorias inusitadas com personalidade
{encerramento}

REGRAS:
- Todo o conteudo em portugues — traduza perguntas e respostas se necessario
- Cada fala: maximo 2 sentencas
- Tom de game show: animado, dinamico, levemente competitivo
- Reactions genuinas: surpresa, deboche amigavel, admiracao
{solo_note}
- NAO invente informacoes alem do que esta nas perguntas

PERGUNTAS:
{content}

Roteiro:"""


def _reddit_prompt(narrators: list[dict], names: list[str], source_name: str,
                   content: str, is_first_of_day: bool = True,
                   station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block   = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Apresentacao solo: comente os posts diretamente com o ouvinte, tom de conversa"
        if n == 1 else
        f"- Distribua as falas de forma equilibrada entre os {n} apresentadores"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA DO DIA: {names_str} dao bom dia, dizem que os ouvintes estao na {station_name}, "
            f"apresentam o \"{source_name}\" "
            f"explicando que vao trazer o que esta bombando na internet hoje (3-4 falas)"
        )
        encerramento = "4. Encerramento: convide o ouvinte a continuar na programacao (2 falas)"
    else:
        abertura = (
            f'1. ENTRADA: entre direto no assunto — "O que ta bombando no Reddit agora...", '
            f'"A internet ta discutindo..." ou similar. SEM bom dia. (2 falas)'
        )
        encerramento = "4. Encerramento rapido sinalizando que a programacao continua (1-2 falas)"

    return f"""Voce e um roteirista de radio FM brasileira especializado em cultura digital.
Crie o roteiro do segmento "{source_name}" — os posts mais populares do Reddit brasileiro hoje.

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador em todas as falas.

CONTEXTO: estes sao os posts que mais geraram engajamento hoje em cada subreddit — ja estao ordenados por popularidade.

ESTRUTURA:
{abertura}
2. Para cada post: 2-3 falas — o que e, de qual subreddit, por que esta repercutindo, o que isso diz sobre o momento
3. Transicoes variadas: "No r/investimentos ta bombando...", "A galera do r/brasil discutindo...", "Isso aqui gerou debate..."
{encerramento}

REGRAS:
- Cada fala: maximo 2 sentencas
- Mencione sempre o subreddit — da contexto sobre que comunidade esta discutindo
- Use o conteudo do post quando disponivel para enriquecer o comentario
- Conecte posts de subreddits diferentes quando houver relacao tematica
- Reaja com personalidade: curiosidade, critica, humor conforme o perfil de cada apresentador
{solo_note}
- NAO invente informacoes

POSTS:
{content}

Roteiro:"""


def _horoscopo_prompt(narrators: list[dict], names: list[str], source_name: str,
                      content: str, is_first_of_day: bool = True,
                      station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block   = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Apresentacao solo: apresente cada signo diretamente ao ouvinte, tom mistico e caloroso"
        if n == 1 else
        "- Cada apresentador 'assume' um signo — um le a previsao enquanto o outro reage ou complementa"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA DO DIA: {names_str} dao bom dia, dizem que os ouvintes estao na {station_name} "
            f"e apresentam o {source_name} "
            f"com tom mistico — mencione que os astros trazem mensagens especiais hoje (2-3 falas)"
        )
        encerramento = "4. Encerramento: deseje um ótimo dia aos ouvintes e convide a continuar na programacao (2 falas)"
    else:
        abertura = (
            f'1. ENTRADA: entre com mistério — "Os astros têm mensagem para dois signos...", '
            f'"Hora de saber o que o universo reserva..." ou similar. SEM bom dia. (1-2 falas)'
        )
        encerramento = "4. Encerramento curto desejando que as energias se manifestem (1-2 falas)"

    return f"""Voce e um roteirista de horoscopo para radio FM brasileira.
Crie o roteiro do segmento "{source_name}" com as previsoes de hoje para dois signos.

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador mesmo no tom mistico.

ESTRUTURA:
{abertura}
2. Para cada signo:
   - Anuncie o signo com energia e mistério: "Para os nativos de {{signo}}...", "Quem e de {{signo}}..."
   - Apresente a previsao de forma envolvente e pessoal — fale diretamente com o ouvinte do signo
   - Destaque os pontos principais: amor, trabalho, saude ou mensagem especial do dia
   - 3-4 falas por signo
3. Transicao entre os signos com algo do tipo: "E para o proximo signo de hoje..."
{encerramento}

REGRAS:
- Cada fala: maximo 2-3 sentencas
- Tom: mistico, caloroso, pessoal — o ouvinte deve sentir que a mensagem e para ele
- Use expressoes como: "Os astros indicam...", "Esta e uma data propicia para...", "O universo pede..."
- Baseie-se fielmente no conteudo das previsoes fornecidas
- Se o conteudo for escasso, expanda com sabedoria astrologica coerente com o signo
{solo_note}

PREVISOES DE HOJE:
{content}

Roteiro:"""


def _build_filmes_card(i: int, item: dict) -> str:
    return (
        f"[Filme {i}: {item['title']}]\n"
        f"{item.get('text', '')}"
    )


def _filmes_prompt(narrators: list[dict], names: list[str], source_name: str,
                   content: str, is_first_of_day: bool = True,
                   station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block   = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Apresentacao solo: alterne entre recomendar e reagir, como cinefilo apaixonado"
        if n == 1 else
        "- Um apresentador recomenda, o outro reage — troquem esse papel entre os filmes"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA: {names_str} dao bom dia, dizem que os ouvintes estao na {station_name} "
            f"e apresentam o quadro \"{source_name}\" "
            f"com entusiasmo — criem expectativa sobre os filmes (2-3 falas)"
        )
        encerramento = "5. Encerramento convidando o ouvinte a conferir os filmes e continuar na programacao (2 falas)"
    else:
        abertura = (
            f'1. ENTRADA direta no quadro: "E hora do {source_name}!", '
            f'"Quem ai ama cinema?" ou similar. SEM bom dia. (1-2 falas)'
        )
        encerramento = "5. Encerramento rapido desejando bom cinema (1 fala)"

    return f"""Voce e um roteirista de quadro de cinema para radio FM brasileira.
Crie o roteiro do segmento "{source_name}" — indicacoes de filmes descontraidas e apaixonadas.

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador — inclusive nas preferencias cinematograficas.

ESTRUTURA:
{abertura}
2. Para cada filme (2-3 falas cada):
   - Titulo, genero e ano em tom natural — nao leia como lista
   - Destaque o que torna o filme especial: premissa, diretor, elenco, premios
   - Recomende para que tipo de ocasiao: noite romantica, familia, adrenalina, choro garantido...
   - Reacao do outro apresentador: concordar, discordar com bom humor, complementar
3. Transicoes variadas entre filmes: "Falando em...", "Mudando de genero...", "E pra quem prefere..."
{encerramento}

REGRAS:
- Cada fala: maximo 2 sentencas — radio e velocidade
- Tom: apaixonado por cinema, sem ser esnobe — fale como quem recomenda para amigos
- Mencione nota ou popularidade apenas quando impressionante (ex: "quase 9 de nota!")
- Traduza generos e termos tecnicos para o portugues do dia a dia
- NAO invente informacoes alem das fornecidas
{solo_note}

FILMES:
{content}

Roteiro:"""


def _build_whatsapp_card(i: int, item: dict) -> str:
    return (
        f"[Grupo: {item['title']}]\n"
        f"{item.get('text', '')}"
    )


def _whatsapp_prompt(narrators: list[dict], names: list[str], source_name: str,
                     content: str, is_first_of_day: bool = True,
                     station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block   = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Apresentacao solo: comente os assuntos diretamente com o ouvinte, tom de conversa"
        if n == 1 else
        f"- Distribua as falas de forma equilibrada entre os {n} apresentadores"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA: {names_str} dao bom dia, dizem que os ouvintes estao na {station_name} "
            f'e apresentam o quadro "{source_name}" — o resumo do que rolou no grupo (2-3 falas)'
        )
        encerramento = "4. Encerramento: convide o ouvinte a continuar na programacao (1-2 falas)"
    else:
        abertura = (
            f'1. ENTRADA: entre direto no assunto — "O grupo {source_name} esteve movimentado...", '
            f'"Olha o que rolou no grupo hoje..." ou similar. SEM bom dia. (1-2 falas)'
        )
        encerramento = "4. Encerramento curto sinalizando que a programacao continua (1 fala)"

    return f"""Voce e um roteirista de radio FM brasileira especializado em resumos de grupos de mensagens.
Crie o roteiro do segmento "{source_name}" — o resumo do que aconteceu no grupo de WhatsApp.

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador em todas as falas.

TAREFA:
Leia as mensagens do grupo e identifique os temas, discussões e momentos mais relevantes ou interessantes.
NÃO leia as mensagens na íntegra — sintetize como um quadro de rádio descontraído.
Preserve o tom e o humor das conversas quando relevante.

ESTRUTURA:
{abertura}
2. Destaque os principais assuntos discutidos no grupo (3-5 falas por tema)
3. Mencione momentos engraçados, decisões tomadas ou informações importantes compartilhadas
{encerramento}

REGRAS:
- Cada fala: máximo 2 sentenças
- Não cite nomes completos de pessoas — use "um membro do grupo", "alguém no grupo" ou primeiro nome apenas
- Tom: descontraído, como quem conta fofoca boa para um amigo
- Não invente informações além do que está nas mensagens
- Se o grupo tratou de assuntos sensíveis ou privados, seja discreto e genérico
{solo_note}

MENSAGENS DO GRUPO:
{content}

Roteiro:"""


def _build_biblia_card(i: int, item: dict) -> str:
    return (
        f"[Passagem {i}]\n"
        f"Referência: {item['title']}\n"
        f"Livro: {item.get('channel', '')}\n"
        f"{item.get('text', '')}"
    )


def _biblia_prompt(narrators: list[dict], names: list[str], source_name: str,
                   content: str, is_first_of_day: bool = True,
                   station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block   = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Apresentacao solo: conduza a reflexao diretamente com o ouvinte, tom intimo e acolhedor"
        if n == 1 else
        f"- Distribua as falas entre os {n} apresentadores de forma equilibrada"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA: {names_str} dao bom dia, dizem que os ouvintes estao na {station_name} "
            f'e apresentam o quadro "{source_name}" com tom acolhedor e espiritualizado (2-3 falas)'
        )
        encerramento = "4. Encerramento: deseje uma reflexao proveitosa ao ouvinte e convide a continuar na programacao (2 falas)"
    else:
        abertura = (
            f'1. ENTRADA: entre com leveza espiritual — "Chegou o momento da nossa Palavra do Dia...", '
            f'"Paramos um instante para uma reflexao especial..." ou similar. SEM bom dia. (1-2 falas)'
        )
        encerramento = "4. Encerramento curto desejando paz e bencaos ao ouvinte (1-2 falas)"

    return f"""Voce e um roteirista de quadro espiritual para radio FM brasileira.
Crie o roteiro do segmento "{source_name}" — uma reflexao sobre uma passagem biblica.

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador mesmo no tom espiritualizado.

ESTRUTURA:
{abertura}
2. Leia a passagem biblica com calma e reverencia (1-2 falas)
3. Reflexao sobre o significado e aplicacao pratica na vida cotidiana (3-5 falas)
4. Convide o ouvinte a guardar essa mensagem no coracao durante o dia
{encerramento}

REGRAS CRITICAS:
- Refira-se ao trecho sempre pela forma por extenso: "capitulo X, versiculo Y" — NUNCA use o formato numerico "X:Y" pois o audio nao le corretamente
- Cada fala: maximo 2-3 sentencas
- Tom: acolhedor, reflexivo, espiritualizado — como um pastor ou capelao de radio
- Nao mencione links, notas de episodio ou fontes externas — o conteudo e a propria passagem
- Conecte a mensagem biblica a situacoes concretas do dia a dia do ouvinte brasileiro
- NAO invente versos ou trechos que nao estejam na passagem fornecida
{solo_note}

PASSAGEM BIBLICA:
{content}

Roteiro:"""


def _url_prompt(narrators: list[dict], names: list[str], source_name: str,
                content: str, is_first_of_day: bool = True,
                station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block   = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Apresentacao solo: adapte o tom ao tipo de conteudo, fale diretamente com o ouvinte"
        if n == 1 else
        f"- Distribua as falas entre os {n} apresentadores; quem reage, quem comenta, quem contextualiza"
    )

    if is_first_of_day:
        abertura = f"1. ABERTURA: {names_str} dao bom dia, dizem que estao na {station_name} e apresentam o que vem por ai (2 falas)"
        encerramento = "4. Encerramento convidando o ouvinte a continuar na programacao (1-2 falas)"
    else:
        abertura = "1. ENTRADA direta no conteudo, sem bom dia nem apresentacao de nomes (1-2 falas)"
        encerramento = "4. Encerramento rapido sinalizando continuidade da programacao (1 fala)"

    return f"""Voce e um roteirista de radio FM brasileira.
Receberá conteudo extraido de uma pagina web — pode ser noticia, artigo, produto, curiosidade, piada, receita, etc.

TAREFA:
1. Identifique o tipo de conteudo e escolha o tom adequado:
   - Noticia/artigo: informativo e contextualizado
   - Produto/lancamento: entusiasmado, destaque beneficios
   - Curiosidade/ciencia: admirado, exploratorio
   - Humor/piada: leve, bem-humorado — entregue a piada com timing
   - Outros: adapte naturalmente
2. Crie um segmento de radio envolvente, como se fosse um quadro da programacao

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador.

ESTRUTURA:
{abertura}
2. Desenvolvimento do conteudo (4-6 falas): apresente, contextualize, reaja
3. Destaque ou curiosidade extra relacionada ao conteudo (1-2 falas)
{encerramento}

REGRAS:
- Cada fala: maximo 2 sentencas
- NAO mencione "li num site", "encontrei na internet" — apresente como quadro da programacao
- NAO invente informacoes que nao estejam no conteudo fornecido
{solo_note}

CONTEUDO:
{content}

Roteiro:"""


def _receitas_prompt(narrators: list[dict], names: list[str], source_name: str,
                     content: str, is_first_of_day: bool = True,
                     station_name: str = 'RadioIA') -> str:
    n = len(narrators)
    narrator_block = _narrator_block(narrators)
    format_block   = _format_block(narrators)
    names_str = ', '.join(names[:-1]) + f' e {names[-1]}' if n > 1 else names[0]

    solo_note = (
        "- Apresentacao solo: alterne entre apresentar a receita e reagir a ela, como se estivesse experimentando mentalmente"
        if n == 1 else
        "- Um apresentador conduz a receita, o outro reage, faz perguntas e acrescenta dicas — troquem esse papel naturalmente"
    )

    if is_first_of_day:
        abertura = (
            f"1. ABERTURA: {names_str} dao bom dia, dizem que os ouvintes estao na {station_name} "
            f"e apresentam o quadro \"{source_name}\" "
            f"com apetite — criem expectativa sobre o prato do dia (2-3 falas)"
        )
        encerramento = "5. Encerramento: convide o ouvinte a experimentar em casa e continue na programacao (2 falas)"
    else:
        abertura = (
            f'1. ENTRADA: entrem direto com curiosidade — "Boa tarde, chegou a hora do {source_name}!", '
            f'"Voces ja decidiram o que vao cozinhar hoje?" ou similar. SEM bom dia. (1-2 falas)'
        )
        encerramento = "5. Encerramento rapido desejando bom apetite e sinalizando que a programacao continua (1 fala)"

    return f"""Voce e um roteirista de quadro culinario para radio FM brasileira.
Crie o roteiro do segmento "{source_name}" — um quadro de receitas descontraido e apetitoso.

APRESENTADORES:
{narrator_block}

{format_block}

ATENCAO: responda APENAS com as linhas do roteiro no formato acima. Sem titulos, sem markdown, sem asteriscos, sem tracejados, sem comentarios fora do roteiro. Use português correto com todos os acentos (ã, é, ê, ç, à, â, í, ó, ô, ú etc.) — nunca escreva "voce", "nao", "tambem", escreva "você", "não", "também".

PERSONALIDADES: respeite o perfil de cada apresentador — inclusive na culinaria.

ESTRUTURA:
{abertura}
2. APRESENTACAO DO PRATO (2-3 falas):
   - Nome do prato e sua origem/culinaria
   - Historia ou curiosidade sobre o prato
   - Em que ocasiao preparar (jantar romantico, almoço de domingo, festa, dia a dia)
3. INGREDIENTES (2-3 falas):
   - Liste os ingredientes de forma conversacional — nao como uma lista seca
   - Destaque ingredientes inusitados ou importantes
   - Sugira substituicoes faceis se houver ingredientes dificeis de encontrar
4. PREPARO (3-4 falas):
   - Explique os passos principais de forma clara e apetitosa
   - Use linguagem sensorial: cores, cheiros, texturas, sons
   - Dica de ouro: um segredo ou truque que faz diferenca
{encerramento}

REGRAS:
- Cada fala: maximo 3 sentencas
- Tom: descontraido, apetitoso, como conversa entre amigos na cozinha
- Traduza os nomes de ingredientes e tecnicas para portugues brasileiro
- Reaja com expressoes de sabor: "Nossa, deve ficar incrivel!", "Ja da agua na boca..."
- Se o prato for de culinaria estrangeira, mencione onde e popular e como os brasileiros podem adaptar
{solo_note}
- NAO invente ingredientes ou passos que nao estejam na receita

RECEITA:
{content}

Roteiro:"""
