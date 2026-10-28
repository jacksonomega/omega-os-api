# PROMPT DE ESPECIFICACIÓN TÉCNICA — BACKEND OMEGA OS (FastAPI + PostgreSQL + n8n)

Actúa como un **Arquitecto Backend Principal y Especialista en Python 3.12+, FastAPI, SQLAlchemy 2.0 (Async), Pydantic v2 y PostgreSQL**.

Tu misión es programar de principio a fin la API REST de producción para **Omega OS** (`https://api.omega-studio.tech/v1`), el sistema operativo interno de **Omega Studio** (`https://omega-studio.tech`) y su SaaS vertical **Omega Libera** (`https://omega-studio.tech/libera`).

El frontend ya está construido en **Angular 18** (`https://os.omega-studio.tech`) con una capa de caché en cliente (`SHORT_TTL_FINANCE` de 45s para finanzas y `AGGRESSIVE_MANUAL` de 24h con invalidación por mutación para el resto). **Debes respetar al 100 % las rutas, nombres de campos en `camelCase`, tipos de datos y contratos JSON que se especifican a continuación.**

---

## 1. CONTEXTO DEL NEGOCIO Y SOCIOS
- **Empresa:** Omega Studio (desarrollo de software a medida, IA y automatización) y Omega Libera (SaaS vertical por suscripción).
- **Socios únicos autorizados (`PartnerId`):**
  1. `id: "jackson"` — **Jackson Almeida** (`initials: "JA"`)
  2. `id: "yassin"` — **Yassin Khamlichi** (`initials: "YK"`)
- **Filosofía de datos:** Cero datos falsos o inventados (`mock data`). La base de datos arranca limpia salvo los 2 usuarios socios y el catálogo inicial de accesos directos (`DEFAULT_SHORTCUTS`).
- **Herramienta de automatización:** Usamos exclusivamente **n8n** (`https://n8n.omega-studio.tech/`). **NO usamos Apify ni Cloudflare.**

---

## 2. STACK TECNOLÓGICO Y ARQUITECTURA REQUERIDA
- **Framework:** FastAPI (Python 3.12+) con tipado estricto (`mypy` / `pyright`).
- **Base de datos:** PostgreSQL 16 + SQLAlchemy 2.0 (`AsyncSession` con `asyncpg`) + migraciones con **Alembic**.
- **Serialización JSON (`camelCase` obligatorio):**
  - El frontend Angular envía y recibe todos los campos en `camelCase` (`businessName`, `monthlyQuotaEur`, `dueDate`, `linkedEntity`, etc.).
  - En SQLAlchemy usa `snake_case` para las columnas de PostgreSQL, pero configura una clase base en **Pydantic v2** con `alias_generator=to_camel` y `populate_by_name=True`, asegurando que todas las respuestas se serialicen con `by_alias=True`.
- **Prefijo global de la API:** `/v1` (URL base: `https://api.omega-studio.tech/v1`).
- **CORS:** Permitir orígenes `https://os.omega-studio.tech`, `https://omega-studio.tech` y `http://localhost:4200`. Permitir cabeceras `Authorization`, `Content-Type`, `X-Omega-Client` y `X-Omega-Api-Key`.

---

## 3. AUTENTICACIÓN Y SEGURIDAD (DOBLE VÍA)
La API es consumida por dos actores: **el panel Angular (los 2 socios)** y **n8n (automatizaciones)**.

1. **Autenticación de Socios (JWT Bearer):**
   - `POST /v1/auth/login`
     - **Body:** `{ "memberId": "jackson" | "yassin", "password": "string" }`
     - **Respuesta `200 OK`:**
       ```json
       {
         "accessToken": "eyJ...",
         "tokenType": "bearer",
         "expiresIn": 28800,
         "member": {
           "id": "jackson",
           "name": "Jackson Almeida",
           "initials": "JA"
         }
       }
       ```
   - `GET /v1/auth/me` → Devuelve el `PartnerProfile` del token actual.
   - Valida las contraseñas con `bcrypt`/`argon2` (o el hash SHA-256 con salt `omega-os-v1` para compatibilidad directa con el cliente).

