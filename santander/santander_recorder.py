"""
Gravador de macro — Santander Net Empresa PJ.

Como usar:
  1. Execute:  python santander_recorder.py
  2. Escolha a empresa quando solicitado (ou deixe em branco para a primeira)
  3. O login é feito automaticamente
  4. Faça o processo de extrato MANUALMENTE no browser
  5. Pressione ESC 3× rápido (menos de 1 segundo) para parar a gravação
  6. O arquivo  santander_extrato_gravado.py  é gerado com o código pronto

O arquivo gerado já inclui:
  - Waits para cada elemento antes de clicar
  - Pausas proporcionais ao tempo real que você esperou
  - Renomeia os arquivos baixados para o padrão:
      {MM} - EXTRATOS BANCÁRIOS CC - SANTANDER - {NOME_EMPRESA}
"""

import os
import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By

from santander_login   import criar_driver, SantanderSession
from sheets_santander  import ler_empresas_santander

_DIR = Path(__file__).parent
load_dotenv(_DIR / ".env")

OUTPUT_DIR   = Path(os.getenv("OUTPUT_DIR",   str(_DIR / "extratos")))
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(Path.home() / "Downloads")))
ARQUIVO_GERADO = _DIR / "santander_extrato_gravado.py"

# ── JavaScript injetado na página ─────────────────────────────────────

INJECT_JS = r"""
(function() {
  if (window._rec_ativo) return;   // evita injetar duas vezes
  window._rec_ativo = true;
  window._rec = window._rec || [];

  // Gera o melhor seletor possível para um elemento
  function _sel(el) {
    // ID estável (ignora IDs gerados pelo JSF como j_id_xxx)
    if (el.id && !el.id.match(/^j_id/) && !el.id.match(/^\d/)) {
      return {by: 'id', value: el.id};
    }
    // Angular formcontrolname
    var fcn = el.getAttribute && el.getAttribute('formcontrolname');
    if (fcn) return {by: 'css', value: '[formcontrolname="' + fcn + '"]'};

    // name
    if (el.name) return {by: 'name', value: el.name};

    // Texto do elemento (para botões, links, spans)
    var txt = (el.textContent || el.innerText || '').trim()
                .replace(/\s+/g, ' ').substring(0, 60);
    if (txt && !['INPUT','TEXTAREA','SELECT'].includes(el.tagName)) {
      return {by: 'xpath',
              value: '//' + el.tagName.toLowerCase() +
                     '[normalize-space(.)="' + txt.replace(/"/g,"'") + '"]'};
    }

    // Classe CSS (remove classes de estado dinâmico)
    var cls = (el.className || '').trim().split(/\s+/)
      .filter(function(c) {
        return c && !c.match(/^(ng-|active|focus|hover|selected|disabled|ui-state|is-)/);
      })
      .slice(0, 3).join('.');
    if (cls) return {by: 'css', value: el.tagName.toLowerCase() + '.' + cls};

    // ID JSF (último recurso — pode mudar entre sessões)
    if (el.id) return {by: 'id', value: el.id, aviso: 'ID_DINAMICO'};

    return {by: 'xpath', value: '(REVISAR: ' + el.tagName + ')', aviso: 'SEM_SELETOR'};
  }

  // ── Cliques ────────────────────────────────────────────────────────
  document.addEventListener('click', function(e) {
    var el = e.target;
    if (['BODY','HTML','SCRIPT'].includes(el.tagName)) return;
    var s = _sel(el);
    window._rec.push({
      type: 'click',
      by:    s.by,
      value: s.value,
      aviso: s.aviso || null,
      text:  (el.textContent || el.innerText || '').trim()
               .replace(/\s+/g, ' ').substring(0, 80),
      tag:   el.tagName,
      t:     Date.now()
    });
  }, true);

  // ── Preenchimento de campos (captura valor final no blur) ──────────
  document.addEventListener('blur', function(e) {
    var el = e.target;
    if (!['INPUT','TEXTAREA','SELECT'].includes(el.tagName)) return;
    if (el.type === 'password' || el.type === 'hidden') return;
    var s = _sel(el);
    window._rec.push({
      type:  'fill',
      by:    s.by,
      value: s.value,
      aviso: s.aviso || null,
      fill:  el.value,
      tag:   el.tagName,
      t:     Date.now()
    });
  }, true);

  // ── Selects ────────────────────────────────────────────────────────
  document.addEventListener('change', function(e) {
    var el = e.target;
    if (el.tagName !== 'SELECT') return;
    var s = _sel(el);
    window._rec.push({
      type:  'select',
      by:    s.by,
      value: s.value,
      fill:  el.value,
      text:  el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '',
      t:     Date.now()
    });
  }, true);

})();
"""


