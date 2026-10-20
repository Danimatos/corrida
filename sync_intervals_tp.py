"""Sincronizador Automático de Treinos: Intervals.icu -> TrainingPeaks

- Consulta novos treinos no Intervals.icu via API REST.
- Baixa o arquivo FIT original.
- Faz upload diretamente via API REST interna do TrainingPeaks (usando cookie de sessão autenticada do Chrome).
- Registra atividades sincronizadas em `synced_activities.json`.
- Notifica no Telegram.
"""

import os
import sys
import time
import json
import base64
import logging
import argparse
import requests
import subprocess
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
import websocket
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- CONFIGURAÇÃO ---
LOG_FILE = BASE_DIR / "intervals_sync.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "i551380")
API_KEY = os.getenv("INTERVALS_API_KEY")
TP_DEFAULT_ATHLETE_ID = os.getenv("TP_ATHLETE_ID", "5175936")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ADB_TARGET = os.getenv("ANDROID_ADB_TARGET", "127.0.0.1:5555")
CDP_PORT = int(os.getenv("ANDROID_CDP_PORT", "9222"))
DB_FILE = BASE_DIR / "synced_activities.json"


def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        logging.warning("Falha ao enviar mensagem no Telegram: %s", e)


def load_synced_ids() -> set:
    if DB_FILE.exists():
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_synced_ids(synced: set) -> None:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(synced)), f, indent=2)