2. **Autenticación Máquina a Máquina para n8n (`X-Omega-Api-Key`):**
   - Crea una dependencia `get_current_actor` que acepte **cualquiera de los dos métodos**:
     - Un `Authorization: Bearer <jwt>` válido de Jackson o Yassin.
     - O la cabecera `X-Omega-Api-Key: <N8N_SECRET_API_KEY>` definida en `.env` (en cuyo caso el actor se identifica como `"n8n"`).

---

## 4. MODELOS DE DOMINIO Y CONTRATOS JSON EXACTOS (Pydantic v2)

Respeta exactamente estos tipos y literales:

### 4.1. Tipos Literales (Enums)
- `PartnerId`: `"jackson" | "yassin"`
- `ShortcutGroup`: `"Infraestructura y Código" | "Automatización e IA" | "Webs y Entornos"`
- `InterestLevel`: `"Alto" | "Medio" | "Bajo"`
- `LeadStage`: `"Captado (n8n)" | "Cualificado" | "Contactado" | "Demo" | "Negociación"`
- `LeadOrigin`: `"n8n" | "Entrevista" | "Manual"`
- `ContactType`: `"Cliente" | "Lead" | "Proveedor" | "Colaborador" | "Otro"`
- `ProjectDivision`: `"Omega Studio" | "Omega Libera"`
- `TaskColumn`: `"Pendiente" | "En curso" | "Hecho"`
- `TaskPriority`: `"Urgente" | "Alta" | "Media" | "Baja"`
- `NoteType`: `"Acta" | "Guion" | "Arquitectura / SOP" | "Prompt" | "Producto" | "Otro"`
- `OkrKind`: `"breakeven" | "clients" | "custom"`
- `RevenueKind`: `"MRR" | "UNICO"`
- `ExpenseKind`: `"FIJO" | "VARIABLE"`
- `PromptCategory`: `"Agentes IA" | "Automatización (n8n)" | "Ventas y Discovery" | "Desarrollo"`

### 4.2. Esquemas de Entidades (JSON `camelCase`)

