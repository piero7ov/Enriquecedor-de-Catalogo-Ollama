# config.py
# ============================================================
# Configuración FINAL (versión “universal”)
# - Cambia SOLO OLLAMA_MODEL si quieres otro modelo.
# - El resto está pensado para máxima estabilidad de JSON.
# ============================================================

# --- Ollama ---
OLLAMA_ENABLED = True
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Modelo recomendado (Mistral 24B)
OLLAMA_MODEL = "llama3.1:8b-instruct-q4_K_M"


# Ajustes para estabilidad (obediencia + menos inventos)
TEMPERATURE = 0.15
NUM_PREDICT = 420

# Timeouts (connect, read)
TIMEOUT_CONNECT = 10
TIMEOUT_READ = 360

# Si True, añade "format":"json" al payload (muy recomendable)
TRY_FORMAT_JSON = True

# Reintentos si sale JSON roto
MAX_RETRIES = 1

# --- I/O ---
INPUT_XML = "data/productos.xml"
OUTPUT_JSON = "data/productos_enriched.json"
