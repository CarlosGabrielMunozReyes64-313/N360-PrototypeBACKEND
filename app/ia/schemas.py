"""Contratos del análisis inteligente (Gemini).

Dos capas, separadas a propósito:

* CAPA 1 · Diagnóstico — ``ResultadosIn``: lo que el motor existente del
  frontend (``src/engine/scoring.ts``) ya calculó: niveles por materia,
  categoría de cada práctica, oportunidades ordenadas y alertas. El backend
  lo valida con tipos cerrados y NO lo recalcula.
* CAPA 2 · Inteligencia artificial — ``AnalisisIA``: la interpretación que
  devuelve Gemini. No tiene ningún campo numérico: Gemini no puede cambiar ni
  inventar puntajes porque la estructura no le deja dónde escribirlos.

Refleja ``src/auth/analisisIaApi.ts`` del frontend.
"""
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

# ------------------------------------------------------------ vocabulario

NumeroMateria = Annotated[str, StringConstraints(pattern=r"^0[1-7]$")]
CodigoPregunta = Annotated[str, StringConstraints(pattern=r"^0[1-7][a-c]$")]

# Categorías del mapa de prácticas (engine/scoring.ts::categoriaDe).
CategoriaPractica = Literal["fortaleza", "desarrollo", "oportunidad", "diferente", "na", "pendiente"]
CategoriaMateria = Literal["fortaleza", "desarrollo", "oportunidad", "na", "pendiente"]
# Verbo de la oportunidad según la etapa de partida (data/escala.ts::VERBO_ETAPA).
Verbo = Literal["Empezar", "Formalizar", "Fortalecer", "Ampliar"]
IdAlerta = Literal["ley2173", "sst", "datos", "territorio"]


def _texto(maximo: int, minimo: int = 0):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=minimo, max_length=maximo)]


# ======================================================================
# CAPA 1 · Resultados del motor de diagnóstico (entrada)
# ======================================================================

class _Entrada(BaseModel):
    # El front es nuestro: cualquier campo desconocido es un error de
    # contrato, no algo que haya que tolerar en silencio.
    model_config = ConfigDict(extra="forbid")


class PracticaIn(_Entrada):
    codigo: CodigoPregunta
    pregunta: _texto(400, 1)
    # Etapa en palabras («Lo aplicamos y vemos resultados»): es el nivel que
    # eligió la empresa, tal como lo ve en pantalla.
    etapa: _texto(120, 1)
    categoria: CategoriaPractica
    # Lo que la empresa hace hoy, con sus palabras: la respuesta abierta, los
    # ejemplos marcados y «Hacemos algo diferente» (hasta ~1.500 caracteres).
    hace_hoy: _texto(1600)


class MateriaIn(_Entrada):
    numero: NumeroMateria
    nombre: _texto(120, 1)
    aplica: bool
    categoria: CategoriaMateria
    # «¿Qué le gustaría fortalecer?»: la base admite hasta 2.000 caracteres.
    fortalecer: _texto(2000)
    practicas: list[PracticaIn] = Field(max_length=3)


class PrioridadIn(_Entrada):
    """Una oportunidad de la matriz de priorización, en el orden del motor."""
    codigo: CodigoPregunta
    materia_numero: NumeroMateria
    materia: _texto(120, 1)
    verbo: Verbo
    oportunidad: _texto(400, 1)
    hace_hoy: _texto(600)
    alternativas: list[_texto(300, 1)] = Field(max_length=5)
    alerta_legal: Literal["sst", "datos"] | None = None
    fortalecer: _texto(2000)


class AlertaIn(_Entrada):
    id: IdAlerta
    titulo: _texto(200, 1)
    detalle: _texto(900, 1)


class ResultadosIn(_Entrada):
    """Resultados ya calculados por el motor (CAPA 1). Sin datos de
    identificación: ni razón social, ni NIT, ni datos de la cuenta."""
    lectura_concluyente: bool
    practicas_registradas: int = Field(ge=0, le=21)
    fortalezas: int = Field(ge=0, le=21)
    en_desarrollo: int = Field(ge=0, le=21)
    oportunidades: int = Field(ge=0, le=21)
    practicas_propias_por_revisar: int = Field(ge=0, le=21)
    materias: list[MateriaIn] = Field(min_length=1, max_length=7)
    prioridades: list[PrioridadIn] = Field(max_length=5)
    alertas: list[AlertaIn] = Field(max_length=4)
    comentario_final: _texto(2000) = ""

    @model_validator(mode="after")
    def _coherencia(self) -> "ResultadosIn":
        numeros = [m.numero for m in self.materias]
        if len(set(numeros)) != len(numeros):
            raise ValueError("Hay materias repetidas en los resultados.")
        aplican = {m.numero for m in self.materias if m.aplica}
        if not aplican:
            raise ValueError("Ninguna materia aplica: no hay resultados que analizar.")
        if any(p.materia_numero not in aplican for p in self.prioridades):
            raise ValueError("Una prioridad pertenece a una materia que no aplica.")
        return self

    @property
    def materias_aplicables(self) -> set[str]:
        return {m.numero for m in self.materias if m.aplica}


class AnalisisIAIn(_Entrada):
    resultados: ResultadosIn


# ======================================================================
# CAPA 2 · Respuesta de Gemini (salida estructurada)
# ======================================================================

