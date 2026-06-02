# Como gerar a chave OAuth2 para o Google Sheets

## Passo a passo

### 1. Acesse o Google Cloud Console
URL: https://console.cloud.google.com/

### 2. Crie ou selecione um projeto
- Clique em "Selecionar projeto" no topo
- Crie um novo projeto (ex: "EmissaoExtratoBradesco") ou use um existente

### 3. Ative a API do Google Sheets
- Menu lateral → "APIs e serviços" → "Biblioteca"
- Pesquise "Google Sheets API"
- Clique em "Ativar"

### 4. Ative a API do Google Drive (necessária para leitura de planilhas compartilhadas)
- Repita o processo acima para "Google Drive API"

### 5. Crie as credenciais OAuth2
- Menu lateral → "APIs e serviços" → "Credenciais"
- Clique em "+ CRIAR CREDENCIAIS" → "ID do cliente OAuth"
- Tipo de aplicativo: **Aplicativo para computador (Desktop app)**
- Nome: "EmissaoExtrato" (qualquer nome)
- Clique em "Criar"

### 6. Configure a tela de consentimento OAuth (se solicitado)
- Tipo de usuário: **Externo**
- Preencha nome do app e e-mail de suporte (pode usar contabilidade36@akartos.com.br)
- Na seção "Escopos", adicione:
  - `https://www.googleapis.com/auth/spreadsheets.readonly`
- Na seção "Usuários de teste", adicione: **contabilidade36@akartos.com.br**

### 7. Baixe o arquivo JSON
- Após criar, clique no ícone de download (⬇)
- Salve o arquivo como **`credentials.json`** na pasta do projeto:
  ```
  c:\emissaoextrato_bradesco\credentials.json
  ```

### 8. Primeira execução (autorização)
Na primeira vez que rodar o script, abrirá uma janela do browser pedindo
autorização com a conta **contabilidade36@akartos.com.br**.

Após autorizar, será criado o arquivo `token.json` com o token de acesso.
Nas próximas execuções, o token será reutilizado automaticamente.

---

## Checklist antes de rodar

- [ ] `credentials.json` salvo em `c:\emissaoextrato_bradesco\`
- [ ] Python 3.11+ instalado
- [ ] Dependências instaladas: `pip install -r requirements.txt`
- [ ] Google Chrome instalado
- [ ] Planilha compartilhada com contabilidade36@akartos.com.br (ou pública)
