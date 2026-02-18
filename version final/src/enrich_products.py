#!/usr/bin/env python3
# ============================================================
# enrich_products.py
# ------------------------------------------------------------
# MINI PROYECTO (VERSIÓN FINAL UNIVERSAL)
# - Lee productos desde XML (data/productos.xml)
# - Para cada producto llama a Ollama
# - Exige salida SOLO JSON (y tiene fallback si sale roto)
# - Normaliza slug/tags y garantiza estructura final consistente
# - Exporta JSON final (data/productos_enriched.json)
# ============================================================

from __future__ import annotations

import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

import requests

import config


# ============================================================
# Normalización (slug / tags / textos SEO)
# ============================================================

def _strip_accents(s: str) -> str:
    """Quita tildes/acentos para generar tags/slug compatibles."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def to_kebab_case(s: str) -> str:
    """Convierte a kebab-case (sin tildes, sin símbolos raros)."""
    s = _strip_accents((s or "").strip().lower())
    s = re.sub(r"[^a-z0-9\s_-]+", "", s)
    s = s.replace("_", " ")
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"-{2,}", "-", s)
    return s or "producto"


def to_snake_case(s: str) -> str:
    """Convierte a snake_case (sin tildes, sin espacios)."""
    s = _strip_accents((s or "").strip().lower())
    s = re.sub(r"[^a-z0-9\s_-]+", "", s)
    s = s.replace("-", " ")
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"_{2,}", "_", s)
    return s or "tag"


def clamp_len(s: str, max_len: int) -> str:
    """Recorta a un máximo de caracteres."""
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len].rstrip()


def clamp_words(s: str, max_w: int) -> str:
    """Recorta a máximo de palabras (sin inventar)."""
    s = (s or "").strip()
    words = [w for w in s.split() if w]
    if len(words) > max_w:
        words = words[:max_w]
    return " ".join(words)


# ============================================================
# Ollama (robusto)
# ============================================================

def ollama_generate(*, system: str, prompt: str) -> str:
    """Llama a Ollama /api/generate y devuelve el texto de respuesta."""
    payload: Dict[str, Any] = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": float(config.TEMPERATURE),
            "num_predict": int(config.NUM_PREDICT),
        },
    }

    if config.TRY_FORMAT_JSON:
        payload["format"] = "json"

    last_err = None
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            r = requests.post(
                config.OLLAMA_URL,
                json=payload,
                timeout=(config.TIMEOUT_CONNECT, config.TIMEOUT_READ),
            )
            r.raise_for_status()
            data = r.json()
            return (data.get("response") or "").strip()
        except Exception as e:
            last_err = e
            if attempt < config.MAX_RETRIES:
                time.sleep(0.4)
                continue
            raise RuntimeError(f"Error llamando Ollama: {last_err}") from last_err


def extract_json_block(text: str) -> str:
    """
    Extrae el primer objeto JSON { ... } de un texto.
    Si el texto ya es JSON puro, lo devuelve tal cual.
    """
    text = (text or "").strip()
    if not text:
        return ""

    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    if start == -1:
        return ""

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return ""


# ============================================================
# Prompt FINAL (tu versión mejorada)
# ============================================================

def build_system_prompt() -> str:
    return (
        "Devuelve SOLO JSON válido. Sin texto extra.\n"
        "Eres un generador de metadatos para fichas de producto.\n"
        "Idioma: español.\n"
        "NO inventes datos técnicos: si no está en el input, no lo afirmes.\n"
    )


def build_prompt(brief: Dict[str, Any]) -> str:
    return (
        "Genera un enriquecimiento útil y NO redundante.\n"
        "Reglas importantes:\n"
        "- short_desc: 1 frase (12–22 palabras). Parafrasea la descripcion (no copies literal).\n"
        "- bullets: EXACTAMENTE 3 items, 3–6 palabras cada uno.\n"
        "  * Cada bullet debe sonar a IMPACTO para el usuario: qué mejora o facilita al usarlo.\n"
        "  * Puedes partir de una característica, pero redáctala como resultado (evita tecnicismos).\n"
        "  * Evita repetir palabras clave o frases de la descripcion y del short_desc.\n"
        "  * Puedes usar infinitivo SI aporta valor, pero NO repitas los mismos verbos/ideas de la descripcion.\n"
        "  * No inventes medidas, compatibilidades ni datos técnicos.\n"
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


# ============================================================
# Enriquecimiento universal (con post-procesado)
# ============================================================

def build_brief(product: Dict[str, Any]) -> Dict[str, Any]:
    base_keys = {"nombre", "descripcion", "categoria", "material", "precio", "marca", "modelo", "imagen", "enlace"}
    return {
        "nombre": product.get("nombre", ""),
        "descripcion": product.get("descripcion", ""),
        "categoria": product.get("categoria", ""),
        "material": product.get("material", ""),
        "precio": product.get("precio", ""),
        "marca": product.get("marca", ""),
        "modelo": product.get("modelo", ""),
        "extras": {k: product.get(k) for k in product.keys() if k not in base_keys},
    }


def normalize_output(raw: Dict[str, Any], product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Garantiza:
      - claves exactas
      - bullets siempre 3
      - tags snake_case (hasta 10)
      - slug kebab-case (con fallback)
      - límites SEO
    """
    nombre = (product.get("nombre") or "").strip()
    marca = (product.get("marca") or "").strip()

    slug = (raw.get("slug") or "").strip()
    if not slug:
        base = f"{nombre} {marca}".strip() if marca else nombre
        slug = to_kebab_case(base)
    else:
        slug = to_kebab_case(slug)

    short_desc = (raw.get("short_desc") or "").strip()

    bullets = raw.get("bullets")
    if not isinstance(bullets, list):
        bullets = []
    bullets = [str(x).strip() for x in bullets if str(x).strip()]
    bullets = (bullets + ["", "", ""])[:3]
    bullets = [clamp_words(b, 6) for b in bullets]

    tags = raw.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags = [to_snake_case(str(t)) for t in tags if str(t).strip()]

    # Tags “seguros” basados en input (sin inventar)
    safe_tags: List[str] = []
    if product.get("categoria"):
        safe_tags.append(to_snake_case(str(product["categoria"])))
    if product.get("marca"):
        safe_tags.append(to_snake_case(str(product["marca"])))
    if product.get("material"):
        safe_tags.append(to_snake_case(str(product["material"])))

    # Unir + deduplicar
    seen = set()
    all_tags: List[str] = []
    for t in tags + safe_tags:
        if not t or t in seen:
            continue
        seen.add(t)
        all_tags.append(t)

    all_tags = all_tags[:10]

    seo_title = clamp_len((raw.get("seo_title") or "").strip(), 60)
    seo_description = clamp_len((raw.get("seo_description") or "").strip(), 160)

    return {
        "slug": slug,
        "short_desc": short_desc,
        "bullets": bullets,
        "tags": all_tags,
        "seo_title": seo_title,
        "seo_description": seo_description,
    }


