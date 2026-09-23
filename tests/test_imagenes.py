"""Pruebas de la normalización de fotos de perfil (app/imagenes.py).

No necesitan base de datos: generan imágenes en memoria con Pillow.
"""

from io import BytesIO

import pytest
from PIL import Image

from app.imagenes import (
    LADO_SALIDA, MAX_BYTES_ENTRADA, ImagenInvalida, procesar_foto_perfil,
)


def _imagen(formato: str, tamano=(800, 600), modo="RGB", color=(4, 169, 122, 255), **opciones) -> bytes:
    img = Image.new(modo, tamano, color[: len(modo)] if modo != "P" else 0)
    salida = BytesIO()
    img.save(salida, formato, **opciones)
    return salida.getvalue()


def _abrir(datos: bytes) -> Image.Image:
    img = Image.open(BytesIO(datos))
    img.load()
    return img


@pytest.mark.parametrize("formato", ["JPEG", "PNG", "WEBP", "GIF"])
def test_acepta_formatos_comunes_y_devuelve_cuadrada(formato):
    datos, mime = procesar_foto_perfil(_imagen(formato))
    img = _abrir(datos)
    assert mime in {"image/webp", "image/jpeg"}
    assert img.width == img.height == min(LADO_SALIDA, 600)


def test_reduce_imagenes_grandes_a_512():
    datos, _ = procesar_foto_perfil(_imagen("PNG", tamano=(3000, 2000)))
    assert _abrir(datos).size == (LADO_SALIDA, LADO_SALIDA)


def test_no_agranda_imagenes_pequenas():
    datos, _ = procesar_foto_perfil(_imagen("PNG", tamano=(120, 200)))
    assert _abrir(datos).size == (120, 120)


def test_transparencia_queda_blanca():
    datos, _ = procesar_foto_perfil(_imagen("PNG", tamano=(64, 64), modo="RGBA", color=(0, 0, 0, 0)))
    r, g, b = _abrir(datos).convert("RGB").getpixel((32, 32))
    assert min(r, g, b) > 240


def test_elimina_exif_y_aplica_orientacion():
    # 200x100 con orientación 6 (girar 90°): la foto "real" es vertical.
    img = Image.new("RGB", (200, 100), (200, 30, 30))
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation
    exif[0x010F] = "Fabricante de prueba"  # Make
    salida = BytesIO()
    img.save(salida, "JPEG", exif=exif.tobytes())

    datos, _ = procesar_foto_perfil(salida.getvalue())
    resultado = _abrir(datos)
    assert resultado.size == (100, 100)
    assert not resultado.getexif(), "La salida no debe conservar metadatos EXIF"


def test_rechaza_lo_que_no_es_imagen():
    with pytest.raises(ImagenInvalida):
        procesar_foto_perfil(b"esto no es una imagen")


def test_rechaza_cabecera_de_jpeg_con_basura():
    with pytest.raises(ImagenInvalida):
        procesar_foto_perfil(b"\xff\xd8\xff\xe0" + b"\x00" * 200)


def test_rechaza_vacio():
    with pytest.raises(ImagenInvalida):
        procesar_foto_perfil(b"")


def test_rechaza_demasiado_pesada():
    with pytest.raises(ImagenInvalida):
        procesar_foto_perfil(b"\x00" * (MAX_BYTES_ENTRADA + 1))


def test_rechaza_demasiado_pequena():
    with pytest.raises(ImagenInvalida):
        procesar_foto_perfil(_imagen("PNG", tamano=(8, 8)))


@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
def test_rechaza_bomba_de_descompresion():
    # PNG de una sola fila de color: pesa poco pero declara 10000x10000 px.
    datos = _imagen("PNG", tamano=(10_000, 10_000), modo="L", color=(0,), optimize=True)
    assert len(datos) < MAX_BYTES_ENTRADA
    with pytest.raises(ImagenInvalida):
        procesar_foto_perfil(datos)


def test_rechaza_svg():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(ImagenInvalida):
        procesar_foto_perfil(svg)
