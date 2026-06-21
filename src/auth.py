import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

logger = logging.getLogger(__name__)


def get_youtube_credentials() -> Credentials | None:
    """
    Lê e (se preciso) renova o token OAuth do YouTube a partir de token.json.

    Nunca inicia um fluxo interativo (run_local_server) — isso exige um
    browser e uma porta acessível, o que não existe no servidor headless.
    O token deve ser gerado uma vez localmente com authenticate_and_deploy.py
    e copiado para o servidor; aqui só se faz leitura + refresh automático.
    Retorna None se não houver token válido (o bot cai para YOUTUBE_API_KEY).
    """
    if not os.path.exists("token.json"):
        return None

    try:
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    except Exception:
        logger.warning("[auth] token.json inválido ou corrompido", exc_info=True)
        return None

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            logger.warning(
                "[auth] falha ao renovar token do YouTube — rode "
                "authenticate_and_deploy.py novamente",
                exc_info=True,
            )
            return None
        with open("token.json", "w") as f:
            f.write(creds.to_json())
        return creds

    logger.warning("[auth] token.json sem refresh_token válido — reautentique localmente")
    return None
