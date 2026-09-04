from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, status

from ..db import fijar_usuario_actual, get_conn
from ..errors import ApiError
from ..schemas_empresa import EmpresaIn, EmpresaOut, RespuestasIn, RespuestasOut
from ..security import requerir_token

router = APIRouter(prefix="/empresa", tags=["empresa"])


async def _contexto(token: str, conn: asyncpg.Connection) -> str:
    """Valida el token y fija app.current_usuario_id. Debe llamarse DENTRO
    de una transacción abierta (igual que en auth.py) para que el SET
    LOCAL siga vigente en las consultas de después."""
    usuario_id = await conn.fetchval("SELECT nexus360.validar_sesion($1)", token)
    if usuario_id is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "CREDENCIALES_INVALIDAS", "La sesión no es válida o expiró.")
    await fijar_usuario_actual(conn, usuario_id)
    return usuario_id


async def _mi_empresa_ciclo(conn: asyncpg.Connection, anio: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT e.empresa_id, e.razon_social, e.nit, e.dv, e.sector_id, e.municipio,
               e.departamento, e.extranjera,
               c.ciclo_id, c.anio, c.tamano, c.empleados, c.areas_de_vida,
               c.ciclo_previo, c.comunidades_etnicas, c.consumidor_final
          FROM nexus360.empresa e
          JOIN nexus360.usuario_empresa ue ON ue.empresa_id = e.empresa_id
          LEFT JOIN nexus360.ciclo_tamizaje c ON c.empresa_id = e.empresa_id AND c.anio = $1
         WHERE ue.usuario_id = nexus360.current_usuario_id()
           AND e.archivado_en IS NULL
         LIMIT 1
        """,
        anio,
    )


@router.get("/mio", response_model=EmpresaOut)
async def obtener_mi_empresa(
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    anio_actual = datetime.now(timezone.utc).year
    async with conn.transaction():
        await _contexto(token, conn)
        fila = await _mi_empresa_ciclo(conn, anio_actual)

    if fila is None or fila["ciclo_id"] is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "DESCONOCIDO", "Todavía no hay datos guardados para esta cuenta.")
    return EmpresaOut(**dict(fila))


@router.put("/mio", response_model=EmpresaOut, status_code=status.HTTP_200_OK)
async def guardar_mi_empresa(
    payload: EmpresaIn,
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Crea o actualiza la empresa + el ciclo de tamizaje del año actual
    para la cuenta en sesión. Perfil y tamizaje viajan juntos porque así
    los maneja el front (un solo paso antes de Diagnóstico)."""
    anio_actual = datetime.now(timezone.utc).year

    async with conn.transaction():
        await _contexto(token, conn)

        existente = await conn.fetchrow(
            """
            SELECT e.empresa_id FROM nexus360.empresa e
              JOIN nexus360.usuario_empresa ue ON ue.empresa_id = e.empresa_id
             WHERE ue.usuario_id = nexus360.current_usuario_id()
               AND e.archivado_en IS NULL
             LIMIT 1
            """
        )

        try:
            if existente:
                empresa_id = existente["empresa_id"]
                await conn.execute(
                    """
                    UPDATE nexus360.empresa
                       SET razon_social = $2, nit = $3, dv = $4, sector_id = $5,
                           municipio = $6, departamento = $7, extranjera = $8
                     WHERE empresa_id = $1
                    """,
                    empresa_id, payload.razon_social, payload.nit, payload.dv, payload.sector_id,
                    payload.municipio, payload.departamento, payload.extranjera,
                )
            else:
                empresa_id = await conn.fetchval(
                    """
                    INSERT INTO nexus360.empresa (razon_social, nit, dv, sector_id, municipio, departamento, extranjera)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING empresa_id
                    """,
                    payload.razon_social, payload.nit, payload.dv, payload.sector_id,
                    payload.municipio, payload.departamento, payload.extranjera,
                )
        except asyncpg.UniqueViolationError as exc:
            raise ApiError(
                status.HTTP_409_CONFLICT, "EMAIL_YA_REGISTRADO",
                "Ese NIT ya está registrado por otra cuenta. Contacta al administrador para vincular el acceso.",
            ) from exc
        except asyncpg.CheckViolationError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION",
                "El dígito de verificación no corresponde al NIT.",
            ) from exc

        await conn.execute(
            """
            INSERT INTO nexus360.ciclo_tamizaje
                (empresa_id, anio, tamano, empleados, areas_de_vida, ciclo_previo, comunidades_etnicas, consumidor_final)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT ON CONSTRAINT uq_ciclo_empresa_anio DO UPDATE SET
                tamano = EXCLUDED.tamano,
                empleados = EXCLUDED.empleados,
                areas_de_vida = EXCLUDED.areas_de_vida,
                ciclo_previo = EXCLUDED.ciclo_previo,
                comunidades_etnicas = EXCLUDED.comunidades_etnicas,
                consumidor_final = EXCLUDED.consumidor_final
            """,
            empresa_id, anio_actual, payload.tamano, payload.empleados, payload.areas_de_vida,
            payload.ciclo_previo, payload.comunidades_etnicas, payload.consumidor_final,
        )

        fila = await _mi_empresa_ciclo(conn, anio_actual)

    return EmpresaOut(**dict(fila))


