"""
Motor de Auto-Aprendizaje y Destilación Nocturna (Autonomous Self-Distillation Engine).
Permite dejar la computadora trabajando durante la noche para que el sistema
consulte a los modelos gigantes (Groq LLaMA-3.3-70B, GPT-OSS-120B + Gemini) mediante debate adversarial,
generando un dataset de razonamiento de nivel de élite adaptado a la PC del usuario.

Cero dependencias externas: biblioteca estándar de Python.
"""

import os
import sys
import json
import time
import re
import argparse
from pathlib import Path
from datetime import datetime

# Configurar salida segura en consola de Windows con autoflush
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from agent.cloud_debate import CloudDebateEngine
    from agent.tools import AgentTools
except Exception:
    from cloud_debate import CloudDebateEngine
    from tools import AgentTools

DATA_DIR = BASE_DIR / "data"
DATASET_FILE = DATA_DIR / "distillation_dataset.jsonl"
LOG_FILE = DATA_DIR / "overnight_distillation.log"

def log_event(message: str, also_stdout: bool = True):
    """Registra eventos con marca temporal en el archivo de log permanente y en la consola."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{now_str}] {message}"
    if also_stdout:
        print(formatted, flush=True)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# CURRICULUM DE CONOCIMIENTO (Adaptado a Trading, Bots, Python y Sistemas)
# ---------------------------------------------------------------------------
CURRICULUM = [
    # MÓDULO 1: TRADING CUANTITATIVO Y ARQUITECTURA DE BOTS
    "Explica cómo implementar un cálculo de Drawdown Máximo en tiempo real para un bot de trading en Python sin saturar la memoria.",
    "¿Cómo diseñar un sistema de Trailing Stop dinámico basado en ATR (Average True Range) para capturar tendencias en acciones y cripto?",
    "Escribe una clase en Python para gestionar órdenes con la API de Alpaca, manejando reconexiones automáticas y errores de red.",
    "Compara las estrategias de Momentum vs Mean Reversion: cuándo falla cada una en mercados de alta volatilidad y cómo filtrarlas.",
    "¿Cómo estructurar un bucle principal de trading en Python que procese ticks en tiempo real mediante WebSockets sin bloquear la UI?",
    "Diseña una función para calcular el tamaño óptimo de posición (Position Sizing) usando una fracción del Criterio de Kelly.",
    "¿Qué es el slippage en trading algorítmico, cómo se mide a partir del libro de órdenes (Order Book) y cómo mitigarlo?",
    "Escribe un script en Python para validar si una señal de compra de RSI + EMA Crossover no es una falsa ruptura con confirmación de volumen.",
    "¿Cómo implementar un 'Trend Shield' o filtro de tendencia macro para pausar un bot cuando el índice general (SPY/BTC) cae bruscamente?",
    "Explica cómo almacenar velas japonesas históricas de forma compacta en SQLite usando el modo WAL para consultas ultra-rápidas.",
    "¿Cómo manejar de forma segura las API Keys y Secret Keys de brokers en Windows para que nunca queden en texto plano en Git?",
    "Escribe una función de post-mortem para analizar los trades perdedores de un bot e identificar horarios con peor rendimiento.",
    "¿Cómo estructurar una interfaz gráfica desacoplada (usando Tkinter o Qt) que monitorice un bot de trading en ejecución?",
    "Explica el funcionamiento de un filtro de Kalman o regresión lineal rápida para estimar la dirección inmediata del precio.",
    "¿Cómo programar un sistema de alertas por Telegram para un bot de trading con reintentos exponenciales si falla la conexión?",
    "Muestra cómo calcular los soportes y resistencias dinámicos usando máximos y mínimos locales de las últimas N velas.",
    "¿Cómo evitar el sobreajuste (Overfitting) al optimizar parámetros de una estrategia de trading cuantitativo?",
    "Escribe un simulador de Paper Trading en memoria en Python que emule ejecuciones con spread y comisiones realistas.",
    "¿Cómo detectar divergencias alcistas y bajistas entre el precio y el oscilador MACD de manera programática en Python?",
    "Escribe un gestor de riesgo diario que apague automáticamente el bot si la pérdida diaria supera el 2% del balance de la cuenta.",
    "Explica cómo diseñar un reconciliador de estado de órdenes en segundo plano para verificar que el broker y la base de datos local coincidan.",
    "¿Cómo manejar desfasajes de tiempo (clock skew / NTP) y latencia de red al enviar órdenes a exchanges en milisegundos?",
    "Escribe un algoritmo de Iceberg Order o TWAP (Time-Weighted Average Price) simple para fragmentar compras grandes sin mover el precio.",
    "¿Cómo implementar un 'Circuit Breaker' automático en Python que congele operaciones tras 3 pérdidas consecutivas en menos de 15 minutos?",
    "Explica la diferencia entre órdenes Market, Limit, Stop-Loss y Stop-Limit, detallando en qué condiciones de pánico una orden Market puede ser desastrosa.",

    # MÓDULO 2: PYTHON DE ALTO RENDIMIENTO Y PROGRAMACIÓN MODERNA
    "Explica la diferencia entre asyncio, threading y multiprocessing en Python y cuándo usar cada uno en aplicaciones de trading.",
    "¿Cómo optimizar el uso de memoria en Python al procesar grandes archivos CSV o registros de transacciones?",
    "Escribe un decorador en Python para medir el tiempo exacto de ejecución y registrar métricas en milisegundos con logging estructurado.",
    "¿Cómo implementar un pool de conexiones HTTP persistentes con urllib nativo o requests para reducir latencia en llamadas API?",
    "Explica el uso de generadores y 'yield' en Python para procesar flujos infinitos de datos sin agotar la RAM.",
    "¿Cómo escribir tests unitarios efectivos con pytest para probar una estrategia de trading sin conectar al broker real?",
    "Explica cómo funciona la gestión de memoria en Python (Garbage Collection y conteo de referencias) y cómo evitar fugas de memoria.",
    "Escribe un parser robusto de archivos de configuración JSON y YAML que aplique valores por defecto y valide tipos de datos.",
    "¿Cómo implementar un sistema de reintentos con 'Exponential Backoff' y 'Jitter' para llamadas a servicios externos en Python?",
    "Explica cómo usar SQLite FTS5 (Full-Text Search) en Python para buscar código y documentos en milisegundos sin bases de datos pesadas.",
    "¿Cómo empaquetar un script de Python con dependencias nativas en un archivo ejecutable o ejecutable sin consola (.pyw)?",
    "Escribe un patrón Singleton seguro para hilos (Thread-safe) en Python para compartir la configuración global del sistema.",
    "¿Cómo usar colas 'queue.Queue' y eventos 'threading.Event' para coordinar hilos de adquisición de datos y ejecución sin bloqueos?",
    "Explica el mecanismo de bloqueo del GIL (Global Interpreter Lock) en Python y cómo librerías nativas como NumPy o Numba lo liberan.",
    "Escribe una función en Python para serializar estructuras complejas en formato binario ligero con struct o ctypes.",
    "¿Cómo diseñar un sistema de caché LRU (Least Recently Used) con expiración por tiempo (TTL) usando solo la biblioteca estándar?",
    "Explica cómo capturar excepciones no controladas a nivel global en Python usando sys.excepthook para guardarlas en un archivo de volcado.",

    # MÓDULO 3: ADMINISTRACIÓN DE SISTEMAS WINDOWS Y POWERSHELL
    "Escribe comandos de PowerShell para monitorizar el uso de memoria y CPU de un proceso de Python específico y reiniciarlo si se congela.",
    "¿Cómo configurar una tarea programada en Windows (Task Scheduler) para ejecutar un script de mantenimiento diario automáticamente?",
    "Explica cómo inspeccionar puertos en uso y matar un proceso que esté bloqueando un puerto HTTP local en Windows desde PowerShell.",
    "¿Cómo crear un script batch (.bat) que active un entorno virtual de Python, verifique dependencias y lance una aplicación en segundo plano?",
    "Escribe una función de PowerShell para buscar texto o funciones dentro de cientos de archivos de código rápidamente.",
    "¿Cómo verificar la salud de los servicios de red de Windows y regenerar conexiones socket bloqueadas desde la consola?",
    "Escribe un script de PowerShell para rotar y comprimir archivos de log de más de 50MB en una carpeta de archivado.",
    "¿Cómo inspeccionar el visor de eventos de Windows (Event Viewer) desde PowerShell para diagnosticar reinicios o fallas del sistema?",

    # MÓDULO 4: INTELIGENCIA ARTIFICIAL, AGENTES Y HERRAMIENTAS
    "¿Cómo funciona el protocolo de llamadas a funciones (Function Calling / Tool Use) en modelos de lenguaje pequeños como Qwen?",
    "Explica cómo un modelo de lenguaje de pocos parámetros puede razonar mejor dividiendo el problema en pasos paso a paso (CoT).",
    "¿Qué es la cuantización de modelos GGUF (Q4_K_M, Q8_0) y por qué permite correr modelos modernos en CPU con poca RAM?",
    "¿Cómo diseñar un prompt de sistema para un agente autónomo que impida alucinaciones y fuerce el uso de datos observados reales?",
    "Explica el concepto de Destilación de Conocimiento (Knowledge Distillation / Teacher-Student) para entrenar modelos pequeños.",
    "¿Qué es LoRA (Low-Rank Adaptation) y por qué permite entrenar modelos de IA en computadoras domésticas sin supercomputadoras?",
    "¿Cómo evaluar si un modelo de lenguaje local está mejorando tras aplicar un dataset de fine-tuning?",
    "Escribe una función en Python para limpiar y formatear respuestas de modelos de lenguaje eliminando tokens repetitivos o caracteres extraños.",
    "¿Cómo implementar un mecanismo de embeddings y búsqueda semántica local con cosine similarity sin requerir PyTorch pesado?",
    "Explica las ventajas de la arquitectura Mixture of Experts (MoE) y por qué modelos de 120B con pocos expertos activos son tan rápidos."
]

def load_existing_queries():
    """Lee las consultas ya registradas en el dataset para evitar duplicados exactos."""
    existing = set()
    if DATASET_FILE.exists():
        try:
            with open(DATASET_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        msgs = data.get("messages", [])
                        if msgs and msgs[0].get("role") == "user":
                            existing.add(msgs[0].get("content", "").strip().lower())
                    except Exception:
                        pass
        except Exception as e:
            log_event(f"[Aviso] No se pudo leer dataset existente: {e}")
    return existing

def parse_rate_limit_wait(err_str: str) -> int:
    """Extrae el tiempo exacto de espera indicado en el error HTTP 429 de Groq o Gemini."""
    # Ejemplos: "Please try again in 24.32s." o "Please try again in 1m15s"
    m_sec = re.search(r'try again in\s+(\d+(?:\.\d+)?)s', err_str, re.IGNORECASE)
    if m_sec:
        try:
            return max(int(float(m_sec.group(1))) + 5, 15)
        except Exception:
            pass

    m_min = re.search(r'try again in\s+(\d+)m(\d+(?:\.\d+)?)s', err_str, re.IGNORECASE)
    if m_min:
        try:
            total = int(m_min.group(1)) * 60 + int(float(m_min.group(2))) + 5
            return max(total, 25)
        except Exception:
            pass

    return 40

def generate_dynamic_topics(engine: CloudDebateEngine, count: int = 15) -> list:
    """Utiliza modelos cloud para generar nuevos temas técnicos avanzados cuando se completa el currículum."""
    prompt = f"""Genera una lista de {count} preguntas y desafíos técnicos de programación de nivel senior.
