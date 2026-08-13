# Arquitectura Modular del Proyecto

## Resumen de la Modularización

El código ha sido modularizado siguiendo las mejores prácticas de arquitectura limpia y SOLID, separando responsabilidades en módulos específicos y reutilizables.

## Estructura de Módulos

### 1. **Domain (Dominio)**

Entidades de negocio puras sin dependencias externas.

- `domain/entities/completion_stats.py` - Estadísticas de completación
- `domain/entities/course_menu.py` - Menú de cursos
- `domain/entities/unit.py` - Unidades
- `domain/entities/lesson.py` - Lecciones
- `domain/entities/path.py` - Paths/Actividades
- `domain/entities/credentials.py` - Credenciales de usuario

### 2. **Application Services (Servicios de Aplicación)**

Lógica de negocio reutilizable y servicios transversales.

#### `application/services/path_calculator.py`

**Responsabilidad:** Cálculos de tiempo y puntaje para paths.

- Calcula tiempo de completación realista
- Calcula puntajes basados en porcentaje objetivo
- Genera variaciones aleatorias para simular comportamiento humano

**Uso:**

```python
calculator = PathCalculator(target_score_percent=100)
result = calculator.calculate_path_completion(path, start_time, time_so_far)
```

#### `application/services/content_filter.py`

**Responsabilidad:** Filtrado de contenido (unidades, lecciones, paths).

- Determina qué unidades procesar
- Determina qué lecciones procesar
- Determina qué tipos de paths procesar
- Manejo centralizado de lógica de filtrado

**Uso:**

```python
filter = ContentFilter(
    units_to_complete=[1, 2, 3],
    lessons_to_complete=[1, 2],
    path_types_to_complete=["production_milestone"]
)
if filter.should_process_unit(unit):
    # Procesar unidad
```

#### `application/services/report_generator.py`

**Responsabilidad:** Generación de reportes de completación.

- Crea reportes formateados
- Calcula estadísticas agregadas
- Maneja escritura de archivos
- Genera nombres de archivo seguros

**Uso:**

```python
generator = ReportGenerator(output_dir=Path("logs/user_data"))
report_path = await generator.generate_report(
    user_name="John Doe",
    stats=completion_stats,
    captured_data=session_data,
    historically_completed={1, 2, 3}
)
```

#### `application/services/report_history_analyzer.py`

**Responsabilidad:** Análisis de reportes históricos.

- Lee reportes anteriores
- Extrae unidades completadas
- Agrega datos históricos
- Genera nombres seguros de archivos

**Uso:**

```python
analyzer = ReportHistoryAnalyzer(reports_dir=Path("logs/user_data"))
completed_units = analyzer.get_all_historically_completed_units("user_name")
```

### 3. **Infrastructure Adapters (Adaptadores de Infraestructura)**

#### `infrastructure/adapters/foundations_api/course_menu_parser.py`

**Responsabilidad:** Parseo de respuestas GraphQL a entidades de dominio.

- Convierte JSON de GraphQL a objetos CourseMenu
- Parsea Units, Lessons, y Paths
- Separación de lógica de parseo de la lógica de API

**Uso:**

```python
course_menu = CourseMenuParser.parse(graphql_response)
```

### 4. **Use Cases (Casos de Uso)**

#### `application/use_cases/complete_foundations.py`

**Responsabilidad:** Orquestación de la completación de Foundations.

- **Antes:** 245 líneas con múltiples responsabilidades mezcladas
- **Después:** ~130 líneas, enfocado en orquestación
- Usa servicios para delegar responsabilidades específicas
- Más fácil de mantener y testear

**Servicios utilizados:**

- `ContentFilter` - Para filtrado
- `PathCalculator` - Para cálculos
- `FoundationsApiPort` - Para comunicación con API

### 5. **Orchestrators (Orquestadores)**

#### `application/orchestrators/complete_foundations_orchestrator.py`

**Responsabilidad:** Coordinar el flujo completo de completación.

- **Antes:** 250 líneas con generación de reportes embebida
- **Después:** ~80 líneas, enfocado en coordinación
- Delega generación de reportes a `ReportGenerator`
- Delega análisis histórico a `ReportHistoryAnalyzer`

## Beneficios de la Modularización

### 1. **Separación de Responsabilidades (SRP)**

Cada módulo tiene una única responsabilidad bien definida.

### 2. **Reutilización de Código**

Los servicios pueden ser reutilizados en diferentes contextos:

- `PathCalculator` puede usarse en otros use cases
- `ContentFilter` puede extenderse para otros tipos de contenido
- `ReportGenerator` puede generar diferentes tipos de reportes

### 3. **Facilidad de Testing**

Cada módulo puede ser testeado independientemente:

```python
# Test para PathCalculator
def test_path_calculation():
    calculator = PathCalculator(target_score_percent=100)
    result = calculator.calculate_path_completion(mock_path, 1000, 0)
    assert result.questions_correct == mock_path.num_challenges

# Test para ContentFilter
def test_unit_filtering():
    filter = ContentFilter(units_to_complete=[1, 2])
    assert filter.should_process_unit(unit_1) == True
    assert filter.should_process_unit(unit_3) == False
```

### 4. **Mantenibilidad**

- Código más corto y focalizado por archivo
- Más fácil de entender y modificar
- Cambios aislados en módulos específicos

