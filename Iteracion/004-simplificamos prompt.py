#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
001 (LITE) - Enriquecedor de catálogo OFFLINE (XML -> JSON) usando Ollama local.

Objetivo:
- Dado un XML con <productos><producto>...</producto></productos>
- Generar un catálogo enriquecido en JSON con campos extra:
  slug, short_desc, bullets, tags, seo_title, seo_description

Características:
- Genérico: funciona con cualquier tipo de producto (no hay "dominios").
- Offline-first: si Ollama falla, usa fallback determinista.
- Cache: evita recomputar productos ya enriquecidos.
- Prompt corto y estricto para reducir JSON roto/timeouts.

Salidas (editables en CONFIG):
- out/catalogo_enriquecido.json
- out/cache_enrichment.json
- out/errors.json
"""

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import requests


# =========================
# CONFIG (EDITA AQUÍ)
# =========================

# Entrada
XML_FILE = "productos3.xml"

# Carpeta de salida
OUT_DIR = "outv2"

# Nombres de salida (para que los puedas cambiar)
OUT_CATALOG_JSON = "catalogo_enriquecido.json"
OUT_CACHE_JSON   = "cache_enrichment.json"
OUT_ERRORS_JSON  = "errors.json"

# Ollama
OLLAMA_ENABLED = True
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Modelo (edítalo aquí)
OLLAMA_MODEL = "qwen2.5-coder:7b"  # también puedes probar: "llama3:latest", "qwen2.5-coder:7b", "phi3:mini"

# Prompt / opciones
TEMPERATURE = 0.2
NUM_PREDICT = 220  # menos tokens => menos timeouts / menos JSON roto (ajusta si quieres más detalle)

# Timeouts (en segundos)
TIMEOUT_CONNECT = 10
TIMEOUT_READ    = 240  # súbelo si tu PC va justo (p.ej. 360)

# Reintentos si la IA devuelve JSON roto
MAX_RETRIES = 1

# Algunos servidores/versions de Ollama soportan "format":"json".
# Si tu Ollama lo soporta, esto reduce muchísimo JSON roto.
# Si no lo soporta, el script detecta error y reintenta sin format.
TRY_OLLAMA_FORMAT_JSON = True

# Tags basura a eliminar (opcional)
STOP_TAGS = {"producto", "catalogo", "tienda", "oferta", "recomendado", "recomendable", "comprar", "venta"}


# =========================
# HELPERS
# =========================
def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(s: str, maxlen: int = 80) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return (s or "item")[:maxlen]


def tagify(s: str, maxlen: int = 40) -> str:
    # tag en minúsculas, con "_" en vez de "-"
    t = slugify(s, maxlen=maxlen).replace("-", "_")
    return t


def sha1_key(obj: dict) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def extract_json_block(text: str) -> str:
    """
    Extrae el bloque JSON más probable si el modelo mete texto extra.
    """
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()
    return text.strip()


def parse_productos_xml(xml_path: Path) -> list[dict]:
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    products = []
    for p in root.findall(".//producto"):
        item = {}
        for child in list(p):
            tag = (child.tag or "").strip()
            text = (child.text or "").strip()
            if tag and text:
                item[tag] = text
        if item:
            products.append(item)
    return products


# =========================
# OLLAMA
# =========================
def ollama_generate(model: str, system: str, prompt: str, read_timeout: int, num_predict: int, force_json_format: bool) -> str:
    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": TEMPERATURE,
            "num_predict": num_predict,
        }
    }

    # Intento opcional: pedir salida JSON “formal” si el servidor lo soporta
    if force_json_format:
        payload["format"] = "json"

    r = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=(TIMEOUT_CONNECT, read_timeout)
    )
    r.raise_for_status()
    data = r.json()
    return (data.get("response") or "").strip()


def ollama_enrich(product: dict) -> dict:
    """
    Devuelve dict con EXACTAMENTE:
    slug, short_desc, bullets(3), tags(max6), seo_title, seo_description

    Prompt corto y estricto => menos fallos y más rápido.
    """
    system = (
        "Devuelve SOLO JSON válido. Sin texto extra.\n"
        "Eres un asistente que redacta fichas cortas de catálogo web.\n"
        "No inventes especificaciones ni características que no estén en los datos.\n"
        "Si falta un dato, no lo menciones.\n"
    )

    # Base: siempre nombre/descripcion/categoria/material si existen
    nombre = product.get("nombre", "")
    descripcion = product.get("descripcion", "")
    categoria = product.get("categoria", "")
    material = product.get("material", "")

    # Extras: todo lo demás que venga en el XML
    extras = {k: v for k, v in product.items() if k not in {"nombre", "descripcion", "categoria", "material", "imagen", "enlace", "precio"}}

    brief = {
        "nombre": nombre,
        "descripcion": descripcion,
        "categoria": categoria,
        "material": material,
        "precio": product.get("precio", ""),
        "extras": extras
    }

    user = (
        "Genera una ficha corta para catálogo.\n"
        "Devuelve JSON con EXACTAMENTE estas claves:\n"
        "{"
        "\"slug\":\"\","
        "\"short_desc\":\"\","
        "\"bullets\":[\"\",\"\",\"\"],"
        "\"tags\":[\"\",\"\",\"\",\"\",\"\",\"\"],"
        "\"seo_title\":\"\","
        "\"seo_description\":\"\""
        "}\n"
        "Reglas:\n"
        "- Usa SOLO la info del producto.\n"
        "- bullets: exactamente 3, cortos.\n"
        "- tags: máximo 6, basados en categoria/material/extras (sin 'oferta' por defecto).\n"
        "- seo_title <= 60 chars, seo_description <= 160 chars.\n"
        f"Producto:\n{json.dumps(brief, ensure_ascii=False)}"
    )

    # 1) Intento con format=json (si está activado)
    if TRY_OLLAMA_FORMAT_JSON:
        try:
            txt = ollama_generate(
                model=OLLAMA_MODEL,
                system=system,
                prompt=user,
                read_timeout=TIMEOUT_READ,
                num_predict=NUM_PREDICT,
                force_json_format=True
            )
            # Cuando format=json está activo, normalmente el "response" ya es JSON directo.
            js = extract_json_block(txt)
            return json.loads(js)
        except Exception:
            # Si el servidor no soporta format=json o falla, reintentamos sin format.
            pass

    # 2) Intento normal (sin format)
    txt = ollama_generate(
        model=OLLAMA_MODEL,
        system=system,
        prompt=user,
        read_timeout=TIMEOUT_READ,
        num_predict=NUM_PREDICT,
        force_json_format=False
    )
    js = extract_json_block(txt)
    return json.loads(js)


# =========================
# FALLBACK OFFLINE (DETERMINISTA)
# =========================
def fallback_enrich(product: dict) -> dict:
    nombre = (product.get("nombre") or "").strip()
    descripcion = (product.get("descripcion") or "").strip()
    categoria = (product.get("categoria") or "").strip()
    material = (product.get("material") or "").strip()

    # Extras genéricos: cualquier otro campo (marca, modelo, talla, color, etc.)
    extras = {k: v for k, v in product.items() if k not in {"nombre", "descripcion", "categoria", "material", "imagen", "enlace"}}

    slug = slugify(nombre or "item")

    # bullets: solo cosas que EXISTEN
    bullets = []
    if categoria:
        bullets.append(f"Categoría: {categoria}.")
    if material:
        bullets.append(f"Material: {material}.")
    # si hay extras útiles, mete uno
    if extras:
        k = next(iter(extras.keys()))
        bullets.append(f"{k}: {extras[k]}.")

    # completa hasta 3 sin inventar
    while len(bullets) < 3:
        bullets.append("Ficha generada automáticamente a partir del XML.")

    # tags: de categoria/material + 1-2 extras
    tags = []
    if categoria:
        tags.append(tagify(categoria))
    if material:
        tags.append(tagify(material))
    for k, v in list(extras.items())[:2]:
        # usamos el valor si es más descriptivo
        tags.append(tagify(str(v)))

    # limpia duplicados
    tags = list(dict.fromkeys([t for t in tags if t]))[:6]

    short_desc = descripcion if descripcion else (nombre or "Producto")
    seo_title = (nombre or "Producto")[:60]
    seo_desc = short_desc[:160]

    return {
        "slug": slug,
        "short_desc": short_desc,
        "bullets": bullets[:3],
        "tags": tags,
        "seo_title": seo_title,
        "seo_description": seo_desc
    }


def normalize_ai_output(data: dict, product: dict) -> dict:
    """
    Normaliza el JSON que devuelve la IA para asegurar estructura estable.
    Si falta algo, lo rellenamos sin inventar.
    """
    nombre = (product.get("nombre") or "Producto").strip()

    out = dict(data) if isinstance(data, dict) else {}

    # slug
    out["slug"] = slugify(out.get("slug") or nombre)

    # short_desc
    sd = (out.get("short_desc") or "").strip()
    if not sd:
        sd = (product.get("descripcion") or nombre).strip()
    out["short_desc"] = sd[:220]

    # bullets (exactamente 3)
    bullets = out.get("bullets")
    if not isinstance(bullets, list):
        bullets = []
    bullets = [str(x).strip() for x in bullets if str(x).strip()]
    bullets = bullets[:3]
    while len(bullets) < 3:
        bullets.append("Información basada en el XML del producto.")
    out["bullets"] = bullets[:3]

    # tags (máx 6, sin basura)
    tags = out.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags = [tagify(str(x)) for x in tags if str(x).strip()]
    tags = [t for t in tags if t and t not in STOP_TAGS]
    # si se queda vacío, intentamos con categoria/material
    if not tags:
        cat = product.get("categoria", "")
        mat = product.get("material", "")
        seed = [tagify(cat), tagify(mat)]
        tags = [t for t in seed if t]
    out["tags"] = list(dict.fromkeys(tags))[:6]

    # seo_title / seo_description
    st = (out.get("seo_title") or "").strip()
    if not st:
        st = nombre
    out["seo_title"] = st[:60]

    sdesc = (out.get("seo_description") or "").strip()
    if not sdesc:
        sdesc = out["short_desc"]
    out["seo_description"] = sdesc[:160]

    # fuerza claves exactas (para que sea consistente)
    return {
        "slug": out["slug"],
        "short_desc": out["short_desc"],
        "bullets": out["bullets"],
        "tags": out["tags"],
        "seo_title": out["seo_title"],
        "seo_description": out["seo_description"]
    }


# =========================
# MAIN
# =========================
def main():
    xml_path = Path(XML_FILE)
    if not xml_path.exists():
        raise FileNotFoundError(f"No existe: {xml_path.resolve()}")

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = out_dir / OUT_CATALOG_JSON
    cache_path   = out_dir / OUT_CACHE_JSON
    errors_path  = out_dir / OUT_ERRORS_JSON

    # cache
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        cache = {}

    errors = []

    products = parse_productos_xml(xml_path)
    n = len(products)

    enriched_products = []

    for i, product in enumerate(products, start=1):
        nombre = product.get("nombre", f"producto_{i}")

        # cache key depende del producto y ajustes del modelo
        cache_key_obj = {
            "v": 1,
            "product": product,
            "ollama_enabled": bool(OLLAMA_ENABLED),
            "ollama_model": OLLAMA_MODEL,
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
        }
        key = sha1_key(cache_key_obj)

        if key in cache:
            enriched = cache[key]
            method = "cache"
        else:
            enriched = None
            method = None

            if OLLAMA_ENABLED:
                last_err = None
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        raw = ollama_enrich(product)
                        enriched = normalize_ai_output(raw, product)
                        method = "ollama"
                        break
                    except Exception as e:
                        last_err = e

                if enriched is None:
                    errors.append({
                        "index": i,
                        "stage": "enrich",
                        "nombre": nombre,
                        "error": str(last_err),
                        "ts": now_utc_iso()
                    })
                    enriched = fallback_enrich(product)
                    method = "fallback"
            else:
                enriched = fallback_enrich(product)
                method = "fallback"

            cache[key] = enriched

        # merge
        out_item = dict(product)
        out_item.update(enriched)
        out_item["_meta"] = {
            "method": method
        }

        enriched_products.append(out_item)

        print(f"[{i}/{n}] OK -> {nombre} [{method}]")

    # escribe salidas
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
            "timeouts": {
                "connect": TIMEOUT_CONNECT,
                "read": TIMEOUT_READ
            },
            "try_format_json": bool(TRY_OLLAMA_FORMAT_JSON)
        },
        "count": len(enriched_products),
        "products": enriched_products
    }
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nDONE")
    print(f"- {catalog_path.resolve()}")
    print(f"- {cache_path.resolve()}")
    print(f"- {errors_path.resolve()}")


if __name__ == "__main__":
    main()
