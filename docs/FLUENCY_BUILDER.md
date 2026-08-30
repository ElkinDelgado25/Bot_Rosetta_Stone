# Fluency Builder

Segundo producto de Rosetta Stone, distinto de Foundations. Este documento
describe su mecánica de red tal como se observó capturando el tráfico real de
`learn.rosettastone.com` (un HAR de una corrida completa: login → catálogo →
lección → completar una actividad de 22 pasos). Complementa `CLAUDE.md`, que
describe Foundations.

> El bot **no resuelve** las actividades. Lee el árbol de contenido que la propia
> plataforma entrega —el cual **incluye las respuestas correctas**— y fabrica los
> mensajes de progreso. Misma filosofía que Foundations: la fuente de verdad es
> la respuesta de la API, no nada visible en pantalla.

## En qué se diferencia de Foundations

| | Foundations | Fluency Builder |
|---|---|---|
| Frontend | `totale` / launchpad | `learn.rosettastone.com` |
| Backend | `graph.` (lectura) + `tracking.` (escritura) | `gaia-server.rosettastone.com` (todo) |
| Jerarquía | unidad → lección → path | curso → sequence (lección) → activity → step |
| IDs | strings de curso tipo `SK-ENG-L1-...`, índices numéricos | UUID / hex |
| Escritura | REST + XML, `_method=put` tunelizado | mutation GraphQL `AddProgress` |
| Auth escritura | header `x-rosettastone-session-token` | (ver nota de auth) |
| Truco de índices | `unit_index % 4` | ninguno; todo por ID |

No hay dos APIs de épocas distintas como en Foundations. Aquí lectura y
escritura van al **mismo** endpoint GraphQL (`gaia-server`).

## Endpoint único

```
POST https://gaia-server.rosettastone.com/graphql
```

Todas las operaciones (lectura y escritura) son POST a esta URL con
`content-type: application/json` y `origin: https://learn.rosettastone.com`.

### Nota de auth (pendiente de confirmar)

El HAR se exportó en modo "sanitized", que **elimina los headers `authorization`
y `cookie`**. Por eso no está confirmado si `gaia-server` autentica por header
Bearer o por cookie de sesión. No es bloqueante: igual que Foundations cosecha
sus tokens del tráfico en vivo (`page.on("request")`), aquí la auth se captura en
la fase de navegador y se reenvía —o se hereda del contexto del navegador, que
arrastra las cookies solo. Se resolverá empíricamente en la fase de escritura.

## Lectura

### 1. Catálogo + progreso — `getCoursesAndProgress`

Trae los cursos asignados y el porcentaje completado por lección, en una sola
llamada con dos campos raíz:

```graphql
query getCoursesAndProgress($locale: String) {
  assignedCourses { ...CoursesDetails }   # catálogo
  progress {                              # progreso, keyed por courseId
    id
    courseId
    countOfSequencesInCourse
    sequences { id percentComplete }
  }
}
```

`assignedCourses[]` (campos que usamos):

| Campo | Ejemplo | Uso |
|---|---|---|
| `courseId` | `bba24d6b05441b6e4675959c8276a286` (hex) | clave del curso |
| `productId` | `product.6a1a08c9-...` | identifica el producto |
| `title(locale:)` | `"Window-Shopping (All Skills)"` | ya viene resuelto a string |
| `cefr` | `"B1"` | nivel |
| `topics[].localizations[]` | `"Aviación"` / `"Aviation"` | tema, localizado por locale |
| `sequences[]` | `{ id, title(locale:) }` | lecciones del curso |

**El progreso está en un campo aparte**, no en `assignedCourses`. Se une por id
de sequence: `assignedCourses[].sequences[].id` ↔ `progress[].sequences[].id`,
tomando `percentComplete`. Un curso sin entrada en `progress` está al 0%.

**`percentComplete` es una fracción `[0.0, 1.0]`, no un porcentaje 0–100.** `1.0`
es lección completa; `0.9375` = 15/16. Se guarda como `float` en el dominio.

En la captura: 19 cursos asignados, 15 con progreso.

### 2. Detalle de una lección — `getSequence`

Devuelve el árbol completo de **una** lección: sus actividades, los pasos de cada
una, y **las respuestas correctas**.

```graphql
query getSequence($courseId: String!, $sequenceId: String, $locale: String) {
  sequence(courseId: $courseId, sequenceId: $sequenceId, locale: $locale) {
    sequenceId
    title(locale:)
    version
    activities          # scalar JSON con el árbol de actividades
  }
}
```

`activities` es un escalar JSON (una lista). Cada actividad:

```jsonc
{
  "activityId": "f9d66c8b-...",
  "activityType": "DialogueExpressionWithReco",  // ver tabla abajo
  "ordering": "tree",
  "interaction": "practice",
  "skills": { ... },
  "steps": [
    {
      "activityStepId": "49d13422-...",
      "type": "multipleChoice",
      "content": [ ... ],           // enunciado + opciones (con media_uri)
      "correct": [ "ecded79a-...", "d482215b-...", "79ecc4b0-..." ],
      "behavior": { ... },
      "instructions": { ... }
    }
  ]
}
```

**`step.correct` es la clave de todo**: lista los IDs de las opciones correctas.
El `answer` que el cliente envía en `AddProgress` es exactamente uno de esos IDs.
Así, para fabricar una respuesta correcta basta con leer `step.correct` — no hay
que "resolver" nada.

Tipos de actividad observados (una sola lección ya trae variedad):

| `activityType` | `type` de step | #steps |
|---|---|---|
| `DialogueExpressionWithReco` | `multipleChoice` | 15 |
| `KeyVocabulary` | `card` | 1 |
| `FillInTheBlanks` | `cloze` | 1 |
| `WordAssociation` | `matching` | 1 |
| `KeyGrammarExplanations` | `card` | 1 |
| `RightWordWithReco` | `cloze` | 1 |

Los `card` (vocabulario/gramática) son de solo lectura: no tienen respuesta que
evaluar. El parser tolera `correct` ausente devolviendo lista vacía.

## Escritura — `AddProgress` (implementada)

> Estado real de las respuestas: la captura era de un humano respondiendo, así que
> muchas respuestas venían incorrectas (score 0, 0.4…) o como texto libre. La
> fabricación de respuesta **correcta** es limpia para `multipleChoice`, `cloze` y
> `card` de gramática; **deducible** para `matching` (pares `left:right` del
> contenido); e **incierta** para `writing` (texto libre) y `card` de vocabulario.
> Ver `FluencyProgressBuilder`.

**Confirmado en corrida real (2026-08-12).** La lección *Preflight* del curso
"Speak with Pilots and Airline Mechanics (B1)" pasó de **0% a 100%**, con las 19
actividades al 100% (`0/19 activities still < 100%`) y `bestGrade=1`. La
completación depende del **envío** con respuestas bien formadas, no de un acierto
verificado del lado del servidor.

Los tipos que aparecieron en ese log fueron `generic`, `sequencing` y
`cloze-dropdowns`. `writing` y `matching` no se vieron en esa lección, así que
siguen sin comprobarse de forma explícita.

Implementación: `FluencyProgressBuilder` (arma los mensajes por tipo de step),
`FluencyApiPort.add_progress` / adaptador (mutación), y
`CompleteFluencyOrchestrator` (itera lecciones pendientes, envía, persiste estado
por actividad y **re-lee el catálogo para verificar** que el porcentaje se movió).

Knobs de seguridad (variables de entorno):

- `FLUENCY_MAX_LESSONS` — cuántas lecciones pendientes completar por corrida
  (default `1` para una primera prueba controlada; `0`/`all` = sin límite).
- `FLUENCY_DRY_RUN` — `1`/`true` para construir y loguear los mensajes **sin
  enviarlos**.
- `FLUENCY_TOTAL_COURSE_HOURS` — presupuesto total de horas de estudio
  fabricadas (default `70`, un nivel completo de Rosetta Stone), repartido con
  jitter entre las lecciones de la corrida y, dentro de cada una, entre sus
  steps. Reemplaza el `durationMs` fijo de 5000ms por algo que se parece a
  Foundations, cuyo `PathCalculator` deriva la duración de un `time_estimate`
  real por path. Fluency no trae ese dato en su árbol de contenido, así que
  `FluencyDurationCalculator` fabrica el presupuesto en vez de leerlo.

> **Ojo con el default de 1.** Desde la terminal es deliberado, pero desde la UI
> web se lee como un fallo: completa una lección y termina con éxito dejando el
> resto pendientes. Por eso el perfil web tiene `fluency_max_lessons` (None =
> todas) y los backends exportan `FLUENCY_MAX_LESSONS=all` antes de lanzar. El
> default del motor no se cambió.

### Estado: un archivo por cuenta

Las claves de actividad son `fluency|curso|secuencia|actividad`, **sin la cuenta
dentro**. Con un `fluency_state.json` único y compartido, el segundo usuario
veía como hechas las actividades del primero y las saltaba, terminando con
código 0 sin enviar nada. El estado vive ahora en `fluency_<user_id>.json`,
resuelto en `execute()` porque el `user_id` no se conoce hasta que la corrida lo
captura.

### Formato del mensaje

