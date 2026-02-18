#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
============================================================
- Input: productos.xml con estructura <productos><producto>...</producto></productos>
- Detecta dominio/tipo de producto (3d_printing, footwear, apparel, electronics, food, service, generic)
  * Heurística primero (rápido)
  * Si hay duda: micro-llamada a Ollama para clasificar (JSON corto)
- Enriquecimiento por producto con Ollama (JSON corto):
  slug, short_desc, bullets, tags, seo_title, seo_description, faq
- Output:
  out/catalogo_enriquecido.json
  out/cache_enrichment.json (caché)
  out/errors.json (errores)
============================================================
"""

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import requests


# ============================================================
# CONFIG (EDITA AQUÍ)
# ============================================================
XML_FILE = "productos2.xml"
OUT_DIR = "out"

# Ollama (LOCAL)
USE_OLLAMA = True
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5-coder:7b"   # recomendado para JSON/estructura

# Timeouts (segundos) - por producto (micro llamadas)
OLLAMA_CONNECT_TIMEOUT = 10
OLLAMA_READ_TIMEOUT_CLASSIFY = 60     # clasificación (rápido)
OLLAMA_READ_TIMEOUT_ENRICH = 120      # enriquecimiento
# Si tu PC va lento: sube a 180

# Control de salida (para que NO se enrolle)
OLLAMA_TEMPERATURE = 0.2
OLLAMA_NUM_PREDICT_CLASSIFY = 160
OLLAMA_NUM_PREDICT_ENRICH = 320

# Dominio
DOMAIN_MODE = "auto"   # "auto" o fija uno: "3d_printing", "footwear", "apparel", ...

# Salidas
OUT_JSON = "catalogo_enriquecido2.json"
CACHE_FILE = "cache_enrichment2.json"
ERRORS_FILE = "errors2.json"

# Límites de calidad
MAX_BULLETS = 5
MAX_TAGS = 10
FAQ_COUNT_MIN = 2
FAQ_COUNT_MAX = 3

# Si heurística no llega a este umbral, pedimos clasificación a Ollama
HEURISTIC_CONF_THRESHOLD = 0.70
# ============================================================


# =========================
# Utils
# =========================
def safe_text(s: str) -> str:
    return (s or "").strip()


def slugify_ascii(s: str, maxlen: int = 70) -> str:
    s = safe_text(s).lower()
    repl = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for a, b in repl.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return (s or "producto")[:maxlen]


def sha1_key(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def try_extract_json(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""

    # Quitar fences
    if "```" in t:
        parts = t.split("```")
        for p in parts:
            p2 = p.strip()
            if p2.startswith("{") and p2.endswith("}"):
                t = p2
                break

    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    return t


def parse_json_strict(text: str) -> dict:
    js = try_extract_json(text)
    if not js:
        return {}
    return json.loads(js)


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_utc_iso():
    # ISO en UTC con timezone-aware + formato Z
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# =========================
# Parse XML (flexible)
# =========================
def parse_productos_xml(xml_path: Path) -> list[dict]:
    """
    Lee <productos><producto>... y mete TODOS los tags hijos como campos.
    Así funciona igual para 3D, zapatillas, ropa, etc.
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    productos = []
    for p in root.findall("./producto"):
        item = {}
        for ch in list(p):
            key = ch.tag.strip()
            val = safe_text(ch.text or "")
            if key:
                item[key] = val

        # Normalizamos nombres comunes (si existen)
        # (No obliga, solo ayuda a que el resto tenga claves típicas)
        if "nombre" not in item:
            item["nombre"] = item.get("name", "")

        if "descripcion" not in item:
            item["descripcion"] = item.get("description", "")

        # descarta vacíos
        if safe_text(item.get("nombre", "")) or safe_text(item.get("descripcion", "")):
            productos.append(item)

    return productos