Prioridad = Literal["alta", "media", "baja"]
# Materia a la que apunta una recomendación, o «general» si es transversal.
MateriaRef = Literal["01", "02", "03", "04", "05", "06", "07", "general"]

# Topes amplios: solo evitan respuestas desbordadas (en pantalla y en el
# PDF); la extensión deseada se le pide a Gemini en el prompt.
Item = _texto(700, 3)

MAX_LISTA = 6
MAX_ACCIONES = 5


def _recortar_lista(v: Any, maximo: int) -> Any:
    """Si Gemini devuelve más elementos de la cuenta se conservan los
    primeros: es mejor que descartar un análisis completo por eso."""
    return v[:maximo] if isinstance(v, list) else v


class RecomendacionIA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    titulo: _texto(200, 3) = Field(description="Título corto y accionable de la recomendación.")
    descripcion: _texto(1500, 10) = Field(description="Qué hacer, en términos concretos y realizables para la empresa.")
    prioridad: Prioridad = Field(description="alta, media o baja, según los resultados.")
    justificacion: _texto(1200, 10) = Field(
        description="Qué resultado del diagnóstico la sustenta (materia, práctica o prioridad).",
    )
    materia: MateriaRef = Field(description="Número de la materia ('01'…'07') o 'general' si es transversal.")


class AccionIA(BaseModel):
    model_config = ConfigDict(extra="ignore")
    accion: _texto(500, 5) = Field(description="Acción concreta, empezando con un verbo.")
    objetivo: _texto(700, 5) = Field(description="Para qué se hace: el cambio que busca.")
    horizonte: _texto(120, 2) = Field(description="Plazo aproximado, por ejemplo «4 a 8 semanas».")
    prioridad: Prioridad = Field(description="alta, media o baja.")


class AnalisisIA(BaseModel):
    """Interpretación del diagnóstico. Solo texto y listas: ningún puntaje.

    Sin «resumen» ejecutivo desde el prompt v5: el informe ya no lo muestra.
    Un análisis guardado antes que todavía lo traiga sigue siendo válido
    (extra="ignore"), aunque se regenera por el cambio de VERSION_PROMPT."""
    model_config = ConfigDict(extra="ignore")

    fortalezas: list[Item] = Field(description="Fortalezas que muestran los resultados.")
    areas_oportunidad: list[Item] = Field(description="Áreas de oportunidad que muestran los resultados.")
    prioridades: list[Item] = Field(description="Prioridades, en orden, fundamentadas en la matriz del sistema.")
    recomendaciones: list[RecomendacionIA] = Field(min_length=1, description="Recomendaciones concretas.")
    acciones_corto_plazo: list[AccionIA] = Field(min_length=1, description="Acciones para los próximos 1 a 3 meses.")
    acciones_mediano_plazo: list[AccionIA] = Field(min_length=1, description="Acciones para los próximos 3 a 12 meses.")
    conclusion: _texto(2000, 20) = Field(description="Conclusión ejecutiva.")

    @field_validator("fortalezas", "areas_oportunidad", "prioridades", "recomendaciones", mode="before")
    @classmethod
    def _tope_listas(cls, v: Any) -> Any:
        return _recortar_lista(v, MAX_LISTA)

    @field_validator("acciones_corto_plazo", "acciones_mediano_plazo", mode="before")
    @classmethod
    def _tope_acciones(cls, v: Any) -> Any:
        return _recortar_lista(v, MAX_ACCIONES)


# ------------------------------------------------ esquema para Gemini

# Palabras clave de JSON Schema que la salida estructurada de Gemini
# entiende. Lo demás (title, maxLength, pattern, additionalProperties…) se
# quita: según la versión del modelo o del SDK, o se ignora o provoca un
# 400. Los topes se hacen cumplir aquí, al validar con Pydantic.
_CLAVES_ESQUEMA = {"type", "properties", "required", "items", "enum", "description", "minItems"}


def esquema_gemini() -> dict:
    """JSON Schema autocontenido (sin $ref) de AnalisisIA para
    ``response_json_schema``."""
    crudo = AnalisisIA.model_json_schema()
    definiciones = crudo.get("$defs", {})

    def limpiar(nodo: Any) -> Any:
        if isinstance(nodo, dict):
            if "$ref" in nodo:
                return limpiar(definiciones[nodo["$ref"].rsplit("/", 1)[-1]])
            salida = {}
            for clave, valor in nodo.items():
                if clave == "properties":
                    salida[clave] = {k: limpiar(v) for k, v in valor.items()}
                elif clave in _CLAVES_ESQUEMA:
                    salida[clave] = limpiar(valor)
            # Pydantic describe los Literal como enum sin tipo explícito.
            if "enum" in salida and "type" not in salida:
                salida["type"] = "string"
            return salida
        if isinstance(nodo, list):
            return [limpiar(x) for x in nodo]
        return nodo

    return limpiar(crudo)


# ======================================================================
# Respuesta del endpoint
# ======================================================================

class AnalisisIAOut(BaseModel):
    diagnostico_id: UUID
    analisis: AnalisisIA
    generado_en: datetime
    modelo: str
    version_prompt: str
    # true si se devolvió un análisis ya guardado (sin llamar a Gemini).
    reutilizado: bool
