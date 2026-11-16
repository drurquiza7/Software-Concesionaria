# SPECIFICATION_SRS.md

Especificación de Requisitos de Software — MVP Core de Concesionarias

| | |
|---|---|
| Versión | 0.1 (borrador fundacional) |
| Fecha | 2026-11-16 |
| Alcance | MVP: tenants, sucursales, usuarios y permisos, inventario, imágenes, integración Mercado Libre, API pública |
| Stack | Django + Django Ninja, PostgreSQL, Redis, Celery + Beat, Caddy, Cloudflare R2 |

Convenciones de este documento:

- **DEBE / NO DEBE**: requisito obligatorio. **DEBERÍA**: recomendado, se puede posponer con justificación.
- Los requisitos se identifican como `RF-xx` (funcional), `RS-xx` (seguridad) y `RN-xx` (regla de negocio).
- Todo lo marcado con **[VALIDAR]** es un dato de la API de Mercado Libre que no fue confirmado contra la documentación oficial y DEBE verificarse antes de implementar (ver sección 8).

---

## 1. Alcance

### 1.1 Incluido en el MVP

1. Alta de concesionarias (tenants) aisladas entre sí, cada una con N sucursales.
2. Usuarios globales con membresías por tenant, roles personalizados por tenant y permisos atómicos.
3. Inventario de vehículos con separación física entre datos públicos e internos.
4. Carga, procesamiento y publicación de imágenes (10 a 25 por vehículo) en Cloudflare R2.
5. Integración con Mercado Libre: OAuth, renovación de tokens, sincronización de atributos, subida de imágenes y alta/edición/pausa/cierre de publicaciones.
6. API REST pública de solo lectura por tenant, autenticada por API Key.

### 1.2 Fuera del MVP

CRM de leads y seguimiento comercial, facturación, financiación y `sale_terms` de ML, preguntas y mensajes de ML, publicación en otros portales, dominios propios por tenant, app móvil, reportes avanzados, cobro de suscripciones.

### 1.3 Glosario

| Término | Definición |
|---|---|
| Tenant | Una concesionaria cliente del SaaS. Unidad de aislamiento de datos. |
| Sucursal | Punto de venta físico de un tenant. |
| Membresía | Vínculo entre un usuario y un tenant. Un usuario puede tener varias. |
| Permiso atómico | Capacidad indivisible, identificada por código (`stock.ver_costo`). |
| Toma | Precio al que la concesionaria adquirió el vehículo. |
| Consignación | Vehículo de un tercero que la concesionaria vende a cambio de comisión. |
| Variante | Versión redimensionada de una imagen, generada por un worker. |
| Publicación | Ítem de un vehículo en Mercado Libre. |

---

## 2. Modelo de datos

### 2.1 Convenciones generales

- **PK**: `id` UUID (v7 si está disponible, si no v4) en todas las tablas. Nunca se exponen IDs secuenciales.
- **Timestamps**: `created_at` y `updated_at` (`timestamptz`, UTC) en todas las tablas.
- **Dinero**: `NUMERIC(14,2)` + columna de moneda `CHAR(3)` con valores `ARS` o `USD`. Prohibido usar `float`.
- **Enumeraciones**: `VARCHAR` con `CHECK` (Django `TextChoices`), no enums nativos de PostgreSQL.
- **Tablas de tenant**: toda tabla con datos de una concesionaria hereda de `TenantModel`, que aporta `tenant_id` (FK a `Tenant`, `NOT NULL`, indexada, `ON DELETE PROTECT`).
- **Integridad cruzada**: toda FK entre dos tablas de tenant DEBE validar que ambos registros pertenecen al mismo tenant (validación en `clean()` más test).
- **Borrado**: los vehículos no se borran físicamente; pasan a estado `baja`. El resto usa borrado físico salvo indicación.

### 2.2 Diagrama de relaciones

```
Tenant 1──N Sucursal
Tenant 1──N Rol N──M Permiso (catálogo global)
Usuario 1──N Membresia N──1 Tenant
Membresia N──M Rol
Membresia N──M Sucursal            (alcance por sucursal)
Tenant 1──N Vehiculo N──1 Sucursal
Vehiculo 1──1 VehiculoInterno 1──N GastoAcondicionamiento
Vehiculo 1──N VehiculoImagen
Vehiculo 1──0..1 MeliPublicacion
Tenant 1──0..1 MeliCredential
Tenant 1──N ApiKey
```

### 2.3 Tenant

| Campo | Tipo | Restricciones |
|---|---|---|
| `id` | UUID | PK |
| `nombre` | VARCHAR(120) | NOT NULL. Nombre comercial. |
| `slug` | VARCHAR(60) | NOT NULL, UNIQUE, `[a-z0-9-]`, inmutable tras el alta |
| `razon_social` | VARCHAR(160) | NULL |
| `cuit` | CHAR(11) | NULL, UNIQUE si no es NULL, solo dígitos, dígito verificador válido |
| `estado` | VARCHAR(12) | `activo` \| `suspendido`. Default `activo` |
| `zona_horaria` | VARCHAR(40) | Default `America/Argentina/Buenos_Aires` |
| `moneda_por_defecto` | CHAR(3) | `ARS` \| `USD`. Default `USD` |

- **RN-01**: un tenant `suspendido` no puede iniciar sesión en el panel, su API pública responde `403` y sus tareas de sincronización con ML no se ejecutan. Sus publicaciones en ML no se tocan automáticamente.

### 2.4 Sucursal (`TenantModel`)

| Campo | Tipo | Restricciones |
|---|---|---|
| `nombre` | VARCHAR(100) | NOT NULL. UNIQUE (`tenant_id`, `nombre`) |
| `slug` | VARCHAR(60) | NOT NULL. UNIQUE (`tenant_id`, `slug`). Usado como filtro en la API pública |
| `direccion` | VARCHAR(200) | NULL |
| `localidad` | VARCHAR(100) | NULL |
| `provincia` | VARCHAR(60) | NULL |
| `telefono` | VARCHAR(30) | NULL |
| `whatsapp` | VARCHAR(30) | NULL. Formato E.164 |
| `email` | VARCHAR(254) | NULL |
| `meli_ubicacion` | JSONB | NULL. Datos de `location` requeridos por ML **[VALIDAR]** |
| `activa` | BOOLEAN | Default `true` |

- **RN-02**: todo tenant DEBE tener al menos una sucursal activa. No se puede desactivar la última.
- **RN-03**: no se puede desactivar una sucursal con vehículos en estado `disponible` o `reservado`.

