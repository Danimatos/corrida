"""Sincronizador Automático de Treinos Planejados: TrainingPeaks -> Intervals.icu -> Huawei Watch

- Conecta à sessão ativa do TrainingPeaks via CDP no Chrome (servidor Realme).
- Consulta os treinos prescritos pela assessoria para os próximos 14 dias.
- Converte a estrutura de tiros, repetições, durações e zonas de FC para o formato Intervals.icu/Huawei Health.
- Publica no calendário do Intervals.icu (que envia diretamente para o Huawei Watch GT4).
- Registra histórico em `synced_planned_workouts.json`.
- Envia notificações no Telegram via STAS.
"""

import os
import sys
import time
import json
import logging
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- CONFIGURAÇÃO ---
LOG_FILE = BASE_DIR / "planned_sync.log"
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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DB_FILE = BASE_DIR / "synced_planned_workouts.json"

# Calibração do atleta Daniel Belini:
TP_LTHR = 179.0         # LTHR configurado na assessoria / TrainingPeaks
INTERVALS_LTHR = 155.0  # LTHR atual no perfil do Intervals.icu

PACE_TO_HR_MAP = [
    (0, 80, 125, 143),    # Z1/Z2 baixo (Easy/Aquecimento/Relaxar)
    (81, 86, 150, 154),   # Z2 baixo
    (86.1, 89, 154, 159), # Z2 alto
    (89.1, 94, 161, 168), # Z3
    (94.1, 110, 170, 179) # Z4 / Tiros
]


def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        logging.warning("Falha ao enviar mensagem no Telegram: %s", e)


def load_synced_db() -> dict:
    if DB_FILE.exists():
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_synced_db(data: dict) -> None:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def map_pace_to_bpm(min_pct: float, max_pct: float):
    mid = (min_pct + max_pct) / 2.0
    for p_min, p_max, hr_min, hr_max in PACE_TO_HR_MAP:
        if p_min <= mid <= p_max:
            return hr_min, hr_max
    return 130, 150


def bpm_to_intervals_lthr(hr_min: int, hr_max: int):
    pct_min = round((hr_min / INTERVALS_LTHR) * 100)
    pct_max = round((hr_max / INTERVALS_LTHR) * 100)
    return pct_min, pct_max


def convert_step(step: dict, primary_metric: str) -> str:
    name = step.get("name", "").strip()
    length = step.get("length", {})
    val = length.get("value", 0)
    unit = length.get("unit", "")

    if unit == "second":
        if val % 60 == 0:
            dur_str = f"{int(val // 60)}m"
        else:
            dur_str = f"{int(val)}s"
    elif unit == "meter":
        if val >= 1000 and val % 1000 == 0:
            dur_str = f"{int(val // 1000)}km"
        elif val >= 1000:
            dur_str = f"{val / 1000:.2f}km"
        else:
            dur_str = f"{int(val)} meters"
    else:
        dur_str = f"{int(val)}m"

    iclass = step.get("intensityClass", "").lower()
    if "warmup" in iclass:
        intensity = "warmup"
    elif "cooldown" in iclass:
        intensity = "cooldown"
    elif "rest" in iclass or "recovery" in iclass:
        intensity = "rest"
    else:
        intensity = "active"

    targets = step.get("targets", [])
    if targets and targets[0].get("minValue") is not None:
        t_min = targets[0].get("minValue")
        t_max = targets[0].get("maxValue")
        if primary_metric == "percentOfThresholdHr":
            hr_min = round(TP_LTHR * (t_min / 100.0))
            hr_max = round(TP_LTHR * (t_max / 100.0))
        else:
            hr_min, hr_max = map_pace_to_bpm(t_min, t_max)

        p_min, p_max = bpm_to_intervals_lthr(hr_min, hr_max)
        target_str = f"{p_min}-{p_max}% LTHR"
    else:
        target_str = "81-99% LTHR"

    line = f"- {dur_str} {target_str} intensity={intensity}"
    if name and not any(k in name.lower() for k in ("warmup", "cooldown")):
        return f"{name}\n{line}"
    return line


def convert_tp_workout(workout: dict) -> str:
    struct = workout.get("structure", {})
    items = struct.get("structure", [])
    primary_metric = struct.get("primaryIntensityMetric", "percentOfThresholdHr")

    lines = []
    for item in items:
        itype = item.get("type")
        if itype == "repetition":
            reps = item.get("length", {}).get("value", 1)
            lines.append(f"{reps}x")
            for s in item.get("steps", []):
                for sl in convert_step(s, primary_metric).split("\n"):
                    if sl.startswith("- "):
                        lines.append(sl)
            lines.append("")
        elif itype == "step":
            for s in item.get("steps", []):
                lines.append(convert_step(s, primary_metric))
                lines.append("")

    return "\n".join(lines).strip()


