# Portal Horarios Backend

Backend en FastAPI + MongoDB para el portal de horarios. Cubre autenticación
de usuarios (login, logout, bloqueo por intentos fallidos, expiración de
sesión por inactividad) y administración del directorio de empleados
(alta individual, consulta, edición) según `specs/001-login` y
`specs/002-roles-permisos-empleados`.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Variables de entorno (`.env`, ver `.env.example`):

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `MONGO_URI` | Cadena de conexión a MongoDB | `mongodb://localhost:27017` |
| `MONGO_DB_NAME` | Nombre de la base de datos | `portal_horarios` |

`src/core/config.py` también define (no configurables por `.env` todavía):
`max_failed_attempts` (5), `lockout_minutes` (15) y `session_inactivity_minutes` (30).

## Ejecutar

```bash
uvicorn src.main:app --reload
```

La API queda disponible en `http://localhost:8000`, con documentación interactiva en `http://localhost:8000/docs`.

### CLI de administración

Además de la API HTTP, `src/cli.py` ofrece una interfaz de línea de comandos
para tareas de administración (crea su propia conexión a MongoDB y devuelve
resultados en JSON por stdout/stderr):

```bash
python -m src.cli create-admin --name "Nombre" --email admin@hispacontact.com
python -m src.cli unlock-user --email usuario@hispacontact.com
python -m src.cli deactivate-user --email usuario@hispacontact.com
python -m src.cli create-employee --name "Nombre" --position lider --area "Área"
python -m src.cli list-employees
python -m src.cli update-employee --id <id> [--name ...] [--position ...] [--area ...]
```

## Tests

```bash
python -m pytest -q
```

> Usar `python -m pytest`, no `pytest` a secas: el proyecto no tiene un
> `pyproject.toml`/`setup.cfg` que fije el rootdir, así que `pytest` directo
> falla al resolver `import src...` en `test/conftest.py`.

## Estructura

```
src/
├── main.py                  # instancia de FastAPI, registra el router principal
├── cli.py                   # CLI de administración (create-admin, employees, etc.)
├── core/
│   ├── config.py             # configuración (variables de entorno)
│   ├── database.py           # conexión a MongoDB (Motor)
│   └── security.py           # hashing de contraseñas y tokens de sesión
├── api/
│   ├── router.py              # router principal, agrega todas las rutas
│   ├── deps.py                 # dependencias FastAPI (sesión actual, requiere admin)
│   └── routes/
│       ├── health.py            # GET /health
│       ├── auth.py              # POST /auth/login, POST /auth/logout
│       ├── users.py             # POST /users (alta de cuentas, requiere admin)
│       └── employees.py         # CRUD de /employees (requiere admin)
├── services/                # lógica de negocio (sin ella en las rutas)
│   ├── auth_service.py       # autenticación, bloqueo por intentos, alta de cuentas
│   ├── session_service.py    # ciclo de vida de la sesión (crear/validar/cerrar)
│   └── employee_service.py   # alta/consulta/edición de empleados
├── models/                  # acceso a MongoDB por colección
│   ├── user.py
│   ├── session.py
│   └── employee.py
└── schemas/                 # esquemas Pydantic de entrada/salida
    ├── auth.py
    ├── user.py
    └── employee.py
```

## Endpoints principales

| Método | Ruta | Protegido | Descripción |
|---|---|---|---|
| GET | `/health` | No | Verifica conexión a MongoDB |
| POST | `/auth/login` | No | Login con correo/contraseña; bloquea tras `max_failed_attempts` fallidos |
| POST | `/auth/logout` | Sesión válida | Invalida la sesión activa |
| POST | `/users` | Admin | Da de alta una cuenta (`junta_directiva` o `lider`) con contraseña temporal |
| POST | `/employees` | Admin | Crea un empleado (`recursos_humanos` o `lider`) |
| GET | `/employees` | Admin | Lista todos los empleados |
| GET | `/employees/{id}` | Admin | Detalle de un empleado |
| PATCH | `/employees/{id}` | Admin | Edita nombre, cargo o área de un empleado |

Nota: los empleados gestionados por `/employees` son registros administrativos
sin cuenta ni sesión propia (spec 002) — distintos de las cuentas de acceso
al portal gestionadas por `/users` y `/auth` (spec 001).
