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