### 2.5 Usuario (global, no es `TenantModel`)

Modelo de usuario propio (`AUTH_USER_MODEL`) definido desde la primera migración.

| Campo | Tipo | Restricciones |
|---|---|---|
| `email` | VARCHAR(254) | NOT NULL, UNIQUE (case-insensitive). Es el identificador de login |
| `password` | VARCHAR(128) | Hash de Django (Argon2) |
| `nombre` | VARCHAR(80) | NOT NULL |
| `apellido` | VARCHAR(80) | NOT NULL |
| `is_active` | BOOLEAN | Default `true` |
| `is_staff` | BOOLEAN | Default `false`. Solo personal del SaaS |
| `email_verificado_at` | timestamptz | NULL |

- El usuario NO tiene `tenant_id`. Su acceso a datos existe solo a través de una `Membresia`.
- `is_staff` / `is_superuser` habilitan únicamente el admin interno del SaaS; no otorgan permisos dentro de ningún tenant.

### 2.6 Membresía (`TenantModel`)

Relación N:M entre `Usuario` y `Tenant`.

| Campo | Tipo | Restricciones |
|---|---|---|
| `usuario_id` | FK Usuario | NOT NULL. UNIQUE (`usuario_id`, `tenant_id`) |
| `estado` | VARCHAR(12) | `invitada` \| `activa` \| `suspendida` |
| `es_propietario` | BOOLEAN | Default `false` |
| `todas_las_sucursales` | BOOLEAN | Default `true` |
| `sucursales` | M2M Sucursal | Se usa solo si `todas_las_sucursales = false` |
| `roles` | M2M Rol | Vía `MembresiaRol` |
| `invitado_por_id` | FK Usuario | NULL |
| `invitacion_token_hash` | CHAR(64) | NULL. SHA-256 del token de invitación |
| `invitacion_expira_at` | timestamptz | NULL |

- **RN-04**: todo tenant DEBE tener al menos una membresía activa con `es_propietario = true`. No se puede quitar ni suspender al último propietario.
- **RN-05**: el propietario tiene todos los permisos, sin importar sus roles. No se puede restringir.
- **RN-06**: los roles y sucursales asignados a una membresía DEBEN pertenecer al mismo tenant.
- **RN-07**: si `todas_las_sucursales = false`, el usuario solo ve y opera vehículos de las sucursales asignadas. Este filtro se aplica además del filtro por tenant.
- El tenant activo de la sesión se guarda en la sesión del usuario y se valida en cada request contra una membresía `activa`.

### 2.7 Permiso (catálogo global)

Los permisos se definen **en código** (un registro por app) y se sincronizan a la tabla en cada migración. Los tenants no pueden crear permisos, solo asignarlos a roles.

| Campo | Tipo | Restricciones |
|---|---|---|
| `codigo` | VARCHAR(60) | PK lógica, UNIQUE. Formato `modulo.accion` |
| `modulo` | VARCHAR(30) | NOT NULL |
| `nombre` | VARCHAR(100) | NOT NULL. Texto para la UI |
| `descripcion` | VARCHAR(250) | NULL |
| `sensible` | BOOLEAN | Default `false`. La UI lo resalta al asignarlo |

Catálogo inicial del MVP:

| Código | Permite | Sensible |
|---|---|---|
| `tenant.configurar` | Editar datos de la concesionaria | sí |
| `sucursal.gestionar` | Crear, editar y desactivar sucursales | no |
| `miembros.gestionar` | Invitar, suspender y asignar roles a usuarios | sí |
| `roles.gestionar` | Crear, editar y eliminar roles | sí |
| `vehicle.ver` | Ver el listado y la ficha pública del vehículo | no |
| `vehicle.crear` | Dar de alta vehículos | no |
| `vehicle.editar` | Editar datos públicos | no |
| `vehicle.editar_precio` | Modificar el precio de venta | no |
| `vehicle.cambiar_estado` | Reservar, marcar vendido, dar de baja | no |
| `media.gestionar` | Subir, ordenar y eliminar imágenes | no |
| `stock.ver_costo` | Ver toma, gastos, costo total y margen | sí |
| `stock.editar_costo` | Editar toma, gastos y margen mínimo | sí |
| `stock.ver_consignacion` | Ver datos del dueño anterior | sí |
| `stock.editar_consignacion` | Editar datos del dueño anterior | sí |
| `meli.conectar` | Vincular o desvincular la cuenta de ML | sí |
| `meli.publicar` | Publicar y editar publicaciones | no |
| `meli.pausar` | Pausar, reactivar y cerrar publicaciones | no |
| `apikey.gestionar` | Crear y revocar API Keys | sí |
| `auditoria.ver` | Consultar el registro de auditoría | sí |

### 2.8 Rol (`TenantModel`)

| Campo | Tipo | Restricciones |
|---|---|---|
| `nombre` | VARCHAR(60) | NOT NULL. UNIQUE (`tenant_id`, `nombre`) |
| `color` | CHAR(7) | NULL. Hex `#RRGGBB` |
| `posicion` | INTEGER | NOT NULL. UNIQUE (`tenant_id`, `posicion`). Mayor número = mayor jerarquía |
| `es_predeterminado` | BOOLEAN | Default `false`. Roles creados por el sistema en el alta |
| `permisos` | M2M Permiso | Vía `RolPermiso` |

- **RN-08**: los permisos efectivos de una membresía son la **unión** de los permisos de todos sus roles. En el MVP no existen permisos de denegación.
- **RN-09** (jerarquía estilo Discord): un usuario solo puede editar, eliminar o asignar roles cuya `posicion` sea **menor** a la de su rol más alto. El propietario no tiene límite.
- **RN-10** (anti-escalada): un usuario no puede otorgar a un rol un permiso que él mismo no posee.
- **RN-11**: en el alta de un tenant se crean tres roles editables: `Administrador` (todos los permisos), `Vendedor` (`vehicle.ver`, `vehicle.crear`, `vehicle.editar`, `vehicle.cambiar_estado`, `media.gestionar`) y `Publicador` (`vehicle.ver`, `media.gestionar`, `meli.publicar`, `meli.pausar`).
- Los permisos efectivos se cachean en Redis por membresía y se invalidan al cambiar roles o permisos de un rol.

### 2.9 Vehículo — datos públicos (`TenantModel`)

Separación estricta: la tabla `Vehiculo` contiene **únicamente** datos publicables. Todo dato interno vive en `VehiculoInterno` (sección 2.10), en otra tabla y otro módulo.

