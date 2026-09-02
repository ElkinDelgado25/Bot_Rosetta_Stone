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
  fabricadas por curso (default `70`, un nivel completo de Rosetta Stone),
  repartido con jitter entre **todas las lecciones que tiene el curso**
  (`course.sequences`, no solo las que esta corrida procesa) y, dentro de
  cada lección, entre sus steps. Divide por el total del curso a propósito:
  una corrida con `FLUENCY_MAX_LESSONS=1` solo toca una lección, y dividir el
  presupuesto por "1" en vez de por el tamaño real del curso inflaría cada
  step a decenas de minutos. Reemplaza el `durationMs` fijo de 5000ms por
  algo que se parece a Foundations, cuyo `PathCalculator` deriva la duración
  de un `time_estimate` real por path. Fluency no trae ese dato en su árbol
  de contenido, así que `FluencyDurationCalculator` fabrica el presupuesto en
  vez de leerlo.

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

### `AddUsageOverhead` (capturada del reproductor, 01-09-2026)

Estuvo mucho tiempo inferida por analogía con `AddProgress`. Ya no: las trazas
de Playwright que deja una actividad de voz fallida guardan el tráfico real, y
dentro había dos llamadas `AddUsageOverhead` con su query y sus variables.

```graphql
mutation AddUsageOverhead($messages: [UsageOverheadMessage!]!) {
  usageOverhead(messages: $messages)
}
```

```json
{"messages": [{
  "id": "7985d048-0243-4a35-a8c7-09f966930f3e",
  "userAgent": "Mozilla/5.0 (...) Chrome/140.0.0.0 Safari/537.36",
  "learningContext": "aefc3bf647e0c78b1f6ffce3415c61ca",
  "durationMs": 21521,
  "endTimestamp": "2026-09-01T15:22:28.871Z"
}]}
```

**La versión inferida era inválida por tres motivos a la vez**, y cualquiera de
los tres bastaba para que el servidor la rechazara sin llegar a mirar los datos:

1. La variable se llama `$messages`, no `$overheads`.
2. No lleva `userId` — el usuario sale del Bearer.
3. `usageOverhead` devuelve un **escalar**: pedirle `{ id __typename }` es un
   error de validación por sí solo.

El mensaje tampoco es un `ProgressMessage` recortado, que es lo que se había
supuesto: no hay `sequenceId` ni `activityId`, el curso viaja como
`learningContext` y el `id` es del mensaje, no de la actividad. `UsageOverheadMessage`
es un input estricto, así que los campos de más no se ignoran: invalidan.

Sigue siendo **best-effort** y apagada por default
(`FLUENCY_SEND_USAGE_OVERHEAD=0`): la completación (0%→100%, confirmada en
corrida real) funciona solo con `AddProgress`, esto es telemetría de tiempo de
uso. Un fallo aquí se loguea a `debug` y nunca revierte el `AddProgress` ya
exitoso. Lo que queda por confirmar es solo que el servidor la acepta con el
esquema bueno.

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

## Medido sobre corridas reales (31-08-2026)

Cruzando los volcados de `getProgress` con los de `getSequence` (78.700 registros
de actividad), quedan **49 actividades distintas** por debajo del 100%:

| `activityType` | Nº | `percentComplete` |
|---|---|---|
| `DialogueExpressionWithReco` | 27 | 0 |
| `DialogueExpressionWithoutReco` | 17 | 0 |
| `PronunciationPhoneme` | 1 | 0 |
| `Vocabulary` / `KeyVocabulary` | 4 | 0,056 · 0,059 · 0,091 — **lectura transitoria**, ver abajo |

Dos hallazgos que cambiaron el código:

1. Se probó a enrutar también `DialogueExpressionWithoutReco` al navegador y
   **salió mal**: "WithoutReco" significa sin reconocimiento de voz, o sea que la
   actividad no tiene botón de micrófono; la espera agotaba 90 s por actividad y
   fallaba igual. `BROWSER_COMPLETED_TYPES` vuelve a llevar solo
   `DialogueExpressionWithReco`. Esos 17 siguen siendo un hueco abierto: por API
   no se completan y por la ruta de voz tampoco, porque no hay voz que dar.
   Para probar otro tipo sin tocar código: `FLUENCY_BROWSER_EXTRA_TYPES=Tipo1,Tipo2`.