```typescript
// 1. Launchpad
interface QuickShortcut {
  id: string;        // ej. "sc-n8n"
  title: string;     // ej. "n8n"
  group: ShortcutGroup;
  url: string;
}

interface ActivityEvent {
  id: string;        // ej. "act-..."
  at: string;        // ISO 8601 UTC
  actor: string;     // "Jackson Almeida" | "Yassin Khamlichi" | "n8n"
  module: string;    // "CRM" | "Contactos" | "Proyectos" | "Tareas" | "Contabilidad"
  text: string;
}

// 2. CRM y Entrevistas
interface FieldInterview {
  id: string;            // "int-..."
  businessName: string;
  contactPerson: string;
  employees: number;     // >= 1
  currentApp: string;
  painPoint: string;
  interest: InterestLevel;
  createdBy: PartnerId;
  createdAt: string;     // ISO 8601
  inPipeline: boolean;
}

interface CrmLead {
  id: string;            // "lead-..."
  company: string;
  contact: string;
  employees: number;     // >= 1
  stage: LeadStage;      // por defecto "Captado (n8n)"
  origin: LeadOrigin;    // "n8n" | "Entrevista" | "Manual"
  createdAt: string;     // ISO 8601
}

interface ClosedClient {
  id: string;              // "cli-..."
  companyName: string;
  cif: string;             // Uppercase
  employees: number;       // >= 1
  monthlyQuotaEur: number; // SIEMPRE calculado: 25 + (15 * employees)
  setupFeeEur: number;     // >= 0
  signedAt: string;        // ISO 8601
}

// 3. Agenda de Contactos
interface Contact {
  id: string;          // "ct-..."
  name: string;
  company: string;
  role: string;
  phone: string;
  email: string;
  type: ContactType;
  notes: string;
  lastContact: string; // "YYYY-MM-DD" o ""
  createdAt: string;   // ISO 8601
}

// 4. Proyectos y Entregas
interface ChecklistItem {
  id: string;     // "chk-..."
  label: string;
  done: boolean;
}

interface OmegaProject {
  id: string;               // "prj-..."
  name: string;
  client: string;
  division: ProjectDivision;
  repoUrl: string;
  prodUrl: string;
  checklist: ChecklistItem[];
  createdAt: string;        // ISO 8601
}

// 5. Tareas Operativas
interface PartnerTask {
  id: string;             // "tsk-..."
  title: string;
  column: TaskColumn;     // "Pendiente" | "En curso" | "Hecho"
  priority: TaskPriority; // "Urgente" | "Alta" | "Media" | "Baja"
  assignee: PartnerId;    // "jackson" | "yassin"
  tags: string[];
  dueDate: string;        // "YYYY-MM-DD" o ""
  createdAt: string;      // ISO 8601
}

// 6. Notas y Wiki (Estilo Notion)
interface WikiNote {
  id: string;            // "note-..."
  title: string;
  type: NoteType;
  icon: string;          // Nombre de icono SVG: "file"|"clipboard"|"target"|"cpu"|"sparkles"|"lightbulb"|"rocket"|"bookmark"
  pinned: boolean;
  tags: string[];
  linkedEntity: string;  // Nombre de proyecto o cliente vinculado (o "")
  markdown: string;
  lastAuthor: PartnerId;
  updatedAt: string;     // ISO 8601
}

// 7. Progresos y Logros
interface Okr {
  id: string;            // "okr-..."
  title: string;
  kind: OkrKind;         // "breakeven" | "clients" | "custom"
  target: number;
  manualCurrent: number;
  unit: string;          // "€" | "clientes" | custom
  deadline: string;      // "YYYY-MM-DD" o ""
}

interface Milestone {
  id: string;     // "ms-..."
  title: string;
  date: string;   // ISO 8601
}

// 8. Contabilidad y Gastos
interface RevenueRecord {
  id: string;                // "rev-..."
  concept: string;
  client: string;
  kind: RevenueKind;         // "MRR" | "UNICO"
  division: ProjectDivision; // "Omega Studio" | "Omega Libera"
  amountEur: number;
  date: string;              // ISO 8601
  clientId?: string | null;  // FK opcional a ClosedClient.id
}

interface ExpenseRecord {
  id: string;          // "exp-..."
  concept: string;
  provider: string;
  kind: ExpenseKind;   // "FIJO" | "VARIABLE"
  amountEur: number;
  date: string;        // ISO 8601
}

interface Ledger {
  revenues: RevenueRecord[];
  expenses: ExpenseRecord[];
  openingCashEur: number;
}

// 9. Cerebro Omega (RAG + Prompt Vault)
interface PromptVersion {
  tag: string;       // "v1", "v2"...
  changelog: string;
  template: string;
  createdAt: string; // ISO 8601
  author: PartnerId;
}

interface PromptEntry {
  id: string;               // "prm-..."
  title: string;
  category: PromptCategory;
  currentVersion: string;   // ej. "v1"
  template: string;
  versions: PromptVersion[];
}

interface ChatMessage {
  id: string;
  sender: "partner" | "brain";
  text: string;
  createdAt: string;
  sources?: string[];
}
```

---

## 5. CATÁLOGO COMPLETO DE ENDPOINTS Y COMPORTAMIENTO

**IMPORTANTE SOBRE MUTACIONES EN EL FRONTEND ACTUAL:**
El servicio `FastApiGatewayService.mutate()` de Angular actualiza su estado local con la respuesta de las mutaciones, o bien espera que los endpoints de lista devuelvan la colección actualizada (ordenada por fecha descendente salvo donde se indique). Para máxima compatibilidad:
- Todos los `GET` de colección devuelven el `array` JSON directamente (`[...]`), salvo `/v1/accounting/ledger` que devuelve el objeto `Ledger`.
- En las mutaciones (`POST`, `PUT`, `PATCH`, `DELETE`), soporta devolver la lista actualizada (o la entidad si se pasa el query param `?return_entity=true` para cuando la llame **n8n**).