| Campo | Tipo | Restricciones |
|---|---|---|
| `sucursal_id` | FK Sucursal | NOT NULL. Mismo tenant |
| `condicion` | VARCHAR(8) | `nuevo` \| `usado` |
| `marca` | VARCHAR(60) | NOT NULL |
| `modelo` | VARCHAR(80) | NOT NULL |
| `version` | VARCHAR(120) | NULL |
| `anio` | SMALLINT | NOT NULL. CHECK entre 1900 y año actual + 1 |
| `kilometros` | INTEGER | NOT NULL. CHECK ≥ 0. Si `condicion = nuevo`, DEBE ser 0 |
| `combustible` | VARCHAR(16) | `nafta` \| `diesel` \| `gnc` \| `nafta_gnc` \| `hibrido` \| `electrico` |
| `transmision` | VARCHAR(12) | `manual` \| `automatica` |
| `carroceria` | VARCHAR(16) | NULL. `sedan` \| `hatchback` \| `suv` \| `pickup` \| `coupe` \| `furgon` \| `otro` |
| `color` | VARCHAR(40) | NULL |
| `puertas` | SMALLINT | NULL. CHECK entre 2 y 5 |
| `precio` | NUMERIC(14,2) | NULL en `borrador`; obligatorio y > 0 desde `disponible` |
| `moneda` | CHAR(3) | `ARS` \| `USD` |
| `mostrar_precio` | BOOLEAN | Default `true`. Si es `false`, la API pública devuelve `precio: null` |
| `descripcion` | TEXT | NULL. Máx. 5000 caracteres. Texto plano |
| `estado` | VARCHAR(12) | `borrador` \| `disponible` \| `reservado` \| `vendido` \| `baja` |
| `publicar_en_web` | BOOLEAN | Default `true`. Controla la API pública |
| `publicar_en_meli` | BOOLEAN | Default `false`. Controla la sincronización con ML |
| `publicado_at` | timestamptz | NULL. Primera vez que pasó a `disponible` |
| `vendido_at` | timestamptz | NULL |
| `meli_atributos` | JSONB | Default `{}`. Atributos de ML que no tienen columna propia |

Índices: (`tenant_id`, `estado`), (`tenant_id`, `sucursal_id`, `estado`), (`tenant_id`, `precio`), (`tenant_id`, `anio`).

Máquina de estados:

```
borrador ──► disponible ◄──► reservado
                 │               │
                 ├──► vendido ◄──┘
                 └──► baja   (también desde borrador y reservado)
vendido ──► disponible   (reversión; requiere vehicle.cambiar_estado)
```

- **RN-12**: para pasar a `disponible` el vehículo DEBE tener precio, moneda y al menos 1 imagen en estado `lista`.
- **RN-13**: `baja` es terminal. `vendido` solo admite la reversión a `disponible`.
- **RN-14**: todo cambio de estado, precio o flag de publicación dispara la sincronización asíncrona con ML (sección 4.5), nunca una llamada directa.

### 2.10 VehiculoInterno — datos privados (`TenantModel`)

Relación 1:1 con `Vehiculo` (`vehiculo_id` UNIQUE). Se crea junto con el vehículo. Vive en el módulo `inventory/internal/` y **ningún módulo de `public_api` puede importarlo** (sección 5.4).

| Campo | Tipo | Restricciones |
|---|---|---|
| `vehiculo_id` | FK Vehiculo | NOT NULL, UNIQUE, `ON DELETE CASCADE` |
| `patente` | VARCHAR(10) | NULL. Mayúsculas, sin espacios. UNIQUE (`tenant_id`, `patente`) cuando no es NULL y el vehículo no está en `baja` |
| `vin` | VARCHAR(17) | NULL |
| `origen` | VARCHAR(14) | `compra` \| `toma` \| `consignacion` |
| `precio_toma` | NUMERIC(14,2) | NULL. CHECK ≥ 0 |
| `moneda_toma` | CHAR(3) | `ARS` \| `USD` |
| `fecha_ingreso` | DATE | NULL |
| `margen_minimo` | NUMERIC(14,2) | NULL. CHECK ≥ 0. En la moneda de venta |
| `comision_consignacion_pct` | NUMERIC(5,2) | NULL. CHECK entre 0 y 100. Solo si `origen = consignacion` |
| `propietario_nombre` | TEXT cifrado | NULL. Solo si `origen = consignacion` |
| `propietario_documento` | TEXT cifrado | NULL |
| `propietario_telefono` | TEXT cifrado | NULL |
| `propietario_email` | TEXT cifrado | NULL |
| `notas_internas` | TEXT | NULL |

**GastoAcondicionamiento** (`TenantModel`, N:1 con `VehiculoInterno`):

| Campo | Tipo | Restricciones |
|---|---|---|
| `vehiculo_interno_id` | FK | NOT NULL, `ON DELETE CASCADE` |
| `concepto` | VARCHAR(120) | NOT NULL |
| `monto` | NUMERIC(14,2) | NOT NULL. CHECK > 0 |
| `moneda` | CHAR(3) | `ARS` \| `USD` |
| `fecha` | DATE | NOT NULL |
| `registrado_por_id` | FK Usuario | NOT NULL |

- **RN-15**: `costo_total` = `precio_toma` + suma de gastos. Es un valor **calculado**, no se persiste. Solo se calcula si toma y gastos están en la misma moneda; si no, se muestran por separado sin convertir (el MVP no maneja tipo de cambio).
- **RN-16**: `margen` = `precio` − `costo_total`, bajo la misma condición de moneda. Si `margen < margen_minimo`, el panel muestra una advertencia a quien tenga `stock.ver_costo`.
- **RS-01**: sin `stock.ver_costo`, ningún campo de costo, gasto o margen se envía al navegador: no se renderiza en el HTML ni viaja en respuestas HTMX. Ocultar con CSS no cumple este requisito.
- **RS-02**: los campos `propietario_*` se cifran a nivel de aplicación (sección 6.2) y requieren `stock.ver_consignacion`.

### 2.11 VehiculoImagen (`TenantModel`)