def sync_planned_workouts() -> None:
    if not API_KEY:
        logging.error("INTERVALS_API_KEY não configurada.")
        return

    # Importa get_tp_session do módulo base
    from sync_intervals_tp import get_tp_session

    try:
        auth_cookie, tp_athlete_id = get_tp_session()
    except Exception as e:
        logging.error("Falha ao obter sessão do TrainingPeaks via Chrome CDP: %s", e)
        return

    db = load_synced_db()

    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    url = f"https://tpapi.trainingpeaks.com/fitness/v6/athletes/{tp_athlete_id}/workouts/{start_date}/{end_date}"
    headers = {
        "Cookie": f"Production_tpAuth={auth_cookie}",
        "Origin": "https://app.trainingpeaks.com",
        "Referer": "https://app.trainingpeaks.com/",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        res = requests.get(url, headers=headers, timeout=20)
        if res.status_code != 200:
            logging.error("Erro na API do TP (%d): %s", res.status_code, res.text[:200])
            return
        workouts = res.json()
    except Exception as e:
        logging.error("Erro ao consultar treinos no TrainingPeaks: %s", e)
        return

    running_workouts = [
        w for w in workouts
        if w.get("workoutTypeValueId") == 3 and w.get("structure")
    ]

    logging.info("Treinos estruturados de corrida encontrados no TP: %d", len(running_workouts))

    for w in running_workouts:
        tp_id = str(w.get("workoutId"))
        title = w.get("title", "Treino de Corrida")
        workout_day = w.get("workoutDay")[:10]
        start_date_local = f"{workout_day}T07:00:00"

        # Converte para descrição Intervals/Huawei
        intervals_desc = convert_tp_workout(w)
        if not intervals_desc:
            logging.warning("Treino %s (%s) não gerou descrição compatível.", tp_id, title)
            continue

        intervals_auth = ("API_KEY", API_KEY)
        events_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events"

        if tp_id in db:
            # Já sincronizado anteriormente
            saved_event_id = db[tp_id].get("intervals_id")
            last_desc = db[tp_id].get("description", "")
            if last_desc != intervals_desc:
                # O treinador alterou o treino no TP! Atualiza no Intervals
                logging.info("Atualizando treino modificado: %s (%s)", title, workout_day)
                update_url = f"{events_url}/{saved_event_id}"
                put_res = requests.put(update_url, auth=intervals_auth, json={"description": intervals_desc}, timeout=15)
                if put_res.status_code in (200, 201):
                    db[tp_id]["description"] = intervals_desc
                    db[tp_id]["last_sync"] = datetime.now().isoformat()
                    save_synced_db(db)
                    send_telegram(
                        f"🔄 <b>Treino Atualizado pelo Treinador!</b>\n"
                        f"🏃‍♂️ <b>{title}</b> ({workout_day})\n"
                        f"Atualizado no Intervals.icu e Huawei Watch GT4."
                    )
            continue

        # Novo treino encontrado! Cria no Intervals.icu
        logging.info("Sincronizando novo treino: %s (%s)...", title, workout_day)
        payload = {
            "start_date_local": start_date_local,
            "category": "WORKOUT",
            "type": "Run",
            "name": title,
            "description": intervals_desc
        }

        try:
            c_res = requests.post(events_url, auth=intervals_auth, json=payload, timeout=20)
            if c_res.status_code in (200, 201):
                created_data = c_res.json()
                created_id = created_data.get("id")
                logging.info("Treino %s criado com sucesso no Intervals! ID: %s", title, created_id)

                db[tp_id] = {
                    "title": title,
                    "date": workout_day,
                    "intervals_id": created_id,
                    "description": intervals_desc,
                    "synced_at": datetime.now().isoformat()
                }
                save_synced_db(db)

                send_telegram(
                    f"🏃‍♂️ <b>Novo Treino Prescrito!</b>\n"
                    f"📌 <b>{title}</b>\n"
                    f"📅 Data: <b>{workout_day}</b>\n"
                    f"⌚ Sincronizado automaticamente para o <b>Huawei Watch GT4</b>!"
                )
            else:
                logging.error("Erro ao criar treino no Intervals (%d): %s", c_res.status_code, c_res.text[:200])
        except Exception as e:
            logging.error("Exceção ao criar treino no Intervals: %s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Executar em loop a cada 1 hora")
    args = parser.parse_args()

    if args.loop:
        logging.info("Iniciando monitor de treinos planejados (polling a cada 1 hora)...")
        while True:
            try:
                sync_planned_workouts()
            except Exception as ex:
                logging.error("Erro no ciclo: %s", ex)
            time.sleep(3600)
    else:
        sync_planned_workouts()
