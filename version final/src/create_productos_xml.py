#!/usr/bin/env python3
# ============================================================
# create_productos_xml.py
# ------------------------------------------------------------
# Generador ESTÁTICO de productos.xml (sin IA)
# - Crea data/productos.xml con una lista base de productos
# - Pensado para que el mini proyecto sea “universal”
# ============================================================

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import config


def prettify(elem: ET.Element) -> None:
    """Indent simple para que el XML quede legible (Python 3.9+)."""
    try:
        ET.indent(elem, space="  ")
    except Exception:
        # Si tu Python no soporta indent, igual funciona sin formateo bonito.
        pass


def main() -> None:
    os.makedirs(os.path.dirname(config.INPUT_XML), exist_ok=True)

    # Productos base (edítalos a tu gusto)
    productos = [
        {
            "nombre": "Soporte elevador para monitor",
            "descripcion": "Soporte impreso en 3D para elevar el monitor, mejorar la postura y ganar espacio en el escritorio.",
            "categoria": "Oficina",
            "material": "PLA",
            "precio": "12.90",
            "marca": "PIERODEV",
            "modelo": "MON-01",
            "color": "negro",
        },
        {
            "nombre": "Organizador de cables para escritorio",
            "descripcion": "Canaleta compacta para ordenar cables y reducir el desorden en la zona de trabajo.",
            "categoria": "Oficina",
            "material": "PETG",
            "precio": "6.50",
            "marca": "PIERODEV",
            "modelo": "CAB-02",
            "color": "blanco",
        },
        {
            "nombre": "Soporte para auriculares de escritorio",
            "descripcion": "Base para mantener los auriculares siempre a mano y liberar espacio sobre la mesa.",
            "categoria": "Gaming",
            "material": "PLA",
            "precio": "9.90",
            "marca": "PIERODEV",
            "modelo": "AUR-01",
            "color": "gris",
        },
        {
            "nombre": "Maceta geométrica decorativa",
            "descripcion": "Maceta moderna para interior, ideal para suculentas y decoración minimalista.",
            "categoria": "Hogar",
            "material": "PLA",
            "precio": "8.90",
            "marca": "PIERODEV",
            "modelo": "MAC-03",
            "color": "terracota",
        },
        {
            "nombre": "Llaveros personalizados (pack)",
            "descripcion": "Pack de llaveros impresos en 3D personalizables con texto corto o iniciales.",
            "categoria": "Personalizado",
            "material": "PLA",
            "precio": "7.90",
            "marca": "PIERODEV",
            "modelo": "KEY-10",
            "color": "multicolor",
        },
        {
            "nombre": "Soporte para mando de consola",
            "descripcion": "Base estable para apoyar el mando y mantener la zona gaming más ordenada.",
            "categoria": "Gaming",
            "material": "PETG",
            "precio": "10.90",
            "marca": "PIERODEV",
            "modelo": "PAD-02",
            "color": "negro",
        },
    ]

    root = ET.Element("productos")
    for p in productos:
        prod = ET.SubElement(root, "producto")
        for k, v in p.items():
            ET.SubElement(prod, k).text = str(v)

    prettify(root)

    tree = ET.ElementTree(root)
    tree.write(config.INPUT_XML, encoding="utf-8", xml_declaration=True)

    print(f"✅ Creado: {config.INPUT_XML} ({len(productos)} productos)")


if __name__ == "__main__":
    main()