| Campo | Tipo | Restricciones |
|---|---|---|
| `vehiculo_id` | FK Vehiculo | NOT NULL, `ON DELETE CASCADE` |
| `orden` | SMALLINT | NOT NULL. CHECK ≥ 0. UNIQUE (`vehiculo_id`, `orden`) DEFERRABLE. `orden = 0` es la portada |
| `estado` | VARCHAR(12) | `pendiente` \| `procesando` \| `lista` \| `error` |
| `error_detalle` | VARCHAR(250) | NULL |
| `key_original` | VARCHAR(300) | NOT NULL. Objeto en el bucket privado |
| `key_thumb` | VARCHAR(300) | NULL. WebP, 400 px de lado mayor |
| `key_web` | VARCHAR(300) | NULL. WebP, 1200 px |
| `key_full` | VARCHAR(300) | NULL. WebP, 1920 px |
| `key_ml` | VARCHAR(300) | NULL. JPEG, 1920 px, bucket privado |
| `ancho`, `alto` | INTEGER | NULL. Dimensiones del original |
| `bytes_original` | INTEGER | NULL |
| `sha256` | CHAR(64) | NULL. Hash del original; evita duplicados dentro del mismo vehículo |
| `meli_picture_id` | VARCHAR(60) | NULL. ID devuelto por ML al subir la variante `ml` |
| `meli_subida_at` | timestamptz | NULL |
| `subida_por_id` | FK Usuario | NOT NULL |

- **RN-17**: máximo 25 imágenes por vehículo. El máximo efectivo que se envía a ML es el menor entre 25 y el `max_pictures_per_item` de la categoría.
- **RN-18**: formatos de entrada aceptados: JPEG, PNG, WebP y HEIC. Tamaño máximo por archivo: 25 MB. Lado menor mínimo: 500 px.
- **RN-19**: si cambia el archivo de una imagen ya subida a ML, se anula `meli_picture_id` y se vuelve a subir. Reordenar no invalida el `meli_picture_id`.
- Layout de claves en R2: `t/{tenant_id}/v/{vehiculo_id}/{imagen_id}/{variante}.{ext}`.
- Dos buckets: uno **privado** (originales y variante `ml`) y uno **público** detrás del CDN (variantes `thumb`, `web`, `full`).

### 2.12 MeliCredential (`TenantModel`)

Una cuenta de ML por tenant en el MVP (`tenant_id` UNIQUE).

| Campo | Tipo | Restricciones |
|---|---|---|
| `tenant_id` | FK Tenant | NOT NULL, UNIQUE |
| `meli_user_id` | BIGINT | NOT NULL, UNIQUE global. Una cuenta de ML no puede vincularse a dos tenants |
| `meli_nickname` | VARCHAR(80) | NULL |
| `access_token_enc` | TEXT | NOT NULL. Cifrado |
| `refresh_token_enc` | TEXT | NOT NULL. Cifrado |
| `scope` | VARCHAR(120) | NOT NULL. DEBE incluir `offline_access` |
| `expires_at` | timestamptz | NOT NULL. Vencimiento del access token |
| `refreshed_at` | timestamptz | NULL. Último refresh exitoso |
| `estado` | VARCHAR(24) | `activa` \| `requiere_reautorizacion` \| `desvinculada` |
| `fallos_consecutivos` | SMALLINT | Default 0 |
| `ultimo_error` | VARCHAR(250) | NULL. Nunca contiene tokens |
| `conectada_por_id` | FK Usuario | NOT NULL |

- **RS-03**: los tokens nunca se guardan en claro, nunca se loguean y nunca se devuelven al navegador.
- **RS-04**: toda lectura con intención de refrescar DEBE hacerse con `SELECT ... FOR UPDATE` dentro de una transacción (sección 4.2).

### 2.13 MeliPublicacion (`TenantModel`)

| Campo | Tipo | Restricciones |
|---|---|---|
| `vehiculo_id` | FK Vehiculo | NOT NULL, UNIQUE |
| `item_id` | VARCHAR(20) | NULL hasta la creación. UNIQUE cuando no es NULL |
| `permalink` | VARCHAR(300) | NULL |
| `category_id` | VARCHAR(20) | NOT NULL |
| `listing_type_id` | VARCHAR(30) | NOT NULL |
| `estado_meli` | VARCHAR(20) | NULL. Último `status` informado por ML |
| `subestado_meli` | VARCHAR(60) | NULL |
| `estado_sync` | VARCHAR(14) | `pendiente` \| `en_curso` \| `sincronizado` \| `error` |
| `payload_hash` | CHAR(64) | NULL. Hash del último payload enviado; evita PUT sin cambios |
| `intentos` | SMALLINT | Default 0 |
| `ultimo_error` | TEXT | NULL. Mensaje y `cause` devueltos por ML |
| `sincronizado_at` | timestamptz | NULL |

### 2.14 MeliCategoriaAtributo (caché global, no es `TenantModel`)

| Campo | Tipo | Restricciones |
|---|---|---|
| `category_id` | VARCHAR(20) | NOT NULL. UNIQUE (`category_id`, `attribute_id`) |
| `attribute_id` | VARCHAR(60) | NOT NULL |
| `nombre` | VARCHAR(120) | NOT NULL |
| `value_type` | VARCHAR(20) | NOT NULL |
| `requerido` | BOOLEAN | NOT NULL. Derivado de `tags.required` |
| `valores` | JSONB | Lista de `{id, name}` permitidos |
| `actualizado_at` | timestamptz | NOT NULL |

### 2.15 ApiKey (`TenantModel`)

| Campo | Tipo | Restricciones |
|---|---|---|
| `nombre` | VARCHAR(80) | NOT NULL. Etiqueta para identificarla |
| `prefijo` | CHAR(8) | NOT NULL, UNIQUE global. Visible en el panel |
| `hash` | CHAR(64) | NOT NULL. SHA-256 de la clave completa |
| `sucursales` | M2M Sucursal | Vacío = todas |
| `origenes_permitidos` | JSONB | Lista de orígenes para CORS. Vacío = sin CORS (solo server-side) |
| `ultimo_uso_at` | timestamptz | NULL |
| `revocada_at` | timestamptz | NULL |
| `creada_por_id` | FK Usuario | NOT NULL |

- Formato de la clave: `dms_live_{prefijo}_{secreto}`, con `secreto` de 32 bytes aleatorios en base62.
- **RS-05**: la clave completa se muestra una sola vez al crearla. Solo se persiste el hash.

### 2.16 RegistroAuditoria (`TenantModel`)

Registro append-only: `usuario_id`, `accion`, `entidad`, `entidad_id`, `cambios` (JSONB con valores anterior y nuevo), `ip`, `created_at`. Se registran como mínimo: cambios de precio, de estado, de costos, de roles y permisos, creación y revocación de API Keys, y conexión o desconexión de ML. Los valores cifrados no se guardan en `cambios`.

---

## 3. Autorización