# =========================
# Detección de dominio (heurística)
# =========================
def heuristic_domain(prod: dict) -> tuple[str, float, list[str]]:
    """
    Devuelve (domain, confidence, signals)
    domain in: 3d_printing, footwear, apparel, electronics, food, service, generic
    """
    text = " ".join([
        safe_text(prod.get("nombre", "")),
        safe_text(prod.get("descripcion", "")),
        safe_text(prod.get("categoria", "")),
        safe_text(prod.get("material", "")),
        safe_text(prod.get("tamano", "")),
        safe_text(prod.get("talla", "")),
        safe_text(prod.get("numero", "")),
        safe_text(prod.get("color", "")),
        safe_text(prod.get("marca", "")),
    ]).lower()

    signals = []

    # 3D printing muy claro por materiales típicos
    if any(k in text for k in ["pla", "petg", "resina", "abs", "filamento", "impreso en 3d", "impresion 3d", "stl"]):
        signals.append("material/keywords 3d")
        return "3d_printing", 0.95, signals

    # Footwear (zapatillas)
    footwear_kw = ["zapatill", "sneaker", "running", "suela", "cordones", "plantilla", "amortigu", "pisada", "trail"]
    if any(k in text for k in footwear_kw) or re.search(r"\b(eu\s*)?\d{2}\b", text):
        signals.append("keywords/talla footwear")
        return "footwear", 0.85, signals

    # Apparel (ropa)
    apparel_kw = ["camiseta", "sudadera", "pantalon", "chaqueta", "talla s", "talla m", "talla l", "algodon", "poliester"]
    if any(k in text for k in apparel_kw) or "talla" in text:
        signals.append("keywords talla apparel")
        return "apparel", 0.75, signals

    # Electronics
    elec_kw = ["usb", "bluetooth", "cargador", "bateria", "volt", "watt", "hz", "compatible con", "smartphone", "auricular"]
    if any(k in text for k in elec_kw):
        signals.append("keywords electronics")
        return "electronics", 0.70, signals

    # Food
    food_kw = ["ingrediente", "alergen", "sabor", "kcal", "gramos", "gluten", "vegano", "sin azucar"]
    if any(k in text for k in food_kw):
        signals.append("keywords food")
        return "food", 0.70, signals

    # Service
    service_kw = ["servicio", "suscripcion", "mantenimiento", "instalacion", "consultoria", "clases", "reserva"]
    if any(k in text for k in service_kw):
        signals.append("keywords service")
        return "service", 0.70, signals

    return "generic", 0.40, ["no strong signals"]


# =========================
# Ollama: clasificación (micro)
# =========================
def ollama_classify(prod: dict) -> dict:
    system = (
        "DEVUELVE SOLO JSON válido. Sin markdown. Sin texto extra.\n"
        "Clasifica el producto en un dominio.\n"
        "Dominios permitidos: 3d_printing, footwear, apparel, electronics, food, service, generic.\n"
    )

    user = (
        f"Producto:\n{json.dumps(prod, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "Devuelve JSON EXACTO:\n"
        "{"
        "\"domain\":\"generic\","
        "\"confidence\":0.0,"
        "\"signals\":[\"...\"]"
        "}\n"
        "Reglas:\n"
        "- domain debe ser UNO de los permitidos.\n"
        "- confidence entre 0.0 y 1.0.\n"
        "- signals: 1 a 4 frases cortas.\n"
        "- SOLO JSON.\n"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": user,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": OLLAMA_NUM_PREDICT_CLASSIFY
        }
    }

    r = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT_CLASSIFY)
    )
    r.raise_for_status()
    txt = (r.json() or {}).get("response", "")
    data = parse_json_strict(txt)
    if not isinstance(data, dict):
        raise ValueError("Clasificación no es dict JSON.")
    return data


def choose_domain(prod: dict, errors: list, index: int) -> tuple[str, float, list[str], str]:
    """
    Elige dominio final:
    - Si DOMAIN_MODE != auto -> fijo
    - Si auto -> heurística; si baja confianza -> Ollama classify
    Returns: (domain, confidence, signals, method)
    """
    if DOMAIN_MODE != "auto":
        return DOMAIN_MODE, 1.0, ["forced by config"], "forced"

    h_domain, h_conf, h_signals = heuristic_domain(prod)
    if (not USE_OLLAMA) or h_conf >= HEURISTIC_CONF_THRESHOLD:
        return h_domain, h_conf, h_signals, "heuristic"

    # Duda -> classify con Ollama (micro)
    try:
        c = ollama_classify(prod)
        domain = safe_text(c.get("domain", "")) or h_domain
        conf = c.get("confidence", h_conf)
        sig = c.get("signals", h_signals)
        if not isinstance(sig, list):
            sig = h_signals
        # sanity
        allowed = {"3d_printing", "footwear", "apparel", "electronics", "food", "service", "generic"}
        if domain not in allowed:
            domain = h_domain
        try:
            conf = float(conf)
        except Exception:
            conf = h_conf
        conf = max(0.0, min(1.0, conf))
        return domain, conf, sig[:4], "ollama_classify"
    except Exception as e:
        errors.append({"index": index, "stage": "classify", "nombre": prod.get("nombre", ""), "error": str(e), "ts": now_utc_iso()})
        return h_domain, h_conf, h_signals, "heuristic_fallback"