def run_adb(*args: str, check: bool = True) -> str:
    res = subprocess.run(
        ["adb", "-s", ADB_TARGET, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check
    )
    return res.stdout.strip()


def ensure_device_connected() -> None:
    state = run_adb("get-state", check=False)
    if state != "device":
        logging.info("Tentando reconectar ADB em %s...", ADB_TARGET)
        run_adb("connect", ADB_TARGET, check=False)
        time.sleep(2)
        if run_adb("get-state", check=False) != "device":
            raise RuntimeError(f"Dispositivo ADB indisponível: {ADB_TARGET}")


def prepare_chrome_cdp() -> None:
    run_adb("forward", f"tcp:{CDP_PORT}", "localabstract:chrome_devtools_remote")
    run_adb("shell", "am", "start", "-n", "com.android.chrome/com.google.android.apps.chrome.Main")
    time.sleep(2)


def get_tp_session():
    """Obtém cookie de autenticação e ID do atleta a partir da sessão ativa no Chrome."""
    ensure_device_connected()
    prepare_chrome_cdp()

    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json"))
    pages = [item for item in targets if item.get("type") == "page"]
    if not pages:
        raise RuntimeError("Nenhuma página do Chrome aberta encontrada.")

    ws_url = pages[0]["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url, timeout=15, suppress_origin=True)

    seq = 1
    def send_cmd(method, params=None):
        nonlocal seq
        cid = seq
        seq += 1
        ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == cid:
                return r

    try:
        send_cmd("Network.enable")
        cookies_res = send_cmd("Network.getCookies")
        auth_cookie = None
        for c in cookies_res.get("result", {}).get("cookies", []):
            if c.get("name") == "Production_tpAuth":
                auth_cookie = c.get("value")
                break

        if not auth_cookie:
            raise RuntimeError("Cookie Production_tpAuth não encontrado no Chrome.")

        user_eval = send_cmd("Runtime.evaluate", {
            "expression": f"document.querySelector('input[type=file]') ? (document.querySelector('input[type=file]').__reactFiber$ ? {TP_DEFAULT_ATHLETE_ID} : {TP_DEFAULT_ATHLETE_ID}) : {TP_DEFAULT_ATHLETE_ID}",
            "returnByValue": True
        })
        tp_athlete_id = user_eval.get("result", {}).get("result", {}).get("value") or TP_DEFAULT_ATHLETE_ID

        return auth_cookie, tp_athlete_id
    finally:
        ws.close()


def upload_to_tp_api(fit_bytes: bytes, filename: str, workout_day: str) -> dict:
    """Faz o upload direto usando a API REST do TrainingPeaks via cookie de sessão, com retentativas automáticas."""
    auth_cookie, tp_athlete_id = get_tp_session()

    url = f"https://tpapi.trainingpeaks.com/fitness/v7/athletes/{tp_athlete_id}/workouts/filedata"
    headers = {
        "Cookie": f"Production_tpAuth={auth_cookie}",
        "Origin": "https://app.trainingpeaks.com",
        "Referer": "https://app.trainingpeaks.com/",
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json"
    }

    b64_fit = base64.b64encode(fit_bytes).decode()
    payload = {
        "workoutDay": workout_day,
        "data": b64_fit,
        "fileName": filename,
        "uploadClient": "TP Web App"
    }

    max_attempts = 3
    last_err = None

    for attempt in range(1, max_attempts + 1):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=35)
            if res.status_code in (200, 201):
                data = res.json()
                logging.info("Upload aceito pela API do TrainingPeaks: %s", data)
                return data
            elif res.status_code == 422 and "already been uploaded" in res.text:
                logging.info("Atividade já existente no TrainingPeaks (422): %s", filename)
                return {"status": "already_uploaded"}
            else:
                raise RuntimeError(f"Erro na API TP ({res.status_code}): {res.text[:200]}")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as conn_err:
            last_err = conn_err
            logging.warning("Instabilidade na conexão com o TP (tentativa %d/%d): %s", attempt, max_attempts, conn_err)
            if attempt < max_attempts:
                time.sleep(3 * attempt)
            else:
                raise last_err


def sync_recent_runs() -> None:
    if not API_KEY:
        logging.error("INTERVALS_API_KEY não configurada.")
        return

    synced_ids = load_synced_ids()
    auth_str = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_str}"}

    # Busca treinos dos últimos 3 dias
    oldest_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={oldest_date}"

    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code != 200:
        logging.error("Erro ao consultar Intervals.icu: %d - %s", r.status_code, r.text[:200])
        return

    activities = r.json()
    runs = [a for a in activities if a.get("type") in ("Run", "TrailRun", "VirtualRun")]

    for act in runs:
        act_id = act.get("id")
        act_name = act.get("name", "Treino de Corrida")
        act_date = act.get("start_date_local", "")[:10]

        if act_id in synced_ids:
            continue

        logging.info("Novo treino detectado: %s (%s - %s)", act_id, act_date, act_name)

        dl_url = f"https://intervals.icu/api/v1/activity/{act_id}/file"
        dl = requests.get(dl_url, headers=headers, timeout=30)
        if dl.status_code != 200:
            logging.error("Falha ao baixar FIT para %s: %s", act_id, dl.text[:200])
            continue

        try:
            up_res = upload_to_tp_api(dl.content, f"{act_id}.fit", act_date)
            synced_ids.add(act_id)
            save_synced_ids(synced_ids)
            if up_res.get("status") != "already_uploaded":
                send_telegram(
                    f"✅ <b>Treino Sincronizado!</b>\n"
                    f"🏃‍♂️ <b>{act_name}</b> ({act_date})\n"
                    f"📥 <i>Intervals.icu</i> ➔ 📤 <i>TrainingPeaks</i>"
                )
            logging.info("Treino %s sincronizado com sucesso!", act_id)
        except Exception as e:
            logging.error("Erro durante upload no TrainingPeaks para %s: %s", act_id, e)
            send_telegram(f"❌ <b>Falha ao sincronizar treino:</b>\n{act_name} ({act_date})\nErro: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Executar em loop a cada 10 minutos")
    args = parser.parse_args()

    if args.loop:
        logging.info("Iniciando modo contínuo (polling a cada 10 min)...")
        while True:
            try:
                sync_recent_runs()
            except Exception as ex:
                logging.error("Erro no ciclo: %s", ex)
            time.sleep(600)
    else:
        sync_recent_runs()
