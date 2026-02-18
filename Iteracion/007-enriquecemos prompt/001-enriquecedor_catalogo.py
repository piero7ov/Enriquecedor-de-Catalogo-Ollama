#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
001 / Script:
XML (productos) -> catálogo enriquecido (JSON) + cache + errores

- Pensado para funcionar bien con cualquier temática (3D, electrónica, ropa, etc.)
- Prompt estricto para evitar repetición entre short_desc / bullets / seo_description
- Cache por hash para no volver a llamar a Ollama si no cambia el producto
- Fallback si Ollama falla (no revienta la ejecución)

Salidas (editables en CONFIG):
  OUT_DIR/OUT_CATALOG_FILE
  OUT_DIR/OUT_CACHE_FILE
  OUT_DIR/OUT_ERRORS_FILE
"""

from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone

import xml.etree.ElementTree as ET
import requests
from difflib import SequenceMatcher


# =========================
# CONFIG (EDITA AQUÍ)
# =========================
XML_FILE = "productos3d.xml"

OUT_DIR = "out"
OUT_CATALOG_FILE = "catalogo_enriquecido.json"
OUT_CACHE_FILE = "cache_enrichment.json"
OUT_ERRORS_FILE = "errors.json"

# --- Ollama ---
OLLAMA_ENABLED = True
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5-coder:7b"

# Si tu modelo soporta `format: "json"` úsalo: reduce mucho errores.
TRY_FORMAT_JSON = True

TEMPERATURE = 0.2
NUM_PREDICT = 220

# Timeouts (connect, read)
TIMEOUT_CONNECT = 10
TIMEOUT_READ = 240

MAX_RETRIES = 1  # 0 = sin reintentos

PRINT_PROGRESS = True

# Versión de reglas (si cambias prompt/validación, sube el número para invalidar cache)
RULES_VERSION = 3


# =========================
# HELPERS
# =========================
def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(s: str, maxlen: int = 80) -> str:
    s = (s or "").strip().lower()
    # quitar tildes "suave" (opcional)
    repl = str.maketrans("áéíóúüñ", "aeiouun")
    s = s.translate(repl)
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return (s or "item")[:maxlen]


def extract_json_block(text: str) -> str:
    """
    Extrae el bloque JSON más probable si el modelo mete texto extra.
    """
    if not text:
        return ""
    text = text.strip()
    # si ya es JSON puro:
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        return text
    # intenta recortar
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def sha1_key(obj: dict) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _norm(s: str) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _sim(a: str, b: str) -> float:
    a = _norm(a)
    b = _norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def dedupe_near(items: list[str], threshold: float = 0.90) -> list[str]:
    out: list[str] = []
    for it in items:
        it = str(it).strip()
        if not it:
            continue
        if any(_sim(it, prev) >= threshold for prev in out):
            continue
        out.append(it)
    return out


def cut_smart(text: str, limit: int) -> str:
    """
    Corta sin partir palabra (si se puede).
    """
    t = str(text or "").strip()
    if len(t) <= limit:
        return t
    cut = t[:limit].rstrip()
    # corta al último espacio si es viable
    pos = cut.rfind(" ")
    if pos >= max(10, limit - 20):
        cut = cut[:pos].rstrip()
    return cut


def to_snake_tag(t: str) -> str:
    t = slugify(t, 40).replace("-", "_")
    t = re.sub(r"_+", "_", t).strip("_")
    return t


def unique_case_insensitive(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        k = _norm(x)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


# =========================
# OLLAMA
# =========================
def ollama_generate(system: str, prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
        }
    }
    if TRY_FORMAT_JSON:
        payload["format"] = "json"

    r = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=(TIMEOUT_CONNECT, TIMEOUT_READ)
    )
    r.raise_for_status()
    data = r.json()
    return (data.get("response") or "").strip()


def ollama_enrich(product: dict) -> dict:
    """
    Devuelve dict con claves:
      slug, short_desc, bullets, tags, seo_title, seo_description
    """

    system = (
        "Devuelve SOLO JSON válido. Sin texto extra, sin markdown, sin explicaciones.\n"
        "No inventes datos técnicos. Si falta un dato, no lo inventes.\n\n"
        "Objetivo: enriquecer un producto SIN repetir información.\n"
        "REGLA CLAVE: NO repitas la misma idea en short_desc, bullets y seo_description.\n\n"
        "Devuelve EXACTAMENTE estas claves:\n"
        '{'
        '"slug":"",'
        '"short_desc":"",'
        '"bullets":["","",""],'
        '"tags":["","","","","",""],'
        '"seo_title":"",'
        '"seo_description":""}\n\n'
        "Reglas estrictas:\n"
        "- slug: minúsculas, sin tildes, con guiones, sin .html.\n"
        "- short_desc: 1 frase (60-95 chars aprox). SIN prefijos tipo 'Material:', 'Tamaño:', 'Categoría:', 'Precio:', 'Marca:', 'Modelo:'.\n"
        "  Debe decir para qué sirve / beneficio principal.\n"
        "- bullets: EXACTAMENTE 3, 3 a 8 palabras cada uno, SIN ':' y SIN repetir.\n"
        "  PROHIBIDO mencionar material/tamaño/categoría/marca/modelo/precio/garantía.\n"
        "  Deben ser beneficios/uso.\n"
        "- tags: 6 a 10 tags, snake_case, únicas, sin repetir palabras de short_desc.\n"
        "- seo_title: <= 60 caracteres (no cortar palabra).\n"
        "- seo_description: <= 160 caracteres, 1-2 frases, SIN repetir short_desc literal.\n"
    )

    # brief: manda lo útil, sin esquema enorme
    brief = {
        "nombre": product.get("nombre", ""),
        "descripcion": product.get("descripcion", ""),
        "categoria": product.get("categoria", ""),
        "material": product.get("material", product.get("tamaño", "")),
        "tamano": product.get("tamano", product.get("tamaño", "")),
        "precio": product.get("precio", ""),
        "marca": product.get("marca", ""),
        "modelo": product.get("modelo", ""),
        # extras automáticos (cualquier campo adicional del producto)
        "extras": {k: product.get(k) for k in product.keys()
                   if k not in {"nombre", "descripcion", "categoria", "material", "tamano", "tamaño",
                                "precio", "marca", "modelo", "imagen", "enlace"}}
    }

    user = (
        "Genera el JSON siguiendo las reglas.\n"
        f"Producto:\n{json.dumps(brief, ensure_ascii=False)}"
    )

    txt = ollama_generate(system=system, prompt=user)
    js = extract_json_block(txt)
    return json.loads(js)


# =========================
# VALIDACIÓN + NORMALIZACIÓN
# =========================
def normalize_enriched(enriched: dict, product: dict) -> dict:
    """
    Limpia y fuerza:
    - slug válido
    - bullets 3 (sin repetidos y sin ':'), cortos
    - tags 6-10, snake_case, únicos
    - seo_title/seo_description con límites
    """
    if not isinstance(enriched, dict):
        raise ValueError("Enriched no es dict")

    nombre = str(product.get("nombre", "Producto")).strip()
    desc = str(product.get("descripcion", "")).strip()

    slug = str(enriched.get("slug", "")).strip()
    if not slug:
        # slug más informativo si hay marca
        marca = str(product.get("marca", "")).strip()
        base = f"{nombre} {marca}".strip()
        slug = slugify(base)
    else:
        slug = slugify(slug)

    short_desc = str(enriched.get("short_desc", "")).strip()
    if not short_desc:
        short_desc = desc or nombre
    # quitar prefijos tipo "Material:" si el modelo se lo salta
    short_desc = re.sub(r"^(material|tamaño|tamano|categoría|categoria|precio|marca|modelo)\s*:\s*",
                        "", short_desc, flags=re.IGNORECASE).strip()
    short_desc = cut_smart(short_desc, 140)

    # bullets
    bullets = enriched.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    bullets = [str(b).strip() for b in bullets if str(b).strip()]
    bullets = [b.replace(":", "").strip() for b in bullets]  # regla: sin ':'
    bullets = dedupe_near(bullets, threshold=0.90)

    # filtra bullets demasiado parecidos a short_desc
    bullets2 = []
    for b in bullets:
        if _sim(b, short_desc) >= 0.82:
            continue
        bullets2.append(b)
    bullets = bullets2

    # asegura 3 bullets
    fallback_pool = [
        "Diseño pensado para uso diario",
        "Ideal para regalo o escritorio",
        "Acabado limpio y elegante",
        "Fácil de usar y mantener",
        "Listo para tu setup o casa",
    ]
    while len(bullets) < 3:
        cand = fallback_pool[len(bullets) % len(fallback_pool)]
        if not any(_sim(cand, x) >= 0.90 for x in bullets):
            bullets.append(cand)
        else:
            bullets.append("Listo para usar")
    bullets = bullets[:3]

    # tags
    tags = enriched.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [to_snake_tag(str(t)) for t in tags if str(t).strip()]
    tags = unique_case_insensitive(tags)

    # añade tags razonables si faltan (sin reventar)
    extra_tags = []
    for k in ("categoria", "material", "tamano", "tamaño", "marca", "modelo"):
        v = str(product.get(k, "")).strip()
        if v:
            extra_tags.append(to_snake_tag(v))
    extra_tags = unique_case_insensitive(extra_tags)

    tags = unique_case_insensitive(tags + extra_tags)

    # mínimo 6, máximo 10
    while len(tags) < 6:
        tags.append(to_snake_tag("producto"))
        tags = unique_case_insensitive(tags)
        if len(tags) > 20:
            break
    tags = tags[:10]

    seo_title = str(enriched.get("seo_title", "")).strip() or f"{nombre}"
    seo_title = cut_smart(seo_title, 60)

    seo_description = str(enriched.get("seo_description", "")).strip() or (desc or short_desc or nombre)
    # evita repetir short_desc literal
    if _norm(seo_description) == _norm(short_desc):
        seo_description = (desc or "").strip()
        if not seo_description:
            seo_description = f"{short_desc}. Descubre más detalles en la ficha."
    seo_description = cut_smart(seo_description, 160)

    return {
        "slug": slug,
        "short_desc": short_desc,
        "bullets": bullets,
        "tags": tags,
        "seo_title": seo_title,
        "seo_description": seo_description,
    }


# =========================
# FALLBACK (si Ollama falla)
# =========================
def fallback_enrich(product: dict) -> dict:
    nombre = str(product.get("nombre", "Producto")).strip()
    desc = str(product.get("descripcion", "")).strip()
    marca = str(product.get("marca", "")).strip()

    slug = slugify(f"{nombre} {marca}".strip())
    short_desc = cut_smart(desc or nombre, 140)

    bullets = [
        "Diseño pensado para uso diario",
        "Ideal para regalo o escritorio",
        "Acabado limpio y elegante",
    ]

    tags = []
    for k in ("categoria", "material", "tamano", "tamaño", "marca", "modelo"):
        v = str(product.get(k, "")).strip()
        if v:
            tags.append(to_snake_tag(v))
    tags = unique_case_insensitive(tags)
    while len(tags) < 6:
        tags.append("producto")
        tags = unique_case_insensitive(tags)
    tags = tags[:10]

    seo_title = cut_smart(nombre, 60)
    seo_description = cut_smart((desc or short_desc or nombre), 160)

    return {
        "slug": slug,
        "short_desc": short_desc,
        "bullets": bullets,
        "tags": tags,
        "seo_title": seo_title,
        "seo_description": seo_description,
    }


# =========================
# XML LOAD
# =========================
def parse_productos_xml(xml_path: Path) -> list[dict]:
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    products: list[dict] = []
    for p in root.findall(".//producto"):
        item: dict = {}
        for child in list(p):
            tag = (child.tag or "").strip()
            text = (child.text or "").strip()
            if tag and text:
                item[tag] = text
        if item:
            products.append(item)
    return products


# =========================
# MAIN
# =========================
def main():
    xml_path = Path(XML_FILE)
    if not xml_path.exists():
        raise FileNotFoundError(f"No existe: {xml_path.resolve()}")

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = out_dir / OUT_CATALOG_FILE
    cache_path = out_dir / OUT_CACHE_FILE
    errors_path = out_dir / OUT_ERRORS_FILE

    # cache
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            cache = {}
    else:
        cache = {}

    errors: list[dict] = []

    products = parse_productos_xml(xml_path)
    n = len(products)
    enriched_products: list[dict] = []

    for i, product in enumerate(products, start=1):
        nombre = product.get("nombre", f"producto_{i}")

        # cache key
        cache_key_obj = {
            "v": RULES_VERSION,
            "nombre": product.get("nombre", ""),
            "descripcion": product.get("descripcion", ""),
            "categoria": product.get("categoria", ""),
            "material": product.get("material", ""),
            "tamano": product.get("tamano", product.get("tamaño", "")),
            "marca": product.get("marca", ""),
            "modelo": product.get("modelo", ""),
            "extras": {k: product.get(k) for k in product.keys()
                       if k not in {"nombre", "descripcion", "categoria", "material", "tamano", "tamaño",
                                    "precio", "marca", "modelo", "imagen", "enlace"}},
            "ollama": {
                "enabled": bool(OLLAMA_ENABLED),
                "model": OLLAMA_MODEL,
                "format_json": bool(TRY_FORMAT_JSON),
                "temp": TEMPERATURE,
                "num_predict": NUM_PREDICT,
            }
        }
        key = sha1_key(cache_key_obj)

        method = "cache"
        enriched = None

        if key in cache:
            enriched = cache[key]
        else:
            method = "ollama"
            if OLLAMA_ENABLED:
                last_err = None
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        raw = ollama_enrich(product)
                        enriched = normalize_enriched(raw, product)
                        break
                    except Exception as e:
                        last_err = e
                        enriched = None
                if enriched is None:
                    method = "fallback"
                    errors.append({
                        "index": i,
                        "nombre": nombre,
                        "stage": "ollama_enrich",
                        "error": f"{type(last_err).__name__}: {last_err}",
                        "ts": now_utc_iso(),
                    })
                    enriched = fallback_enrich(product)
            else:
                method = "fallback"
                enriched = fallback_enrich(product)

            cache[key] = enriched

        out_item = dict(product)
        out_item.update(enriched or {})
        out_item["_meta"] = {
            "method": method,
            "ts": now_utc_iso(),
            "rules_v": RULES_VERSION,
            "ollama": {
                "enabled": bool(OLLAMA_ENABLED),
                "model": OLLAMA_MODEL,
                "format_json": bool(TRY_FORMAT_JSON),
            }
        }
        enriched_products.append(out_item)

        if PRINT_PROGRESS:
            print(f"[{i}/{n}] OK -> {nombre} [{method}]")

    # write files
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    errors_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

    catalog = {
        "generated_at": now_utc_iso(),
        "source_xml": xml_path.name,
        "ollama": {
            "enabled": bool(OLLAMA_ENABLED),
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
            "timeouts": {"connect": TIMEOUT_CONNECT, "read": TIMEOUT_READ},
            "try_format_json": bool(TRY_FORMAT_JSON),
        },
        "rules_v": RULES_VERSION,
        "count": len(enriched_products),
        "products": enriched_products,
    }
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nDONE")
    print(f"- {catalog_path.resolve()}")
    print(f"- {cache_path.resolve()}")
    print(f"- {errors_path.resolve()}")


if __name__ == "__main__":
    main()
