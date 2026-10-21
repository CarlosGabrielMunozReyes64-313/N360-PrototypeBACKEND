"""Lectura y escritura del autodiagnóstico RSE Express.

Compartido por /empresa (la empresa responde) y /admin (NEXUS lee y
clasifica). Todas las funciones reciben una conexión que ya tiene fijado
app.current_usuario_id dentro de una transacción: el RLS decide qué filas
ve cada quien.
"""
import json
from uuid import UUID

import asyncpg

from .schemas_empresa import DiagnosticoIn, DiagnosticoOut, RespuestaIn, RespuestaOut, TamizajeOut

FORMATO_RSE = "rse_express"

SQL_TAMIZAJE = """
    SELECT ciclo_id, anio, tamano, ingresos_rango, personas, vinculacion,
           vinculacion_detalle, zonas, territorio, vecinos, clientes, clientes_detalle,
           actualizado_en
      FROM nexus360.ciclo_tamizaje
     WHERE empresa_id = $1
     ORDER BY anio DESC, creado_en DESC
     LIMIT 1
"""


def etapa_de(fila: asyncpg.Record) -> str | None:
    """Traduce (valor, es_na, es_diferente) a la etapa que ve el front."""
    if fila["es_na"]:
        return "NA"
    if fila["es_diferente"]:
        return "diferente"
    if fila["valor"] is not None:
        return str(fila["valor"])
    return None


def columnas_de(r: RespuestaIn) -> tuple[int | None, bool, bool]:
    """Etapa -> (valor, es_na, es_diferente) para guardar."""
    if r.etapa == "NA":
        return None, True, False
    if r.etapa == "diferente":
        return None, False, True
    if r.etapa is None:
        return None, False, False
    return int(r.etapa), False, False


async def ultimo_tamizaje(conn: asyncpg.Connection, empresa_id: UUID) -> TamizajeOut | None:
    fila = await conn.fetchrow(SQL_TAMIZAJE, empresa_id)
    return TamizajeOut(**dict(fila)) if fila else None


async def diagnostico_vigente_id(conn: asyncpg.Connection, empresa_id: UUID, ciclo_id: UUID) -> UUID | None:
    return await conn.fetchval(
        """
        SELECT diagnostico_id FROM nexus360.diagnostico
         WHERE empresa_id = $1 AND ciclo_id = $2 AND formato_id = $3 AND estado <> 'archivado'
         ORDER BY creado_en DESC LIMIT 1
        """,
        empresa_id, ciclo_id, FORMATO_RSE,
    )


async def leer_diagnostico(conn: asyncpg.Connection, diagnostico_id: UUID) -> DiagnosticoOut | None:
    d = await conn.fetchrow(
        """
        SELECT diagnostico_id, formato_id, estado, creado_en, completado_en, actualizado_en,
               comentario_final, priorizacion
          FROM nexus360.diagnostico WHERE diagnostico_id = $1
        """,
        diagnostico_id,
    )
    if d is None:
        return None

    filas = await conn.fetch(
        """
        SELECT r.respuesta_id, p.codigo, r.valor, r.es_na, r.es_diferente, r.texto, r.ejemplos,
               r.otro_texto, r.valor_clasificado, r.clasificado_en, r.respondido_en
          FROM nexus360.respuesta r
          JOIN nexus360.pregunta p ON p.pregunta_id = r.pregunta_id
         WHERE r.diagnostico_id = $1
         ORDER BY p.codigo
        """,
        diagnostico_id,
    )
    respuestas = {
        f["codigo"]: RespuestaOut(
            respuesta_id=f["respuesta_id"],
            texto=f["texto"] or "",
            ejemplos=list(f["ejemplos"] or []),
            otro=f["otro_texto"] or "",
            etapa=etapa_de(f),
            clasificada=f["valor_clasificado"],
            clasificado_en=f["clasificado_en"],
            respondido_en=f["respondido_en"],
        )
        for f in filas
    }

    materias = await conn.fetch(
        """
        SELECT dim.numero, rm.fortalecer
          FROM nexus360.respuesta_materia rm
          JOIN nexus360.dimension dim ON dim.dimension_id = rm.dimension_id
         WHERE rm.diagnostico_id = $1
        """,
        diagnostico_id,
    )
    priorizacion = d["priorizacion"]
    if isinstance(priorizacion, str):
        priorizacion = json.loads(priorizacion)

    return DiagnosticoOut(
        diagnostico_id=d["diagnostico_id"],
        formato_id=d["formato_id"],
        estado=d["estado"],
        creado_en=d["creado_en"],
        completado_en=d["completado_en"],
        actualizado_en=d["actualizado_en"],
        respuestas=respuestas,
        fortalecer={m["numero"]: m["fortalecer"] for m in materias},
        comentario_final=d["comentario_final"],
        priorizacion=priorizacion,
    )