@router.put("/mio/diagnosticos/{formato_id}/respuestas", response_model=RespuestasOut)
async def guardar_respuestas(
    formato_id: str,
    payload: RespuestasIn,
    token: str = Depends(requerir_token),
    conn: asyncpg.Connection = Depends(get_conn),
):
    anio_actual = datetime.now(timezone.utc).year

    async with conn.transaction():
        await _contexto(token, conn)

        fila_empresa = await conn.fetchrow(
            """
            SELECT e.empresa_id FROM nexus360.empresa e
              JOIN nexus360.usuario_empresa ue ON ue.empresa_id = e.empresa_id
             WHERE ue.usuario_id = nexus360.current_usuario_id()
               AND e.archivado_en IS NULL
             LIMIT 1
            """
        )
        if fila_empresa is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION",
                "Primero hay que guardar el perfil y el tamizaje de la empresa.",
            )
        empresa_id = fila_empresa["empresa_id"]

        ciclo_id = await conn.fetchval(
            "SELECT ciclo_id FROM nexus360.ciclo_tamizaje WHERE empresa_id = $1 AND anio = $2",
            empresa_id, anio_actual,
        )
        if ciclo_id is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDACION",
                "Primero hay que guardar el tamizaje de este año.",
            )

        diagnostico_id = await conn.fetchval(
            """
            SELECT diagnostico_id FROM nexus360.diagnostico
             WHERE empresa_id = $1 AND ciclo_id = $2 AND formato_id = $3 AND estado <> 'archivado'
             ORDER BY creado_en DESC LIMIT 1
            """,
            empresa_id, ciclo_id, formato_id,
        )
        if diagnostico_id is None:
            diagnostico_id = await conn.fetchval(
                """
                INSERT INTO nexus360.diagnostico (empresa_id, ciclo_id, formato_id)
                VALUES ($1, $2, $3) RETURNING diagnostico_id
                """,
                empresa_id, ciclo_id, formato_id,
            )

        for codigo, valor in payload.respuestas.items():
            pregunta_id = await conn.fetchval(
                """
                SELECT p.pregunta_id
                  FROM nexus360.pregunta p
                  JOIN nexus360.seccion s ON s.seccion_id = p.seccion_id
                  JOIN nexus360.dimension d ON d.dimension_id = s.dimension_id
                 WHERE d.formato_id = $1 AND p.codigo = $2 AND p.archivado_en IS NULL
                """,
                formato_id, codigo,
            )
            if pregunta_id is None:
                continue  # código desconocido para este formato: se ignora, no rompe el guardado del resto

            es_na = valor == "NA"
            valor_num = None if es_na else int(valor)

            await conn.execute(
                """
                INSERT INTO nexus360.respuesta (diagnostico_id, pregunta_id, valor, es_na, respondido_por)
                VALUES ($1, $2, $3, $4, nexus360.current_usuario_id())
                ON CONFLICT ON CONSTRAINT uq_respuesta DO UPDATE SET
                    valor = EXCLUDED.valor, es_na = EXCLUDED.es_na,
                    respondido_en = now(), respondido_por = EXCLUDED.respondido_por
                """,
                diagnostico_id, pregunta_id, valor_num, es_na,
            )

        if payload.completo:
            await conn.execute(
                """
                UPDATE nexus360.diagnostico
                   SET estado = 'completado', completado_en = now()
                 WHERE diagnostico_id = $1 AND estado <> 'completado'
                """,
                diagnostico_id,
            )

        estado = await conn.fetchval("SELECT estado FROM nexus360.diagnostico WHERE diagnostico_id = $1", diagnostico_id)

    return RespuestasOut(formato_id=formato_id, estado=estado, respuestas=payload.respuestas)