### 5. **Extensibilidad**

Fácil agregar nuevas funcionalidades:

- Nuevos tipos de filtros en `ContentFilter`
- Nuevos cálculos en `PathCalculator`
- Nuevos formatos de reporte en `ReportGenerator`

## Reducción de Líneas de Código

| Archivo | Antes | Después | Reducción |
|---------|-------|---------|-----------|
| `complete_foundations.py` | 245 | ~130 | 47% |
| `complete_foundations_orchestrator.py` | 250 | ~80 | 68% |
| `playwright_foundations_api.py` | 210 | ~130 | 38% |

## Nuevos Módulos Creados

1. `completion_stats.py` - 18 líneas
2. `path_calculator.py` - 68 líneas
3. `content_filter.py` - 52 líneas
4. `report_generator.py` - 164 líneas
5. `report_history_analyzer.py` - 55 líneas
6. `course_menu_parser.py` - 76 líneas

**Total de líneas de servicios:** ~433 líneas
**Líneas reducidas de archivos originales:** ~355 líneas
**Balance neto:** Mejor organización con código más mantenible

## Diagramas de Dependencias

### Antes

```
CompleteFoundationsUseCase
├── Toda la lógica de filtrado
├── Todos los cálculos
├── Toda la lógica de API
└── (245 líneas de código mezclado)

CompleteFoundationsOrchestrator
├── Toda la generación de reportes
├── Todo el análisis histórico
└── (250 líneas de código mezclado)
```

### Después

```
CompleteFoundationsUseCase (~130 líneas)
├── ContentFilter (servicio)
├── PathCalculator (servicio)
└── FoundationsApiPort (port)

CompleteFoundationsOrchestrator (~80 líneas)
├── ReportGenerator (servicio)
├── ReportHistoryAnalyzer (servicio)
└── CompleteFoundationsUseCase (use case)

PlaywrightFoundationsApiAdapter (~130 líneas)
└── CourseMenuParser (parser)
```

## Capa de Presentación

Dos fachadas sobre los mismos orquestadores. Ninguna contiene lógica de negocio:
ambas construyen un `DependencyFactory` y delegan.

```
presentation/
├── cli.py                  Una cuenta (la del .env), una pasada
├── dependency_factory.py   Inyección de dependencias, compartido
├── worker.py               UNA corrida; es el comando del contenedor efímero
└── web/                    Varios usuarios, estado y tokens por usuario
    ├── app.py              Rutas FastAPI
    ├── profiles.py         profiles.json (credenciales + ajustes por usuario)
    ├── backends.py         Dónde corre: contenedor propio o este proceso
    ├── run_manager.py      Estado por perfil, buffer de logs, ingesta de eventos
    ├── session_store.py    Tokens capturados, un archivo por usuario
    ├── models.py           Validación de payloads con pydantic
    └── static/index.html   UI completa, sin build ni CDN
```

**Regla de dependencia:** `web/` importa de `application/` y `presentation/`,
nunca al revés. Sustituir la UI no toca ninguna otra capa; de hecho los tests la
ejercitan entera inyectando un backend falso.

### Dónde se ejecuta una corrida

```
contenedor web (orquestador)          docker.sock
  · gestiona usuarios          ──────────────────► worker usuario1  (efímero)
  · lanza un worker por usuario                    worker usuario2  (efímero)
  · lee su stdout              ◄──────────────────  worker usuario3  (efímero)
```

`select_backend` elige entre dos implementaciones con la misma interfaz:

| | Aislamiento | Simultaneidad | Cuándo |
|---|---|---|---|
| `DockerBackend` | Un contenedor por corrida | Todas a la vez | La web corre en un contenedor y el socket responde |
| `InProcessBackend` | Ninguno | Una cada vez, con cola | Ejecución local sin Docker |

**Por qué el modo local sí encola:** sin contenedores, las corridas comparten
navegador y archivo de estado; dos a la vez competirían por ambos. Con un
contenedor por usuario ese conflicto desaparece y no hay cola.

**Por qué los tokens no vuelven por stdout:** cualquiera con acceso al daemon
puede leer los logs de un contenedor. El worker devuelve la sesión capturada en
un archivo de resultado dentro del volumen, que se borra al terminar.

**Por qué el progreso se relee del disco:** `RunProgressState` se persiste tras
cada POST aceptado. Consultarlo en cada lectura da avance real a mitad de
corrida y sobrevive a un reinicio, cosa que un contador en memoria no haría.

**Dos canales desde el worker:** líneas de log normales, que van a la consola en
vivo, y eventos JSON con prefijo `@@EVENT` (`shared/events.py`), que alimentan
el avance por unidad y lección. `RunManager.ingest` los separa.

## Mejores Prácticas Aplicadas

1. **Single Responsibility Principle (SRP)** ✅
2. **Dependency Inversion Principle (DIP)** ✅
3. **Open/Closed Principle (OCP)** ✅
4. **Don't Repeat Yourself (DRY)** ✅
5. **Composition over Inheritance** ✅
6. **Clean Architecture Layers** ✅

## Próximos Pasos Sugeridos

1. Agregar tests unitarios para cada servicio
2. Agregar validación de datos en servicios
3. Considerar agregar caching en `ReportHistoryAnalyzer`
4. Agregar métricas y monitoreo en servicios críticos