# =========================
# Enriquecimiento (prompt adaptado a dominio)
# =========================
DOMAIN_HINTS = {
    "3d_printing": "Enfócate en uso práctico, material de impresión, tamaño, personalización y cuidados básicos. No inventes tiempos exactos ni specs técnicas no dadas.",
    "footwear": "Enfócate en comodidad, uso (running/casual), tallas/ajuste, materiales si existen y cuidados. No inventes tecnologías específicas.",
    "apparel": "Enfócate en tallas, tejido/material si existe, comodidad, estilo y cuidados. No inventes composición si no está.",
    "electronics": "Enfócate en compatibilidad, uso, beneficios, y precauciones. No inventes especificaciones técnicas (voltios, etc.).",
    "food": "Enfócate en sabor/uso y advertencias generales. No inventes ingredientes ni alérgenos si no están.",
    "service": "Enfócate en beneficios, proceso, qué incluye/no incluye y FAQs típicas. No inventes precios ni condiciones legales.",
    "generic": "Enfócate en beneficios, uso típico y claridad. No inventes características no presentes."
}


def build_enrich_prompts(prod: dict, domain: str, signals: list[str]) -> tuple[str, str]:
    hint = DOMAIN_HINTS.get(domain, DOMAIN_HINTS["generic"])
    system = (
        "DEVUELVE SOLO JSON válido. Sin markdown. Sin texto extra.\n"
        "Eres un asistente para enriquecer fichas de productos.\n"
        "Idioma: español.\n"
        f"Contexto dominio: {domain}. {hint}\n"
        "No inventes datos concretos. Si falta info, mantente genérico.\n"
        "Campos a devolver: slug, short_desc, bullets, tags, seo_title, seo_description, faq.\n"
    )

    user = (
        f"Producto:\n{json.dumps(prod, ensure_ascii=False, separators=(',', ':'))}\n"
        f"Dominio detectado: {domain}\n"
        f"Señales: {signals}\n\n"
        "Devuelve JSON EXACTO:\n"
        "{\n"
        '  "slug": "kebab-case-ascii",\n'
        '  "short_desc": "1 frase corta (<= 140 chars)",\n'
        '  "bullets": ["...","..."],\n'
        '  "tags": ["...","..."],\n'
        '  "seo_title": "<= 60 chars",\n'
        '  "seo_description": "<= 155 chars",\n'
        '  "faq": [{"q":"...","a":"..."},{"q":"...","a":"..."}]\n'
        "}\n\n"
        f"Reglas:\n"
        f"- bullets: 3 a {MAX_BULLETS}.\n"
        f"- tags: 5 a {MAX_TAGS} (usa campos reales del producto: categoria/material/talla/color/etc. si existen).\n"
        f"- faq: {FAQ_COUNT_MIN} a {FAQ_COUNT_MAX} preguntas.\n"
        "- slug: solo a-z 0-9 y guiones, sin tildes ni ñ.\n"
        "- No emojis.\n"
        "- No incluir precio.\n"
        "- SOLO JSON.\n"
    )
    return system, user


def ollama_enrich(prod: dict, domain: str, signals: list[str]) -> dict:
    system, user = build_enrich_prompts(prod, domain, signals)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": user,
        "system": system,
        "stream": False,
        "options": {
            "temperature": OLLAMA_TEMPERATURE,
            "num_predict": OLLAMA_NUM_PREDICT_ENRICH
        }
    }

    r = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT_ENRICH)
    )
    r.raise_for_status()
    txt = (r.json() or {}).get("response", "")
    data = parse_json_strict(txt)
    if not isinstance(data, dict):
        raise ValueError("Enriquecimiento no es dict JSON.")
    return data