def ollama_enrich(product: Dict[str, Any]) -> Dict[str, Any]:
    brief = build_brief(product)
    system = build_system_prompt()
    prompt = build_prompt(brief)

    txt = ollama_generate(system=system, prompt=prompt)
    js = extract_json_block(txt)

    raw: Dict[str, Any] = {}
    if js:
        try:
            parsed = json.loads(js)
            if isinstance(parsed, dict):
                raw = parsed
        except Exception:
            raw = {}

    return normalize_output(raw, product)


# ============================================================
# XML -> dict (simple)
# ============================================================

def parse_productos_xml(path: str) -> List[Dict[str, Any]]:
    """
    Asume estructura:
      <productos>
        <producto>
          <nombre>...</nombre>
          ...
        </producto>
      </productos>
    """
    tree = ET.parse(path)
    root = tree.getroot()

    products: List[Dict[str, Any]] = []
    for p in root.findall(".//producto"):
        d: Dict[str, Any] = {}
        for child in list(p):
            key = (child.tag or "").strip()
            val = (child.text or "").strip()
            if key:
                d[key] = val
        products.append(d)

    return products


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    if not config.OLLAMA_ENABLED:
        raise SystemExit("OLLAMA_ENABLED=False en config.py")

    productos = parse_productos_xml(config.INPUT_XML)

    out: List[Dict[str, Any]] = []
    for i, prod in enumerate(productos, start=1):
        enriched = ollama_enrich(prod)
        out.append({**prod, **enriched})
        print(f"[{i}/{len(productos)}] OK -> {enriched.get('slug','')}")

    with open(config.OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"productos": out}, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Generado: {config.OUTPUT_JSON}")


if __name__ == "__main__":
    main()