- **RF-01**: cada vista y cada endpoint interno declara explícitamente el permiso requerido. Una vista sin permiso declarado DEBE fallar en los tests.
- **RF-02**: orden de evaluación por request: sesión válida → membresía `activa` en el tenant de la sesión → tenant `activo` → permiso atómico → alcance por sucursal.
- **RF-03**: los objetos fuera del tenant o del alcance de sucursal responden `404`, no `403`, para no revelar su existencia.

---

## 4. Integración con Mercado Libre

### 4.1 Vinculación OAuth 2.0

Flujo Authorization Code, server-side:

1. Un usuario con `meli.conectar` inicia la vinculación. El sistema genera un `state` aleatorio (32 bytes), lo guarda en Redis asociado a `tenant_id` y `usuario_id` con TTL de 10 minutos, y redirige a la página de autorización de ML con `response_type=code`, `client_id`, `redirect_uri` y `state`.
2. ML redirige al `redirect_uri` con `code` y `state`.
3. El sistema valida que el `state` exista, no esté vencido y corresponda a la sesión actual. Si no, rechaza y registra el intento. El `state` es de un solo uso.
4. Se intercambia el `code` en `POST https://api.mercadolibre.com/oauth/token` (`grant_type=authorization_code`). Esta es la **única** llamada a ML permitida dentro de un request web, porque el `code` vence rápido; lleva timeout de 10 s.
5. Se guardan `access_token` y `refresh_token` cifrados, `expires_at = ahora + expires_in`, `meli_user_id`, `scope` y `estado = activa`.
6. Si el `scope` no incluye `offline_access`, la vinculación se rechaza con mensaje claro.
7. Si el `meli_user_id` ya pertenece a otro tenant, se rechaza.

- **RF-04**: desvincular marca `estado = desvinculada` y borra ambos tokens. Las publicaciones existentes en ML no se modifican.

### 4.2 Renovación automática de tokens

Datos confirmados en la documentación de ML: el access token dura 6 horas; cada refresh devuelve un **nuevo** refresh token; solo es válido el último refresh token generado. Por eso dos refresh concurrentes de la misma cuenta pueden dejarla inutilizable.

**Tarea periódica** (Celery Beat, cada 10 minutos):

1. Selecciona credenciales con `estado = activa` y `expires_at < ahora + 60 min`.
2. Encola una tarea `refrescar_credencial(credential_id)` por cada una.

**Tarea `refrescar_credencial`**:

1. Abre una transacción y lee la fila con `SELECT ... FOR UPDATE`.
2. **Revalida** dentro del lock: si `expires_at` ya es mayor a `ahora + 60 min`, otro proceso ya refrescó; termina sin hacer nada.
3. Llama a `POST /oauth/token` con `grant_type=refresh_token` y timeout de 10 s. La llamada se hace **dentro** de la transacción a propósito: el lock de fila es lo que garantiza un solo refresh por cuenta.
4. Si responde OK: guarda el nuevo `access_token`, el nuevo `refresh_token`, `expires_at`, `refreshed_at` y pone `fallos_consecutivos = 0`. Commit.
5. Si responde `invalid_grant` o equivalente (refresh token revocado o inválido): `estado = requiere_reautorizacion`, se notifica por email a propietarios y a quienes tengan `meli.conectar`. No se reintenta.
6. Si hay error de red, timeout, `429` o `5xx`: incrementa `fallos_consecutivos` y reintenta con backoff exponencial. Con 5 fallos consecutivos se notifica, pero la credencial sigue `activa` mientras el access token no haya vencido.

**Obtención del token para usar** (`obtener_access_token(tenant_id)`): toda tarea que llama a ML pasa por esta única función. Si faltan menos de 5 minutos para el vencimiento, ejecuta el mismo procedimiento de refresh bajo el mismo lock antes de devolver el token.

- **RF-05**: si una llamada a ML responde `401`, la tarea fuerza un refresh una única vez y reintenta. Un segundo `401` marca `requiere_reautorizacion`.

### 4.3 Categorías y atributos de vehículos

- Árbol de referencia en Argentina: `MLA1743` ("Autos, Motos y Otros") es la raíz y `MLA1744` es la rama de autos y camionetas. La publicación se hace siempre en una **categoría hoja**, que se obtiene recorriendo `GET /categories/{id}` (`children_categories`).
- **RF-06**: los atributos obligatorios NO se hardcodean. Se obtienen de `GET /categories/{category_id}/attributes` y un atributo es obligatorio cuando trae `tags.required = true`.
- **RF-07**: una tarea semanal de Celery Beat refresca `MeliCategoriaAtributo` para las categorías en uso. Un cambio en el conjunto de atributos obligatorios genera una alerta al equipo del SaaS.
- **RF-08**: mapeo entre el modelo interno y ML en una tabla de correspondencias mantenida en código, con dos niveles: campo interno → `attribute_id`, y valor interno → `value_id` o `value_name`.

Mapeo inicial previsto (los IDs de atributo son los del dominio de autos de ML; **[VALIDAR]** uno por uno contra la respuesta real de la categoría):

| Campo interno | Atributo ML | Tipo de mapeo |
|---|---|---|
| `marca` | `BRAND` | Selección sobre los valores de ML |
| `modelo` | `MODEL` | Selección dependiente de la marca |
| `version` | `SHORT_VERSION` / `TRIM` **[VALIDAR]** | Texto o selección |
| `anio` | `VEHICLE_YEAR` | Valor directo |
| `kilometros` | `KILOMETERS` **[VALIDAR]** | Número con unidad `km` |
| `combustible` | `FUEL_TYPE` **[VALIDAR]** | Tabla de equivalencias de valores |
| `transmision` | `TRANSMISSION` / `TRANSMISSION_CONTROL_TYPE` **[VALIDAR]** | Tabla de equivalencias |
| `puertas` | `DOORS` **[VALIDAR]** | Valor directo |
| `color` | `COLOR` **[VALIDAR]** | Texto o selección |
| `condicion` | campo `condition` del ítem (`new` / `used`) | Valor directo |

- **RF-09**: en el alta y edición de vehículos, marca, modelo y versión se eligen de listas alimentadas por los valores de ML, guardando texto visible e ID de ML. Esto evita rechazos por valores inexistentes.
- **RF-10**: los atributos obligatorios de ML sin columna propia se cargan en un formulario dinámico generado desde `MeliCategoriaAtributo` y se guardan en `Vehiculo.meli_atributos`.
- **RF-11**: antes de encolar una publicación se valida localmente que estén todos los atributos obligatorios. Si falta alguno, no se encola y se informa cuáles faltan.

### 4.4 Subida de imágenes

