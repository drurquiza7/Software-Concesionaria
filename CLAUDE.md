# CLAUDE.md

Reglas de gobernanza para el desarrollo asistido por IA de este repositorio.

Este proyecto es un SaaS multi-tenant de gestión de concesionarias automotrices (DMS). La especificación funcional está en `SPECIFICATION_SRS.md` y es la fuente de verdad. Si una instrucción contradice el SRS, frená y preguntá antes de escribir código.

## 1. Reglas que nunca se rompen

1. **Toda consulta a datos de una concesionaria pasa por un manager filtrado por tenant.** Sin excepciones silenciosas.
2. **Ninguna vista, endpoint ni señal llama a la API de Mercado Libre.** Todo va a Celery. Única excepción: el intercambio del `code` en el callback de OAuth.
3. **Tokens, API Keys y datos de terceros se cifran o se hashean.** Nunca en claro en la base, en logs ni en respuestas.
4. **`public_api` nunca importa `inventory.internal`.** Los schemas públicos se escriben campo por campo.
5. **Cambio sin tests no está terminado.** Los tests de aislamiento entre tenants son obligatorios, no opcionales.
6. **No inventes datos de APIs externas.** Si no sabés un endpoint, un atributo o un límite de Mercado Libre, consultá la documentación oficial o marcalo como `[VALIDAR]` y avisá.

## 2. Stack aprobado

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12+ |
| Framework | Django (LTS vigente) |
| API pública | Django Ninja |
| Frontend | Templates Django + HTMX + Alpine.js, CSS nativo |
| Base de datos | PostgreSQL (driver `psycopg` 3) |
| Caché, broker y locks | Redis |
| Tareas | Celery + Celery Beat |
| Almacenamiento | Cloudflare R2 vía `django-storages` (API S3) |
| Imágenes | pyvips |
| Cliente HTTP | httpx, siempre con timeout explícito |
| Cifrado | `cryptography` (Fernet / MultiFernet) |
| Hash de contraseñas | Argon2 vía `argon2-cffi` |
| Servidor WSGI | gunicorn |
| Proxy | Caddy |
| Despliegue | Docker Compose: `caddy`, `web`, `worker`, `beat`, `postgres`, `redis` |
| Tests | pytest, pytest-django, factory_boy, respx |
| Calidad | ruff (lint y formato) |

**No agregues dependencias, servicios ni contenedores sin aprobación explícita.** Quedan fuera del stack: Node en producción, React o cualquier SPA, Tailwind, DRF, GraphQL, MinIO, microservicios, un segundo motor de base de datos.

## 3. Estructura de carpetas

Monolito modular. Cada app es dueña de sus modelos y expone su lógica por `services.py` y `selectors.py`.

```
.
├── CLAUDE.md
├── SPECIFICATION_SRS.md
├── docker-compose.yml
├── Caddyfile
├── pyproject.toml
├── config/
│   ├── settings/          # base.py, dev.py, prod.py, test.py
│   ├── urls.py
│   └── celery.py
├── apps/
│   ├── core/              # TenantModel, managers, contexto de tenant, cifrado, utilidades
│   ├── tenants/           # Tenant, Sucursal
│   ├── accounts/          # Usuario, Membresia, Rol, Permiso, autorización
│   ├── inventory/         # Vehiculo (datos públicos)
│   │   └── internal/      # VehiculoInterno, GastoAcondicionamiento (datos privados)
│   ├── media/             # VehiculoImagen, URLs prefirmadas, procesamiento
│   ├── meli/              # MeliCredential, MeliPublicacion, cliente, sync, webhooks
│   └── public_api/        # API Ninja, ApiKey, schemas públicos
├── templates/
├── static/
└── tests/
    └── architecture/      # tests de imports y de reglas globales
```

Archivos esperados dentro de cada app:

| Archivo | Contenido |
|---|---|
| `models.py` | Modelos y constraints. Sin lógica de negocio |
| `services.py` | Operaciones que escriben. Transaccionales |
| `selectors.py` | Consultas de lectura |
| `permissions.py` | Códigos de permiso que declara la app |
| `views.py` / `api.py` | Capa delgada: valida, autoriza, llama a un servicio o selector |
| `tasks.py` | Tareas Celery. Capa delgada sobre `services.py` |
| `tests/` | Tests de la app |

Dependencias permitidas entre apps (una app solo importa de las que están a su derecha):

