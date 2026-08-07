# Upload automático pro Drive por banco — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada pasta de banco (bradesco, caixa, itau, santander, sicredi) sobe automaticamente os extratos de cada empresa pro Google Drive logo após o download daquela empresa terminar com sucesso — sem alterar a lógica de login/extrato existente.

**Architecture:** Cada pasta ganha seu próprio `drive_upload.py` (cópia adaptada do módulo já usado por `Enviar pro drive/`), reaproveitando as credenciais Google já existentes (`credentials.json`/`token_drive.json`, sem nova autenticação OAuth). `main.py` de cada banco cria o serviço do Drive uma vez no início e chama `enviar_empresa(...)` no ponto onde hoje marca a empresa como `resultados["ok"]`. Falha de upload nunca derruba o resultado do download.

**Tech Stack:** Python 3.14 (via `py` launcher — não há `python` no PATH deste ambiente), `google-api-python-client`/`google-auth-oauthlib` (já usados no projeto), `pytest` (novo, dev-only).

## Global Constraints

- Não alterar nenhuma lógica de login, extrato ou notificação existente — o Drive é estritamente aditivo. (spec)
- Upload acontece **por empresa**, logo após aquele download terminar com sucesso — não em lote no fim do banco. (spec)
- Falha de upload (serviço indisponível, erro de rede, etc.) **não** marca a empresa como erro de extrato — apenas loga um aviso no console. (spec)
- Reaproveitar o `token_drive.json` já existente em `Enviar pro drive/token_drive.json` (conta `contabilidade36@akartos.com.br`, já com acesso à pasta de destino) — nenhum novo fluxo OAuth interativo. (spec)
- Resolução de credenciais segue o padrão já usado por `sheets_reader.py`/`sheets_santander.py`/`sheets_caixa.py`/`sheets_sicredi.py`: `bradesco/` e `itau/` são self-contained (própria pasta); `caixa/`, `santander/`, `sicredi/` usam `_DIR.parent / "bradesco"` quando rodando como script fonte, e a própria pasta quando `frozen` (executável). (spec)
- `DRIVE_FOLDER_ID` é um default hardcoded em cada `drive_upload.py`: `"1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN"` (mesmo valor de `Enviar pro drive/.env`), seguindo o padrão já usado por `SPREADSHEET_ID`/`SHEET_NAME`. Não cria `.env` novo em nenhuma pasta. (spec)
- Nome da pasta do banco no Drive = `BANCO_DIR.name` de cada `main.py` (não hardcodear a string de novo — evita divergência com o nome real da pasta de Downloads).
- `construir.bat` precisa copiar `token_drive.json` (com fallback pra `bradesco/`) na sub-rotina `:restaurar`, igual já faz com `credentials.json`/`token.json`.
- `Enviar pro drive/` permanece inalterada — vira ferramenta de backup/re-sync manual. (spec)
- Nota (não bloqueia a implementação): `Enviar pro drive/main.py` usa `"CAIXA"` na lista `BANCOS`, mas a pasta real de downloads da Caixa é `"CAIXA ECONÔMICA"` (`caixa/main.py:32`). Como usamos `BANCO_DIR.name`, o upload automático vai criar/usar a pasta `"CAIXA ECONÔMICA"` no Drive — correta, mas divergente do que a ferramenta manual criaria hoje. Fora de escopo corrigir a ferramenta manual (spec diz para não alterá-la).

---

## Task 1: Infraestrutura compartilhada — credenciais, .gitignore, construir.bat, pytest

**Files:**
- Create: `bradesco/token_drive.json` (cópia de `Enviar pro drive/token_drive.json`)
- Create: `itau/token_drive.json` (cópia de `Enviar pro drive/token_drive.json`)
- Modify: `.gitignore`
- Modify: `construir.bat`

**Interfaces:**
- Produces: `bradesco/token_drive.json` e `itau/token_drive.json` no disco, prontos para os módulos `drive_upload.py` das Tasks 2–6 autenticarem sem prompt interativo.
- Produces: `construir.bat` copiando `token_drive.json` pra `Executavel_bancos/{banco}/` na Task 7.

- [ ] **Step 1: Instalar pytest (dependência de desenvolvimento, não vai pro executável)**

Run: `py -m pip install pytest`
Expected: instalação concluída sem erro.