Datos confirmados en la documentación de ML: acepta JPG, JPEG y PNG de hasta 10 MB; recomienda 1200 x 1200 px; el máximo es 1920 x 1920 px y reduce lo que lo supere; el máximo de fotos por publicación lo define `max_pictures_per_item` de la categoría; las publicaciones tipo `silver` se rechazan si no incluyen el array `pictures` en la creación.

Pipeline:

1. El navegador pide una URL prefirmada y sube el original **directo** al bucket privado de R2. El archivo no pasa por el VPS.
2. El navegador confirma la subida. Se crea `VehiculoImagen` en `pendiente` y se encola `procesar_imagen`.
3. El worker valida el archivo real (tipo por contenido, no por extensión; dimensiones; tamaño), corrige la orientación EXIF, elimina metadatos (incluida la geolocalización) y genera las cuatro variantes. La variante `ml` es JPEG, sRGB, 1920 px de lado mayor, calidad 85, y DEBE pesar menos de 10 MB.
4. La imagen pasa a `lista` o a `error` con detalle.
5. Al publicar, por cada imagen `lista` sin `meli_picture_id` la tarea `subir_imagen_a_meli` descarga la variante `ml` del bucket privado y la envía por `multipart/form-data` (campo `file`) a `POST https://api.mercadolibre.com/pictures/items/upload`. Guarda el `id` devuelto en `meli_picture_id`.
6. La publicación referencia las imágenes por ID (`"pictures": [{"id": "..."}]`), respetando `orden`.

- **RF-12**: la subida de imágenes a ML es idempotente: una imagen con `meli_picture_id` no se vuelve a subir salvo RN-19.
- **RF-13**: si alguna imagen falla tras agotar reintentos, la publicación queda en `error` y no se crea con fotos incompletas.
- **RF-14** (DEBERÍA): validar la portada con la API de diagnóstico de imágenes de ML antes de publicar y mostrar las advertencias al usuario.

### 4.5 Sincronización de publicaciones

Toda operación sobre ML se ejecuta en Celery. El panel solo cambia datos locales, marca `estado_sync = pendiente` y encola `sincronizar_publicacion(vehiculo_id)` con `transaction.on_commit`.

Estado deseado en ML según el estado local:

| Estado del vehículo | `publicar_en_meli` | Acción en ML |
|---|---|---|
| `borrador` | cualquiera | Ninguna |
| `disponible` | `true`, sin publicación | Crear (`POST /items`) |
| `disponible` | `true`, con publicación | Actualizar y dejar `active` |
| `disponible` | `false`, con publicación | `PUT status = paused` |
| `reservado` | cualquiera, con publicación | `PUT status = paused` |
| `vendido` | cualquiera, con publicación | `PUT status = closed` |
| `baja` | cualquiera, con publicación | `PUT status = closed` |
| `disponible` (reversión desde `vendido`) | `true` | Publicación nueva: `closed` no se puede reactivar |

Tarea `sincronizar_publicacion`:

1. Activa el contexto del tenant y toma lock (`SELECT ... FOR UPDATE`) sobre la fila de `MeliPublicacion`. Esto serializa las sincronizaciones del mismo vehículo.
2. Calcula el estado deseado según la tabla.
3. **Crear**: verifica atributos obligatorios, sube las imágenes faltantes, arma el payload y hace `POST /items`. Guarda `item_id` y `permalink` inmediatamente. Si la tarea se reintenta y ya existe `item_id`, no vuelve a crear.
4. **Actualizar**: arma el payload, calcula su hash y, si es distinto de `payload_hash`, hace `PUT /items/{item_id}`. Si es igual, no llama a ML.
5. **Pausar, reactivar o cerrar**: `PUT /items/{item_id}` con `status` en minúsculas (`paused`, `active`, `closed`).
6. Actualiza `estado_meli`, `estado_sync`, `sincronizado_at` y `payload_hash`.

Payload de creación (estructura conceptual; **[VALIDAR]** contra la guía "Publica vehículos"):

- `title`, `category_id` (hoja), `price`, `currency_id` (`ARS` \| `USD`), `available_quantity: 1`, `buying_mode: "classified"`, `listing_type_id`, `condition`, `pictures` (por ID), `attributes`, `location` (desde la sucursal), `seller_contact` (desde la sucursal), `description`.

Reglas:

- **RN-20**: en clasificados de vehículos, publicar requiere que la cuenta de ML tenga un paquete de publicaciones contratado con el equipo comercial de ML; no se puede contratar por API. Antes de crear, el sistema consulta el cupo disponible y, si no hay, informa el motivo sin encolar.
- **RN-21**: el `listing_type_id` de una publicación solo se puede modificar una vez. El sistema no lo cambia automáticamente.
- **RN-22**: un error `4xx` de validación de ML no se reintenta: se guarda el `message` y `cause` en `ultimo_error` y se muestra al usuario traducido a una acción concreta.
- **RN-23**: el panel muestra por vehículo el estado de sincronización (`pendiente`, `en_curso`, `sincronizado`, `error`), el último error y un botón de reintento manual que requiere `meli.publicar`.

### 4.6 Notificaciones entrantes de ML

- Endpoint `POST /webhooks/meli`, sin sesión ni CSRF.
- ML envía un JSON con `resource`, `user_id`, `topic`, `application_id`, `attempts` y `sent`. El contenido del recurso no viene en la notificación.
- **RF-15**: el endpoint valida la forma del payload, verifica que `application_id` sea el propio, busca el tenant por `user_id`, encola `procesar_notificacion_meli` y responde `200` de inmediato. No hace trabajo en el request.
- **RF-16**: la tarea hace `GET` del recurso con el token del tenant y actualiza `estado_meli` y `subestado_meli`. La notificación nunca se toma como verdad: es solo un disparador.
- **RF-17**: si ML pausa o modera una publicación (por ejemplo `under_review` o pausa preventiva), se refleja en el panel y se notifica. El sistema no la reactiva automáticamente.
- **RF-18**: deduplicación por `resource` + `sent` con una clave en Redis de TTL corto.
- Tópico suscripto en el MVP: `items`.

### 4.7 Reconciliación

- **RF-19**: una tarea diaria por tenant compara las publicaciones locales contra `GET /items/{id}` y corrige `estado_meli`. Cubre notificaciones perdidas.
- **RF-20**: una publicación cerrada o eliminada directamente desde ML se marca localmente y desactiva `publicar_en_meli` en el vehículo, con aviso al usuario.

---

## 5. API REST pública (Django Ninja)

### 5.1 Generalidades