2. Las tarjetas de vocabulario **no están rotas**. Los 1/18, 1/17 y 1/11 son
   fotos tomadas *durante* la escritura: mirando la línea de tiempo de esas 4
   actividades (`8dc8f563`, `c368ff9e`, `5bc0a3fc`, `9eff7a94`) cada una sube a
   1,0 en el mismo minuto. Un escaneo que se quede con el mínimo histórico las
   da por estancadas y no lo están. Con `answers=[]` se completan.

## La conversación por navegador, paso a paso (01-09-2026)

20 corridas reales sobre una cuenta B1 hasta dar con el bloqueo de verdad.
Resumen de lo aprendido, por si alguien vuelve a pelearse con esto:

**El bloqueo real: un modal de "Comprobación de micrófono".** Se pinta *encima*
de la actividad al entrar en un paso de conversación, con un desplegable de
dispositivos y un botón *Comenzar*. Detrás de esa capa ningún clic llega a las
respuestas y el micrófono sigue `disabled`. Durante once corridas pareció un
problema de selectores; lo destapó mirar un fotograma de la traza, no el DOM.

Lo que hace falta para pasarlo:

1. `--use-fake-device-for-media-stream` al lanzar Chromium, o el desplegable
   sale vacío (un contenedor no tiene micrófonos) — más un parche de
   `enumerateDevices` por si acaso.
2. Un vigilante (`MutationObserver`) que pulse *Comenzar* y *Volver a intentar*
   en cuanto aparezcan: el modal **no está** cuando se abre la actividad, sale
   un momento después (en la traza aparece en 1 de 110 instantáneas).
3. **Señal audible durante la comprobación.** La prueba pide decir "1, 2, 3, 4,
   5" y escucha: un micrófono virtual sin nada inyectado es silencio y responde
   *"No se detectó su entrada de audio"*. Se reproduce en bucle
   `<ROSETTA_HOME>/audio/mic_check.wav` si existe (una voz real), y si no un
   tono de 220 Hz.
4. *Comenzar* no es un `<button>`: es un `div`/`span` con `data-qa`. Buscarlo
   por rol devuelve cero y el modal se queda abierto en silencio.
5. **La señal tiene que llegar de verdad al micrófono** (01-09-2026). El
   destino (`MediaStreamDestination`) se crea *dentro* de `getUserMedia`, y la
   señal arrancaba antes de que la página pidiera el micrófono: se conectaba a
   un destino que aún no existía y no sonaba nada. Se ve en el medidor
   (`[data-qa=CalibrateMeter]`): **1 barra encendida de 10** y la ventana sin
   irse nunca. La forma que funciona es un `GainNode` permanente —el bus— al
   que se conecta todo, y que `getUserMedia` engancha a cada destino nuevo. Así
   da igual el orden, y sobrevive a que la página vuelva a pedir el micrófono.

**El modal tiene dos caras y solo una tiene botón** (01-09-2026). Primero
elegir dispositivo y *Comenzar*; después "Comprobando el micrófono…", que se
queda escuchando sin nada que pulsar. Buscar el botón en la segunda registraba
`por rol=0, por data-qa=0, por texto=0` — que se lee como "no hay modal"— mientras
la ventana seguía tapando la pantalla entera (`position: fixed`, `z-index: 7000`).
Se reconoce por `[data-qa=CalibrationWindow]`, y lo que hay que esperar es a que
**desaparezca**: pulsar el botón no es que la comprobación haya pasado.

El síntoma, si no se espera, engaña del todo: las cinco formas de marcar una
respuesta fallan una tras otra y el log dice "el paso 1 no llegó a seleccionar
ninguna respuesta". No es que la respuesta no se pueda pulsar — es que hay un
modal encima. El altavoz de la respuesta sí sonaba, lo que despista más todavía
(cae fuera del modal).

Y hay una **tercera cara**: "Comprobación de micrófono exitosa · ¡Está todo
listo!" con un *Continuar*. Sale cuando la prueba ha ido **bien** y aun así se
queda esperando encima de la actividad. El vigilante solo conocía *Comenzar* y
*Volver a intentar*, así que ahí se plantaba. Además esa comprobación se come
la primera pulsación del micrófono de la actividad: hay que volver a pulsarlo
cuando la ventana se ha ido.

## El paso de conversación, resuelto (01-09-2026)

Con la comprobación pasada, quedaban cuatro cosas mal entendidas. Las cuatro se
vieron en corridas reales, y cada una escondía a la siguiente:

1. **La respuesta no se marca: se dice.** Se gastaban cinco formas de pulsar la
   ficha y se daba el paso por perdido. No hace falta ninguna: el reconocedor
   decide cuál de las tres has dicho. Se comprobó sin ninguna marcada — el
   reproductor escuchó y contestó. Marcar sigue intentándose porque ayuda, pero
   no marcar ya no hunde el paso.
2. **El micrófono se pide una sola vez.** ``getUserMedia`` se llama en la
   comprobación y el reproductor reutiliza ese ``MediaStream``. Esperar una
   segunda llamada eran 90 s muertos; y aun con un sondeo corto, esperar 15 s
   antes de inyectar es peor que inútil: el reconocedor escucha unos segundos y
   si no oye nada da la respuesta por no entendida.
3. **El botón de enviar solo tiene dos textos mientras el paso no se resuelve:**
   "Omitir" (no ha oído nada) y "Volver a intentar" (ha oído y no ha entendido).
   Dar por buena "cualquier cosa que no sea Omitir" hacía pulsar *Volver a
   intentar*, que **reinicia el paso**: el enunciado no cambiaba nunca y la
   espera moría a los 90 s señalando al sitio equivocado. Ahora "Volver a
   intentar" es un veredicto y se vuelve a hablar (3 intentos por paso).
4. **"Próximo paso" llega deshabilitado.** Con la respuesta aceptada el pie se
   vuelve morado con "Esta es la respuesta correcta" y el botón cambia — pero
   está deshabilitado mientras suena la confirmación, así que el primer clic se
   pierde. Se pulsa hasta que el enunciado cambie.

5. **``expected_steps`` no es lo que pinta el reproductor.** Una actividad que
   la API declaraba de 13 tenía 10 enunciados. Al acabar el décimo se esperaban
   90 s a un micrófono que ya no vuelve y la conversación —terminada, y al 100%
   según ``getProgress``— se daba por fallida y no se persistía. Que el
   micrófono no reaparezca es el final, no un error: se comprueba con el sondeo
   corto y se sale del bucle.

Resultado medido: **10 pasos de 10** en dos actividades
``DialogueExpressionWithReco`` reales, y ``getProgress`` devolviendo
``percentComplete=1`` en ambas. Un detalle constante: el **primer intento de
habla casi siempre se rechaza y el segundo entra**; por eso los reintentos no
son un adorno. Se probó a esperar a que el botón entrara en modo grabación
antes de inyectar, por si el rechazo era de tiempo: **no lo era** — sigue
pasando igual con la espera puesta.

