"""
Lê as credenciais das empresas a partir do Google Sheets.
Ignora linhas em branco e células com status especial (ACESSO INVÁLIDO, etc.).
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
load_dotenv(_DIR / ".env")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
TOKEN_FILE = str(_DIR / "token.json")
CREDENTIALS_FILE = os.getenv("GOOGLE_OAUTH_CREDENTIALS_FILE", str(_DIR / "credentials.json"))
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1gZUGKOk0VXw1KOb3Shx3MVQez53bGb1jvZCUHEheCeA")
SHEET_NAME = os.getenv("SHEET_NAME", "ACESSO SECUNDÁRIO - TODOS OS BANCOS")

# Statuses que devem ser ignorados (aparecem na coluna B quando não há credenciais válidas)
STATUS_INVALIDOS = {
    "ACESSO INVÁLIDO",
    "ACESSO BLOQUEADO",
    "SEM MOVIMENTAÇÃO",
    "ACESSO INVALIDO",
}


@dataclass
class Empresa:
    nome: str
    usuario: str
    senha: str

    def __repr__(self):
        return f"Empresa(nome={self.nome!r}, usuario={self.usuario!r})"


def autenticar() -> Credentials:
    """Autentica via OAuth2. Salva o token em token.json para reutilização."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Arquivo de credenciais '{CREDENTIALS_FILE}' não encontrado.\n"
                    "Gere o OAuth2 no Google Cloud Console e salve como credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def ler_empresas() -> list[Empresa]:
    """
    Lê as empresas da planilha e retorna apenas as que possuem
    usuário e senha válidos (ignora mescladas, brancas e com status especial).
    """
    creds = autenticar()
    service = build("sheets", "v4", credentials=creds)
    sheets = service.spreadsheets()

    # Lê colunas A, B e C a partir da linha 3 (dados começam na linha 3 da planilha)
    range_name = f"'{SHEET_NAME}'!A3:C"
    resultado = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()

    linhas = resultado.get("values", [])
    empresas: list[Empresa] = []

    for i, linha in enumerate(linhas, start=3):
        # Garante que a linha tem ao menos 3 colunas
        while len(linha) < 3:
            linha.append("")

        nome = str(linha[0]).strip()
        usuario = str(linha[1]).strip()
        senha = str(linha[2]).strip()

        # Ignora linhas com nome vazio (células mescladas ou em branco)
        if not nome:
            continue

        # Ignora linhas com status especial na coluna B
        if usuario.upper() in STATUS_INVALIDOS:
            print(f"  [IGNORADO] Linha {i}: {nome!r} — status: {usuario}")
            continue

        # Ignora linhas sem usuário ou senha
        if not usuario or not senha:
            print(f"  [IGNORADO] Linha {i}: {nome!r} — usuário ou senha vazio")
            continue

        empresas.append(Empresa(nome=nome, usuario=usuario, senha=senha))

    return empresas


if __name__ == "__main__":
    print("Lendo empresas da planilha...")
    lista = ler_empresas()
    print(f"\n{len(lista)} empresa(s) válida(s) encontrada(s):\n")
    for emp in lista:
        print(f"  - {emp}")