- Base: `/api/v1`. Solo lectura. Solo HTTPS.
- Formato: JSON, UTF-8. Fechas ISO 8601 en UTC. Montos como **string decimal** (`"18500.00"`) para evitar errores de coma flotante.
- Documentación OpenAPI generada por Ninja en `/api/v1/docs`.
- Versionado por prefijo de URL. Los cambios incompatibles van a `/api/v2`.

### 5.2 Autenticación

- Header: `Authorization: Bearer dms_live_{prefijo}_{secreto}`.
- Resolución: se extrae el prefijo, se busca la `ApiKey`, se calcula el SHA-256 de la clave recibida y se compara en tiempo constante contra `hash`. El resultado se cachea en Redis 60 s por hash.
- La clave determina el tenant. **No existe** ningún parámetro para indicar el tenant: es imposible pedir datos de otra concesionaria.
- Errores: sin header o formato inválido → `401`; clave inexistente o revocada → `401` (mismo mensaje, sin distinguir el caso); tenant suspendido → `403`.
- Rate limit: 60 requests por minuto por clave, con respuesta `429` y header `Retry-After`.
- CORS: solo para los orígenes listados en `origenes_permitidos`. Si la lista está vacía no se emiten headers CORS.
- Una clave usada desde el navegador queda expuesta al visitante. Es aceptable porque solo da acceso de lectura a datos ya públicos, pero se DEBE usar una clave distinta por landing para poder revocarla.

### 5.3 GET /api/v1/vehicles

Lista los vehículos publicables del tenant de la clave.

**Visibilidad** (condiciones acumulativas, no configurables por parámetro):

- `estado` en (`disponible`, `reservado`). Los estados `borrador`, `vendido` y `baja` nunca se exponen.
- `publicar_en_web = true`.
- Sucursal activa y dentro del alcance de la clave.

**Query params**:

| Parámetro | Tipo | Descripción |
|---|---|---|
| `sucursal` | string | `slug` de la sucursal. Repetible |
| `estado` | string | `disponible` \| `reservado`. Default: ambos |
| `condicion` | string | `nuevo` \| `usado` |
| `marca` | string | Coincidencia exacta, sin distinguir mayúsculas |
| `modelo` | string | Coincidencia exacta, sin distinguir mayúsculas |
| `precio_min`, `precio_max` | decimal | Requieren `moneda`. Excluyen vehículos con `mostrar_precio = false` |
| `moneda` | string | `ARS` \| `USD`. Filtra por moneda de publicación; no hay conversión |
| `anio_min`, `anio_max` | int | Rango inclusivo |
| `km_max` | int | Máximo de kilómetros |
| `orden` | string | `recientes` (default) \| `precio_asc` \| `precio_desc` \| `anio_desc` \| `km_asc` |
| `limit` | int | Default 24, máximo 100 |
| `offset` | int | Default 0 |

Un parámetro desconocido o con valor inválido responde `422` con el detalle del campo. No se ignoran en silencio.

**Respuesta `200`**:

```json
{
  "count": 37,
  "limit": 24,
  "offset": 0,
  "results": [
    {
      "id": "0193a5b2-7c1e-7d3a-9f10-2b6e4c8a1d55",
      "estado": "disponible",
      "condicion": "usado",
      "marca": "Toyota",
      "modelo": "Hilux",
      "version": "2.8 SRX 4x4 AT",
      "anio": 2021,
      "kilometros": 68000,
      "combustible": "diesel",
      "transmision": "automatica",
      "carroceria": "pickup",
      "color": "Blanco",
      "puertas": 4,
      "precio": "38500.00",
      "moneda": "USD",
      "descripcion": "Único dueño, service oficial al día.",
      "sucursal": {
        "slug": "casa-central",
        "nombre": "Casa Central",
        "localidad": "Baradero",
        "provincia": "Buenos Aires",
        "telefono": "+543329000000",
        "whatsapp": "+5493329000000"
      },
      "imagenes": [
        {
          "orden": 0,
          "thumb": "https://img.example.com/t/.../thumb.webp",
          "web": "https://img.example.com/t/.../web.webp",
          "full": "https://img.example.com/t/.../full.webp"
        }
      ],
      "meli_url": "https://auto.mercadolibre.com.ar/MLA-0000000000",
      "publicado_at": "2026-11-10T14:03:00Z",
      "actualizado_at": "2026-11-15T18:22:41Z"
    }
  ]
}
```

- Si `mostrar_precio = false`: `"precio": null` y `"moneda": null`.
- `imagenes` incluye solo imágenes en estado `lista`, ordenadas por `orden`.
- `meli_url` es `null` si no hay publicación activa.

**GET /api/v1/vehicles/{id}**: devuelve un único vehículo con el mismo schema. Responde `404` si no existe, es de otro tenant o no cumple las condiciones de visibilidad.

**GET /api/v1/branches**: lista las sucursales activas dentro del alcance de la clave.

**Formato de error** (todos los endpoints):

```json
{ "error": { "code": "invalid_parameter", "message": "precio_min requiere el parámetro moneda", "field": "precio_min" } }
```

Códigos: `unauthorized` (401), `forbidden` (403), `not_found` (404), `invalid_parameter` (422), `rate_limited` (429), `internal_error` (500, sin detalles internos).

**Caché**: respuestas cacheadas en Redis 60 s por (clave, query normalizada), con invalidación al modificar un vehículo o sus imágenes. Header `Cache-Control: private, max-age=60`.

### 5.4 Sanitización estricta

Garantía: los campos privados (toma, costo, gastos, margen, patente, VIN, datos del dueño anterior, notas internas) **no pueden** aparecer en esta capa. Se sostiene con cinco barreras independientes:

1. **Separación física**: los datos privados están en otra tabla (`VehiculoInterno`, `GastoAcondicionamiento`). Una consulta sobre `Vehiculo` no los trae.
2. **Prohibición de importación**: el módulo `public_api` no puede importar nada de `inventory/internal/`. Se verifica con un test de arquitectura que inspecciona los imports.
3. **Schemas por lista blanca**: los schemas de salida se declaran campo por campo. Prohibido `ModelSchema` con `fields = "__all__"` o con `exclude`. Todos los schemas públicos rechazan campos extra.
4. **Consulta acotada**: los selectores de `public_api` usan `.only()` con la lista explícita de columnas públicas y nunca hacen `select_related` hacia `VehiculoInterno`.
5. **Test de contrato**: un test crea un vehículo con valores centinela únicos en todos los campos privados, llama a cada endpoint público y falla si alguno de esos valores, o alguna clave de una lista negra (`precio_toma`, `costo`, `margen`, `gasto`, `patente`, `vin`, `propietario`, `notas_internas`, `tenant_id`), aparece en el cuerpo de la respuesta. Otro test fija el conjunto exacto de claves del schema: agregar un campo a la API exige modificar ese test a conciencia.