Las tres respuestas son la **misma frase dicha de tres formas** ("I began
Athena Cell Phones in 1990" / "Our company's history began in 1990" / "Athena
Cell Phones began in 1990"), así que al aceptarse una se iluminan las tres. No
hay una correcta y dos incorrectas, y por eso da igual cuál se diga.

**El audio de referencia se saca del buffer que suena, no de la URL.** La media
va firmada (500 al descargarla, incluso desde dentro de la página) y se descifra
en un worker donde los ganchos del hilo principal no llegan. Lo que sí funciona:
enganchar `AudioBufferSourceNode.start` y serializar `getChannelData` a WAV.

**Lo que se probó y NO funciona** (para no repetirlo):

- Reproducir el audio del enunciado antes de responder: deja el reproductor
  ocupado y los altavoces de las respuestas dejan de sonar.
- Enrutar `DialogueExpressionWithoutReco` a la ruta de voz **tal y como estaba**:
  esperaba el micrófono y esa actividad no lo tiene. Lo que fallaba era la
  espera, no el enrutado — ver "La conclusión que estaba mal".
- Esperar a que el micrófono se habilite como prueba de que se eligió respuesta:
  son dos cosas distintas.

## Fallos del flujo de voz corregidos (31-08-2026)

Tres, sacados de los errores de una corrida real:

- **El botón de micrófono llega deshabilitado.** El reproductor lo marca
  `disabled` mientras suena el audio del diálogo y pinta encima una capa que se
  traga el clic (`<div class="css-onwehy"> intercepts pointer events`).
  Playwright reintentaba 60 veces y moría a los 30 s. Ahora se espera a que el
  botón no tenga `disabled` y se pulsa con `force`, que salta la comprobación de
  interceptación.
- **Títulos de lección repetidos.** `Registration` existe en más de un curso, y
  el código exigía una coincidencia exacta (`lesson card not found uniquely`), lo
  que tumbaba la actividad sin intentarla. Ahora varias coincidencias abren la
  primera y se avisa; cero sigue siendo error.
- **Descubrir que no hay micrófono costaba 90 s.** Esa espera ahora es de 15 s
  (`probe_timeout_ms`) y dice explícitamente que la actividad no tiene micrófono.

## Pendiente / parcial

- **KeyVocabulary**: nada que arreglar. Se llegó a implementar el envío de un
  `"SS:<wordId>:1:false"` por palabra del carrusel y se revirtió: las tarjetas ya
  se completan con `answers=[]`, así que era cambiar el tráfico con un formato sin
  verificar a cambio de nada. Si algún día una tarjeta se queda de verdad en 1/N,
  los `wordId` están en `content[0].carousel` con `type: "word"`.

- **`DialogueExpressionWithoutReco`**: ya no es un hueco, es una ruta. Ver
  "La conclusión que estaba mal" más abajo. Falta confirmarlo contra la cuenta
  viva: el código está, la corrida que lo ejercite no.

## La conclusión que estaba mal (02-09-2026)

Durante dos semanas la nota decía que `DialogueExpressionWithoutReco` era un
hueco imposible: 17 actividades que la API acepta y deja en 0, y a las que la
ruta de voz no sirve "porque no tienen micrófono". La primera mitad es cierta.
La segunda es una conclusión sacada de un síntoma.

Lo que se hizo entonces fue enrutar el tipo a la ruta de voz **sin cambiarla**.
La ruta abría la actividad y esperaba el botón de micrófono; como no llegaba, se
agotaban 90 s y se abandonaba. De ahí salió "no se puede", cuando lo que se había
medido es "esta espera no vale para este tipo".

Lo que dicen los datos, cruzando el catálogo entero (5.701 actividades con
pasos):

| | `ordering` | `inputType` de sus pasos |
|---|---|---|
| `DialogueExpressionWithReco` | `tree` | `speaking` (351 pasos) |
| `DialogueExpressionWithoutReco` | `tree` | `select` (224 pasos) |
| Todo lo demás | `fixed` / `random` | — |

Dos cosas caen de ahí:

- **`ordering: "tree"` existe en 46 actividades y solo en esas 46**: las 27
  `WithReco` más las 19 `WithoutReco`. Son exactamente las que la API no
  acredita. Lo que el servidor no acepta fabricado **es el árbol, no la voz** —
  y por eso el resto de tipos con pasos `select` (128 `RightWordWithoutReco`,
  117 `WordOrderWithoutReco`, 92 `FITB`…) se completan por API sin problema.
- **`WithoutReco` se contesta pulsando** (`inputType: select`). No es que no
  haya forma de responder: es que no se responde hablando.

El arreglo es un detector de modo en la página (`_input_mode`): tras abrir la
actividad se espera a que aparezca **el micrófono o las respuestas**, lo primero
que llegue. Con micrófono, el flujo de siempre. Sin él, `_complete_visible_choice_step`
marca una respuesta y pulsa *Próximo paso*, sin tocar el micrófono virtual ni la
comprobación de micrófono. `_another_step_starts` también depende del modo:
eligiendo, la señal de que queda otro turno es que vuelva a haber respuestas, no
que vuelva el micrófono — preguntando por el micrófono, toda conversación
`WithoutReco` se daba por acabada en su primer paso.

Una diferencia que sí importa: hablando, marcar la respuesta es opcional (el
reconocedor decide cuál has dicho); eligiendo es obligatorio, porque no hay otra
forma de contestar. Un clic que no se registra es el final del paso, no un aviso.

**Falta la confirmación contra la cuenta viva.** Nada de esto se ha ejercitado
todavía contra el servidor: la última corrida es del 01-09 a las 11:02 y el
código cambió después.

## Resuelto

- Auth de `gaia-server`: **Bearer token** (un UUID, no un JWT `eyJ`), capturado en
  vivo por `FluencySessionCapturer`. Confirmado en corrida real (2026-08-09).
- Detección de producto y enrutado tras login (`RosettaProduct`).
- Lectura (catálogo + secuencia) verificada contra la API real.
- Escritura (`AddProgress`) implementada con knobs de seguridad.
