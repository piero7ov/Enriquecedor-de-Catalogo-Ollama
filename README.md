# Enriquecedor de Catálogo con Ollama (XML → IA → JSON)

Mini proyecto en **Python + Ollama** que toma un catálogo en **XML** y lo enriquece automáticamente con metadatos útiles para una tienda online: **slug**, **short description**, **bullets**, **tags** y **SEO** (title/description), exportándolo como **JSON** listo para consumir desde una web.

> En este proyecto se realizaron **múltiples pruebas** con distintos modelos, prompts y catálogos (especialmente un catálogo de **tienda de impresiones 3D**).  
> Tras iteraciones y ajustes, el mejor resultado (calidad/estabilidad/compatibilidad con el hardware) se logró con:
> **`llama3.1:8b-instruct-q4_K_M`** en Ollama.

---

## ✅ Objetivo del proyecto

- Partir de un `productos.xml` simple (fuente “cruda”).
- Generar un `productos_enriched.json` **consistente** con campos enriquecidos:
  - `slug`
  - `short_desc`
  - `bullets` (exactamente 3)
  - `tags` (snake_case)
  - `seo_title` (<= 60 chars)
  - `seo_description` (<= 160 chars)
- Disponer de una **vista web estática** para comprobar rápidamente el resultado.

---

## 🧠 Enfoque “Universal”

Aunque el trabajo empezó centrado en la **página de producto**, la versión final se diseñó como un flujo universal:

**productos.xml (catálogo) → enriquecimiento con IA → productos_enriched.json → consumo en web (categoría / producto / SEO)**

Esto permite:
- Reutilizar el mismo dataset para listados, detalle, filtros, tags y SEO.
- Evitar inconsistencias de campos y formatos entre productos.
- Mantener el “frontend” limpio, consumiendo un JSON ya preparado.

---

## 📌 Modelo recomendado (hardware friendly)

Durante las pruebas, algunos modelos “grandes” fallaron por memoria en equipos con RAM limitada.  
El modelo final recomendado por estabilidad y obediencia al prompt fue:

- **`llama3.1:8b-instruct-q4_K_M`**

Instalación:

```bash
ollama pull llama3.1:8b-instruct-q4_K_M
````

---

## 📁 Estructura del proyecto (Universal)

```
mini-proyecto-enrich/
│
├─ data/
│  ├─ productos.xml                 # entrada (se crea con el generador)
│  └─ productos_enriched.json       # salida (se genera al enriquecer)
│
├─ src/
│  ├─ config.py                     # configuración de Ollama + rutas
│  ├─ create_productos_xml.py       # generador estático del XML (sin IA)
│  └─ enrich_products.py            # enriquecedor: XML → Ollama → JSON
│
├─ web/
│  ├─ index.html                    # vista estática para revisar resultados
│  └─ styles.css                    # estilos
│
├─ requirements.txt
└─ README.md
```

---

## ✅ Requisitos

* **Python 3.9+**
* **Ollama** instalado y corriendo en:

  * `http://127.0.0.1:11434`
* Dependencias Python:

  * `requests`

Instalar dependencias:

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuración (src/config.py)

Valores clave:

* `OLLAMA_URL`: endpoint de Ollama
* `OLLAMA_MODEL`: modelo a usar
* `TEMPERATURE`, `NUM_PREDICT`: estabilidad y longitud de salida
* `INPUT_XML`, `OUTPUT_JSON`: rutas de entrada/salida

Ejemplo recomendado:

```py
OLLAMA_MODEL = "llama3.1:8b-instruct-q4_K_M"
```

---

## 🚀 Uso (paso a paso)

### 1) Generar el catálogo XML (estático)

Crea `data/productos.xml` con un tema concreto (por ejemplo: setup gamer/escritorio):

```bash
python src/create_productos_xml.py
```

### 2) Enriquecer el catálogo con IA (Ollama)

Genera `data/productos_enriched.json`:

```bash
python src/enrich_products.py
```

---

## 🌐 Vista web estática (para comprobar el resultado)

### Opción A: servidor simple de Python

```bash
python -m http.server 8000
```

Abrir:

* `http://127.0.0.1:8000/web/`

### Opción B: XAMPP (Apache)

Coloca la carpeta del proyecto dentro de:

```
C:\xampp\htdocs\mini-proyecto-enrich\
```

Abrir:

* `http://localhost/mini-proyecto-enrich/web/`

La web carga el JSON con:

* `fetch("../data/productos_enriched.json")`

---

## 🧩 Formato de salida (productos_enriched.json)

Salida (resumen de campos enriquecidos):

```json
{
  "productos": [
    {
      "nombre": "...",
      "descripcion": "...",
      "categoria": "...",
      "material": "...",
      "precio": "...",
      "marca": "...",
      "modelo": "...",
      "color": "...",

      "slug": "...",
      "short_desc": "...",
      "bullets": ["...", "...", "..."],
      "tags": ["..."],
      "seo_title": "...",
      "seo_description": "..."
    }
  ]
}
```

---

## 🧪 Notas sobre las pruebas y el resultado

Este proyecto se construyó mediante **iteración**:

* Varias pruebas con diferentes modelos y prompts.
* Enfoque inicial en una tienda de **impresiones 3D** (calidad de bullets/tags/SEO).
* Ajustes para evitar:

  * bullets repetidos / “comodines”
  * copias literales de la descripción
  * tags con espacios o tildes
  * JSON roto o incompleto
* El resultado estable final se consiguió con:

  * **`llama3.1:8b-instruct-q4_K_M`**
  * prompt estricto orientado a “impacto/beneficio” sin inventar datos.

---

## 👨‍💻 Desarrollado por

**Piero Olivares (PieroDev)**