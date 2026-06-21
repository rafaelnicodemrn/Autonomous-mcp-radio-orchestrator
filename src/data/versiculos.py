# src/data/versiculos.py
# Lista curada de versículos para o cabeçalho do briefing matinal.
#
# Propositalmente separada do plugin plugins/biblia.py ("Palavra do Dia"):
# este módulo é só uma linha de texto local, sem chamada de API e sem
# geração de episódio em áudio — o plugin biblia.py continua sendo a fonte
# completa usada em /fe e /briefing. Curadoria alinhada à fé católica
# tradicional do usuário, com foco em conforto e sabedoria (evita
# passagens duras demais para abrir o dia).
from datetime import date

VERSICULOS = [
    {"texto": "O Senhor é o meu pastor; nada me faltará.", "referencia": "Salmos 23:1"},
    {
        "texto": "Tudo posso naquele que me fortalece.",
        "referencia": "Filipenses 4:13",
    },
    {
        "texto": "Entrega o teu caminho ao Senhor; confia nele, e ele tudo fará.",
        "referencia": "Salmos 37:5",
    },
    {
        "texto": "Não temas, porque eu sou contigo; não te assombres, porque eu sou o teu Deus.",
        "referencia": "Isaías 41:10",
    },
    {
        "texto": "O amor é paciente, o amor é bondoso.",
        "referencia": "1 Coríntios 13:4",
    },
    {
        "texto": "Vinde a mim, todos os que estais cansados e oprimidos, e eu vos aliviarei.",
        "referencia": "Mateus 11:28",
    },
    {
        "texto": (
            "Não andeis ansiosos por coisa alguma; em tudo, pela oração e súplica, "
            "com ações de graças, apresentai a Deus as vossas petições."
        ),
        "referencia": "Filipenses 4:6",
    },
    {
        "texto": (
            "Sei que os planos que tenho para vocês são planos de fazê-los prosperar "
            "e não de causar-lhes dano, planos de dar-lhes esperança num futuro."
        ),
        "referencia": "Jeremias 29:11",
    },
    {
        "texto": (
            "Esforça-te e tem bom ânimo; não temas, nem te espantes, porque o Senhor, "
            "teu Deus, é contigo, por onde quer que andares."
        ),
        "referencia": "Josué 1:9",
    },
    {
        "texto": "O Senhor é a minha luz e a minha salvação; a quem temerei?",
        "referencia": "Salmos 27:1",
    },
    {
        "texto": "Bendito o homem que confia no Senhor, e cuja esperança é o Senhor.",
        "referencia": "Jeremias 17:7",
    },
    {
        "texto": "Lancem sobre ele toda a sua ansiedade, porque ele tem cuidado de vocês.",
        "referencia": "1 Pedro 5:7",
    },
    {
        "texto": "A alegria do Senhor é a vossa força.",
        "referencia": "Neemias 8:10",
    },
    {
        "texto": (
            "Buscai primeiro o Reino de Deus e a sua justiça, e tudo o mais vos será "
            "acrescentado."
        ),
        "referencia": "Mateus 6:33",
    },
    {
        "texto": "Tudo o que pedirdes na oração, crede que o recebereis, e assim vos acontecerá.",
        "referencia": "Marcos 11:24",
    },
    {
        "texto": "O Senhor é bom; a sua misericórdia dura para sempre.",
        "referencia": "Salmos 100:5",
    },
    {
        "texto": (
            "Confia no Senhor de todo o teu coração, e não te apoies no teu próprio "
            "entendimento."
        ),
        "referencia": "Provérbios 3:5",
    },
    {
        "texto": "Deus é o nosso refúgio e fortaleza, socorro bem presente na angústia.",
        "referencia": "Salmos 46:1",
    },
    {
        "texto": "Pedi, e dar-se-vos-á; buscai, e encontrareis; bati, e abrir-se-vos-á.",
        "referencia": "Mateus 7:7",
    },
    {
        "texto": "As misericórdias do Senhor se renovam a cada manhã; grande é a sua fidelidade.",
        "referencia": "Lamentações 3:22-23",
    },
    {
        "texto": "Em paz me deito e logo durmo, porque só tu, Senhor, me fazes repousar seguro.",
        "referencia": "Salmos 4:8",
    },
    {
        "texto": "Permanecei em mim, e eu permanecerei em vós.",
        "referencia": "João 15:4",
    },
    {
        "texto": "A paz vos deixo, a minha paz vos dou; não a dou como o mundo a dá.",
        "referencia": "João 14:27",
    },
    {
        "texto": "Maria guardava todas estas coisas, conferindo-as em seu coração.",
        "referencia": "Lucas 2:19",
    },
    {
        "texto": "Quem habita no esconderijo do Altíssimo, à sombra do Onipotente descansará.",
        "referencia": "Salmos 91:1",
    },
]


def get_verse_of_day() -> dict:
    """
    Seleciona um versículo de forma determinística pelo dia do ano, para
    não variar se o briefing rodar mais de uma vez no mesmo dia.
    """
    index = date.today().timetuple().tm_yday % len(VERSICULOS)
    return VERSICULOS[index]


def format_verse_of_day() -> str:
    """Retorna o versículo do dia já formatado para exibição."""
    verse = get_verse_of_day()
    return f'📖 "{verse["texto"]}" — {verse["referencia"]}'