- [ ] **Step 2: Copiar o token_drive.json existente para bradesco/ e itau/**

```powershell
Copy-Item "Enviar pro drive\token_drive.json" "bradesco\token_drive.json"
Copy-Item "Enviar pro drive\token_drive.json" "itau\token_drive.json"
```

Verifique que os dois arquivos existem:

Run: `Test-Path "bradesco\token_drive.json"` e `Test-Path "itau\token_drive.json"`
Expected: `True` para os dois.

- [ ] **Step 3: Adicionar token_drive.json ao .gitignore**

Arquivo `.gitignore` — adicionar a linha `token_drive.json` junto das outras credenciais:

```diff
 # Credenciais e segredos
 .env
 credentials.json
 token.json
+token_drive.json
```

- [ ] **Step 4: Verificar que o git realmente ignora os dois arquivos novos**

Run: `git status --short bradesco/token_drive.json itau/token_drive.json`
Expected: nenhuma saída (arquivos ignorados, não aparecem como untracked).

- [ ] **Step 5: Adicionar variável TOKD e cópia de token_drive.json no construir.bat**

No topo do arquivo, junto das outras variáveis (logo depois de `set "TOK=%ROOT%bradesco\token.json"`):

```diff
 set "ROOT=%~dp0"
 set "CRED=%ROOT%bradesco\credentials.json"
 set "TOK=%ROOT%bradesco\token.json"
+set "TOKD=%ROOT%bradesco\token_drive.json"
```

Na sub-rotina `:restaurar`, logo depois do bloco `REM token.json` (antes de `echo    Config restaurada...`):

```diff
 REM token.json
 if exist "%SRC%\token.json" (
     copy /Y "%SRC%\token.json" "%DEST%\token.json" >nul
 ) else if exist "%TOK%" (
     copy /Y "%TOK%" "%DEST%\token.json" >nul
 )
 
+REM token_drive.json
+if exist "%SRC%\token_drive.json" (
+    copy /Y "%SRC%\token_drive.json" "%DEST%\token_drive.json" >nul
+) else if exist "%TOKD%" (
+    copy /Y "%TOKD%" "%DEST%\token_drive.json" >nul
+)
+
 echo    Config restaurada em Executavel_bancos\%BANCO%\
 goto :eof
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore construir.bat
GIT_AUTHOR_NAME="Jonas" GIT_AUTHOR_EMAIL="contabilidade25@akartos.com.br" GIT_COMMITTER_NAME="Jonas" GIT_COMMITTER_EMAIL="contabilidade25@akartos.com.br" git commit -m "chore: infraestrutura compartilhada pro upload automático no Drive"
```

---

## Task 2: Bradesco — drive_upload.py + integração no main.py

**Files:**
- Create: `bradesco/drive_upload.py`
- Create: `bradesco/test_drive_upload.py`
- Modify: `bradesco/main.py:24-26` (imports), `bradesco/main.py:157` (criação do serviço), `bradesco/main.py:202-207` (chamada de upload)

**Interfaces:**
- Consumes: nenhuma (primeiro módulo, self-contained — usa `bradesco/credentials.json` e `bradesco/token_drive.json` da Task 1).
- Produces: `criar_service(base_dir: Path = _DIR) -> googleapiclient.discovery.Resource`, `enviar_empresa(service, banco: str, empresa_dir: Path, drive_root_id: str = DRIVE_FOLDER_ID) -> None`, `DRIVE_FOLDER_ID: str`. Task 3 (itaú) copia este arquivo com o mesmo self-contained pattern; Tasks 4–6 adaptam pra variante compartilhada.

- [ ] **Step 1: Escrever o teste (falha primeiro — módulo ainda não existe)**

Criar `bradesco/test_drive_upload.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import drive_upload


def test_drive_folder_id_has_hardcoded_default():
    assert drive_upload.DRIVE_FOLDER_ID == "1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN"


def test_enviar_empresa_cria_pasta_banco_depois_pasta_empresa_e_sincroniza(tmp_path, monkeypatch):
    empresa_dir = tmp_path / "Empresa Teste"
    empresa_dir.mkdir()
    (empresa_dir / "extrato.pdf").write_text("conteudo")

    chamadas = []

    def fake_pasta_id(service, nome, parent_id):
        chamadas.append(("pasta", nome, parent_id))
        return f"id-{nome}"

    def fake_sincronizar_dir(service, local, drive_parent_id):
        chamadas.append(("sync", local, drive_parent_id))

    monkeypatch.setattr(drive_upload, "_pasta_id", fake_pasta_id)
    monkeypatch.setattr(drive_upload, "_sincronizar_dir", fake_sincronizar_dir)

    drive_upload.enviar_empresa(object(), "BRADESCO", empresa_dir, "root-id")

    assert chamadas == [
        ("pasta", "BRADESCO", "root-id"),
        ("pasta", "Empresa Teste", "id-BRADESCO"),
        ("sync", empresa_dir, "id-Empresa Teste"),
    ]
```

- [ ] **Step 2: Rodar o teste e confirmar que falha (módulo não existe)**

Run: `py -m pytest bradesco/test_drive_upload.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'drive_upload'`

- [ ] **Step 3: Criar bradesco/drive_upload.py**

```python
"""
Upload dos extratos de uma empresa para o Google Drive.
Chamado pelo main.py logo após o download daquela empresa terminar com sucesso.
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

_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

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


def criar_service(base_dir: Path = _DIR):
    creds = _autenticar(base_dir)
    return build("drive", "v3", credentials=creds)
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `py -m pytest bradesco/test_drive_upload.py -v`
Expected: 2 passed

- [ ] **Step 5: Integrar no bradesco/main.py — import**

Em `bradesco/main.py`, linhas 24–26:

```diff
 from bradesco_login   import criar_driver, BradescoSession
 from bradesco_extrato import BradescoExtrato
 from sheets_reader    import ler_empresas
+from drive_upload     import criar_service, enviar_empresa, DRIVE_FOLDER_ID
```

- [ ] **Step 6: Integrar no bradesco/main.py — criar serviço do Drive**

Linha 157 (logo após a criação do `driver`):

```diff
     driver     = criar_driver(headless=False, download_dir=str(BANCO_DIR))
     resultados = {"ok": [], "erro_login": [], "erro_extrato": []}
+
+    try:
+        drive_service = criar_service()
+    except Exception as e:
+        print(f"  ⚠ Não foi possível conectar ao Google Drive ({e}) — uploads serão pulados.")
+        drive_service = None
```

- [ ] **Step 7: Integrar no bradesco/main.py — upload após sucesso da empresa**

Linhas 202–207:

```diff
             if erro:
                 resultados["erro_extrato"].append(empresa.nome)
             else:
                 resultados["ok"].append(empresa.nome)
+                if drive_service is not None:
+                    try:
+                        enviar_empresa(drive_service, BANCO_DIR.name, empresa_dir, DRIVE_FOLDER_ID)
+                    except Exception as e:
+                        print(f"  ⚠ Falha ao enviar '{empresa.nome}' pro Drive: {e}")
 
             sessao.logout()
```

- [ ] **Step 8: Verificar sintaxe do main.py (sem rodar o fluxo completo com Selenium)**

Run: `py -m py_compile bradesco/main.py`
Expected: sem saída, sem erro (exit code 0).

- [ ] **Step 9: Commit**

```bash
git add bradesco/drive_upload.py bradesco/test_drive_upload.py bradesco/main.py
GIT_AUTHOR_NAME="Jonas" GIT_AUTHOR_EMAIL="contabilidade25@akartos.com.br" GIT_COMMITTER_NAME="Jonas" GIT_COMMITTER_EMAIL="contabilidade25@akartos.com.br" git commit -m "feat(bradesco): upload automático dos extratos pro Drive por empresa"
```

---

## Task 3: Itaú — drive_upload.py + integração no main.py

**Files:**
- Create: `itau/drive_upload.py`
- Create: `itau/test_drive_upload.py`
- Modify: `itau/main.py:28-31` (imports), `itau/main.py:151` (criação do serviço), `itau/main.py:237-239` (chamada de upload)

**Interfaces:**
- Consumes: nenhuma (self-contained, usa `itau/credentials.json` e `itau/token_drive.json` da Task 1 — mesmo padrão da Task 2).
- Produces: mesma interface pública da Task 2 (`criar_service`, `enviar_empresa`, `DRIVE_FOLDER_ID`).

- [ ] **Step 1: Escrever o teste (falha primeiro)**

Criar `itau/test_drive_upload.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import drive_upload


def test_drive_folder_id_has_hardcoded_default():
    assert drive_upload.DRIVE_FOLDER_ID == "1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN"


def test_enviar_empresa_cria_pasta_banco_depois_pasta_empresa_e_sincroniza(tmp_path, monkeypatch):
    empresa_dir = tmp_path / "Empresa Teste"
    empresa_dir.mkdir()
    (empresa_dir / "extrato.pdf").write_text("conteudo")

    chamadas = []

    def fake_pasta_id(service, nome, parent_id):
        chamadas.append(("pasta", nome, parent_id))
        return f"id-{nome}"

    def fake_sincronizar_dir(service, local, drive_parent_id):
        chamadas.append(("sync", local, drive_parent_id))

    monkeypatch.setattr(drive_upload, "_pasta_id", fake_pasta_id)
    monkeypatch.setattr(drive_upload, "_sincronizar_dir", fake_sincronizar_dir)

    drive_upload.enviar_empresa(object(), "ITAU", empresa_dir, "root-id")

    assert chamadas == [
        ("pasta", "ITAU", "root-id"),
        ("pasta", "Empresa Teste", "id-ITAU"),
        ("sync", empresa_dir, "id-Empresa Teste"),
    ]
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `py -m pytest itau/test_drive_upload.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'drive_upload'`

- [ ] **Step 3: Criar itau/drive_upload.py**

Conteúdo idêntico ao `bradesco/drive_upload.py` da Task 2 (mesmo padrão self-contained — Itaú também tem `credentials.json`/`token_drive.json` próprios):

```python
"""
Upload dos extratos de uma empresa para o Google Drive.
Chamado pelo main.py logo após o download daquela empresa terminar com sucesso.
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

_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

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


def criar_service(base_dir: Path = _DIR):
    creds = _autenticar(base_dir)
    return build("drive", "v3", credentials=creds)
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `py -m pytest itau/test_drive_upload.py -v`
Expected: 2 passed

- [ ] **Step 5: Integrar no itau/main.py — import**

Linhas 28–31:

```diff
 from notificacao              import notificar_resumo
 from itau_login               import criar_driver, ItauSession
 from sheets_itau              import ler_empresas_itau
 from itau_extrato_gravado     import extrato_gravado, _mes_anterior
+from drive_upload             import criar_service, enviar_empresa, DRIVE_FOLDER_ID
```

- [ ] **Step 6: Integrar no itau/main.py — criar serviço do Drive**

Linha 151 (logo após a criação do `driver`):

```diff
     driver     = criar_driver(download_dir=str(BANCO_DIR))
     resultados = {"ok": [], "verificacao": [], "erro_login": [], "erro_extrato": []}
     sessao     = ItauSession(driver)
+
+    try:
+        drive_service = criar_service()
+    except Exception as e:
+        print(f"  ⚠ Não foi possível conectar ao Google Drive ({e}) — uploads serão pulados.")
+        drive_service = None
```

- [ ] **Step 7: Integrar no itau/main.py — upload após sucesso da empresa**

Linhas 237–239:

```diff
             else:
                 resultados["ok"].append(empresa.nome)
                 print(f"  → Extratos em: {empresa_dir}")
+                if drive_service is not None:
+                    try:
+                        enviar_empresa(drive_service, BANCO_DIR.name, empresa_dir, DRIVE_FOLDER_ID)
+                    except Exception as e:
+                        print(f"  ⚠ Falha ao enviar '{empresa.nome}' pro Drive: {e}")
```

Nota: o `driver` do Itaú é recriado em dois pontos de recuperação de erro (sessão inválida) mais abaixo no loop — `drive_service` não depende do Selenium, então não precisa ser recriado nesses pontos.

- [ ] **Step 8: Verificar sintaxe**

Run: `py -m py_compile itau/main.py`
Expected: sem saída, exit code 0.

- [ ] **Step 9: Commit**

```bash
git add itau/drive_upload.py itau/test_drive_upload.py itau/main.py
GIT_AUTHOR_NAME="Jonas" GIT_AUTHOR_EMAIL="contabilidade25@akartos.com.br" GIT_COMMITTER_NAME="Jonas" GIT_COMMITTER_EMAIL="contabilidade25@akartos.com.br" git commit -m "feat(itau): upload automático dos extratos pro Drive por empresa"
```

(Nota: `itau/` está no `.gitignore` — este commit é local só pra histórico da pasta de trabalho; confirme com `git status itau/` se necessário.)

---

## Task 4: Caixa — drive_upload.py (credenciais compartilhadas) + integração no main.py

**Files:**
- Create: `caixa/drive_upload.py`
- Create: `caixa/test_drive_upload.py`
- Modify: `caixa/main.py:22-26` (imports), `caixa/main.py:144` (criação do serviço), `caixa/main.py:201-206` (chamada de upload)

**Interfaces:**
- Consumes: `bradesco/credentials.json` e `bradesco/token_drive.json` (Task 1) via `_CREDS_DIR`, quando rodando como script fonte.
- Produces: mesma interface pública das Tasks 2–3, mais `_CREDS_DIR: Path`.

- [ ] **Step 1: Escrever o teste (falha primeiro)**

Criar `caixa/test_drive_upload.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import drive_upload


def test_drive_folder_id_has_hardcoded_default():
    assert drive_upload.DRIVE_FOLDER_ID == "1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN"


def test_creds_dir_falls_back_to_bradesco_folder_when_running_from_source():
    assert drive_upload._CREDS_DIR == drive_upload._DIR.parent / "bradesco"


def test_creds_dir_uses_own_folder_when_frozen(monkeypatch):
    import importlib
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    importlib.reload(drive_upload)
    assert drive_upload._CREDS_DIR == drive_upload._DIR
    monkeypatch.delattr(sys, "frozen", raising=False)
    importlib.reload(drive_upload)


def test_enviar_empresa_cria_pasta_banco_depois_pasta_empresa_e_sincroniza(tmp_path, monkeypatch):
    empresa_dir = tmp_path / "Empresa Teste"
    empresa_dir.mkdir()
    (empresa_dir / "extrato.pdf").write_text("conteudo")

    chamadas = []

    def fake_pasta_id(service, nome, parent_id):
        chamadas.append(("pasta", nome, parent_id))
        return f"id-{nome}"

    def fake_sincronizar_dir(service, local, drive_parent_id):
        chamadas.append(("sync", local, drive_parent_id))

    monkeypatch.setattr(drive_upload, "_pasta_id", fake_pasta_id)
    monkeypatch.setattr(drive_upload, "_sincronizar_dir", fake_sincronizar_dir)

    drive_upload.enviar_empresa(object(), "CAIXA ECONÔMICA", empresa_dir, "root-id")

    assert chamadas == [
        ("pasta", "CAIXA ECONÔMICA", "root-id"),
        ("pasta", "Empresa Teste", "id-CAIXA ECONÔMICA"),
        ("sync", empresa_dir, "id-Empresa Teste"),
    ]
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `py -m pytest caixa/test_drive_upload.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'drive_upload'`

- [ ] **Step 3: Criar caixa/drive_upload.py**

Igual à Task 2, mas com `_CREDS_DIR` compartilhando `bradesco/` (mesmo padrão de `caixa/sheets_caixa.py:24-25`):

```python
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
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `py -m pytest caixa/test_drive_upload.py -v`
Expected: 4 passed

- [ ] **Step 5: Integrar no caixa/main.py — import**

Linhas 22–26:

```diff
 from notificacao import notificar_resumo
 
 from caixa_login   import criar_driver, CaixaSession
 from caixa_extrato_gravado import extrato_caixa, _mes_anterior
 from sheets_caixa  import ler_empresas_caixa
+from drive_upload  import criar_service, enviar_empresa, DRIVE_FOLDER_ID
```

- [ ] **Step 6: Integrar no caixa/main.py — criar serviço do Drive**

Linha 144 (logo após a criação do `driver`):

```diff
     driver     = criar_driver(headless=False, download_dir=str(BANCO_DIR))
     resultados = {"ok": [], "erro_login": [], "erro_extrato": []}
+
+    try:
+        drive_service = criar_service()
+    except Exception as e:
+        print(f"  ⚠ Não foi possível conectar ao Google Drive ({e}) — uploads serão pulados.")
+        drive_service = None
```

- [ ] **Step 7: Integrar no caixa/main.py — upload após sucesso da empresa**

Linhas 201–206:

```diff
             if exc_holder[0]:
                 print(f"  ✗ Erro: {exc_holder[0]}")
                 resultados["erro_extrato"].append(empresa.nome)
             else:
                 resultados["ok"].append(empresa.nome)
                 print(f"  → Extratos em: {empresa_dir}")
+                if drive_service is not None:
+                    try:
+                        enviar_empresa(drive_service, BANCO_DIR.name, empresa_dir, DRIVE_FOLDER_ID)
+                    except Exception as e:
+                        print(f"  ⚠ Falha ao enviar '{empresa.nome}' pro Drive: {e}")
 
             sessao.logout()
```

- [ ] **Step 8: Verificar sintaxe**

Run: `py -m py_compile caixa/main.py`
Expected: sem saída, exit code 0.

- [ ] **Step 9: Commit**

```bash
git add caixa/drive_upload.py caixa/test_drive_upload.py caixa/main.py
GIT_AUTHOR_NAME="Jonas" GIT_AUTHOR_EMAIL="contabilidade25@akartos.com.br" GIT_COMMITTER_NAME="Jonas" GIT_COMMITTER_EMAIL="contabilidade25@akartos.com.br" git commit -m "feat(caixa): upload automático dos extratos pro Drive por empresa"
```

---

## Task 5: Santander — drive_upload.py (credenciais compartilhadas) + integração no main.py

**Files:**
- Create: `santander/drive_upload.py`
- Create: `santander/test_drive_upload.py`
- Modify: `santander/main.py:23-27` (imports), `santander/main.py:147` (criação do serviço), `santander/main.py:205-210` (chamada de upload)

**Interfaces:**
- Consumes: `bradesco/credentials.json` e `bradesco/token_drive.json` (Task 1) via `_CREDS_DIR`.
- Produces: mesma interface pública da Task 4.

- [ ] **Step 1: Escrever o teste (falha primeiro)**

Criar `santander/test_drive_upload.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import drive_upload


def test_drive_folder_id_has_hardcoded_default():
    assert drive_upload.DRIVE_FOLDER_ID == "1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN"


def test_creds_dir_falls_back_to_bradesco_folder_when_running_from_source():
    assert drive_upload._CREDS_DIR == drive_upload._DIR.parent / "bradesco"


def test_creds_dir_uses_own_folder_when_frozen(monkeypatch):
    import importlib
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    importlib.reload(drive_upload)
    assert drive_upload._CREDS_DIR == drive_upload._DIR
    monkeypatch.delattr(sys, "frozen", raising=False)
    importlib.reload(drive_upload)


def test_enviar_empresa_cria_pasta_banco_depois_pasta_empresa_e_sincroniza(tmp_path, monkeypatch):
    empresa_dir = tmp_path / "Empresa Teste"
    empresa_dir.mkdir()
    (empresa_dir / "extrato.pdf").write_text("conteudo")

    chamadas = []

    def fake_pasta_id(service, nome, parent_id):
        chamadas.append(("pasta", nome, parent_id))
        return f"id-{nome}"

    def fake_sincronizar_dir(service, local, drive_parent_id):
        chamadas.append(("sync", local, drive_parent_id))

    monkeypatch.setattr(drive_upload, "_pasta_id", fake_pasta_id)
    monkeypatch.setattr(drive_upload, "_sincronizar_dir", fake_sincronizar_dir)

    drive_upload.enviar_empresa(object(), "SANTANDER", empresa_dir, "root-id")

    assert chamadas == [
        ("pasta", "SANTANDER", "root-id"),
        ("pasta", "Empresa Teste", "id-SANTANDER"),
        ("sync", empresa_dir, "id-Empresa Teste"),
    ]
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `py -m pytest santander/test_drive_upload.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'drive_upload'`

- [ ] **Step 3: Criar santander/drive_upload.py**

Conteúdo idêntico ao `caixa/drive_upload.py` da Task 4 (mesmo padrão de credenciais compartilhadas):

```python
"""
Upload dos extratos de uma empresa para o Google Drive.
Chamado pelo main.py logo após o download daquela empresa terminar com sucesso.
Credenciais compartilhadas com bradesco/ (mesmo padrão de sheets_santander.py).
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
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `py -m pytest santander/test_drive_upload.py -v`
Expected: 4 passed

- [ ] **Step 5: Integrar no santander/main.py — import**

Linhas 23–27:

```diff
 from notificacao import notificar_resumo
 
 from santander_login           import criar_driver, SantanderSession
 from sheets_santander          import ler_empresas_santander
 from santander_extrato_gravado import extrato_gravado, _mes_anterior
+from drive_upload               import criar_service, enviar_empresa, DRIVE_FOLDER_ID
```

- [ ] **Step 6: Integrar no santander/main.py — criar serviço do Drive**

Linha 147 (logo após a criação do `driver`):

```diff
     driver     = criar_driver(headless=False, download_dir=str(BANCO_DIR))
     resultados = {"ok": [], "erro_login": [], "erro_extrato": []}
+
+    try:
+        drive_service = criar_service()
+    except Exception as e:
+        print(f"  ⚠ Não foi possível conectar ao Google Drive ({e}) — uploads serão pulados.")
+        drive_service = None
```

- [ ] **Step 7: Integrar no santander/main.py — upload após sucesso da empresa**

Linhas 205–210:

```diff
             if exc_holder[0]:
                 print(f"  ✗ Erro: {exc_holder[0]}")
                 resultados["erro_extrato"].append(empresa.nome)
             else:
                 resultados["ok"].append(empresa.nome)
                 print(f"  → Extratos em: {empresa_dir}")
+                if drive_service is not None:
+                    try:
+                        enviar_empresa(drive_service, BANCO_DIR.name, empresa_dir, DRIVE_FOLDER_ID)
+                    except Exception as e:
+                        print(f"  ⚠ Falha ao enviar '{empresa.nome}' pro Drive: {e}")
 
             sessao.logout()
```

- [ ] **Step 8: Verificar sintaxe**

Run: `py -m py_compile santander/main.py`
Expected: sem saída, exit code 0.

- [ ] **Step 9: Commit**

```bash
git add santander/drive_upload.py santander/test_drive_upload.py santander/main.py
GIT_AUTHOR_NAME="Jonas" GIT_AUTHOR_EMAIL="contabilidade25@akartos.com.br" GIT_COMMITTER_NAME="Jonas" GIT_COMMITTER_EMAIL="contabilidade25@akartos.com.br" git commit -m "feat(santander): upload automático dos extratos pro Drive por empresa"
```

---

## Task 6: Sicredi — drive_upload.py (credenciais compartilhadas) + integração no main.py

**Files:**
- Create: `sicredi/drive_upload.py`
- Create: `sicredi/test_drive_upload.py`
- Modify: `sicredi/main.py:22-26` (imports), `sicredi/main.py:144` (criação do serviço), `sicredi/main.py:208-213` (chamada de upload)

**Interfaces:**
- Consumes: `bradesco/credentials.json` e `bradesco/token_drive.json` (Task 1) via `_CREDS_DIR`.
- Produces: mesma interface pública das Tasks 4–5.

- [ ] **Step 1: Escrever o teste (falha primeiro)**

Criar `sicredi/test_drive_upload.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import drive_upload


def test_drive_folder_id_has_hardcoded_default():
    assert drive_upload.DRIVE_FOLDER_ID == "1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN"


def test_creds_dir_falls_back_to_bradesco_folder_when_running_from_source():
    assert drive_upload._CREDS_DIR == drive_upload._DIR.parent / "bradesco"


def test_creds_dir_uses_own_folder_when_frozen(monkeypatch):
    import importlib
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    importlib.reload(drive_upload)
    assert drive_upload._CREDS_DIR == drive_upload._DIR
    monkeypatch.delattr(sys, "frozen", raising=False)
    importlib.reload(drive_upload)


def test_enviar_empresa_cria_pasta_banco_depois_pasta_empresa_e_sincroniza(tmp_path, monkeypatch):
    empresa_dir = tmp_path / "Empresa Teste"
    empresa_dir.mkdir()
    (empresa_dir / "extrato.pdf").write_text("conteudo")

    chamadas = []

    def fake_pasta_id(service, nome, parent_id):
        chamadas.append(("pasta", nome, parent_id))
        return f"id-{nome}"

    def fake_sincronizar_dir(service, local, drive_parent_id):
        chamadas.append(("sync", local, drive_parent_id))

    monkeypatch.setattr(drive_upload, "_pasta_id", fake_pasta_id)
    monkeypatch.setattr(drive_upload, "_sincronizar_dir", fake_sincronizar_dir)

    drive_upload.enviar_empresa(object(), "SICREDI", empresa_dir, "root-id")

    assert chamadas == [
        ("pasta", "SICREDI", "root-id"),
        ("pasta", "Empresa Teste", "id-SICREDI"),
        ("sync", empresa_dir, "id-Empresa Teste"),
    ]
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `py -m pytest sicredi/test_drive_upload.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'drive_upload'`

- [ ] **Step 3: Criar sicredi/drive_upload.py**

Conteúdo idêntico ao `caixa/drive_upload.py` da Task 4 (mesmo padrão de credenciais compartilhadas):

```python
"""
Upload dos extratos de uma empresa para o Google Drive.
Chamado pelo main.py logo após o download daquela empresa terminar com sucesso.
Credenciais compartilhadas com bradesco/ (mesmo padrão de sheets_sicredi.py).
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
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `py -m pytest sicredi/test_drive_upload.py -v`
Expected: 4 passed

- [ ] **Step 5: Integrar no sicredi/main.py — import**

Linhas 22–26:

```diff
 from notificacao import notificar_resumo
 
 from sicredi_login          import criar_driver, SicrediSession
 from sicredi_extrato_gravado import extrato_sicredi, _mes_anterior
 from sheets_sicredi          import ler_empresas_sicredi
+from drive_upload            import criar_service, enviar_empresa, DRIVE_FOLDER_ID
```

- [ ] **Step 6: Integrar no sicredi/main.py — criar serviço do Drive**

Linha 144 (logo após a criação do `driver`):

```diff
     driver     = criar_driver(headless=False, download_dir=str(BANCO_DIR))
     resultados = {"ok": [], "erro_login": [], "erro_extrato": []}
+
+    try:
+        drive_service = criar_service()
+    except Exception as e:
+        print(f"  ⚠ Não foi possível conectar ao Google Drive ({e}) — uploads serão pulados.")
+        drive_service = None
```

- [ ] **Step 7: Integrar no sicredi/main.py — upload após sucesso da empresa**

Linhas 208–213:

```diff
             if exc_holder[0]:
                 print(f"  ✗ Erro: {exc_holder[0]}")
                 resultados["erro_extrato"].append(empresa.nome)
             else:
                 resultados["ok"].append(empresa.nome)
                 print(f"  → Extratos em: {empresa_dir}")
+                if drive_service is not None:
+                    try:
+                        enviar_empresa(drive_service, BANCO_DIR.name, empresa_dir, DRIVE_FOLDER_ID)
+                    except Exception as e:
+                        print(f"  ⚠ Falha ao enviar '{empresa.nome}' pro Drive: {e}")
 
             sessao.logout()
```

- [ ] **Step 8: Verificar sintaxe**

Run: `py -m py_compile sicredi/main.py`
Expected: sem saída, exit code 0.

- [ ] **Step 9: Commit**

```bash
git add sicredi/drive_upload.py sicredi/test_drive_upload.py sicredi/main.py
GIT_AUTHOR_NAME="Jonas" GIT_AUTHOR_EMAIL="contabilidade25@akartos.com.br" GIT_COMMITTER_NAME="Jonas" GIT_COMMITTER_EMAIL="contabilidade25@akartos.com.br" git commit -m "feat(sicredi): upload automático dos extratos pro Drive por empresa"
```

---

## Task 7: Rebuild dos 5 executáveis

**Files:**
- Nenhum arquivo novo — regenera `Executavel_bancos/{bradesco,caixa,itau,santander,sicredi}/` via PyInstaller.

**Interfaces:**
- Consumes: código-fonte atualizado das Tasks 2–6 e `construir.bat` atualizado da Task 1.
- Produces: 5 `.exe` atualizados em `Executavel_bancos/`, cada um com `drive_upload.py` embutido e `token_drive.json` copiado pra pasta do executável.

- [ ] **Step 1: Rodar os testes de cada pasta, pra garantir que nada quebrou entre as tasks**

Todas as 5 pastas têm um `test_drive_upload.py` com o mesmo nome de arquivo, em diretórios sem `__init__.py` — rodar `pytest` apontando pras 5 pastas de uma vez só dá erro de coleta do pytest (`import file mismatch`, não é falha de teste real). Rode uma pasta por vez, cada uma em sua própria invocação do pytest:

Run:
```
py -m pytest bradesco/test_drive_upload.py -v
py -m pytest itau/test_drive_upload.py -v
py -m pytest caixa/test_drive_upload.py -v
py -m pytest santander/test_drive_upload.py -v
py -m pytest sicredi/test_drive_upload.py -v
```
Expected: todos os testes `passed` em cada uma das 5 invocações, nenhum `failed` (2 no bradesco, 2 no itaú, 4 cada em caixa/santander/sicredi).

- [ ] **Step 2: Rodar o construir.bat**

O script termina com `pause`, que trava esperando Enter — redirecionar stdin de um arquivo vazio evita isso.

Run (a partir da raiz do projeto): `cmd /c "construir.bat < nul"`
Expected: saída mostrando `[1/5]` até `[5/5]` concluídos sem `ERRO no <Banco>`, terminando em `CONCLUIDO — executaveis em: Executavel_bancos\`. Pode levar vários minutos (PyInstaller com `--collect-all` de várias libs, 5 builds).

- [ ] **Step 3: Verificar que os 5 executáveis foram gerados e têm token_drive.json**

```powershell
foreach ($banco in "bradesco","caixa","itau","santander","sicredi") {
    Test-Path "Executavel_bancos\$banco\$banco.exe"
    Test-Path "Executavel_bancos\$banco\token_drive.json"
}
```

Expected: `True` para todas as 10 checagens.

- [ ] **Step 4: Commit (se houver algo além dos binários ignorados)**

`Executavel_bancos/` já está no `.gitignore` — normalmente não há nada pra commitar aqui. Confirme:

Run: `git status --short`
Expected: nenhuma mudança relacionada a `Executavel_bancos/` (pasta ignorada).

---

## Fora de escopo (confirmado no spec)

- Lógica de login, extrato ou notificação de qualquer banco.
- Retry/fila de upload — falha apenas loga aviso.
- Alterações em `Enviar pro drive/` (ferramenta manual de backup/re-sync).
