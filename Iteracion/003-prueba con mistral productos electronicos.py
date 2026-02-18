#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML (productos) -> catálogo enriquecido (JSON) + cache + errores

- Offline-first: funciona con heurísticas y solo usa Ollama si está disponible.
- Dominios soportados: 3d_printing, yarn_crafts, apparel, footwear, generic
- Salidas:
  - OUT_CATALOG_FILE
  - OUT_CACHE_FILE
  - OUT_ERRORS_FILE
"""

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import requests


# =========================
# CONFIG
# =========================
XML_FILE = "productos3.xml"
OUT_DIR = "out"

# ✅ NOMBRES DE SALIDA (EDITABLES)
OUT_CATALOG_FILE = "catalogo_enriquecido3.json"
OUT_CACHE_FILE = "cache_enrichment3.json"
OUT_ERRORS_FILE = "errors3.json"

# --- Ollama ---
OLLAMA_ENABLED = True
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Puedes usar 2 modelos distintos (rápido para classify, mejor para enrich)
OLLAMA_MODEL_CLASSIFY = "phi3:mini"         # rápido
OLLAMA_MODEL_ENRICH = "mistral:instruct"    # más capaz en JSON (puedes cambiarlo)

# Ajustes de salida (para evitar timeouts)
TEMPERATURE = 0.2
NUM_PREDICT_CLASSIFY = 120   # menos tokens -> más rápido
NUM_PREDICT_ENRICH = 220     # menos tokens -> reduce timeouts

# Timeouts (connect, read)
TIMEOUT_CONNECT = 10
TIMEOUT_CLASSIFY_READ = 60
TIMEOUT_ENRICH_READ = 240    # antes 120; subimos para evitar cortes

MAX_RETRIES = 1  # reintento simple si el JSON sale roto o se corta


# =========================
# HELPERS
# =========================
def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(s: str, maxlen: int = 80) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", s="-", repl="-") if False else re.sub(r"[\s_-]+", "-", s)
    s = s.strip("-")
    return (s or "item")[:maxlen]


def extract_json_block(text: str) -> str:
    """Extrae el bloque JSON más probable si el modelo mete texto extra."""
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text.strip()


def sha1_key(obj: dict) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def norm_text(*parts: str) -> str:
    return " ".join([p.strip().lower() for p in parts if p]).strip()


# =========================
# DOMAIN DETECTION (HEURISTIC FIRST)
# =========================
# IMPORTANT: usamos regex con límites de palabra para evitar:
#   "plata" -> NO debe hacer match con "pla"
RE_MATERIAL_3D = re.compile(r"\b(pla|petg|abs|asa|resina|resin)\b", re.IGNORECASE)

YARN_HINTS = (
    "lana", "ovillo", "hilo", "merino", "alpaca", "algodón", "algodon",
    "chenille", "amigurumi", "crochet", "ganchillo", "tejer", "punto"
)

FOOTWEAR_HINTS = ("zapatilla", "zapato", "talla", "suela", "sneaker")


def detect_domain_heuristic(product: dict) -> dict | None:
    """
    Devuelve domain_info o None si no está claro.
    """
    nombre = str(product.get("nombre", ""))
    desc = str(product.get("descripcion", ""))
    material = str(product.get("material", ""))
    categoria = str(product.get("categoria", ""))

    blob = norm_text(nombre, desc, material, categoria)

    # --- 3D printing ---
    if (
        RE_MATERIAL_3D.search(blob)
        or "impresion 3d" in blob
        or "impresión 3d" in blob
        or "impreso en 3d" in blob
        or "impresa en 3d" in blob
    ):
        return {
            "domain": "3d_printing",
            "confidence": 0.95,
            "signals": ["material/keywords 3d"],
            "method": "heuristic"
        }

    # --- Yarn / Crafts ---
    if any(k in product for k in ("grosor", "metros", "lavado", "color")):
        return {
            "domain": "yarn_crafts",
            "confidence": 0.95,
            "signals": ["fields: grosor/metros/lavado/color"],
            "method": "heuristic"
        }
    if any(h in blob for h in YARN_HINTS):
        return {
            "domain": "yarn_crafts",
            "confidence": 0.9,
            "signals": ["keywords yarn/crafts"],
            "method": "heuristic"
        }

    # --- Footwear ---
    if any(h in blob for h in FOOTWEAR_HINTS):
        return {
            "domain": "footwear",
            "confidence": 0.85,
            "signals": ["keywords footwear"],
            "method": "heuristic"
        }

    return None


# =========================
# OLLAMA CALLS (MINIMAL PROMPTS)
# =========================
def ollama_generate(model: str, system: str, prompt: str, read_timeout: int, num_predict: int) -> str:
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
    r = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=(TIMEOUT_CONNECT, read_timeout)
    )
    r.raise_for_status()
    data = r.json()
    return (data.get("response") or "").strip()


def ollama_classify_domain(product: dict) -> dict:
    """
    Devuelve {"domain","confidence","signals","method"} con JSON.
    """
    system = (
        "Devuelve SOLO JSON válido. Sin texto extra.\n"
        "Eres un clasificador de dominio de producto para un catálogo.\n"
        "Dominios permitidos: 3d_printing, yarn_crafts, apparel, footwear, generic.\n"
        "Usa yarn_crafts para lanas/ovillos/hilos/tejer/crochet/amigurumi.\n"
        "Usa 3d_printing para PLA/PETG/Resina/impresión 3D.\n"
    )

    brief = {
        "nombre": product.get("nombre", ""),
        "descripcion": product.get("descripcion", ""),
        "categoria": product.get("categoria", ""),
        "material": product.get("material", ""),
        "extras": {k: product.get(k) for k in ("grosor", "metros", "lavado", "color", "tamano") if k in product}
    }

    user = (
        "Clasifica el dominio del siguiente producto.\n"
        "Responde con JSON:\n"
        '{"domain":"...","confidence":0.0,"signals":["..."]}\n'
        f"Producto:\n{json.dumps(brief, ensure_ascii=False)}"
    )

    txt = ollama_generate(
        model=OLLAMA_MODEL_CLASSIFY,
        system=system,
        prompt=user,
        read_timeout=TIMEOUT_CLASSIFY_READ,
        num_predict=NUM_PREDICT_CLASSIFY
    )
    js = extract_json_block(txt)
    out = json.loads(js)

    domain = out.get("domain") or "generic"
    conf = float(out.get("confidence") or 0.0)
    signals = out.get("signals") or []
    return {
        "domain": domain,
        "confidence": conf,
        "signals": signals[:6],
        "method": "ollama_classify"
    }


def ollama_enrich(product: dict, domain: str) -> dict:
    """
    Enriquecimiento con JSON compacto.
    """
    system = (
        "Devuelve SOLO JSON válido. Sin texto extra.\n"
        "Eres un generador de fichas de producto para un catálogo.\n"
        "No inventes datos técnicos (no inventes medidas si no existen).\n"
        "Usa bullets concretos basados en nombre/descripcion/material/campos.\n"
    )

    brief = {
        "domain": domain,
        "nombre": product.get("nombre", ""),
        "descripcion": product.get("descripcion", ""),
        "categoria": product.get("categoria", ""),
        "material": product.get("material", ""),
        "precio": product.get("precio", ""),
        "extras": {k: product.get(k) for k in ("tamano", "grosor", "metros", "lavado", "color") if k in product}
    }

    user = (
        "Genera un enriquecimiento corto.\n"
        "Devuelve JSON con EXACTAMENTE estas claves:\n"
        '{'
        '"slug":"",'
        '"short_desc":"",'
        '"bullets":["","",""],'
        '"tags":["",""],'
        '"seo_title":"",'
        '"seo_description":"",'
        '"faq":[{"q":"","a":""},{"q":"","a":""}]'
        '}\n'
        "Reglas:\n"
        "- bullets: 3 items, cortos.\n"
        "- tags: 6 a 10 tags max, sin palabras tipo 'oferta' por defecto.\n"
        "- seo_title <= 60 chars, seo_description <= 160 chars.\n"
        f"Producto:\n{json.dumps(brief, ensure_ascii=False)}"
    )

    txt = ollama_generate(
        model=OLLAMA_MODEL_ENRICH,
        system=system,
        prompt=user,
        read_timeout=TIMEOUT_ENRICH_READ,
        num_predict=NUM_PREDICT_ENRICH
    )
    js = extract_json_block(txt)
    data = json.loads(js)

    # normalizaciones mínimas
    data["slug"] = slugify(data.get("slug") or product.get("nombre") or "item")

    bullets = data.get("bullets") or []
    if not isinstance(bullets, list):
        bullets = []
    data["bullets"] = [str(x).strip() for x in bullets][:3]

    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    data["tags"] = [slugify(str(x), 40).replace("-", "_") for x in tags][:10]

    return data


# =========================
# FALLBACK ENRICH (OFFLINE)
# =========================
def fallback_enrich(product: dict, domain: str) -> dict:
    nombre = str(product.get("nombre", "")).strip()
    desc = str(product.get("descripcion", "")).strip()
    categoria = str(product.get("categoria", "")).strip()
    material = str(product.get("material", "")).strip()

    slug = slugify(nombre)

    bullets = []
    tags = []

    if domain == "yarn_crafts":
        grosor = str(product.get("grosor", "")).strip()
        metros = str(product.get("metros", "")).strip()
        lavado = str(product.get("lavado", "")).strip()
        color = str(product.get("color", "")).strip()

        if grosor:
            bullets.append(f"Grosor: {grosor}.")
            tags.append(slugify(grosor, 30))
        if metros:
            bullets.append(f"Metraje aprox.: {metros} m.")
            tags.append(slugify(f"{metros}m", 30))
        if lavado:
            bullets.append(f"Cuidado: {lavado}.")
            tags.append("lavado")

        if color:
            tags.append(slugify(color, 30))
        if material:
            tags.append(slugify(material, 30))
        if categoria:
            tags.append(slugify(categoria, 30))

        while len(bullets) < 3:
            bullets.append("Ideal para proyectos de punto y crochet.")

    elif domain == "3d_printing":
        tamano = str(product.get("tamano", "")).strip()
        bullets = [
            "Pieza pensada para impresión 3D.",
            f"Material: {material or 'N/D'}.",
            f"Tamaño: {tamano or 'N/D'}."
        ]
        tags = [slugify(x, 30) for x in (categoria, material, tamano) if x]
        tags += ["3d_printing"]

    else:
        bullets = [
            "Producto listo para catálogo.",
            f"Categoría: {categoria or 'N/D'}.",
            f"Material: {material or 'N/D'}."
        ]
        tags = [slugify(x, 30) for x in (categoria, material) if x]
        if not tags:
            tags = ["catalogo"]

    short_desc = desc if desc else f"{nombre} ({categoria})"
    seo_title = nombre[:60]
    seo_desc = (desc or short_desc)[:160]

    return {
        "slug": slug,
        "short_desc": short_desc,
        "bullets": bullets[:3],
        "tags": list(dict.fromkeys(tags))[:10],
        "seo_title": seo_title,
        "seo_description": seo_desc,
        "faq": [
            {"q": "¿Para qué sirve?", "a": short_desc},
            {"q": "¿Qué incluye la compra?", "a": "El producto descrito en la ficha."}
        ]
    }


# =========================
# XML LOAD
# =========================
def parse_productos_xml(xml_path: Path) -> list[dict]:
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    products = []
    for p in root.findall(".//producto"):
        item = {}
        for child in list(p):
            tag = child.tag.strip()
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

    # ✅ ahora salen desde CONFIG
    cache_path = out_dir / OUT_CACHE_FILE
    errors_path = out_dir / OUT_ERRORS_FILE
    catalog_path = out_dir / OUT_CATALOG_FILE

    # load cache
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

        # 1) Domain detection
        domain_info = detect_domain_heuristic(product)
        if domain_info is None and OLLAMA_ENABLED:
            try:
                domain_info = ollama_classify_domain(product)
            except Exception as e:
                domain_info = {
                    "domain": "generic",
                    "confidence": 0.0,
                    "signals": [f"classify_error: {type(e).__name__}"],
                    "method": "fallback"
                }
                errors.append({
                    "index": i,
                    "stage": "classify",
                    "nombre": nombre,
                    "error": str(e),
                    "ts": now_utc_iso()
                })

        if domain_info is None:
            domain_info = {"domain": "generic", "confidence": 0.0, "signals": ["unknown"], "method": "fallback"}

        domain = domain_info["domain"]

        # 2) Cache key
        cache_key_obj = {
            "v": 2,
            "domain": domain,
            "nombre": product.get("nombre", ""),
            "descripcion": product.get("descripcion", ""),
            "categoria": product.get("categoria", ""),
            "material": product.get("material", ""),
            "extras": {k: product.get(k) for k in ("tamano", "grosor", "metros", "lavado", "color") if k in product},
            "model": OLLAMA_MODEL_ENRICH if OLLAMA_ENABLED else "none"
        }
        key = sha1_key(cache_key_obj)

        # 3) Enrich (cache -> ollama -> fallback)
        if key in cache:
            cached = cache[key]
            domain_info = cached.get("domain_info", domain_info)
            enriched = cached.get("enriched", {})
            method = "cache"
        else:
            enriched = None
            method = None

            if OLLAMA_ENABLED:
                last_err = None
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        enriched = ollama_enrich(product, domain)
                        method = "ollama_enrich"
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
                    enriched = fallback_enrich(product, domain)
                    method = "fallback"

            else:
                enriched = fallback_enrich(product, domain)
                method = "fallback"

            cache[key] = {"domain_info": domain_info, "enriched": enriched}

        # 4) Merge into product
        out_item = dict(product)
        out_item["_domain"] = domain_info
        out_item.update(enriched)

        enriched_products.append(out_item)

        print(f"[{i}/{n}] OK -> {nombre} | domain={domain} ({domain_info.get('method','?')}) [{method}]")

    # write files (con nombres configurables)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    errors_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")

    catalog = {
        "generated_at": now_utc_iso(),
        "source_xml": xml_path.name,
        "ollama": {
            "enabled": bool(OLLAMA_ENABLED),
            "url": OLLAMA_URL,
            "model": {"classify": OLLAMA_MODEL_CLASSIFY, "enrich": OLLAMA_MODEL_ENRICH},
            "temperature": TEMPERATURE,
            "num_predict": {"classify": NUM_PREDICT_CLASSIFY, "enrich": NUM_PREDICT_ENRICH},
            "timeouts": {
                "connect": TIMEOUT_CONNECT,
                "classify_read": TIMEOUT_CLASSIFY_READ,
                "enrich_read": TIMEOUT_ENRICH_READ
            }
        },
        "domain_mode": "auto",
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