async def guardar_diagnostico(
    conn: asyncpg.Connection, empresa_id: UUID, ciclo_id: UUID, payload: DiagnosticoIn,
) -> UUID:
    """Crea (si hace falta) el diagnóstico del ciclo y escribe SOLO lo que
    cambió: el front manda el formulario completo en cada envío, y reescribir
    todo pisaría `respondido_por`/`respondido_en` de respuestas que nadie tocó
    (la trazabilidad de quién respondió qué)."""
    diagnostico_id = await diagnostico_vigente_id(conn, empresa_id, ciclo_id)
    if diagnostico_id is None:
        diagnostico_id = await conn.fetchval(
            """
            INSERT INTO nexus360.diagnostico (empresa_id, ciclo_id, formato_id)
            VALUES ($1, $2, $3) RETURNING diagnostico_id
            """,
            empresa_id, ciclo_id, FORMATO_RSE,
        )

    preguntas = {
        f["codigo"]: f["pregunta_id"]
        for f in await conn.fetch(
            """
            SELECT p.codigo, p.pregunta_id
              FROM nexus360.pregunta p
              JOIN nexus360.seccion s ON s.seccion_id = p.seccion_id
              JOIN nexus360.dimension d ON d.dimension_id = s.dimension_id
             WHERE d.formato_id = $1 AND p.archivado_en IS NULL
            """,
            FORMATO_RSE,
        )
    }

    for codigo, r in payload.respuestas.items():
        pregunta_id = preguntas.get(codigo)
        if pregunta_id is None:
            continue  # código desconocido: se ignora sin romper el resto
        valor, es_na, es_diferente = columnas_de(r)
        texto = r.texto.strip() or None
        otro = r.otro.strip() or None
        if r.vacia:
            # No se crea una fila vacía; si existía, se vacía.
            await conn.execute(
                """
                UPDATE nexus360.respuesta
                   SET valor = NULL, es_na = FALSE, es_diferente = FALSE, texto = NULL,
                       ejemplos = '{}', otro_texto = NULL, valor_clasificado = NULL,
                       clasificado_por = NULL, clasificado_en = NULL,
                       respondido_en = now(), respondido_por = nexus360.current_usuario_id()
                 WHERE diagnostico_id = $1 AND pregunta_id = $2
                   AND (valor IS NOT NULL OR es_na OR es_diferente OR texto IS NOT NULL
                        OR cardinality(ejemplos) > 0 OR otro_texto IS NOT NULL)
                """,
                diagnostico_id, pregunta_id,
            )
            continue
        await conn.execute(
            """
            INSERT INTO nexus360.respuesta
                (diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, ejemplos,
                 otro_texto, respondido_por)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, nexus360.current_usuario_id())
            ON CONFLICT ON CONSTRAINT uq_respuesta DO UPDATE SET
                valor = EXCLUDED.valor,
                es_na = EXCLUDED.es_na,
                es_diferente = EXCLUDED.es_diferente,
                texto = EXCLUDED.texto,
                ejemplos = EXCLUDED.ejemplos,
                otro_texto = EXCLUDED.otro_texto,
                -- La clasificación de NEXUS solo vale mientras siga siendo
                -- «Hacemos algo diferente».
                valor_clasificado = CASE WHEN EXCLUDED.es_diferente THEN respuesta.valor_clasificado END,
                clasificado_por   = CASE WHEN EXCLUDED.es_diferente THEN respuesta.clasificado_por END,
                clasificado_en    = CASE WHEN EXCLUDED.es_diferente THEN respuesta.clasificado_en END,
                respondido_en = now(),
                respondido_por = EXCLUDED.respondido_por
            WHERE (respuesta.valor, respuesta.es_na, respuesta.es_diferente, respuesta.texto,
                   respuesta.ejemplos, respuesta.otro_texto)
                  IS DISTINCT FROM
                  (EXCLUDED.valor, EXCLUDED.es_na, EXCLUDED.es_diferente, EXCLUDED.texto,
                   EXCLUDED.ejemplos, EXCLUDED.otro_texto)
            """,
            diagnostico_id, pregunta_id, valor, es_na, es_diferente, texto, r.ejemplos, otro,
        )

    dimensiones = {
        f["numero"]: f["dimension_id"]
        for f in await conn.fetch(
            "SELECT numero, dimension_id FROM nexus360.dimension WHERE formato_id = $1 AND archivado_en IS NULL",
            FORMATO_RSE,
        )
    }
    for numero, texto in payload.fortalecer.items():
        dimension_id = dimensiones.get(numero)
        if dimension_id is None:
            continue
        texto = texto.strip()
        if not texto:
            await conn.execute(
                "DELETE FROM nexus360.respuesta_materia WHERE diagnostico_id = $1 AND dimension_id = $2",
                diagnostico_id, dimension_id,
            )
            continue
        await conn.execute(
            """
            INSERT INTO nexus360.respuesta_materia (diagnostico_id, dimension_id, fortalecer, respondido_por)
            VALUES ($1, $2, $3, nexus360.current_usuario_id())
            ON CONFLICT (diagnostico_id, dimension_id) DO UPDATE SET
                fortalecer = EXCLUDED.fortalecer, respondido_en = now(),
                respondido_por = EXCLUDED.respondido_por
            WHERE respuesta_materia.fortalecer IS DISTINCT FROM EXCLUDED.fortalecer
            """,
            diagnostico_id, dimension_id, texto,
        )

    comentario = (payload.comentario_final or "").strip() or None
    priorizacion = payload.priorizacion.model_dump() if payload.priorizacion else None
    await conn.execute(
        """
        UPDATE nexus360.diagnostico
           SET comentario_final = $2,
               priorizacion = COALESCE($3::jsonb, priorizacion),
               actualizado_en = now(),
               estado = CASE WHEN $4 THEN 'completado' ELSE estado END,
               completado_en = CASE WHEN $4 AND estado <> 'completado' THEN now() ELSE completado_en END
         WHERE diagnostico_id = $1
        """,
        diagnostico_id, comentario, json.dumps(priorizacion) if priorizacion is not None else None,
        payload.completo,
    )
    return diagnostico_id
