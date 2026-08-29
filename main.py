"""Punto de entrada de compatibilidad: `uvicorn main:app --reload`.

La app real vive en app/main.py (estructura modular: config, db, routers).
"""
from app.main import app  # noqa: F401
