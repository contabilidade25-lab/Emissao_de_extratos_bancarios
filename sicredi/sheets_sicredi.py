"""
Lê os dados do Sicredi da aba "ACESSO SECUNDÁRIO - TODOS OS BANCOS".

Layout (Sicredi fica nas colunas I–L, dados a partir da linha 23):
  I = EMPRESAS  (nome)
  J = USUÁRIO
  K = SENHA
  L = CNPJ

Linhas 21-22 são cabeçalhos — ignora.
Para quando encontra linha com nome vazio.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from sicredi_login import EmpresaSicredi

_DIR          = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
_CREDS_DIR    = _DIR if getattr(sys, 'frozen', False) else _DIR.parent / "bradesco"
load_dotenv(_DIR / ".env")

SCOPES           = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
TOKEN_FILE       = str(_CREDS_DIR / "token.json")
CREDENTIALS_FILE = os.getenv("GOOGLE_OAUTH_CREDENTIALS_FILE", str(_CREDS_DIR / "credentials.json"))
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID", "1gZUGKOk0VXw1KOb3Shx3MVQez53bGb1jvZCUHEheCeA")
SHEET_NAME       = os.getenv("SHEET_NAME", "ACESSO SECUNDÁRIO - TODOS OS BANCOS")

# Dados Sicredi: linha 23 em diante (21=header seção, 22=header colunas, 23+ dados)
RANGE_SICREDI = f"'{SHEET_NAME}'!I23:L"

STATUS_INVALIDOS = {"ACESSO INVÁLIDO", "ACESSO BLOQUEADO", "SEM MOVIMENTAÇÃO", "ACESSO INVALIDO"}


def _autenticar() -> Credentials:
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Arquivo '{CREDENTIALS_FILE}' não encontrado.\n"
                    "Gere o OAuth2 no Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def ler_empresas_sicredi() -> list[EmpresaSicredi]:
    creds   = _autenticar()
    service = build("sheets", "v4", credentials=creds)
    resultado = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_SICREDI,
            valueRenderOption="UNFORMATTED_VALUE",
        )
        .execute()
    )

    empresas: list[EmpresaSicredi] = []

    for i, linha in enumerate(resultado.get("values", []), start=23):
        while len(linha) < 4:
            linha.append("")

        nome, usuario, senha, cnpj = [str(c).strip() for c in linha[:4]]

        if not nome:
            break

        if usuario.upper() in STATUS_INVALIDOS:
            print(f"  [IGNORADO] Linha {i}: {nome!r} — {usuario}")
            continue

        if not usuario or not senha:
            print(f"  [IGNORADO] Linha {i}: {nome!r} — usuário/senha incompletos")
            continue

        empresas.append(EmpresaSicredi(nome=nome, usuario=usuario, senha=senha, cnpj=cnpj))

    return empresas


if __name__ == "__main__":
    print("Lendo empresas Sicredi...")
    lista = ler_empresas_sicredi()
    print(f"\n{len(lista)} empresa(s):\n")
    for e in lista:
        print(f"  - {e}")
