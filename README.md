# Portal Horarios Backend

Backend en FastAPI + MongoDB para el portal de horarios.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Ejecutar

```bash
uvicorn src.main:app --reload
```

La API queda disponible en `http://localhost:8000`, con documentación interactiva en `http://localhost:8000/docs`.

## Estructura

```
src/
├── main.py            # instancia de FastAPI
├── core/
│   ├── config.py       # configuración (variables de entorno)
│   └── database.py     # conexión a MongoDB (Motor)
├── api/
│   ├── router.py        # router principal
│   └── routes/          # endpoints
├── models/              # documentos/entidades de MongoDB
└── schemas/              # esquemas Pydantic
```
