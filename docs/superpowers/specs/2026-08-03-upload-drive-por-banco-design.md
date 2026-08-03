# Upload automático para o Drive embutido em cada banco

## Contexto

Hoje, o download dos extratos (bradesco, caixa, itaú, santander, sicredi) e o envio
para o Google Drive são dois passos desacoplados:

1. Cada pasta de banco tem seu próprio `main.py` que faz login, baixa os extratos
   de cada empresa em `Downloads/{BANCO}/{empresa}/` e ao final chama
   `notificar_resumo(...)`.
2. A pasta `Enviar pro drive/` (com sua versão empacotada em
   `Enviar pro drive (executavel)/`) é uma ferramenta manual separada:
   `main.py` varre `Downloads/{BANCO}/{empresa}/` para todos os bancos e sobe
   tudo para o Drive via `drive_upload.py` (`sincronizar_banco` /
   `_sincronizar_dir`), autenticando com `credentials.json` + `token_drive.json`
   (OAuth `https://www.googleapis.com/auth/drive`).

O usuário precisa rodar essa sincronização manualmente depois que os bancos
terminam. O objetivo desta mudança é eliminar esse passo manual: cada banco
sobe seus próprios arquivos para o Drive automaticamente, empresa por empresa,
como parte do próprio fluxo de download — sem alterar a lógica de
login/extrato existente.

## Descobertas relevantes do código atual

- **Credenciais Google não são uniformes por pasta.** Só `bradesco/` e
  `itau/` têm `credentials.json`/`token.json` próprios. `santander/`,
  `caixa/` e `sicredi/` **compartilham** as credenciais do bradesco via
  caminho relativo, resolvido em `sheets_*.py`:
  ```python
  _CREDS_DIR = _DIR if getattr(sys, 'frozen', False) else _DIR.parent / "bradesco"
  ```
  ou seja: rodando como script fonte, sobe um nível e entra em `bradesco/`;
  rodando como `.exe` empacotado, usa a própria pasta do executável (onde o
  build copiou os arquivos).
- **`bradesco/credentials.json`, `itau/credentials.json` e
  `Enviar pro drive/credentials.json` são idênticos** (mesmo client OAuth,
  confirmado por diff). Logo, um único `token_drive.json` já autorizado
  funciona para qualquer um desses três — não é necessário repetir o consentimento
  OAuth por pasta.
- **`Enviar pro drive/token_drive.json` já existe e já está autenticado**
  para o escopo Drive com esse client, como a conta
  `contabilidade36@akartos.com.br` — a mesma que já tem acesso à pasta de
  destino no Drive (confirmado: a ferramenta manual já funciona hoje com
  esse token). Pode ser copiado diretamente, sem novo fluxo interativo de
  login.
- **Defaults hardcoded já são o padrão do projeto** para configuração que não
  muda por ambiente: `sheets_santander.py`/`sheets_caixa.py`/`sheets_sicredi.py`
  já usam `os.getenv("SPREADSHEET_ID", "<id fixo>")`. `caixa/` e `santander/`
  nem têm `.env` real hoje (só `.env.example` no caso do santander) e mesmo
  assim funcionam, porque tudo cai no default.
- **`construir.bat`** gera os 5 executáveis via PyInstaller (`--onedir`,
  `--distpath Executavel_bancos`) e, na sub-rotina `:restaurar`, copia
  `.env`, `credentials.json` e `token.json` da pasta fonte (ou do fallback
  `bradesco/`) para `Executavel_bancos/{banco}/`. Ela **não** copia
  `token_drive.json` hoje — precisa ganhar esse passo.

## Design

### 1. Módulo `drive_upload.py` em cada pasta de banco

Cada uma das 5 pastas (`bradesco/`, `caixa/`, `itau/`, `santander/`,
`sicredi/`) ganha uma cópia enxuta do `drive_upload.py` existente em
`Enviar pro drive/`, mantendo as mesmas funções (`criar_service`,
`sincronizar_banco`/equivalente por empresa, `_upload`, `_pasta_id`,
`_arquivo_existente`), mas resolvendo credenciais com o mesmo padrão já usado
por `sheets_*.py`:

```python
_DIR       = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
_CREDS_DIR = _DIR if getattr(sys, 'frozen', False) else _DIR.parent / "bradesco"  # exceto bradesco/itau, que usam _DIR direto
```

