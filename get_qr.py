"""
Solicita el QR de la instancia Colibry en Evolution API
y guarda el resultado como qr_colibry.png.
"""

import base64
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Evolution API corre en el servidor remoto; reemplazamos localhost por la IP pública
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").replace(
    "localhost", "178.104.58.204"
)
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE_NAME     = os.getenv("INSTANCE_NAME", "Colibry").strip()

OUTPUT_FILE = "qr_colibry.png"


def get_qr():
    url     = f"{EVOLUTION_API_URL}/instance/connect/{INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY}

    print(f"Conectando a: {url}")
    response = requests.get(url, headers=headers, timeout=15)

    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        return

    data = response.json()

    # Evolution API puede devolver el QR como base64 dentro de 'base64' o 'qrcode'
    qr_base64 = data.get("base64") or data.get("qrcode") or data.get("code")

    if not qr_base64:
        print("Respuesta recibida (sin QR en formato esperado):")
        print(data)
        return

    # Limpia el prefijo data:image/png;base64, si viene incluido
    if "," in qr_base64:
        qr_base64 = qr_base64.split(",", 1)[1]

    img_bytes = base64.b64decode(qr_base64)
    with open(OUTPUT_FILE, "wb") as f:
        f.write(img_bytes)

    print(f"QR guardado en: {OUTPUT_FILE}")
    print("Escanéalo con WhatsApp antes de que expire (~60 segundos).")


if __name__ == "__main__":
    get_qr()
