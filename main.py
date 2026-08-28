from fastapi import FastAPI

# 1. Crea la instancia de la aplicación
app = FastAPI()


# 2. Define tu primera ruta (endpoint)
@app.get("/")
def leer_raiz():
    return {"mensaje": "¡Hola, mi servidor FastAPI está corriendo!"}


# 3. Una ruta adicional para probar parámetros
@app.get("/saludo/{nombre}")
def saludar(nombre: str):
    return {"mensaje": f"¡Hola, {nombre}!"}
