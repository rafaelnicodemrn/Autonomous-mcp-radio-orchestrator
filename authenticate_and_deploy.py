"""
authenticate_and_deploy.py — Autentica o YouTube OAuth localmente e publica
o token.json resultante no servidor de produção via gcloud CLI.

Por quê rodar isso só localmente: o fluxo OAuth (run_local_server) abre um
browser e troca o código de autorização pelo token NO MESMO PROCESSO que
gerou a URL de consentimento (o code_verifier do PKCE vive em memória nesse
processo). Tentar gerar a URL num lugar e trocar o código em outro (ex: no
servidor, sem browser) é a causa do erro "Missing code verifier" — por isso
o fluxo interativo nunca deve rodar no servidor (ver src/auth.py).

Uso:
    python authenticate_and_deploy.py
    python authenticate_and_deploy.py --skip-restart   # só copia o token
    python authenticate_and_deploy.py --instance outro-nome --zone us-central1-a

Requisitos:
    - credentials.json (OAuth client, tipo "web" ou "desktop") na raiz do projeto
    - gcloud CLI autenticado (gcloud auth login) com acesso à instância
"""

import argparse
import subprocess
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

DEFAULT_PROJECT = "gen-lang-client-0103774511"
DEFAULT_INSTANCE = "radioia-server"
DEFAULT_ZONE = "us-east1-b"
DEFAULT_REMOTE_PATH = "~/radioIA/token.json"
DEFAULT_SERVICE = "radioia-bot"


def authenticate_local(port: int) -> None:
    print("1/3 — Abrindo browser para autenticar no Google (escopo youtube.readonly)...")
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=port)

    with open("token.json", "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print("    token.json gerado localmente.\n")


def run(cmd: list, description: str) -> None:
    print(f"{description}\n    $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"    Falhou (exit code {result.returncode}). Abortando.")
    print("    OK.\n")


def copy_token_to_server(project: str, instance: str, zone: str, remote_path: str) -> None:
    run(
        [
            "gcloud",
            "compute",
            "scp",
            "token.json",
            f"{instance}:{remote_path}",
            f"--project={project}",
            f"--zone={zone}",
        ],
        "2/3 — Copiando token.json para o servidor via gcloud compute scp...",
    )


def restart_bot(project: str, instance: str, zone: str, service: str) -> None:
    run(
        [
            "gcloud",
            "compute",
            "ssh",
            instance,
            f"--project={project}",
            f"--zone={zone}",
            "--command",
            f"sudo systemctl restart {service} && sudo systemctl is-active {service}",
        ],
        f"3/3 — Reiniciando {service} no servidor via gcloud compute ssh...",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080, help="Porta local do redirect OAuth")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--instance", default=DEFAULT_INSTANCE)
    parser.add_argument("--zone", default=DEFAULT_ZONE)
    parser.add_argument("--remote-path", default=DEFAULT_REMOTE_PATH)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument(
        "--skip-restart", action="store_true", help="Só copia o token, não reinicia o serviço"
    )
    args = parser.parse_args()

    authenticate_local(args.port)
    copy_token_to_server(args.project, args.instance, args.zone, args.remote_path)

    if args.skip_restart:
        print("Concluído (--skip-restart): reinicie o serviço manualmente quando quiser.")
        return

    restart_bot(args.project, args.instance, args.zone, args.service)
    print("Concluído. YouTube OAuth atualizado e bot reiniciado em produção.")


if __name__ == "__main__":
    main()
