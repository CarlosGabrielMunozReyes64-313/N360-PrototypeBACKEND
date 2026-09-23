"""Normalización de fotos de perfil.

El front ya recorta la foto (cuadrada, 512 px) antes de subirla, pero el
backend no confía en eso: cualquier cliente puede llamar a la API
directamente. Por eso toda imagen se vuelve a decodificar y a codificar
aquí, lo que de paso:

  * descarta cualquier cosa que no sea realmente una imagen (un archivo
    con cabecera de JPEG y contenido arbitrario no sobrevive a Pillow);
  * elimina metadatos EXIF — incluida la ubicación GPS que traen muchas
    fotos de celular;
  * aplica la orientación EXIF antes de descartarla, para que la foto no
    quede de lado;
  * limita las dimensiones, para que nadie pueda dejar en la base una
    imagen gigante que tumbe el navegador de quien la vea (p. ej. el
    panel de admin, que muestra las fotos de todos).

Es trabajo de CPU: el router lo corre en un hilo aparte
(run_in_threadpool) para no bloquear el event loop.
"""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError, features

# Bytes máximos que se aceptan en la subida. Lo que manda el front pesa
# unas decenas de KB; el margen es para clientes que suban la foto sin
# recortar.
MAX_BYTES_ENTRADA = 5 * 1024 * 1024

# Lado de la imagen que se guarda. En pantalla la foto más grande mide
# 112 px, así que 512 cubre de sobra pantallas de alta densidad.
LADO_SALIDA = 512

# Tope de píxeles de la imagen de entrada (≈ una foto de 40 MP), revisado
# con la cabecera ANTES de decodificar: protege contra "bombas" de
# descompresión (un PNG de pocos KB que se expande a varios GB).
MAX_PIXELES_ENTRADA = 40_000_000

LADO_MINIMO = 16

FORMATOS_ACEPTADOS = {"JPEG", "PNG", "WEBP", "GIF"}


class ImagenInvalida(ValueError):
    """La imagen no se puede usar como foto de perfil. El mensaje es apto
    para mostrarse tal cual al usuario."""


def _formato_salida() -> tuple[str, str, dict]:
    # Las ruedas oficiales de Pillow traen WebP; si una instalación rara no
    # lo tuviera, JPEG sigue siendo una salida perfectamente válida.
    if features.check("webp"):
        return "WEBP", "image/webp", {"quality": 88, "method": 4}
    return "JPEG", "image/jpeg", {"quality": 88, "optimize": True, "progressive": True}


def _aplanar_sobre_blanco(img: Image.Image) -> Image.Image:
    """Convierte a RGB. Las zonas transparentes quedan blancas (así se ve
    igual que en el editor del front, que también pinta fondo blanco)."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        fondo = Image.new("RGB", rgba.size, (255, 255, 255))
        fondo.paste(rgba, mask=rgba.getchannel("A"))
        return fondo
    return img.convert("RGB")


def procesar_foto_perfil(datos: bytes) -> tuple[bytes, str]:
    """Valida y normaliza una foto de perfil.

    Devuelve (bytes, mime) listos para guardar: imagen cuadrada (recorte
    centrado si no lo era), de como máximo LADO_SALIDA px de lado, sin
    metadatos. Lanza ImagenInvalida con un mensaje para el usuario.
    """
    if not datos:
        raise ImagenInvalida("No llegó ninguna imagen.")
    if len(datos) > MAX_BYTES_ENTRADA:
        raise ImagenInvalida("La imagen es demasiado pesada (máximo 5 MB).")

    try:
        with Image.open(BytesIO(datos)) as original:
            if original.format not in FORMATOS_ACEPTADOS:
                raise ImagenInvalida("Formato no soportado. Usa una imagen JPG, PNG o WebP.")

            ancho, alto = original.size
            if ancho * alto > MAX_PIXELES_ENTRADA:
                raise ImagenInvalida("La imagen tiene demasiados píxeles. Usa una de menor resolución.")
            if min(ancho, alto) < LADO_MINIMO:
                raise ImagenInvalida("La imagen es demasiado pequeña.")

            # En un GIF animado solo cuenta el primer cuadro.
            original.seek(0)
            img = ImageOps.exif_transpose(original)
            img = _aplanar_sobre_blanco(img)
    except ImagenInvalida:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as exc:
        raise ImagenInvalida("El archivo no es una imagen válida.") from exc

    lado = min(LADO_SALIDA, img.width, img.height)
    img = ImageOps.fit(img, (lado, lado), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

    formato, mime, opciones = _formato_salida()
    salida = BytesIO()
    # save() sin exif= ni icc_profile= no copia metadatos a la salida.
    img.save(salida, formato, **opciones)
    return salida.getvalue(), mime