- `bradesco/` e `itau/`: `_CREDS_DIR = _DIR` sempre (têm credenciais próprias).
- `caixa/`, `santander/`, `sicredi/`: `_CREDS_DIR` segue o padrão acima
  (compartilha bradesco/ quando rodando como script; própria pasta quando
  `.exe`, já que o build copia os arquivos pra lá).

`DRIVE_FOLDER_ID` vira um default hardcoded dentro do próprio
`drive_upload.py` (`os.getenv("DRIVE_FOLDER_ID",
"1DWuN3LZKQUtkyFTF0Sa1H-JHfLtbxweN")`, o mesmo ID já usado em
`Enviar pro drive/.env`), seguindo o padrão de `SPREADSHEET_ID`/
`SHEET_NAME`. Não é necessário criar `.env` novo em nenhuma pasta.

Nova função de conveniência para upload incremental por empresa (em vez de
varrer `Downloads/{BANCO}/` inteiro):

```python
def enviar_empresa(service, banco: str, empresa_dir: Path, drive_root_id: str):
    banco_id = _pasta_id(service, banco, drive_root_id)
    empresa_id = _pasta_id(service, empresa_dir.name, banco_id)
    _sincronizar_dir(service, empresa_dir, empresa_id)  # reaproveita a função existente
```

### 2. Arquivos de credencial

- Copiar `Enviar pro drive/token_drive.json` → `bradesco/token_drive.json` e
  `itau/token_drive.json`. Nenhum novo login OAuth necessário.
- `caixa/`, `santander/`, `sicredi/` não recebem cópia própria — resolvem
  `../bradesco/token_drive.json` em tempo de execução (mesmo padrão do
  `token.json` de sheets).

### 3. Integração no `main.py` de cada banco

Depois que uma empresa termina de baixar com sucesso (mesmo ponto onde hoje
o loop decide `resultados["ok"].append(empresa.nome)`), chama o upload
daquela pasta específica:

```python
try:
    enviar_empresa(drive_service, "BRADESCO", empresa_dir, DRIVE_FOLDER_ID)
except Exception as e:
    print(f"  ⚠ Falha ao enviar pro Drive: {e}")
    # não marca a empresa como erro — o download já foi bem-sucedido
```

- `drive_service` é criado uma vez no início do `main()` (`criar_service`),
  igual ao padrão de `criar_driver` para o Selenium.
- Falha de upload **não** deve derrubar o resultado do download: a empresa
  continua contando como `ok` no resumo (extrato baixado é o que importa
  primeiro); registra um aviso separado no console. Isso preserva 100% do
  comportamento atual de login/extrato — o Drive é estritamente aditivo.
- Nenhuma mudança em `bradesco_login.py`, `*_extrato*.py`, `*_login.py`,
  `sheets_*.py` ou `notificacao.py`.

### 4. `construir.bat`

Sub-rotina `:restaurar` ganha a cópia de `token_drive.json`, com o mesmo
fallback já usado para `credentials.json`/`token.json`:

```bat
set "TOKD=%ROOT%bradesco\token_drive.json"
...
if exist "%SRC%\token_drive.json" (
    copy /Y "%SRC%\token_drive.json" "%DEST%\token_drive.json" >nul
) else if exist "%TOKD%" (
    copy /Y "%TOKD%" "%DEST%\token_drive.json" >nul
)
```

Nenhuma nova dependência PyInstaller é necessária — `--collect-all
google.auth`, `google_auth_oauthlib` e `googleapiclient` já estão no
`COMUM` do `construir.bat` e cobrem o `drive_upload.py`.

### 5. `Enviar pro drive/` (ferramenta manual)

Mantida como está, sem alterações — vira uma ferramenta de backup/re-sync
manual, para o caso de algum upload individual falhar ou for preciso
re-sincronizar tudo de uma vez.

### 6. Executáveis

Depois de implementado o código-fonte e o `construir.bat`, rodar
`construir.bat` para regerar os 5 `.exe` em `Executavel_bancos/` com a nova
lógica embutida. Isso é uma regeneração via PyInstaller, não uma edição
manual do binário.

## Fora de escopo

- Não altera a lógica de login, captura de extrato ou notificação de nenhum
  banco.
- Não adiciona retry/fila de upload — falha de upload apenas loga um aviso.
- Não muda a ferramenta manual `Enviar pro drive/`.