# =========================
# Fallback de enriquecimiento
# =========================
def fallback_enrich(prod: dict, domain: str) -> dict:
    nombre = prod.get("nombre", "") or "Producto"
    desc = prod.get("descripcion", "") or ""
    categoria = prod.get("categoria", "") or prod.get("category", "") or ""
    material = prod.get("material", "") or ""
    tamano = prod.get("tamano", "") or prod.get("size", "") or ""
    talla = prod.get("talla", "") or prod.get("numero", "") or ""
    color = prod.get("color", "") or ""
    marca = prod.get("marca", "") or ""

    slug = slugify_ascii(nombre)
    short_desc = desc if len(desc) <= 140 else (desc[:137].rstrip() + "...")

    bullets = []
    if categoria:
        bullets.append(f"Ideal para {categoria.lower()}.")
    if domain == "3d_printing":
        if material:
            bullets.append(f"Fabricado en {material}.")
        if tamano:
            bullets.append(f"Tamaño: {tamano}.")
        bullets.append("Diseño práctico para escritorio y organización.")
    elif domain == "footwear":
        if talla:
            bullets.append(f"Tallas disponibles: {talla}.")
        if color:
            bullets.append(f"Color: {color}.")
        bullets.append("Pensado para comodidad y uso diario.")
    else:
        if marca:
            bullets.append(f"Marca: {marca}.")
        if material:
            bullets.append(f"Material: {material}.")
        bullets.append("Producto pensado para un uso práctico y claro.")

    # asegura 3 bullets
    while len(bullets) < 3:
        bullets.append("Buena opción para uso cotidiano.")
    bullets = bullets[:MAX_BULLETS]
    bullets = list(dict.fromkeys(bullets))

    tags = []
    for t in [categoria, material, tamano, talla, color, marca]:
        t = safe_text(t).lower()
        if t:
            tags.append(slugify_ascii(t, 40))
    tags.append(domain)
    tags = list(dict.fromkeys([t for t in tags if t]))[:MAX_TAGS]
    if len(tags) < 5:
        tags = list(dict.fromkeys(tags + ["catalogo", "producto", "oferta", "recomendado"]))[:MAX_TAGS]

    seo_title = nombre[:60]
    seo_description = (short_desc or nombre)[:155]

    faq = [
        {"q": "¿Cómo se usa?", "a": "Se utiliza según el propósito descrito en la ficha del producto."},
        {"q": "¿Se puede personalizar?", "a": "Depende del producto. Si aplica, se puede ajustar bajo pedido."}
    ][:FAQ_COUNT_MAX]

    return {
        "slug": slug,
        "short_desc": short_desc,
        "bullets": bullets,
        "tags": tags,
        "seo_title": seo_title,
        "seo_description": seo_description,
        "faq": faq
    }


def normalize_enriched(prod: dict, domain: str, enriched: dict) -> dict:
    nombre = prod.get("nombre", "") or "Producto"

    slug = safe_text(enriched.get("slug", "")) or slugify_ascii(nombre)
    slug = slugify_ascii(slug)

    short_desc = safe_text(enriched.get("short_desc", "")) or safe_text(prod.get("descripcion", ""))[:140]
    if len(short_desc) > 140:
        short_desc = short_desc[:137].rstrip() + "..."

    bullets = enriched.get("bullets", [])
    if not isinstance(bullets, list):
        bullets = []
    bullets = [safe_text(x) for x in bullets if safe_text(x)]
    bullets = bullets[:MAX_BULLETS]
    if len(bullets) < 3:
        fb = fallback_enrich(prod, domain)
        bullets = list(dict.fromkeys((bullets + fb["bullets"])[:MAX_BULLETS]))

    tags = enriched.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [slugify_ascii(safe_text(x), 40) for x in tags if safe_text(x)]
    # añade tags de campos reales
    base_tags = []
    for k in ["categoria", "material", "tamano", "talla", "numero", "color", "marca"]:
        v = safe_text(prod.get(k, "")).lower()
        if v:
            base_tags.append(slugify_ascii(v, 40))
    tags = list(dict.fromkeys(base_tags + tags + [domain]))[:MAX_TAGS]
    if len(tags) < 5:
        fb = fallback_enrich(prod, domain)
        tags = list(dict.fromkeys(tags + fb["tags"]))[:MAX_TAGS]

    seo_title = safe_text(enriched.get("seo_title", "")) or nombre
    seo_title = seo_title[:60]

    seo_description = safe_text(enriched.get("seo_description", "")) or short_desc
    seo_description = seo_description[:155]

    faq = enriched.get("faq", [])
    if not isinstance(faq, list):
        faq = []
    norm_faq = []
    for item in faq:
        if isinstance(item, dict):
            q = safe_text(item.get("q", ""))
            a = safe_text(item.get("a", ""))
            if q and a:
                norm_faq.append({"q": q, "a": a})
        if len(norm_faq) >= FAQ_COUNT_MAX:
            break
    if len(norm_faq) < FAQ_COUNT_MIN:
        fb = fallback_enrich(prod, domain)
        norm_faq = (norm_faq + fb["faq"])[:FAQ_COUNT_MAX]

    return {
        "slug": slug,
        "short_desc": short_desc,
        "bullets": bullets,
        "tags": tags,
        "seo_title": seo_title,
        "seo_description": seo_description,
        "faq": norm_faq
    }