### Módulo 1 — Launchpad
1. `GET /v1/launchpad/shortcuts` → Devuelve `QuickShortcut[]`.
   - **Seed inicial obligatorio si la tabla está vacía:**
     - `sc-github`: GitHub (`https://github.com`, grupo `"Infraestructura y Código"`)
     - `sc-vercel`: Vercel (`https://vercel.com/dashboard`, grupo `"Infraestructura y Código"`)
     - `sc-vps`: VPS (`""`, grupo `"Infraestructura y Código"`)
     - `sc-n8n`: n8n (`https://n8n.omega-studio.tech/`, grupo `"Automatización e IA"`)
     - `sc-openai`: OpenAI (`https://platform.openai.com`, grupo `"Automatización e IA"`)
     - `sc-chatwoot`: Chatwoot (`""`, grupo `"Automatización e IA"`)
     - `sc-twilio`: Twilio (`https://console.twilio.com`, grupo `"Automatización e IA"`)
     - `sc-studio`: Omega Studio (`https://omega-studio.tech`, grupo `"Webs y Entornos"`)
     - `sc-libera`: Omega Libera (`https://omega-studio.tech/libera`, grupo `"Webs y Entornos"`)
2. `PATCH /v1/launchpad/shortcuts`
   - **Body:** `{ "id": "string", "url": "string" }` → Actualiza la URL del acceso directo y devuelve `QuickShortcut[]`.
3. `GET /v1/launchpad/activity` → Devuelve los últimos 20 `ActivityEvent[]` ordenados por `at DESC`.
4. `POST /v1/launchpad/activity` → Inserta un `ActivityEvent` y devuelve los últimos 20 `ActivityEvent[]`.

### Módulo 2 — CRM y Entrevistas
1. `GET /v1/crm/interviews` → Devuelve `FieldInterview[]` (`createdAt DESC`).
2. `POST /v1/crm/interviews` → Crea entrevista, registra evento en `ActivityEvent` (`"Entrevista registrada: {businessName}"`) y devuelve `FieldInterview[]`.
3. `PATCH /v1/crm/interviews/{id}` → Body `{ "inPipeline": true }`. Actualiza la entrevista y devuelve `FieldInterview[]`.
4. `DELETE /v1/crm/interviews/{id}` → Elimina entrevista y devuelve `FieldInterview[]`.
5. `GET /v1/crm/leads` → Devuelve `CrmLead[]` (`createdAt DESC`).
6. `POST /v1/crm/leads` → Crea un `CrmLead` (si no viene `stage`, por defecto `"Captado (n8n)"`). Devuelve `CrmLead[]`.
7. `PATCH /v1/crm/leads/{id}` → Body `{ "stage": LeadStage }`. Actualiza etapa y devuelve `CrmLead[]`.
8. `DELETE /v1/crm/leads/{id}` → Elimina lead y devuelve `CrmLead[]`.
9. `GET /v1/crm/clients` → Devuelve `ClosedClient[]` (`signedAt DESC`).
10. `POST /v1/crm/clients`
    - **Regla de negocio crítica:**
      - Recalcula siempre en servidor `monthlyQuotaEur = 25 + (15 * max(1, employees))`.
      - Si no existen ya en `RevenueRecord` para ese `clientId`, crea automáticamente:
        1. Un `RevenueRecord` con `kind: "MRR"`, `division: "Omega Libera"`, `concept: "Suscripción Omega Libera ({employees} empleados)"`, `amountEur: monthlyQuotaEur`, `clientId: client.id`.
        2. Si `setupFeeEur > 0`, un `RevenueRecord` con `kind: "UNICO"`, `division: "Omega Libera"`, `concept: "Setup inicial"`, `amountEur: setupFeeEur`, `clientId: client.id`.
      - Dispara en background el webhook a **n8n** `client.closed` (ver Sección 6).
      - Devuelve `ClosedClient[]`.
11. `DELETE /v1/crm/clients/{id}`
    - Elimina el cliente y **elimina en cascada** todos los `RevenueRecord` cuyo `clientId == id`. Devuelve `ClosedClient[]`.

### Módulo 3 — Agenda de Contactos
1. `GET /v1/contacts` → Devuelve `Contact[]`.
2. `POST /v1/contacts` → Crea contacto (o hace upsert por `email`/`phone` si viene de n8n para evitar duplicados) y devuelve `Contact[]`.
3. `PUT /v1/contacts/{id}` → Actualiza un contacto completo y devuelve `Contact[]`.
4. `PATCH /v1/contacts/{id}` → Body `{ "lastContact": "YYYY-MM-DD" }`. Actualiza la fecha de último contacto y devuelve `Contact[]`.
5. `DELETE /v1/contacts/{id}` → Elimina contacto y devuelve `Contact[]`.