# ── Listener de teclado (ESC × 3) ─────────────────────────────────────

def _iniciar_listener_esc(stop_event: threading.Event):
    """Aguarda ESC pressionado 3× em menos de 1 segundo."""
    try:
        from pynput import keyboard as pynput_kb

        esc_times = []

        def on_press(key):
            nonlocal esc_times
            if key == pynput_kb.Key.esc:
                agora = time.time()
                esc_times = [t for t in esc_times if agora - t < 1.2]
                esc_times.append(agora)
                if len(esc_times) >= 3:
                    stop_event.set()
                    return False  # encerra o listener

        listener = pynput_kb.Listener(on_press=on_press)
        listener.start()
        stop_event.wait()          # fica bloqueado até ESC×3
        try:
            listener.stop()
        except Exception:
            pass

    except ImportError:
        print("\n[AVISO] pynput não instalado — usando modo ENTER para parar.")
        print("        Instale com:  pip install pynput")
        print("        Pressione ENTER para encerrar a gravação.\n")
        input()
        stop_event.set()


# ── Loop de gravação ──────────────────────────────────────────────────

def _gravar(driver: webdriver.Chrome, stop_event: threading.Event) -> list:
    """
    Injeta o JS em cada nova URL e coleta eventos até stop_event ser setado.
    Retorna a lista de eventos gravados.
    """
    eventos = []
    ultima_url = ""
    total_impresso = 0

    print("\n" + "█" * 55)
    print("  ⏺  GRAVAÇÃO INICIADA")
    print("  Faça o processo manualmente no browser.")
    print("  Pressione  ESC × 3 rápido  para encerrar.")
    print("█" * 55 + "\n")

    while not stop_event.is_set():
        try:
            url_atual = driver.current_url

            # Re-injeta quando muda de página
            if url_atual != ultima_url:
                driver.execute_script(INJECT_JS)
                ultima_url = url_atual
                print(f"  📄 Página: {url_atual[:70]}")

            # Coleta eventos novos
            novos = driver.execute_script(
                "var e = window._rec || []; window._rec = []; return e;"
            )
            if novos:
                eventos.extend(novos)
                # Mostra resumo dos novos eventos
                for ev in novos[total_impresso - len(eventos):] if total_impresso else novos:
                    _tipo = ev.get("type", "?")
                    _txt  = ev.get("text") or ev.get("fill") or ev.get("value", "")
                    _txt  = str(_txt).strip()[:40]
                    _av   = "  ⚠ " + ev["aviso"] if ev.get("aviso") else ""
                    print(f"  ✎ [{_tipo}] {_txt}{_av}")
                total_impresso = len(eventos)

        except Exception:
            pass  # página carregando — ignora

        time.sleep(0.4)

    print(f"\n  ⏹  Gravação encerrada — {len(eventos)} ação(ões) capturada(s).")
    return eventos


# ── Gerador de código ─────────────────────────────────────────────────

_BY_MAP = {
    "id":    "By.ID",
    "name":  "By.NAME",
    "css":   "By.CSS_SELECTOR",
    "xpath": "By.XPATH",
}


