# Introducción — Generador Offline de Catálogo 3D con IA Local (Ollama)

## 1) Idea del proyecto
Este proyecto construye un **pipeline 100% local (sin internet)** para convertir un catálogo de productos en XML en un **catálogo “pro” enriquecido** usando una **IA local (Ollama)**.

La meta es que, a partir de tu `productos.xml`, puedas generar automáticamente contenido útil para tu web y para tu base de datos, sin depender de APIs externas ni servicios online.

---

## 2) Entrada (fuente de verdad)
El archivo base será un XML de este estilo:
````
<productos>
  <producto>
    <nombre>...</nombre>
    <descripcion>...</descripcion>
    <imagen>...</imagen>
    <enlace>...</enlace>
    <precio>...</precio>
    <material>...</material>
    <tamano>...</tamano>
    <categoria>...</categoria>
  </producto>
</productos>
````

Este XML es la **fuente de verdad**: si actualizas productos ahí, todo lo demás se regenera.

---

## 3) Qué aporta la IA local (Ollama)

El XML trae datos básicos (nombre, descripción, precio…).
La IA se usará para generar **campos extra** que mejoran muchísimo el catálogo:

* `slug` (URL amigable) si no existe o si queremos normalizarlo
* `short_desc` (descripción corta en 1 frase, potente)
* `bullets` (3–5 puntos de venta/beneficios)
* `tags` (etiquetas para filtros en la web)
* `seo_title` y `seo_description` (para mejorar SEO y snippets)
* `faq` (2–3 preguntas frecuentes del producto)
* (opcional) `print_notes` (notas orientativas: soportes/postproceso, etc.)

⚠️ Importante:

* La IA debe devolver **JSON estricto**.
* Se trabajará en **micro-tareas por producto** para que sea rápido y no se cuelgue.
* Si la IA falla en un producto, el proceso continúa con fallback (no bloquea el pipeline).

---

## 4) Salidas (outputs) del proyecto

El script generará un paquete de archivos listos para usar:

### 4.1 Catálogo enriquecido (principal)

* `out/catalogo_enriquecido.json`

  * Cada producto incluirá los campos originales + los campos generados por IA.
  * Útil para tu web (JS), para panel admin, o para consumirlo desde backend.

### 4.2 Exportaciones “de trabajo”

* `out/productos.csv`

  * Para Excel / importación / revisiones rápidas.
* `out/catalogo.sql`

  * Tablas mínimas de catálogo + inserts para MySQL/MariaDB (local, XAMPP).

### 4.3 Páginas estáticas opcionales

* `out/pages/*.html`

  * Una página por producto con copy mejorado, bullets y FAQ.
  * Perfecto para demos y para entregar algo presentable rápido.

---

## 5) Qué tiene en común con lo del profe

Mantiene la misma lógica:

1. **XML = fuente de verdad**
2. Script **parsea** el XML
3. IA local (**Ollama**) genera contenido estructurado (JSON)
4. Script **genera archivos** automáticamente (assets del proyecto)

La diferencia es que aquí:

* No generamos imágenes (evitamos Stable Diffusion y su consumo de recursos).
* Generamos **contenido y datos** listos para web/BBDD/documentación.
* Todo es **offline y repetible**.

---

## 6) Enfoque por iteraciones (como proyecto real)

### Iteración 001 (la que haremos primero)

* Leer `productos.xml`
* Para cada producto: pedir a Ollama un JSON corto con campos extra (slug/tags/SEO/bullets/FAQ)
* Guardar `out/catalogo_enriquecido.json`
* Añadir caché local para no recalcular productos ya procesados

### Iteración 002 (después)

* Generar `productos.csv` desde el JSON enriquecido
* Generar `catalogo.sql` (tablas + inserts)
* Generar páginas HTML estáticas (opcional)

---

## 7) Requisitos (local)

* Python 3.x
* Ollama instalado y funcionando en local (`http://127.0.0.1:11434`)
* Un modelo local recomendado:

  * `qwen2.5-coder:7b` (mejor para JSON/estructura)
  * Alternativa rápida: `phi3:mini`

---

## 8) Objetivo final (lo que vas a poder hacer)

* Cambiar/añadir productos en `productos.xml`
* Ejecutar el script
* Obtener un catálogo pro enriquecido y listo para:

  * mostrar en tu web
  * filtrar por tags/material/categoría
  * importar a BBDD
  * presentar como demo completa