Especialidades prioritarias:
- Python avanzado (concurrencia, optimización, asyncio, bajo nivel)
- Bots de trading cuantitativo (gestión de riesgo, Alpaca, Binance, websockets, mitigación de fallas, reconciliación)
- Automatización y scripting en Windows/PowerShell
- Arquitectura limpia, algoritmos robustos y bases de datos locales (SQLite WAL)

Responde ÚNICAMENTE con una lista en formato JSON de cadenas de texto, sin explicaciones adicionales:
["Pregunta 1...", "Pregunta 2...", ...]"""

    for model_name in ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]:
        try:
            raw = engine._call_groq([
                {"role": "system", "content": "Eres un arquitecto de software senior especializado en diseño de currículos técnicos. Responde solo con JSON."},
                {"role": "user", "content": prompt}
            ], model=model_name, max_tokens=850)
            
            raw_clean = raw.strip()
            if "```json" in raw_clean:
                raw_clean = raw_clean.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_clean:
                raw_clean = raw_clean.split("```")[1].split("```")[0].strip()
            
            topics = json.loads(raw_clean)
            if isinstance(topics, list) and all(isinstance(t, str) for t in topics):
                valid = [t.strip() for t in topics if len(t.strip()) > 15]
                if valid:
                    return valid
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "rate limit" in err_msg.lower():
                wait_sec = parse_rate_limit_wait(err_msg)
                log_event(f"[Aviso] Limite de cuota en generador de temas. Pausando {wait_sec}s...")
                time.sleep(wait_sec)
            else:
                log_event(f"[Info] Generación dinámica con {model_name} omitida: {err_msg[:80]}")

    return []

def run_overnight_distillation(target_samples: int = 400, delay_seconds: int = 18):
    """Bucle principal de auto-entrenamiento y destilación nocturna resiliente."""
    log_event("=" * 70)
    log_event("  [*] AURA - MOTOR DE AUTO-APRENDIZAJE Y DESTILACION NOCTURNA")
    log_event("=" * 70)
    log_event(f"  Objetivo de muestras : {target_samples} pares de razonamiento")
    log_event(f"  Pausa de cortesía    : {delay_seconds}s entre debates (respeto a límites de API)")
    log_event(f"  Destino del dataset  : {DATASET_FILE}")
    log_event(f"  Archivo de auditoría : {LOG_FILE}")
    log_event("-" * 70)

    engine = CloudDebateEngine()
    status = engine.is_configured()

    if not status["debate_ready"] and not status["groq_ready"]:
        log_event("\n[ERROR CRITICO] Se requiere al menos la clave API de Groq configurada en config.json.")
        return

    tools_handler = AgentTools(workspace_root=str(BASE_DIR))
    existing_queries = load_existing_queries()
    current_count = len(existing_queries)
    log_event(f"  Dataset actual       : {current_count} pares ya grabados.")
    log_event("-" * 70)

    pending_topics = [t for t in CURRICULUM if t.strip().lower() not in existing_queries]
    log_event(f"  Temas base pendientes: {len(pending_topics)}")
    log_event("  Iniciando proceso autónomo. Supervisión continua activa.\n")

    success_count = 0

    while (current_count + success_count) < target_samples:
        if not pending_topics:
            log_event("\n[GEN] [Curriculum base completado] Generando nuevos temas técnicos avanzados...")
            new_topics = generate_dynamic_topics(engine, count=15)
            for nt in new_topics:
                if nt.strip().lower() not in existing_queries:
                    pending_topics.append(nt)
            if not pending_topics:
                log_event("[Pausa] Esperando 60s para enfriamiento de generador dinámico...")
                time.sleep(60)
                continue

        # NUNCA descartar la pregunta por adelantado: se inspecciona el frente de la cola
        current_query = pending_topics[0]
        total_now = current_count + success_count + 1

        log_event(f"\n[NOCHE - MUESTRA #{total_now}/{target_samples}]")
        log_event(f"Consulta: {current_query[:80]}...")

        t_start = time.time()
        consecutive_non_rate_errors = 0
        debate_success = False

        while not debate_success:
            try:
                res = engine.run_debate(
                    current_query,
                    system_tools_info="Sistema: Windows 10.",
                    tools_handler=tools_handler
                )

                if res and res.get("success"):
                    elapsed = round(time.time() - t_start, 2)
                    response_len = len(res.get("final_response", ""))
                    log_event(f"  [OK] Consenso generado en {elapsed}s ({response_len} caracteres).")
                    
                    # Confirmado con éxito: ahora sí removemos de la cola y sumamos
                    pending_topics.pop(0)
                    existing_queries.add(current_query.strip().lower())
                    success_count += 1
                    debate_success = True
                else:
                    err_msg = res.get('error', 'desconocido') if res else 'Sin respuesta'
                    log_event(f"  [Aviso] Consenso no directo: {err_msg}")
                    consecutive_non_rate_errors += 1
                    if consecutive_non_rate_errors >= 3:
                        log_event("  [REORDENAR] Moviendo consulta no consensuada al final de la cola.")
                        pending_topics.pop(0)
                        pending_topics.append(current_query)
                        break
                    time.sleep(6)

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate limit" in err_str.lower():
                    # Parsear el tiempo exacto de enfriamiento sugerido por la API
                    wait_time = parse_rate_limit_wait(err_str)
                    log_event(f"  [PAUSA] Límite de tasa alcanzado (HTTP 429). Esperando {wait_time}s para resetear cuota...")
                    time.sleep(wait_time)
                    # NO incrementamos consecutive_non_rate_errors; se reintenta la misma consulta
                else:
                    consecutive_non_rate_errors += 1
                    log_event(f"  [ERROR] Fallo en ciclo de debate ({consecutive_non_rate_errors}/3): {err_str[:120]}")
                    if consecutive_non_rate_errors >= 3:
                        log_event("  [REORDENAR] Moviendo consulta con errores recurrentes al final de la cola.")
                        pending_topics.pop(0)
                        pending_topics.append(current_query)
                        break
                    time.sleep(8)

        if debate_success:
            log_event(f"  [PAUSA] Esperando {delay_seconds}s (respetando límites de API)...")
            time.sleep(delay_seconds)
        else:
            time.sleep(6)

    log_event("\n" + "=" * 70)
    log_event("  [COMPLETADO] Sesión de auto-aprendizaje nocturno finalizada con éxito.")
    log_event(f"  Nuevos pares destilados : {success_count}")
    log_event(f"  Total actual en dataset : {current_count + success_count} pares.")
    log_event(f"  Ubicación               : {DATASET_FILE}")
    log_event("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AURA Auto-Aprendizaje y Destilación Nocturna")
    parser.add_argument("--target", type=int, default=400, help="Número objetivo de muestras en el dataset")
    parser.add_argument("--delay", type=int, default=18, help="Segundos de espera entre consultas")
    args = parser.parse_args()

    try:
        run_overnight_distillation(target_samples=args.target, delay_seconds=args.delay)
    except KeyboardInterrupt:
        log_event("\n[Pausado por el usuario] El dataset ha sido preservado íntegro.")
