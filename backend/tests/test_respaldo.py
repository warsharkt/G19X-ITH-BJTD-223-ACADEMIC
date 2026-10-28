"""Pruebas del respaldo de la base (P8, scripts/respaldo.py).

Las reglas (comparar conteos, cuales respaldos se borran, donde no puede ir
la llave, huella) se prueban sin Docker. La prueba de punta a punta respalda
la base local y la restaura en una base temporal: solo corre si existe el
contenedor rrhh_db (en GitHub Actions la base no es de este compose).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import respaldo
from scripts.respaldo import ErrorDeRespaldo


def test_un_respaldo_completo_cuadra():
    conteo = {"empleados": 350, "avisos": 12}
    assert respaldo.comparar(conteo, conteo, dict(conteo)) == ([], [])


def test_faltan_filas_o_tablas_en_el_respaldo():
    antes = {"empleados": 350, "avisos": 12}
    diferencias, _ = respaldo.comparar(antes, antes, {"empleados": 349})
    assert diferencias == ["avisos: falta en el respaldo", "empleados: 350 filas en la base y 349 en el respaldo"]


def test_una_tabla_que_cambio_mientras_se_respaldaba_no_es_error():
    """La API escribio dos avisos durante el respaldo: la foto queda entre ambos conteos."""
    diferencias, en_movimiento = respaldo.comparar({"avisos": 10}, {"avisos": 12}, {"avisos": 11})
    assert diferencias == [] and en_movimiento == ["avisos"]
    diferencias, _ = respaldo.comparar({"avisos": 10}, {"avisos": 12}, {"avisos": 3})
    assert diferencias == ["avisos: 3 filas en el respaldo, fuera de 10–12"]


def test_se_conservan_los_mas_recientes(tmp_path):
    for nombre in ("talentia-20261001-020000.dump", "talentia-20261003-020000.dump",
                   "talentia-20261002-020000.dump", "antes-de-restaurar-20261001-090000.dump"):
        (tmp_path / nombre).write_bytes(b"x")
    archivos = respaldo.respaldos(tmp_path)
    assert [a.name for a in archivos] == [
        "talentia-20261001-020000.dump", "talentia-20261002-020000.dump", "talentia-20261003-020000.dump",
    ]  # la copia previa a una restauracion nunca se borra sola
    assert [a.name for a in respaldo.sobrantes(archivos, 2)] == ["talentia-20261001-020000.dump"]
    assert respaldo.sobrantes(archivos, 0) == []  # 0 = conservar todos


def test_la_llave_no_se_copia_junto_a_los_respaldos(tmp_path):
    with pytest.raises(ErrorDeRespaldo, match="junto a los respaldos"):
        respaldo.copiar_llave(tmp_path / "respaldos" / "llave", tmp_path / "respaldos")


def test_la_llave_se_copia_a_otra_carpeta(tmp_path, monkeypatch):
    monkeypatch.setenv("MFA_LLAVE", "llave-de-prueba")
    copia = respaldo.copiar_llave(tmp_path / "usb", tmp_path / "respaldos")
    assert copia.parent == tmp_path / "usb" and copia.read_text(encoding="ascii").strip() == "llave-de-prueba"


def test_no_se_restaura_un_archivo_danado(tmp_path):
    archivo = tmp_path / "talentia-20261001-020000.dump"
    archivo.write_bytes(b"respaldo")
    with pytest.raises(ErrorDeRespaldo, match="Falta"):
        respaldo.verificar_huella(archivo)
    (tmp_path / (archivo.name + ".sha256")).write_text(f"{respaldo.huella(archivo)}  {archivo.name}\n")
    respaldo.verificar_huella(archivo)  # integro: no dice nada
    archivo.write_bytes(b"respaldo cambiado")
    with pytest.raises(ErrorDeRespaldo, match="no coincide"):
        respaldo.verificar_huella(archivo)


def _hay_contenedor() -> bool:
    if shutil.which("docker") is None:
        return False
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", respaldo.contenedor()],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


@pytest.mark.skipif(not _hay_contenedor(), reason="sin el contenedor rrhh_db de docker compose")
def test_respaldar_y_probar_la_restauracion(tmp_path: Path):
    antes = respaldo.conteos(respaldo.base_db())
    archivo = respaldo.respaldar(tmp_path)
    assert archivo.name.startswith("talentia-") and archivo.stat().st_size > 0
    respaldo.verificar_huella(archivo)
    filas, _ = respaldo.probar(archivo, antes)
    assert filas > 0 and "empleados" in antes
    # la base temporal de la prueba no se queda
    assert respaldo.BASE_DE_PRUEBA not in respaldo._psql("postgres", "SELECT datname FROM pg_database")
