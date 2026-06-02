"""
Gravador de macro — Sicredi PJ.

Como usar:
  1. Execute:  python sicredi_recorder.py
  2. Escolha a empresa quando solicitado
  3. O Chrome abre na home do Sicredi — faça login manualmente
  4. Faça o processo de extrato MANUALMENTE no browser
  5. Pressione ESC 3× rápido (menos de 1 segundo) para parar
  6. O arquivo  sicredi_extrato_gravado.py  é gerado com o código pronto

Notas:
  - Senha do teclado virtual NÃO é gravada (pares mudam por sessão).
    O login automático de sicredi_login.py será usado na produção.
  - Botão "Imprimir" → bloco CDP inserido automaticamente no código gerado.
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

from sicredi_login  import criar_driver
from sheets_sicredi import ler_empresas_sicredi

_DIR = Path(__file__).parent
load_dotenv(_DIR / ".env")

ARQUIVO_GERADO = _DIR / "sicredi_extrato_gravado.py"
DOWNLOADS      = Path.home() / "Downloads"
BANCO_DIR      = DOWNLOADS / "SICREDI"


# ── JavaScript injetado na página ─────────────────────────────────────

INJECT_JS = r"""
(function() {
  if (window._rec_ativo) return;
  window._rec_ativo = true;
  window._rec = window._rec || [];

  function _sel(el) {
    if (el.id && !el.id.match(/^j_id/) && !el.id.match(/^\d/)) {
      return {by: 'id', value: el.id};
    }
    var fcn = el.getAttribute && el.getAttribute('formcontrolname');
    if (fcn) return {by: 'css', value: '[formcontrolname="' + fcn + '"]'};
    if (el.name) return {by: 'name', value: el.name};
    var txt = (el.textContent || el.innerText || '').trim()
                .replace(/\s+/g, ' ').substring(0, 60);
    if (txt && !['INPUT','TEXTAREA','SELECT'].includes(el.tagName)) {
      return {by: 'xpath',
              value: '//' + el.tagName.toLowerCase() +
                     '[normalize-space(.)="' + txt.replace(/"/g,"'") + '"]'};
    }
    var cls = (el.className || '').trim().split(/\s+/)
      .filter(function(c) {
        return c && !c.match(/^(ng-|active|focus|hover|selected|disabled|ui-state|is-)/);
      })
      .slice(0, 3).join('.');
    if (cls) return {by: 'css', value: el.tagName.toLowerCase() + '.' + cls};
    if (el.id) return {by: 'id', value: el.id, aviso: 'ID_DINAMICO'};
    return {by: 'xpath', value: '(REVISAR: ' + el.tagName + ')', aviso: 'SEM_SELETOR'};
  }

  document.addEventListener('click', function(e) {
    var el = e.target;
    if (['BODY','HTML','SCRIPT'].includes(el.tagName)) return;
    var s = _sel(el);
    window._rec.push({
      type: 'click', by: s.by, value: s.value, aviso: s.aviso || null,
      text: (el.textContent || el.innerText || '').trim()
              .replace(/\s+/g, ' ').substring(0, 80),
      tag: el.tagName, t: Date.now()
    });
  }, true);

  document.addEventListener('blur', function(e) {
    var el = e.target;
    if (!['INPUT','TEXTAREA','SELECT'].includes(el.tagName)) return;
    if (el.type === 'password' || el.type === 'hidden') return;
    var s = _sel(el);
    window._rec.push({
      type: 'fill', by: s.by, value: s.value, aviso: s.aviso || null,
      fill: el.value, tag: el.tagName, t: Date.now()
    });
  }, true);

  document.addEventListener('change', function(e) {
    var el = e.target;
    if (el.tagName !== 'SELECT') return;
    var s = _sel(el);
    window._rec.push({
      type: 'select', by: s.by, value: s.value,
      fill: el.value,
      text: el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : '',
      t: Date.now()
    });
  }, true);

})();
"""


# ── Listener ESC × 3 ─────────────────────────────────────────────────

def _iniciar_listener_esc(stop_event: threading.Event):
    try:
        from pynput import keyboard as kb
        esc_times = []

        def on_press(key):
            nonlocal esc_times
            if key == kb.Key.esc:
                agora = time.time()
                esc_times = [t for t in esc_times if agora - t < 1.2]
                esc_times.append(agora)
                if len(esc_times) >= 3:
                    stop_event.set()
                    return False

        listener = kb.Listener(on_press=on_press)
        listener.start()
        stop_event.wait()
        try:
            listener.stop()
        except Exception:
            pass
    except ImportError:
        print("\n[AVISO] pynput não instalado — pressione ENTER para parar.\n")
        input()
        stop_event.set()


# ── Loop de gravação ──────────────────────────────────────────────────

def _gravar(
    driver:     webdriver.Chrome,
    stop_event: threading.Event,
    output_dir: Path,
) -> list:
    eventos    = []
    ultima_url = ""
    pdf_salvo  = False

    print("\n" + "█" * 55)
    print("  ⏺  GRAVAÇÃO INICIADA")
    print(f"  Pasta: {output_dir}")
    print("  Faça o login e o processo de extrato no browser.")
    print("  Pressione  ESC × 3 rápido  para encerrar.")
    print("█" * 55 + "\n")

    while not stop_event.is_set():
        try:
            url_atual = driver.current_url
            if url_atual != ultima_url:
                driver.execute_script(INJECT_JS)
                ultima_url = url_atual
                print(f"  Página: {url_atual[:70]}")

            novos = driver.execute_script(
                "var e = window._rec || []; window._rec = []; return e;"
            )
            if novos:
                eventos.extend(novos)
                for ev in novos:
                    _tipo = ev.get("type", "?").upper()
                    _by   = ev.get("by", "?").upper()
                    _val  = str(ev.get("value", ""))[:50]
                    _txt  = str(ev.get("text") or ev.get("fill") or "").strip()[:40]
                    _av   = "  ⚠ " + ev["aviso"] if ev.get("aviso") else ""
                    _tag  = ev.get("tag", "")
                    if _tipo == "CLICK":
                        print(f"  ✎ CLICK  <{_tag}>  [{_by}={_val!r}]  texto={_txt!r}{_av}")
                    elif _tipo == "FILL":
                        print(f"  ✎ FILL   <{_tag}>  [{_by}={_val!r}]  valor={_txt!r}{_av}")
                    elif _tipo == "SELECT":
                        _opt = str(ev.get("text", ""))[:30]
                        print(f"  ✎ SELECT <{_tag}>  [{_by}={_val!r}]  opção={_opt!r}{_av}")
                    else:
                        print(f"  ✎ [{_tipo}] {_by}={_val!r}{_av}")

                    val = ev.get("value", "")
                    txt = ev.get("text", "").lower()
                    if not pdf_salvo and ("imprimir" in txt or "imprimir" in val.lower()):
                        print("  → Imprimir detectado — salve o PDF manualmente e continue.")
                        print(f"     Sugestão de pasta: {output_dir}")
                        pdf_salvo = True

        except Exception:
            pass
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

_CDP_PDF = '''\
    # ── PDF via CDP (sem diálogo nativo) ─────────────────────────────
    janelas_antes = set(driver.window_handles)
    # (clique em Imprimir já feito acima)
    nova_janela = None
    prazo = time.time() + 10
    while time.time() < prazo:
        novas = set(driver.window_handles) - janelas_antes
        if novas:
            nova_janela = novas.pop()
            break
        time.sleep(0.2)
    if nova_janela:
        driver.switch_to.window(nova_janela)
        driver.execute_script("window.print = function() {};")
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(1.5)
        _salvar_pdf_cdp(driver, output_dir / f"{mm} - EXTRATOS BANCÁRIOS CC - SICREDI - {empresa_nome}.pdf")
        driver.close()
        driver.switch_to.window(list(janelas_antes)[0])
    else:
        driver.execute_script("window.print = function() {};")
        time.sleep(1.5)
        _salvar_pdf_cdp(driver, output_dir / f"{mm} - EXTRATOS BANCÁRIOS CC - SICREDI - {empresa_nome}.pdf")
    time.sleep(1.5)
'''


def _gerar_codigo(eventos: list, empresa_nome: str) -> str:
    linhas_acoes = []
    t_anterior   = None

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
            linhas_acoes.append(f"    # [{i:02d}] {txt}")
            linhas_acoes.append(f"    el = wait.until(EC.element_to_be_clickable(({by_str}, {val!r})))  {aviso}")
            linhas_acoes.append( "    driver.execute_script('arguments[0].click();', el)")
            if "imprimir" in txt.lower() or "imprimir" in val.lower():
                linhas_acoes.append("")
                linhas_acoes.append(_CDP_PDF)
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
            linhas_acoes.append( "    from selenium.webdriver.support.ui import Select as _Sel")
            linhas_acoes.append(f"    _Sel(el).select_by_value({fill!r})")
        linhas_acoes.append("")

    acoes_str = "\n".join(linhas_acoes)
    agora     = datetime.now().strftime("%d/%m/%Y %H:%M")

    linhas = [
        '"""',
        f'Extrato CC Sicredi — gerado por sicredi_recorder.py',
        f'Empresa : {empresa_nome}',
        f'Gravado : {agora}',
        '',
        '⚠  Revise linhas com  # ⚠ ID_DINAMICO  — podem mudar entre sessões.',
        '"""',
        '',
        'import base64',
        'import time',
        'import shutil',
        'import calendar',
        'from datetime import date',
        'from pathlib import Path',
        'from selenium import webdriver',
        'from selenium.webdriver.common.by import By',
        'from selenium.webdriver.support.ui import WebDriverWait',
        'from selenium.webdriver.support import expected_conditions as EC',
        'from selenium.common.exceptions import TimeoutException, NoSuchElementException',
        '',
        '',
        '_MESES_PT = {',
        '    1: "Janeiro",  2: "Fevereiro", 3: "Março",    4: "Abril",',
        '    5: "Maio",     6: "Junho",     7: "Julho",     8: "Agosto",',
        '    9: "Setembro", 10: "Outubro",  11: "Novembro", 12: "Dezembro",',
        '}',
        '',
        '',
        'def _mes_anterior():',
        '    hoje = date.today()',
        '    ano, mes = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)',
        '    import calendar as _cal',
        '    ultimo = _cal.monthrange(ano, mes)[1]',
        '    mm = f"{mes:02d}"',
        '    return f"01/{mm}/{ano}", f"{ultimo}/{mm}/{ano}", mm, mes, ano',
        '',
        '',
        'def _preencher(driver, el, valor: str):',
        '    driver.execute_script(',
        '        """',
        '        var el=arguments[0]; var val=arguments[1];',
        '        var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,"value").set;',
        '        s.call(el,val);',
        '        el.dispatchEvent(new Event("input",{bubbles:true}));',
        '        el.dispatchEvent(new Event("change",{bubbles:true}));',
        '        el.dispatchEvent(new Event("blur",{bubbles:true}));',
        '        """,',
        '        el, valor,',
        '    )',
        '    time.sleep(0.3)',
        '',
        '',
        'def _salvar_pdf_cdp(driver, destino: Path):',
        '    result = driver.execute_cdp_cmd("Page.printToPDF", {',
        '        "printBackground": True, "paperWidth": 8.27, "paperHeight": 11.69,',
        '        "marginTop": 0.4, "marginBottom": 0.4, "marginLeft": 0.4, "marginRight": 0.4,',
        '    })',
        '    destino.parent.mkdir(parents=True, exist_ok=True)',
        '    destino.write_bytes(base64.b64decode(result["data"]))',
        '    print(f"  ✓ PDF salvo: {destino.name}")',
        '',
        '',
        'def _renomear(download_dir: Path, output_dir: Path, nome: str, ext: str, timeout: int = 45):',
        '    pastas = [download_dir, Path.home() / "Downloads"]',
        '    prazo  = time.time() + timeout',
        '    while time.time() < prazo:',
        '        for pasta in pastas:',
        '            try:',
        '                candidatos = [',
        '                    f for f in pasta.iterdir()',
        '                    if f.suffix.lower() == ext.lower()',
        '                    and not f.name.endswith(".crdownload")',
        '                    and not f.name.endswith(".tmp")',
        '                    and (time.time() - f.stat().st_mtime) < 300',
        '                ]',
        '            except Exception:',
        '                continue',
        '            if candidatos:',
        '                arq = max(candidatos, key=lambda f: f.stat().st_mtime)',
        '                destino = output_dir / f"{nome}{ext}"',
        '                if destino.exists(): destino.unlink()',
        '                output_dir.mkdir(parents=True, exist_ok=True)',
        '                shutil.move(str(arq), str(destino))',
        '                print(f"  ✓ Salvo: {destino.name}")',
        '                return',
        '        time.sleep(0.8)',
        '    print(f"  ✗ Arquivo {ext} não chegou em {timeout}s")',
        '',
        '',
        'def extrato_sicredi(',
        '    driver:       webdriver.Chrome,',
        '    empresa_nome: str,',
        '    mm:           str,',
        '    output_dir:   Path,',
        '    download_dir: Path,',
        '):',
        '    """Executa extrato CC (PDF + OFX) para empresa já logada."""',
        '    wait = WebDriverWait(driver, 20)',
        '    output_dir.mkdir(parents=True, exist_ok=True)',
        '    _, _, mm, mes_ant, ano_ant = _mes_anterior()',
        '    print(f"  [CC] {empresa_nome} — {_MESES_PT[mes_ant]}/{ano_ant}")',
        '',
        acoes_str,
        '    # ── OFX: renomeia arquivo baixado ────────────────────────────',
        '    nome_ofx = f"{mm} - EXTRATOS BANCÁRIOS CC - SICREDI - {empresa_nome}"',
        '    _renomear(download_dir, output_dir, nome_ofx, ".ofx")',
        '    print(f"  ✓ CC concluído: {empresa_nome}")',
    ]

    return "\n".join(linhas)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  GRAVADOR DE MACRO — SICREDI PJ")
    print("=" * 55)

    print("\nLendo planilha...")
    try:
        empresas = ler_empresas_sicredi()
    except FileNotFoundError as e:
        print(f"ERRO: {e}")
        sys.exit(1)

    if not empresas:
        print("Nenhuma empresa válida.")
        sys.exit(0)

    print(f"\n{len(empresas)} empresa(s):\n")
    for i, e in enumerate(empresas, 1):
        print(f"  [{i}] {e.nome}")

    print("\nDigite o número (ENTER = primeira): ", end="")
    escolha = input().strip()
    empresa = (
        empresas[int(escolha) - 1]
        if escolha.isdigit() and 1 <= int(escolha) <= len(empresas)
        else empresas[0]
    )
    print(f"\nEmpresa: {empresa.nome}")

    output_dir = BANCO_DIR / empresa.nome
    output_dir.mkdir(parents=True, exist_ok=True)
    BANCO_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n  + Pasta: {output_dir}")

    driver     = criar_driver(headless=False, download_dir=str(output_dir))
    stop_event = threading.Event()

    try:
        # Abre home do Sicredi — usuário faz login manualmente
        print(f"\nAbrindo https://www.sicredi.com.br/home/ ...")
        driver.get("https://www.sicredi.com.br/home/")

        threading.Thread(
            target=_iniciar_listener_esc, args=(stop_event,), daemon=True
        ).start()

        driver.execute_script(INJECT_JS)
        eventos = _gravar(driver, stop_event, output_dir)

    finally:
        pass

    if not eventos:
        print("\nNenhuma ação gravada.")
        driver.quit()
        sys.exit(0)

    print(f"\nGerando código ({len(eventos)} ações)...")
    codigo = _gerar_codigo(eventos, empresa.nome)
    ARQUIVO_GERADO.write_text(codigo, encoding="utf-8")
    print(f"\n✓ Gerado: {ARQUIVO_GERADO.name}")

    json_path = _DIR / "sicredi_gravacao_raw.json"
    json_path.write_text(
        json.dumps(eventos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  JSON bruto: {json_path.name}")

    print("\nPressione ENTER para fechar o browser...")
    input()
    driver.quit()


if __name__ == "__main__":
    main()
