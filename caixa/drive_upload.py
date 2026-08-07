"""
Upload dos extratos de uma empresa para o Google Drive.
Chamado pelo main.py logo após o download daquela empresa terminar com sucesso.
Credenciais compartilhadas com bradesco/ (mesmo padrão de sheets_caixa.py).
"""
import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN")

_DIR       = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
_CREDS_DIR = _DIR if getattr(sys, "frozen", False) else _DIR.parent / "bradesco"

_cache_pastas: dict[tuple[str, str], str] = {}


def _autenticar(base_dir: Path) -> Credentials:
    token_path = base_dir / "token_drive.json"
    creds_path = base_dir / "credentials.json"
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return creds


_EXTRA = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}


def _pasta_id(service, nome: str, parent_id: str) -> str:
    chave = (nome, parent_id)
    if chave in _cache_pastas:
        return _cache_pastas[chave]
    q = (f"name='{nome}' and mimeType='application/vnd.google-apps.folder'"
         f" and '{parent_id}' in parents and trashed=false")
    res = service.files().list(q=q, fields="files(id)", **_EXTRA).execute()
    arquivos = res.get("files", [])
    if arquivos:
        fid = arquivos[0]["id"]
    else:
        meta = {"name": nome, "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id]}
        fid = service.files().create(body=meta, fields="id",
                                     supportsAllDrives=True).execute()["id"]
        print(f"    + pasta: {nome}")
    _cache_pastas[chave] = fid
    return fid


def _arquivo_existente(service, nome: str, parent_id: str) -> str | None:
    q = f"name='{nome}' and '{parent_id}' in parents and trashed=false"
    res = service.files().list(q=q, fields="files(id)", **_EXTRA).execute()
    arqs = res.get("files", [])
    return arqs[0]["id"] if arqs else None


def _upload(service, caminho: Path, parent_id: str):
    nome = caminho.name
    ext = caminho.suffix.lower()
    mime = "application/pdf" if ext == ".pdf" else "application/octet-stream"
    media = MediaFileUpload(str(caminho), mimetype=mime, resumable=False)
    existente = _arquivo_existente(service, nome, parent_id)
    if existente:
        service.files().update(fileId=existente, media_body=media,
                               supportsAllDrives=True).execute()
        print(f"      ↺ {nome}")
    else:
        meta = {"name": nome, "parents": [parent_id]}
        service.files().create(body=meta, media_body=media, fields="id",
                               supportsAllDrives=True).execute()
        print(f"      + {nome}")


def _sincronizar_dir(service, local: Path, drive_parent_id: str):
    for item in sorted(local.iterdir()):
        if item.is_dir():
            sub_id = _pasta_id(service, item.name, drive_parent_id)
            _sincronizar_dir(service, item, sub_id)
        elif item.is_file() and item.suffix.lower() in (".pdf", ".ofx", ".txt"):
            try:
                _upload(service, item, drive_parent_id)
            except Exception as e:
                print(f"      ✗ {item.name}: {e}")


def enviar_empresa(service, banco: str, empresa_dir: Path, drive_root_id: str = DRIVE_FOLDER_ID) -> None:
    """Sobe Downloads/{banco}/{empresa}/ (e subpastas) pra dentro da pasta do banco no Drive."""
    banco_id = _pasta_id(service, banco, drive_root_id)
    empresa_id = _pasta_id(service, empresa_dir.name, banco_id)
    _sincronizar_dir(service, empresa_dir, empresa_id)


def criar_service(base_dir: Path = _CREDS_DIR):
    creds = _autenticar(base_dir)
    return build("drive", "v3", credentials=creds)