### Módulo 4 — Proyectos y Entregas
1. `GET /v1/projects` → Devuelve `OmegaProject[]` con sus `checklist` anidados.
2. `POST /v1/projects`
   - Si el payload no incluye `checklist` o viene vacío, inicializa por defecto estos 6 ítems:
     1. `"Variables de entorno configuradas"`
     2. `"Dominio y SSL"`
     3. `"Pruebas en staging"`
     4. `"Backups activos"`
     5. `"Monitorización y alertas"`
     6. `"Entrega y cobro"`
   - Devuelve `OmegaProject[]`.
3. `DELETE /v1/projects/{id}` → Elimina el proyecto y su checklist. Devuelve `OmegaProject[]`.
4. `PATCH /v1/projects/{project_id}/checklist/{item_id}` → Invierte (`!done`) el estado del ítem de checklist y devuelve `OmegaProject[]`.
5. `POST /v1/projects/{project_id}/checklist` → Body `{ "label": "string" }`. Añade un ítem (`done: false`) al checklist del proyecto y devuelve `OmegaProject[]`.

### Módulo 5 — Tareas Operativas
1. `GET /v1/tasks` → Devuelve `PartnerTask[]`. Soporta filtros opcionales por query params para n8n: `?assignee=jackson&priority=Urgente&due_before=YYYY-MM-DD&pending_only=true`.
2. `POST /v1/tasks` → Crea tarea y devuelve `PartnerTask[]`.
3. `PATCH /v1/tasks/{id}` → Body parcial con `{ "column"?: TaskColumn, "priority"?: TaskPriority, "dueDate"?: string }`.
   - Si `column` pasa a `"Hecho"`, registra evento en `ActivityEvent` (`"Tarea completada: {title}"`).
   - Devuelve `PartnerTask[]`.
4. `DELETE /v1/tasks/{id}` → Elimina tarea y devuelve `PartnerTask[]`.

### Módulo 6 — Notas y Wiki
1. `GET /v1/wiki/notes` → Devuelve `WikiNote[]` (ordenadas por `pinned DESC, updatedAt DESC`).
2. `POST /v1/wiki/notes` → Crea una nota nueva y devuelve `WikiNote[]`.
3. `PUT /v1/wiki/notes` → Actualiza una nota existente (por `id` en el body) y devuelve `WikiNote[]`.
4. `PATCH /v1/wiki/notes/{id}` → Alterna `pinned = !pinned` (o aplica los campos enviados en el body) y devuelve `WikiNote[]`.
5. `DELETE /v1/wiki/notes/{id}` → Elimina nota y devuelve `WikiNote[]`.

### Módulo 7 — Progresos y Logros
1. `GET /v1/progress/okrs` → Devuelve `Okr[]`.
2. `POST /v1/progress/okrs` → Crea un `Okr` y devuelve `Okr[]`.
3. `PATCH /v1/progress/okrs/{id}` → Body `{ "value": number }`. Actualiza `manualCurrent = value` y devuelve `Okr[]`.
4. `DELETE /v1/progress/okrs/{id}` → Elimina OKR y devuelve `Okr[]`.
5. `GET /v1/progress/milestones` → Devuelve `Milestone[]` (`date DESC`).
6. `POST /v1/progress/milestones` → Crea hito y devuelve `Milestone[]`.
7. `DELETE /v1/progress/milestones/{id}` → Elimina hito y devuelve `Milestone[]`.

### Módulo 8 — Contabilidad y Gastos (Caché de corta duración 45s)
1. `GET /v1/accounting/ledger` → Devuelve el objeto `Ledger`:
   ```json
   {
     "revenues": [...],
     "expenses": [...],
     "openingCashEur": 0
   }
   ```