# =========================
# MAIN
# =========================
def main():
    xml_path = Path(XML_FILE)
    if not xml_path.exists():
        raise FileNotFoundError(f"No existe el XML: {xml_path.resolve()}")

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    cache_path = out_dir / CACHE_FILE
    errors_path = out_dir / ERRORS_FILE
    out_json_path = out_dir / OUT_JSON

    cache = load_json(cache_path, default={})
    errors = load_json(errors_path, default=[])

    productos = parse_productos_xml(xml_path)

    enriched_products = []
    for i, prod in enumerate(productos, start=1):
        domain, conf, signals, method = choose_domain(prod, errors, i)

        # key caché incluye el producto + dominio
        cache_key = sha1_key({
            "domain": domain,
            "fields": prod
        })

        if cache_key in cache:
            pack = cache[cache_key]
            enriched = pack.get("enriched", {})
            domain_info = pack.get("domain_info", {"domain": domain, "confidence": conf, "signals": signals, "method": method})
        else:
            domain_info = {"domain": domain, "confidence": conf, "signals": signals, "method": method}

            if USE_OLLAMA:
                try:
                    raw = ollama_enrich(prod, domain, signals)
                    enriched = normalize_enriched(prod, domain, raw)
                except Exception as e:
                    enriched = fallback_enrich(prod, domain)
                    errors.append({"index": i, "stage": "enrich", "nombre": prod.get("nombre", ""), "error": str(e), "ts": now_utc_iso()})
            else:
                enriched = fallback_enrich(prod, domain)

            cache[cache_key] = {"domain_info": domain_info, "enriched": enriched}

        enriched_products.append({
            **prod,
            "_domain": domain_info,
            **enriched
        })

        print(f"[{i}/{len(productos)}] OK -> {prod.get('nombre','(sin nombre)')} | domain={domain} ({method})")

    result = {
        "generated_at": now_utc_iso(),
        "source_xml": str(xml_path.name),
        "ollama": {
            "enabled": USE_OLLAMA,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "temperature": OLLAMA_TEMPERATURE,
            "num_predict": {
                "classify": OLLAMA_NUM_PREDICT_CLASSIFY,
                "enrich": OLLAMA_NUM_PREDICT_ENRICH
            },
            "timeouts": {
                "connect": OLLAMA_CONNECT_TIMEOUT,
                "classify_read": OLLAMA_READ_TIMEOUT_CLASSIFY,
                "enrich_read": OLLAMA_READ_TIMEOUT_ENRICH
            }
        },
        "domain_mode": DOMAIN_MODE,
        "count": len(enriched_products),
        "products": enriched_products
    }

    save_json(out_json_path, result)
    save_json(cache_path, cache)
    save_json(errors_path, errors)

    print("\nDONE")
    print(f"- {out_json_path.resolve()}")
    print(f"- {cache_path.resolve()}")
    print(f"- {errors_path.resolve()}")


if __name__ == "__main__":
    main()