Cada paso completado dispara una mutación. En la captura, completar la actividad
de 22 pasos generó **106 mutaciones `AddProgress`** (una por step) más 59
`AddUsageOverhead` (tiempo de uso).

```graphql
mutation AddProgress($userId: String, $messages: [ProgressMessage!]!) {
  progress(userId: $userId, messages: $messages) { id __typename }
}
```

`ProgressMessage` (un mensaje por step):

```jsonc
{
  "userAgent": "...",
  "courseId": "bba24d6b...",            // hex del curso
  "sequenceId": "562a6f83-...",         // la lección
  "version": 1,
  "activityId": "f9d66c8b-...",
  "activityAttemptId": "6f34e9b8-...",       // UUID generado por el cliente, por intento de actividad
  "activityStepId": "49d13422-...",
  "activityStepAttemptId": "59ed0cc3-...",   // UUID generado por el cliente, por intento de step
  "answers": [ { "answer": "d482215b-...", "correct": true } ],  // answer = un id de step.correct
  "score": 1,                            // 1 correcto, 0 incorrecto
  "skip": false,
  "durationMs": 76796,
  "endTimestamp": "2026-08-10T00:18:53.151Z"
}
```

Notas para la implementación futura:

- `activityAttemptId` es constante dentro de una actividad; `activityStepAttemptId`
  cambia por step. Ambos los **inventa el cliente** (UUID v4).
- `answers` toma un id de `step.correct` con `correct: true`, `score: 1`. Para un
  `card` sin respuesta, el cliente envió `answer: ""`, `correct: false`, `score: 0`
  (registra la vista, no un acierto).
- La respuesta de la mutación devuelve la lista de `ProgressCourse` con sus ids;
  no hay que interpretarla, solo confirmar 200.

## Mapeo a dominio (capa de lectura implementada)

```
FluencyCatalog
└── FluencyCourse   (course_id, product_id, title, cefr, topic)
    └── FluencySequenceRef  (sequence_id, title, percent_complete)   ← de getCoursesAndProgress

FluencySequence   (sequence_id, course_id, title, version)           ← de getSequence
└── FluencyActivity  (activity_id, activity_type, interaction, ordering)
    └── FluencyStep  (step_id, type, correct_answer_ids)
```

- `FluencyCatalog` / `FluencyCourse` / `FluencySequenceRef`: el "menú", equivale a
  `CourseMenu` de Foundations. Dice qué falta por completar.
- `FluencySequence` / `FluencyActivity` / `FluencyStep`: el detalle de una lección,
  con los IDs y las respuestas correctas que la escritura necesitará.

Adaptador: `PlaywrightFluencyApiAdapter` (`infrastructure/adapters/fluency_api/`),
puerto `FluencyApiPort` (`application/ports/`). Las respuestas crudas se vuelcan a
`logs/diagnostics/` para inspección, igual que en Foundations.

## Límite confirmado: Conversation Practice (voz)

`DialogueExpressionWithReco` ("Prácticas de conversación") **no se puede completar
solo por la API.** El servidor acepta y registra el `AddProgress` (sube `attempts`) pero
deja la actividad en `percentComplete=0, bestGrade=0`. Se comprobó contra una
captura manual real:

- El mensaje del bot es **idéntico** al del navegador (`answer` ∈ `correct`,
  `correct:true`, `score:1`).
- Enviarlo **paso por paso** (un mensaje por llamada, como el navegador) no cambia
  nada: sigue en 0.
- El `score` entero (no float) tampoco.

Requiere el puntaje real del reconocimiento de voz (micrófono), que ocurre en el
navegador. **No hay endpoint de audio separado**; el reco es local. El orquestador
ahora abre la actividad con Playwright, dirige el audio nativo de la respuesta a un
micrófono virtual dentro de la página y deja que el reproductor genere el resultado.
Solo persiste la actividad cuando `getProgress` confirma `percentComplete=1`. Puede
desactivarse con `FLUENCY_SPEECH_BROWSER=0`.

## Pendiente / parcial

- **KeyVocabulary**: con `answers=[]` la tarjeta llega solo a ~1/N (p. ej. 1/18).
  Para completarla haría falta un `"SS:<wordId>:1:false"` por palabra, leyendo los
  `wordId` del carrusel del contenido. Fixeable, pero de valor limitado en lecciones
  que además tienen conversación (ya topan <100% por eso).

## Resuelto

- Auth de `gaia-server`: **Bearer token** (un UUID, no un JWT `eyJ`), capturado en
  vivo por `FluencySessionCapturer`. Confirmado en corrida real (2026-08-09).
- Detección de producto y enrutado tras login (`RosettaProduct`).
- Lectura (catálogo + secuencia) verificada contra la API real.
- Escritura (`AddProgress`) implementada con knobs de seguridad.
