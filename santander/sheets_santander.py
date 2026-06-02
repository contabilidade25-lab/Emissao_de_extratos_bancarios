"""
Lê os dados do Santander da aba "ACESSO SECUNDÁRIO - TODOS OS BANCOS".

Layout da aba (Santander fica nas colunas I–M, dados a partir da linha 3):
  I = EMPRESAS  (nome)
  J = USUÁRIO
  K = SENHA
  L = AGÊNCIA
  M = C.C.      (conta corrente)

Para quando encontra linha com nome vazio (células abaixo do bloco Santander).
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from santander_login import EmpresaSantander

# Pasta do script → busca credentials no Bradesco (compartilhado)
_DIR         = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
_CREDS_DIR   = _DIR if getattr(sys, 'frozen', False) else _DIR.parent / "bradesco"
load_dotenv(_DIR / ".env")

SCOPES           = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
TOKEN_FILE       = str(_CREDS_DIR / "token.json")
CREDENTIALS_FILE = os.getenv("GOOGLE_OAUTH_CREDENTIALS_FILE", str(_CREDS_DIR / "credentials.json"))
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID", "1gZUGKOk0VXw1KOb3Shx3MVQez53bGb1jvZCUHEheCeA")
SHEET_NAME       = os.getenv("SHEET_NAME", "ACESSO SECUNDÁRIO - TODOS OS BANCOS")

# Colunas Santander: I=0, J=1, K=2, L=3, M=4  (dentro do slice da linha)
RANGE_SANTANDER  = f"'{SHEET_NAME}'!I3:M"

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


def ler_empresas_santander() -> list[EmpresaSantander]:
    """
    Lê o bloco Santander da planilha e retorna lista de EmpresaSantander.
    Para ao encontrar a primeira linha com nome vazio.
    """
    creds   = _autenticar()
    service = build("sheets", "v4", credentials=creds)
    resultado = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_SANTANDER,
            valueRenderOption="UNFORMATTED_VALUE",
        )
        .execute()
    )

    empresas: list[EmpresaSantander] = []

    for i, linha in enumerate(resultado.get("values", []), start=3):
        # Garante 5 colunas
        while len(linha) < 5:
            linha.append("")

        nome, usuario, senha, agencia, conta = [str(c).strip() for c in linha[:5]]

        # Para quando o nome está vazio (fim do bloco Santander)
        if not nome:
            break

        # Ignora status especiais na coluna usuário
        if usuario.upper() in STATUS_INVALIDOS:
            print(f"  [IGNORADO] Linha {i}: {nome!r} — {usuario}")
            continue

        # Ignora linhas sem dados essenciais
        if not agencia or not conta or not senha:
            print(f"  [IGNORADO] Linha {i}: {nome!r} — ag/conta/senha incompletos")
            continue

        empresas.append(
            EmpresaSantander(
                nome=nome,
                usuario=usuario,
                senha=senha,
                agencia=agencia,
                conta=conta,
            )
        )

    return empresas


if __name__ == "__main__":
    print("Lendo empresas Santander...")
    lista = ler_empresas_santander()
    print(f"\n{len(lista)} empresa(s):\n")
    for e in lista:
        print(f"  - {e}")