```
public_api ─► inventory, media, tenants, core
meli       ─► inventory, media, tenants, core
media      ─► inventory, tenants, core
inventory  ─► tenants, accounts, core
accounts   ─► tenants, core
tenants    ─► core
```

- Las vistas no escriben con el ORM directo: llaman a un servicio.
- `inventory.internal` solo puede ser importado por `inventory` y por las vistas del panel que verifican `stock.*`.
- Prohibidos los imports circulares y los imports dentro de funciones para esquivarlos.

## 4. Seguridad multi-tenant

### 4.1 Modelos

- Todo modelo con datos de una concesionaria hereda de `core.TenantModel`. Eso incluye las tablas intermedias de M2M: usá siempre `through` explícito con `tenant`.
- Son globales y no heredan de `TenantModel` únicamente: `Tenant`, `Usuario`, `Permiso`, `MeliCategoriaAtributo`.
- Toda FK entre dos modelos de tenant valida en `clean()` que ambos lados tengan el mismo `tenant_id`.
- Las restricciones de unicidad incluyen `tenant` salvo que el SRS diga que son globales.

### 4.2 Managers

- `objects` es el `TenantManager`: filtra por el tenant activo y **lanza `TenantNoDefinido`** si no hay ninguno. Nunca devuelve datos sin filtrar.
- `all_tenants` es el manager sin filtro. Solo se permite en: tareas periódicas de sistema, migraciones de datos, comandos de gestión y el admin interno. Cada uso lleva un comentario `# all_tenants: <motivo>`.
- Única excepción en código de aplicación: `accounts.selectors.membresias_de_usuario()`, que lista las membresías activas del usuario autenticado para el login y el selector de concesionaria, antes de que exista un tenant activo. No se usa en ningún otro flujo.
- Prohibido en código de aplicación: `_base_manager`, `_default_manager`, SQL crudo (`raw()`, `cursor.execute`) y `.extra()`. Si hace falta SQL crudo, pedí aprobación e incluí el filtro por `tenant_id` como parámetro.
- Nunca filtres por un `tenant_id` que venga del cliente (URL, formulario, body, header). El tenant sale de la sesión o de la API Key.

### 4.3 Contexto de tenant

El tenant activo se define en exactamente tres lugares:

| Punto de entrada | Mecanismo |
|---|---|
| Panel | Middleware: lee el tenant de la sesión y valida la membresía activa |
| API pública | Autenticador de API Key |
| Celery | `with tenant_context(tenant_id):` al inicio de la tarea |

- Toda tarea Celery que toca datos de tenant recibe `tenant_id` como argumento explícito.
- Única excepción: el comando de gestión `crear_concesionaria`, que da de alta el tenant con su primera sucursal, sus roles predeterminados y su propietario.
- Cualquier otro código que necesite fijar el tenant está mal diseñado: revisalo.

### 4.4 Autorización

- Cada vista y endpoint interno declara su permiso con el decorador de `accounts`. Una vista sin permiso declarado ni marca explícita de pública hace fallar la suite.
- Las marcas son tres: `@requiere_permiso("modulo.accion")`, `@vista_publica` (sin sesión) y `@requiere_sesion` (usuario autenticado que todavía no eligió concesionaria: solo logout y selector).
- Un objeto de otro tenant o fuera del alcance de sucursal responde `404`, nunca `403`.
- Los datos que requieren un permiso no se envían al navegador si el usuario no lo tiene. Ocultar con CSS o con `hidden` no es control de acceso.
- Respetá las reglas de jerarquía y anti-escalada de roles del SRS (RN-09 y RN-10) en el servicio, no en la vista.

### 4.5 Tests de aislamiento obligatorios

Por cada vista, endpoint o servicio nuevo que lea o escriba datos de tenant:

1. **Test de lectura cruzada**: con dos tenants cargados, el usuario del tenant A pide un objeto del tenant B y recibe `404`.
2. **Test de listado**: el listado del tenant A no contiene ningún objeto del tenant B.
3. **Test de escritura cruzada**: el usuario del tenant A intenta modificar o borrar un objeto del tenant B y el objeto queda intacto.
4. **Test de FK cruzada**: crear un objeto en el tenant A referenciando una sucursal, rol o vehículo del tenant B falla.

Tests globales que deben existir y mantenerse verdes:

- Todo modelo concreto de las apps hereda de `TenantModel` o está en la lista explícita de modelos globales.
- Consultar un `TenantModel` sin tenant activo lanza `TenantNoDefinido`.
- `public_api` no importa `inventory.internal` (inspección de imports).
- Ninguna vista ni `api.py` importa el cliente HTTP de `meli`.
- El schema público de vehículos tiene exactamente el conjunto de campos aprobado, y los valores centinela de los campos privados no aparecen en ninguna respuesta pública (SRS 5.4).

Usá las fixtures compartidas `tenant_a`, `tenant_b`, `usuario_a`, `usuario_b` y las factories de `tests/`. No armes datos a mano en cada test.

## 5. Mercado Libre

### 5.1 Todo asíncrono

- Prohibido llamar a ML desde vistas, endpoints, formularios, señales, templates o comandos ejecutados dentro de un request.
- El flujo es siempre: la vista llama a un servicio → el servicio guarda el cambio local, marca `estado_sync = pendiente` y encola con `transaction.on_commit(...)` → la tarea ejecuta.
- Encolar fuera de `on_commit` está prohibido: la tarea puede correr antes de que exista el dato.
- El único código que habla HTTP con ML es `apps/meli/client.py`. Nadie más construye URLs de ML ni headers de autorización.

### 5.2 Tokens

- El access token se obtiene únicamente con `meli.services.obtener_access_token(tenant_id)`.
- Todo refresh se hace dentro de `transaction.atomic()` con `select_for_update()` sobre la fila de `MeliCredential`, y **revalida `expires_at` después de tomar el lock**.
- El refresh token es de un solo uso: guardá siempre el nuevo junto con el access token, en la misma transacción.
- Un `invalid_grant` no se reintenta: marca `requiere_reautorizacion` y notifica.

### 5.3 Reintentos

| Respuesta | Acción |
|---|---|
| Timeout, error de red, `5xx` | Reintento con backoff exponencial |
| `429` | Reintento respetando `Retry-After` si viene; si no, backoff |
| `401` | Forzar refresh una vez y reintentar. El segundo `401` marca `requiere_reautorizacion` |
| `409` | Reintento con backoff |
| Otros `4xx` | **Sin reintento.** Guardar `message` y `cause` en `ultimo_error` y marcar `error` |

- Configuración estándar de tareas contra ML: `autoretry_for` con las excepciones transitorias, `retry_backoff=30`, `retry_backoff_max=3600`, `retry_jitter=True`, `max_retries=5`, `acks_late=True`.
- Al agotar reintentos, la entidad queda en `error` con el detalle visible en el panel. Ninguna tarea falla en silencio.
- Timeouts de httpx: 5 s de conexión, 20 s de lectura, 60 s para subida de imágenes.

### 5.4 Idempotencia

- Las tareas reciben IDs, nunca instancias ni payloads.
- Antes de un `POST /items`, verificá bajo lock que `item_id` siga vacío. Guardá el `item_id` apenas ML responde.
- No subas una imagen que ya tiene `meli_picture_id`.
- No hagas `PUT` si el hash del payload no cambió.
- Los webhooks solo validan, encolan y responden `200`. El trabajo lo hace la tarea, que vuelve a consultar el recurso.

### 5.5 Datos de ML

- Los atributos obligatorios se leen de `MeliCategoriaAtributo`, nunca de una lista escrita a mano.
- Los valores de enumeraciones internas se traducen con la tabla de equivalencias de `meli/mapping.py`. No armes strings de ML dentro de servicios.

## 6. Datos sensibles

- Tokens de ML y campos `propietario_*`: campo cifrado de `core.fields`. Prohibido guardarlos en `CharField` o `TextField` comunes.
- API Keys y tokens de invitación: solo se guarda el SHA-256. La comparación usa `hmac.compare_digest`.
- Secretos por variables de entorno. Nada de secretos en el repositorio, en `settings`, en fixtures ni en tests. `.env` está en `.gitignore`; mantené actualizado `.env.example` sin valores reales.
- Los modelos con campos sensibles definen `__repr__` y `__str__` sin esos campos.
- Prohibido loguear: headers `Authorization`, tokens, API Keys, contraseñas, cuerpos completos de requests o responses de ML, datos de `propietario_*`.
- Los valores cifrados no se registran en `RegistroAuditoria.cambios`.

