"""Teste rápido de login Caixa — sem Google Sheets."""
from caixa_login import criar_driver, CaixaSession, EmpresaCaixa

empresa = EmpresaCaixa(
    nome    = "MAGNIFICA FASHION",
    usuario = "KASSEUSPRESTES01",
    senha   = "3076464",
)

driver = criar_driver(headless=False)
sessao = CaixaSession(driver)
ok = sessao.login_completo(empresa)
print("\n✓ LOGIN OK" if ok else "\n✗ LOGIN FALHOU")
input("\nPressione Enter para fechar o Chrome...")
driver.quit()