2. `PUT /v1/accounting/ledger`
   - Recibe el objeto `Ledger` completo y sincroniza `openingCashEur`, `revenues` y `expenses` de forma transaccional.
   - **Además, habilita estos endpoints granulares para que n8n pueda inyectar gastos/ingresos sin enviar todo el libro mayor:**
     - `POST /v1/accounting/revenues` → Añade un `RevenueRecord` y devuelve `Ledger`.
     - `DELETE /v1/accounting/revenues/{id}` → Elimina un `RevenueRecord` y devuelve `Ledger`.
     - `POST /v1/accounting/expenses` → Añade un `ExpenseRecord`, evalúa la regla del margen bruto (ver abajo) y devuelve `Ledger`.
     - `DELETE /v1/accounting/expenses/{id}` → Elimina un `ExpenseRecord` y devuelve `Ledger`.
   - **Regla de negocio del Guardián de Margen Bruto (80 %):**
     - Fórmula: `grossMarginPercent = ((totalRevenue - variableExpenses) / totalRevenue) * 100`.
     - Si `totalRevenue > 0` y `grossMarginPercent < 80`, dispara un webhook asíncrono a **n8n** (`margin.alert`) con las métricas actuales.

### Módulo 9 — Cerebro Omega (IA Interna + Prompt Vault)
1. `POST /v1/brain/rag/query`
   - **Body:** `{ "query": "string" }`
   - **Lógica:**
     - Consulta en tiempo real PostgreSQL: métricas del `Ledger` (MRR, ingresos únicos, gastos fijos/variables, caja, margen bruto), `ClosedClient[]`, `PartnerTask[]` abiertas (con su prioridad y fecha de entrega), `OmegaProject[]` y `WikiNote[]` relevantes (búsqueda full-text o ILIKE).
     - Si hay configurada `OPENAI_API_KEY` en `.env`, pasa ese contexto real estructurado al modelo (`gpt-4o-mini` / `gpt-4o`) con la instrucción estricta de responder únicamente con datos reales de Omega OS y devolver las tablas consultadas en `sources`.
     - Si no hay `OPENAI_API_KEY`, ejecuta el motor determinista de respuesta sobre SQL devolviendo los datos exactos de finanzas, tareas o clientes.
   - **Respuesta `200 OK` (`ChatMessage`):**
     ```json
     {
       "id": "m-...",
       "sender": "brain",
       "text": "MRR: 175 €...",
       "createdAt": "2026-10-28T18:00:00Z",
       "sources": ["accounting_ledger", "crm_closed_clients"]
     }
     ```
2. `GET /v1/brain/prompts` → Devuelve `PromptEntry[]` con su historial `versions` anidado (`createdAt DESC`).
3. `POST /v1/brain/prompts` → Crea un `PromptEntry` con su versión inicial `v1` y devuelve `PromptEntry[]`.
4. `POST /v1/brain/prompts/{id}/versions`
   - **Body:** `{ "changelog": "string", "template"?: "string" }`
   - Crea una nueva `PromptVersion` (`v{N+1}`), actualiza `currentVersion` y `template` en el `PromptEntry` padre, y devuelve `PromptEntry[]`.
5. `DELETE /v1/brain/prompts/{id}` → Elimina el prompt y sus versiones, y devuelve `PromptEntry[]`.

---

## 6. INTEGRACIÓN BIDIRECCIONAL CON n8n (`https://n8n.omega-studio.tech/`)

### 6.1. Endpoints de entrada para n8n (autenticados con `X-Omega-Api-Key`)
Además de poder usar cualquiera de los endpoints anteriores, crea un router específico `/v1/integrations/n8n`:
1. `POST /v1/integrations/n8n/lead-intake`
   - Recibe un lead captado por n8n (desde formularios de `omega-studio.tech`, `omega-studio.tech/libera`, WhatsApp/Chatwoot o scraping propio):
     ```json
     {
       "company": "Clínica Dental Sol",
       "contact": "Marta Gómez",
       "phone": "+34600112233",
       "email": "marta@clinicasol.es",
       "employees": 6,
       "notes": "Interesada en Omega Libera desde la landing"
     }
     ```
   - **Acción atómica en FastAPI:**
     1. Crea el `CrmLead` en etapa `"Captado (n8n)"` y origen `"n8n"`.
     2. Crea o actualiza el `Contact` en la Agenda de Contactos con `type: "Lead"` y `lastContact` a la fecha de hoy.
     3. Registra en `ActivityEvent`: `"Lead captado por n8n: {company}"`.
