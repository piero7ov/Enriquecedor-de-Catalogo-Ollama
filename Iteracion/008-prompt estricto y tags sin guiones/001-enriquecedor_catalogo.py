#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
001 / Script:
XML (productos) -> catálogo enriquecido (JSON) + cache + errores

✅ Objetivo:
- Leer productos desde un XML (cualquier temática).
- Generar un JSON enriquecido (slug, short_desc, bullets, tags, seo_*).
- Guardar cache para no “re-preguntar” a Ollama si el producto no cambió.
- Si Ollama falla o devuelve JSON roto => fallback automático.

Salidas (configurables):
  OUT_DIR/OUTPUT_CATALOG_JSON
  OUT_DIR/OUTPUT_CACHE_JSON
  OUT_DIR/OUTPUT_ERRORS_JSON
"""

from __future__ import annotations

import json
import re
import hashlib
import unicodedata
from pathlib import Path
from datetime import datetime, timezone

import xml.etree.ElementTree as ET
import requests


# =========================
# CONFIG (EDITA AQUÍ)
# =========================
XML_FILE = "productos3d.xml"
OUT_DIR = "out"

# ✅ Nombres de salida (editables)
OUTPUT_CATALOG_JSON = "catalogo_enriquecido.json"
OUTPUT_CACHE_JSON = "cache_enrichment.json"
OUTPUT_ERRORS_JSON = "errors.json"

# --- Ollama ---
OLLAMA_ENABLED = True
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5-coder:7b"

# Ajustes para estabilidad
TEMPERATURE = 0.2
NUM_PREDICT = 260

# Timeouts (connect, read)
TIMEOUT_CONNECT = 10
TIMEOUT_READ = 240

# Si True, añade "format":"json" al payload (muy recomendable)
TRY_FORMAT_JSON = True

# Reintentos si sale JSON roto
MAX_RETRIES = 1


# =========================
# HELPERS
# =========================
def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def strip_accents(s: str) -> str:
    s = str(s or "")
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def norm_for_compare(s: str) -> str:
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def slugify(s: str, maxlen: int = 80) -> str:
    s = strip_accents(s).strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return (s or "item")[:maxlen]


def snake_tag(s: str, maxlen: int = 32) -> str:
    """
    Tag 'machine-friendly' tipo snake_case (para JSON / filtros).
    En la web lo “bonito” se hace en 002.
    """
    s = strip_accents(s).strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "_", s).strip("_")
    return (s or "")[:maxlen]


def extract_json_block(text: str) -> str:
    """
    Extrae el bloque JSON más probable si el modelo mete texto extra.
    """
    if not text:
        return ""
    text = text.strip()

    # si ya parece JSON puro
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def sha1_key(obj: dict) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def is_empty(v) -> bool:
    return v is None or str(v).strip() == ""


def compact_whitespace(s: str) -> str:
    s = str(s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


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
        timeout=(TIMEOUT_CONNECT, TIMEOUT_READ),
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
        "Devuelve SOLO JSON válido. Sin texto extra.\n"
        "Eres un generador de metadatos para fichas de producto.\n"
        "Idioma: español.\n"
        "NO inventes datos técnicos: si no está en el input, no lo afirmes.\n"
    )

    # “brief” corto (para reducir errores)
    brief = {
        "nombre": product.get("nombre", ""),
        "descripcion": product.get("descripcion", ""),
        "categoria": product.get("categoria", ""),
        "material": product.get("material", ""),
        "precio": product.get("precio", ""),
        "marca": product.get("marca", ""),
        "modelo": product.get("modelo", ""),
        # extras: cualquier campo adicional que venga del XML
        "extras": {k: product.get(k) for k in list(product.keys()) if k not in {
            "nombre", "descripcion", "categoria", "material", "precio", "marca", "modelo", "imagen", "enlace"
        }}
    }

    # Prompt más estricto para “bullets” (beneficios / no copia literal)
    prompt = (
        "Genera un enriquecimiento útil y NO redundante.\n"
        "Reglas importantes:\n"
        "- short_desc: 1 frase (12–22 palabras). Parafrasea la descripcion (no copies literal).\n"
        "- bullets: EXACTAMENTE 3 items, 3–6 palabras cada uno.\n"
        "  * Deben sonar a BENEFICIO (ej: 'Postura más saludable', 'Espacio libre en escritorio').\n"
        "  * No repitas la misma idea que short_desc palabra-por-palabra.\n"
        "  * No uses verbos en infinitivo tipo 'Mejorar', 'Elevar', 'Ahorrar' (prefiere sustantivos/frases).\n"
        "- tags: 6–10 tags en snake_case (sin tildes, sin espacios). Incluye categoria/marca/material si existe.\n"
        "- seo_title: <= 60 chars. seo_description: <= 160 chars.\n"
        "- slug: kebab-case, idealmente incluye marca si existe.\n"
        "Devuelve JSON EXACTO con estas claves:\n"
        "{"
        "\"slug\":\"\","
        "\"short_desc\":\"\","
        "\"bullets\":[\"\",\"\",\"\"],"
        "\"tags\":[\"\"],"
        "\"seo_title\":\"\","
        "\"seo_description\":\"\""
        "}\n"
        f"Producto:\n{json.dumps(brief, ensure_ascii=False)}"
    )

    txt = ollama_generate(system=system, prompt=prompt)
    js = extract_json_block(txt)
    return json.loads(js)


def try_repair_json(bad_text: str) -> dict | None:
    """
    Si el modelo devuelve JSON roto, intentamos 1 reparación:
    “arregla y devuelve JSON válido”.
    """
    system = "Devuelve SOLO JSON válido. Sin texto extra."
    prompt = (
        "El siguiente JSON está roto o incompleto.\n"
        "Devuélvelo corregido como JSON válido con la MISMA estructura.\n"
        f"JSON roto:\n{bad_text}"
    )
    try:
        txt = ollama_generate(system=system, prompt=prompt)
        js = extract_json_block(txt)
        return json.loads(js)
    except Exception:
        return None


# =========================
# POST-PROCESS (ANTI-REDUNDANCIA)
# =========================
def normalize_enrichment(product: dict, enrich: dict) -> dict:
    nombre = str(product.get("nombre", "")).strip()
    marca = str(product.get("marca", "")).strip()
    desc_src = str(product.get("descripcion", "")).strip()

    # slug
    slug = enrich.get("slug") or (nombre + (" " + marca if marca else ""))
    slug = slugify(slug)

    # short_desc
    short_desc = compact_whitespace(enrich.get("short_desc") or "")
    if not short_desc:
        short_desc = compact_whitespace(desc_src) or nombre

    # bullets
    bullets_raw = enrich.get("bullets")
    bullets: list[str] = []
    if isinstance(bullets_raw, list):
        for b in bullets_raw:
            b = compact_whitespace(b)
            if b:
                bullets.append(b)

    # dedupe bullets + quita bullets demasiado iguales a short_desc/descripcion
    def is_redundant(b: str) -> bool:
        bn = norm_for_compare(b)
        if not bn:
            return True
        sn = norm_for_compare(short_desc)
        dn = norm_for_compare(desc_src)
        # si el bullet está casi totalmente contenido en short_desc/descripcion, lo consideramos redundante
        if bn and sn and bn in sn:
            return True
        if bn and dn and bn in dn:
            return True
        return False

    dedup = []
    seen = set()
    for b in bullets:
        bn = norm_for_compare(b)
        if not bn or bn in seen:
            continue
        if is_redundant(b):
            continue
        seen.add(bn)
        dedup.append(b)

    bullets = dedup[:3]

    # si quedaron < 3, completamos con fallback “no inventado” usando campos existentes
    if len(bullets) < 3:
        bullets = fill_bullets_from_fields(product, bullets, target=3)

    # tags
    tags_raw = enrich.get("tags")
    tags: list[str] = []
    if isinstance(tags_raw, list):
        for t in tags_raw:
            t = snake_tag(str(t))
            if t:
                tags.append(t)

    # fuerza tags útiles desde campos presentes
    for extra in (product.get("categoria"), product.get("material"), product.get("marca"), product.get("modelo")):
        t = snake_tag(str(extra or ""))
        if t:
            tags.append(t)

    # dedupe tags
    tags = list(dict.fromkeys([t for t in tags if t]))[:10]

    # seo
    seo_title = compact_whitespace(enrich.get("seo_title") or "")
    if not seo_title:
        seo_title = f"{nombre} {marca}".strip() if marca else nombre
    seo_title = seo_title[:60]

    seo_desc = compact_whitespace(enrich.get("seo_description") or "")
    if not seo_desc:
        seo_desc = (desc_src or short_desc or nombre)[:160]
    seo_desc = seo_desc[:160]

    return {
        "slug": slug,
        "short_desc": short_desc,
        "bullets": bullets[:3],
        "tags": tags,
        "seo_title": seo_title,
        "seo_description": seo_desc,
    }


def fill_bullets_from_fields(product: dict, current: list[str], target: int = 3) -> list[str]:
    """
    Completa bullets SIN inventar, basándose en campos reales.
    """
    bullets = list(current)

    def add_if(text: str):
        if len(bullets) >= target:
            return
        t = compact_whitespace(text)
        if not t:
            return
        tn = norm_for_compare(t)
        if any(norm_for_compare(x) == tn for x in bullets):
            return
        bullets.append(t)

    # Señales típicas (genéricas)
    nombre = str(product.get("nombre", "")).lower()
    desc = str(product.get("descripcion", "")).lower()
    material = str(product.get("material", "")).strip()
    categoria = str(product.get("categoria", "")).strip()

    # 3D
    if any(x in (material.lower() + " " + desc + " " + nombre) for x in ["pla", "petg", "abs", "asa", "resina", "impreso en 3d", "impresion 3d", "impresión 3d"]):
        add_if("Impresión 3D precisa")
    if material:
        add_if(f"Material: {material}")
    if categoria:
        add_if(f"Categoría: {categoria}")

    # Electrónica (si hay campos)
    if not is_empty(product.get("bateria_horas")):
        add_if(f"Autonomía: {product.get('bateria_horas')} h")
    if not is_empty(product.get("capacidad_mah")):
        add_if(f"Capacidad: {product.get('capacidad_mah')} mAh")
    if not is_empty(product.get("conectividad")):
        add_if(f"Conectividad: {product.get('conectividad')}")
    if not is_empty(product.get("conexion")):
        add_if(f"Conexión: {product.get('conexion')}")

    # Si aún faltan, usa 1–2 frases genéricas “seguras”
    add_if("Listo para usar")
    add_if("Diseño funcional")

    return bullets[:target]


# =========================
# MAIN
# =========================
def main():
    xml_path = Path(XML_FILE)
    if not xml_path.exists():
        raise FileNotFoundError(f"No existe: {xml_path.resolve()}")

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = out_dir / OUTPUT_CATALOG_JSON
    cache_path = out_dir / OUTPUT_CACHE_JSON
    errors_path = out_dir / OUTPUT_ERRORS_JSON

    # load cache
    cache: dict = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    errors: list[dict] = []
    products = parse_productos_xml(xml_path)
    n = len(products)

    enriched_products: list[dict] = []

    for i, product in enumerate(products, start=1):
        nombre = product.get("nombre", f"producto_{i}")

        # clave de cache basada en contenido real del producto
        cache_key_obj = {
            "v": 3,
            "model": OLLAMA_MODEL if OLLAMA_ENABLED else "none",
            "nombre": product.get("nombre", ""),
            "descripcion": product.get("descripcion", ""),
            "categoria": product.get("categoria", ""),
            "material": product.get("material", ""),
            "marca": product.get("marca", ""),
            "modelo": product.get("modelo", ""),
            "extras": {k: product.get(k) for k in sorted(product.keys()) if k not in {
                "nombre", "descripcion", "categoria", "material", "precio", "marca", "modelo", "imagen", "enlace"
            }},
        }
        key = sha1_key(cache_key_obj)

        if key in cache:
            enrich_norm = cache[key]
            method = "cache"
        else:
            method = "fallback"
            enrich_norm = None

            if OLLAMA_ENABLED:
                last_err = None
                raw_txt = ""
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        enrich_raw = ollama_enrich(product)
                        enrich_norm = normalize_enrichment(product, enrich_raw)
                        method = "ollama"
                        break
                    except Exception as e:
                        last_err = e
                        # Intento de reparación si tenemos texto “algo”
                        try:
                            if raw_txt:
                                repaired = try_repair_json(raw_txt)
                                if repaired is not None:
                                    enrich_norm = normalize_enrichment(product, repaired)
                                    method = "ollama_repair"
                                    break
                        except Exception:
                            pass

                        # Si falló parse, probamos capturar algo para repair
                        try:
                            raw_txt = str(e)
                        except Exception:
                            raw_txt = ""

                if enrich_norm is None:
                    errors.append({
                        "index": i,
                        "stage": "enrich",
                        "nombre": nombre,
                        "error": str(last_err),
                        "ts": now_utc_iso(),
                    })
                    # fallback
                    enrich_norm = normalize_enrichment(product, {
                        "slug": "",
                        "short_desc": "",
                        "bullets": [],
                        "tags": [],
                        "seo_title": "",
                        "seo_description": "",
                    })
                    method = "fallback"
            else:
                enrich_norm = normalize_enrichment(product, {
                    "slug": "",
                    "short_desc": "",
                    "bullets": [],
                    "tags": [],
                    "seo_title": "",
                    "seo_description": "",
                })
                method = "fallback"

            cache[key] = enrich_norm

        out_item = dict(product)
        out_item.update(enrich_norm)
        out_item["_meta"] = {"method": method}
        enriched_products.append(out_item)

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