Reglas adicionales:

- **RS-06**: `tenant_id`, IDs de usuarios e IDs internos de sucursal no se exponen. Las sucursales se identifican por `slug`.
- **RS-07**: los errores `500` nunca incluyen trazas, SQL ni nombres de campos internos.

---

## 6. Requisitos no funcionales

### 6.1 Aislamiento multi-tenant

- **RS-08**: aislamiento por fila con `tenant_id`. El manager por defecto de todo `TenantModel` filtra por el tenant activo y **falla** (excepción) si no hay tenant activo. Nunca devuelve datos sin filtrar.
- **RS-09**: el tenant activo se establece en un único lugar por punto de entrada: middleware (panel), autenticador de API Key (API pública) y un context manager explícito (tareas Celery, que reciben `tenant_id` como argumento).
- **RS-10**: el acceso sin filtro por tenant existe solo en un manager con nombre explícito, usado por tareas de sistema y por el admin interno, y cada uso lleva un comentario que lo justifica.
- **RS-11**: cada endpoint y cada vista tiene un test que intenta acceder a un objeto de otro tenant y espera `404`.

### 6.2 Seguridad

- **RS-12**: cifrado a nivel de aplicación (Fernet, con soporte de rotación de claves) para tokens de ML y campos `propietario_*`. Las claves viven en variables de entorno, fuera del repositorio y fuera de la base.
- **RS-13**: contraseñas con Argon2. Sesiones con cookies `Secure`, `HttpOnly` y `SameSite=Lax`. CSRF activo en todo el panel, incluidas las requests de HTMX.
- **RS-14**: los logs nunca contienen tokens, API Keys, contraseñas ni datos de `propietario_*`.
- **RS-15**: las subidas se validan por contenido real del archivo. Las URLs prefirmadas vencen a los 10 minutos y están limitadas a una clave de objeto dentro del prefijo del tenant.
- **RS-16**: rate limit en login (5 intentos por minuto por IP y por email).

### 6.3 Rendimiento y recursos

- `GET /api/v1/vehicles` con caché caliente: p95 menor a 150 ms. Sin caché: p95 menor a 500 ms con 5.000 vehículos por tenant.
- Listados del panel: p95 menor a 800 ms.
- Procesamiento de una imagen de 12 MP: menos de 10 s por imagen en el worker.
- Sin consultas N+1 en listados (verificado con tests de cantidad de queries).

### 6.4 Confiabilidad

- Todas las tareas Celery son idempotentes y reciben IDs, nunca objetos.
- Backup diario de PostgreSQL (`pg_dump`) a un bucket R2 separado, con retención de 30 días y prueba de restauración mensual.
- Ninguna falla de ML o de R2 puede impedir operar el inventario en el panel.

### 6.5 Observabilidad

- Logs estructurados en JSON con `tenant_id`, `request_id` y `task_id`.
- Métricas mínimas: credenciales en `requiere_reautorizacion`, publicaciones en `error`, imágenes en `error`, tareas fallidas y longitud de las colas.
- Endpoint `/healthz` que verifica base de datos y Redis.

---

## 7. Criterios de aceptación del MVP

1. Dos tenants con datos cargados no pueden ver, listar ni modificar nada del otro por ninguna vía (panel, API pública, IDs manipulados en la URL).
2. Un propietario crea un rol nuevo, le asigna permisos y un usuario con ese rol solo puede hacer lo que el rol permite.
3. Un usuario sin `stock.ver_costo` no recibe ningún dato de costo en el HTML ni en respuestas HTMX.
4. Un vehículo con 20 fotos queda con todas sus variantes generadas sin bloquear la interfaz.
5. Una cuenta de ML vinculada se mantiene operativa más de 7 días sin intervención manual.
6. Marcar un vehículo como `reservado` pausa su publicación en ML; volver a `disponible` la reactiva; `vendido` la cierra.
7. Los tests de sanitización y de arquitectura de la sección 5.4 pasan.
8. Una landing externa lista el stock filtrado por sucursal y rango de precio con una API Key, y la clave revocada deja de funcionar en menos de 60 s.

---

## 8. Puntos a validar contra la documentación oficial de Mercado Libre

No confirmados al momento de escribir este documento. Cada uno DEBE resolverse y documentarse antes de implementar la parte afectada.

1. IDs exactos y valores permitidos de los atributos obligatorios de la categoría hoja de autos y camionetas en MLA (sección 4.3).
2. Estructura exacta del payload de `POST /items` para vehículos, en especial `location` y `seller_contact` (sección 4.5).
3. Reglas del campo `title` en vehículos (si es libre o lo genera ML a partir de los atributos).
4. Valor de `max_pictures_per_item` para la categoría de autos.
5. Tipos de publicación (`listing_type_id`) disponibles para concesionarias en Argentina y endpoint para consultar el cupo del paquete contratado.
6. Qué atributos se pueden modificar por `PUT` una vez publicada la unidad y cuáles exigen republicar.
7. Mecanismo de republicación de un ítem `closed` en vehículos.
8. Límites de requests por aplicación y por usuario.
9. Mecanismo de verificación de autenticidad de las notificaciones (IPs de origen o firma).
10. Soporte y obligatoriedad de PKCE en el flujo de autorización.
11. Requisitos de alta y aprobación de la aplicación en el DevCenter de ML.

## 9. Referencias

- Autenticación y autorización: https://developers.mercadolibre.com.ar/autenticacion-y-autorizacion
- OAuth y gestión de tokens: https://developers.mercadolibre.com.ar/gestion-de-identidades-y-accesos-oauth-y-tokens
- Categorías y atributos: https://developers.mercadolibre.com.ar/categorias-y-atributos
- Publica vehículos: https://developers.mercadolibre.com.ar/publica-vehiculos
- Sincroniza publicaciones de vehículos: https://developers.mercadolibre.com.ar/vehiculos-sincroniza-publicaciones
- Paquetes de vehículos: https://developers.mercadolibre.com.ar/vehiculos-gestiona-paquetes
- Trabajar con imágenes: https://developers.mercadolibre.com.ar/trabajar-con-imagenes
- Diagnóstico de imágenes: https://developers.mercadolibre.com.ar/diagnostico-imagenes
- Moderaciones con pausado: https://developers.mercadolibre.com.ar/moderaciones-con-pausado