def _gerar_codigo(eventos: list, empresa_nome: str, complemento: bool = False) -> str:
    """
    Converte lista de eventos em código Python Selenium.
    complemento=True → gera extrato_complemento() em vez de extrato_gravado()
    """
    nome_func = "extrato_complemento" if complemento else "extrato_gravado"
    label     = "COMPLEMENTO" if complemento else "GRAVADO"

    # Gera as linhas de ação com 4 espaços (nível do corpo da função)
    linhas_acoes = []
    t_anterior = None

    for i, ev in enumerate(eventos):
        t = ev.get("t", 0)

        if t_anterior:
            pausa = min(max((t - t_anterior) / 1000, 0.3), 4.0)
            if pausa >= 0.4:
                linhas_acoes.append(f"    time.sleep({pausa:.1f})")
        t_anterior = t

        by_str = _BY_MAP.get(ev.get("by", "xpath"), "By.XPATH")
        val    = ev.get("value", "")
        aviso  = f"  # ⚠ {ev['aviso']}" if ev.get("aviso") else ""

        if ev["type"] == "click":
            txt = ev.get("text", "")[:50].replace("\n", " ")
            linhas_acoes.append(f"    # [{i:02d}] clique — {txt}")
            linhas_acoes.append(f"    el = wait.until(EC.element_to_be_clickable(({by_str}, {val!r})))  {aviso}")
            linhas_acoes.append( "    driver.execute_script('arguments[0].click();', el)")
        elif ev["type"] == "fill":
            fill = ev.get("fill", "")
            linhas_acoes.append(f"    # [{i:02d}] preenche → {fill!r}")
            linhas_acoes.append(f"    el = driver.find_element({by_str}, {val!r})  {aviso}")
            linhas_acoes.append(f"    _preencher(driver, el, {fill!r})")
        elif ev["type"] == "select":
            fill = ev.get("fill", "")
            txt  = ev.get("text", "")
            linhas_acoes.append(f"    # [{i:02d}] select → {txt!r} (value={fill!r})")
            linhas_acoes.append(f"    el = driver.find_element({by_str}, {val!r})  {aviso}")
            linhas_acoes.append( "    from selenium.webdriver.support.ui import Select")
            linhas_acoes.append(f"    Select(el).select_by_value({fill!r})")
        linhas_acoes.append("")

    acoes_str = "\n".join(linhas_acoes)
    agora     = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Monta o código SEM textwrap.dedent (evita strip de indentação das ações)
    linhas = [
        f'"""',
        f'Extrato Santander {"(COMPLEMENTO) " if complemento else ""}— gerado por santander_recorder.py',
        f'Empresa : {empresa_nome}',
        f'Gravado : {agora}',
        f'',
        f'⚠  Revise linhas com  # ⚠ ID_DINAMICO  — podem mudar entre sessões.',
        f'"""',
        f'',
        f'import time',
        f'import shutil',
        f'from pathlib import Path',
        f'from selenium import webdriver',
        f'from selenium.webdriver.common.by import By',
        f'from selenium.webdriver.support.ui import WebDriverWait',
        f'from selenium.webdriver.support import expected_conditions as EC',
        f'from selenium.common.exceptions import TimeoutException, NoSuchElementException',
        f'',
        f'',
        f'def _preencher(driver, el, valor: str):',
        f'    driver.execute_script(',
        f'        """',
        f'        var el=arguments[0]; var val=arguments[1];',
        f'        var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set;',
        f'        s.call(el,val);',
        f'        el.dispatchEvent(new Event("input",{{bubbles:true}}));',
        f'        el.dispatchEvent(new Event("change",{{bubbles:true}}));',
        f'        el.dispatchEvent(new Event("blur",{{bubbles:true}}));',
        f'        """,',
        f'        el, valor,',
        f'    )',
        f'    time.sleep(0.3)',
        f'',
        f'',
        f'def {nome_func}(',
        f'    driver:       webdriver.Chrome,',
        f'    empresa_nome: str,',
        f'    mm:           str,',
        f'    output_dir:   Path,',
        f'    download_dir: Path,',
        f'):',
        f'    """Executa o fluxo {label.lower()} para empresa já logada."""',
        f'    wait = WebDriverWait(driver, 20)',
        f'    output_dir.mkdir(parents=True, exist_ok=True)',
        f'    print(f"  [{label}] {{empresa_nome}}")',
        f'',
        acoes_str,
        f'    print(f"  ✓ {label.lower()} concluído: {{empresa_nome}}")',
    ]

    return "\n".join(linhas)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 55)
    print("  GRAVADOR DE MACRO — SANTANDER NET EMPRESA PJ")
    print("=" * 55)

    # Lê empresas
    print("\nLendo planilha...")
    try:
        empresas = ler_empresas_santander()
    except FileNotFoundError as e:
        print(f"ERRO: {e}")
        sys.exit(1)

    if not empresas:
        print("Nenhuma empresa válida.")
        sys.exit(0)

    # Escolha da empresa
    print(f"\n{len(empresas)} empresa(s) disponível(is):\n")
    for i, e in enumerate(empresas, 1):
        print(f"  [{i}] {e.nome}")

    print("\nDigite o número da empresa para gravar (ENTER = primeira): ", end="")
    escolha = input().strip()
    if escolha.isdigit() and 1 <= int(escolha) <= len(empresas):
        empresa = empresas[int(escolha) - 1]
    else:
        empresa = empresas[0]

    print(f"\nEmpresa selecionada: {empresa.nome}")

    # Tipo de gravação
    print("\nTipo de gravação:")
    print("  [1] Principal  (extrato CC  → sobrescreve santander_extrato_gravado.py)")
    print("  [2] Complemento (investimentos etc. → sobrescreve santander_extrato_complemento.py)")
    print("Digite 1 ou 2 (ENTER = 1): ", end="")
    tipo = input().strip()
    eh_complemento = (tipo == "2")
    arquivo_destino = (
        _DIR / "santander_extrato_complemento.py"
        if eh_complemento
        else ARQUIVO_GERADO
    )
    print(f"  → {'Complemento' if eh_complemento else 'Principal'} — salvando em {arquivo_destino.name}\n")

    # Login
    driver = criar_driver(headless=False, download_dir=str(Path.home() / "Downloads"))
    stop_event = threading.Event()

    try:
        sessao = SantanderSession(driver)
        print("\nRealizando login...")
        logado = sessao.login_completo(empresa)

        if not logado:
            print("✗ Login falhou. Encerrando.")
            driver.quit()
            sys.exit(1)

        print("✓ Login OK\n")

        # Inicia listener ESC em thread separada
        t_esc = threading.Thread(
            target=_iniciar_listener_esc, args=(stop_event,), daemon=True
        )
        t_esc.start()

        # Injeta JS imediatamente após login
        driver.execute_script(INJECT_JS)

        # Grava
        eventos = _gravar(driver, stop_event)

    finally:
        pass  # não fecha driver aqui — mantém aberto para o usuário ver

    if not eventos:
        print("\nNenhuma ação gravada.")
        driver.quit()
        sys.exit(0)

    # Gera código
    print(f"\nGerando código ({len(eventos)} ações)...")
    codigo = _gerar_codigo(eventos, empresa.nome, complemento=eh_complemento)

    arquivo_destino.write_text(codigo, encoding="utf-8")
    print(f"\n✓ Arquivo gerado: {arquivo_destino}")

    # Salva também o JSON bruto (útil para depuração)
    json_path = _DIR / "gravacao_raw.json"
    json_path.write_text(
        json.dumps(eventos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  (JSON bruto em: {json_path.name})")

    print("\nPressione ENTER para fechar o browser...")
    input()
    driver.quit()

    print("\nPróximo passo:")
    print(f"  Abra  {arquivo_destino.name}  e revise as linhas com ⚠")
    if eh_complemento:
        print("  O complemento roda automaticamente após o extrato CC em main.py")
    else:
        print("  Rode  python main.py  para processar todas as empresas")


if __name__ == "__main__":
    main()