## 7. Reglas de código

### 7.1 Estilo

- Dominio en español (`Vehiculo`, `Sucursal`, `precio_toma`); infraestructura y nombres técnicos en inglés (`services`, `tasks`, `created_at`).
- Type hints en toda función pública.
- Comentarios solo donde el porqué no es obvio.
- Sin código muerto, sin `print`, sin `TODO` sin issue asociado.

### 7.2 Modelos y migraciones

- PK UUID. Dinero en `DecimalField(max_digits=14, decimal_places=2)` más moneda. Nunca `FloatField` para dinero.
- Las reglas de integridad van como `CheckConstraint` y `UniqueConstraint` en la base, además de la validación en Python.
- Una migración por cambio lógico. Nunca edites una migración ya aplicada en producción.
- Las migraciones deben ser compatibles con la versión anterior del código: primero agregar la columna nullable, después poblarla, después hacerla obligatoria.
- Operaciones de varias escrituras dentro de `transaction.atomic()`.

### 7.3 Consultas

- Sin N+1: usá `select_related` y `prefetch_related`. Los listados llevan test con `django_assert_num_queries`.
- Todo listado está paginado.
- En `public_api`, las consultas usan `.only()` con columnas explícitas.

### 7.4 Manejo de errores

- Los servicios lanzan excepciones de dominio definidas en el `exceptions.py` de cada app. Las vistas las traducen a una respuesta.
- Prohibido `except:` y `except Exception:` sin relanzar. Capturá excepciones específicas.
- Prohibido tragar errores con `pass`.
- Los mensajes al usuario son en español y dicen qué hacer. Los detalles técnicos van al log, no a la pantalla.
- Las respuestas `500` no exponen trazas, SQL ni nombres de campos.

### 7.5 Frontend

- HTML renderizado en servidor. HTMX para interacciones parciales, Alpine.js solo para estado local de UI.
- CSS nativo con variables. Sin frameworks de CSS ni pasos de build.
- Toda request de HTMX que modifica datos envía el token CSRF.
- Los parciales HTMX pasan por los mismos controles de permiso y tenant que las vistas completas.

### 7.6 Tareas Celery

- Idempotentes, con argumentos serializables en JSON.
- Con `soft_time_limit` y `time_limit` definidos.
- Colas separadas: `default`, `media` (imágenes) y `meli`.
- Las tareas periódicas se registran en el schedule de Beat en código, no desde el admin.

## 8. Definición de terminado

Un cambio está terminado cuando:

1. Cumple lo que dice el SRS, o el SRS se actualizó en el mismo cambio.
2. Tiene tests del camino feliz, de los errores esperables y, si toca datos de tenant, los cuatro tests de aislamiento.
3. `ruff check`, `ruff format --check` y `pytest` pasan completos.
4. `python manage.py makemigrations --check --dry-run` no reporta migraciones pendientes.
5. Si agrega un permiso, está en el catálogo, en el SRS y aplicado en la vista.
6. Si agrega un campo a un schema público, el test de contrato se actualizó a propósito y el campo figura en el SRS.
7. Si agrega una variable de entorno, está en `.env.example`.

## 9. Comandos

```
docker compose up -d                          # levantar el entorno
docker compose exec web python manage.py migrate
docker compose exec web pytest                # suite completa
docker compose exec web pytest apps/meli      # una app
docker compose exec web ruff check . && ruff format --check .
docker compose logs -f worker                 # ver tareas
```

## 10. Forma de trabajo con la IA

- Antes de escribir código para una funcionalidad nueva, leé la sección correspondiente del SRS y proponé un plan corto: archivos a tocar, modelos, tests.
- Cambios chicos y revisables. No mezcles refactors con funcionalidad.
- No modifiques ni borres tests existentes para que pasen. Si un test estorba, explicá por qué y esperá aprobación.
- No toques migraciones aplicadas, `docker-compose.yml`, `Caddyfile` ni `config/settings/prod.py` sin pedirlo.
- Si el pedido es ambiguo o choca con una regla de este archivo, preguntá una sola cosa concreta antes de arrancar.
- Si algo no se puede verificar (un dato de ML, un límite, un comportamiento de R2), decilo. No lo completes con suposiciones.
- Nunca ejecutes comandos destructivos (`flush`, `DROP`, `reset_db`, borrado de volúmenes o de buckets) sin confirmación explícita.