2. `POST /v1/integrations/n8n/variable-expense`
   - Permite a un flujo Cron de n8n registrar consumos diarios/mensuales de OpenAI o Twilio en `ExpenseRecord` (`kind: "VARIABLE"`), recalculando el margen bruto.
3. `GET /v1/integrations/n8n/daily-digest`
   - Devuelve en una sola llamada JSON el resumen matutino para que n8n lo envíe por WhatsApp/Telegram a Jackson y Yassin:
     - Tareas `Urgente` o `Alta` pendientes.
     - Tareas vencidas (`dueDate < hoy`) o que vencen hoy (`dueDate == hoy`).
     - MRR actual, caja y porcentaje de margen bruto.
     - Contactos o leads en fase `"Demo"` o `"Negociación"`.

### 6.2. Webhooks salientes desde FastAPI hacia n8n (`BackgroundTasks` + `httpx.AsyncClient`)
Crea un servicio `N8nWebhookDispatcher` que envíe peticiones `POST` firmadas con cabecera `X-Omega-Webhook-Secret` a las URLs configuradas en `.env` (con timeout de 5s y sin bloquear la respuesta HTTP al cliente):
- `N8N_WEBHOOK_CLIENT_CLOSED`: Se dispara al crear un `ClosedClient`. Payload: datos del cliente, cuota calculada (`25 + 15 * empleados`) y socio que lo cerró.
- `N8N_WEBHOOK_MARGIN_ALERT`: Se dispara cuando el margen bruto baja del `80%`. Payload: `mrr`, `oneOff`, `variableExpenses`, `grossMarginPercent`.
- `N8N_WEBHOOK_URGENT_TASK`: Se dispara cuando se crea una `PartnerTask` con `priority == "Urgente"`. Payload: datos de la tarea y socio asignado (`jackson` o `yassin`).

---

## 7. ESTRUCTURA DEL PROYECTO Y ENTREGABLES REQUERIDOS
Organiza el código limpio y modular con la siguiente estructura:
```text
omega-os-api/
├── alembic/
├── alembic.ini
├── app/
│   ├── main.py                # Inicialización FastAPI, CORS, routers, healthcheck
│   ├── core/
│   │   ├── config.py          # Pydantic Settings (.env)
│   │   ├── database.py        # AsyncEngine y get_db
│   │   └── security.py        # JWT + X-Omega-Api-Key (doble vía)
│   ├── models/                # Modelos SQLAlchemy 2.0 (DeclarativeBase)
│   ├── schemas/               # Esquemas Pydantic v2 (camelCase alias_generator)
│   ├── services/
│   │   ├── finance.py         # Cálculo de cuota (25+15*emp), Ledger y Margen >80%
│   │   ├── rag_brain.py       # Contexto SQL real + OpenAI opcional
│   │   └── n8n_webhooks.py    # Despachador asíncrono hacia n8n.omega-studio.tech
│   └── api/
│       └── v1/
│           ├── auth.py
│           ├── launchpad.py
│           ├── crm.py
│           ├── contacts.py
│           ├── projects.py
│           ├── tasks.py
│           ├── wiki.py
│           ├── progress.py
│           ├── accounting.py
│           ├── brain.py
│           └── n8n_integrations.py
├── Dockerfile
├── docker-compose.yml         # API + PostgreSQL 16
├── requirements.txt
└── .env.example
```

**Requisitos de entrega del código:**
1. Entrega el código completo y funcional de todos los archivos, sin placeholders ni `TODO`.
2. Incluye el script de inicialización (`seed`) que se ejecuta en el `lifespan` de FastAPI para crear únicamente a los dos socios (`jackson` y `yassin`) y los 9 accesos directos oficiales (`DEFAULT_SHORTCUTS`) si la base de datos está vacía.
3. Incluye `docker-compose.yml` y `.env.example` listos para levantar en el VPS detrás de `https://api.omega-studio.tech`.
