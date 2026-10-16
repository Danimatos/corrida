"""Executor Central de Sincronização de Corridas

1. Sentido Treinos Concluídos:
   Huawei Watch GT4 -> Intervals.icu -> TrainingPeaks

2. Sentido Treinos Planejados (Assessoria):
   TrainingPeaks -> Intervals.icu -> Huawei Watch GT4
"""

import sys
import time
import logging
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from sync_intervals_tp import sync_recent_runs
from sync_planned_workouts import sync_planned_workouts

LOG_FILE = BASE_DIR / "runner.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)


def run_full_sync():
    logging.info("=== INICIANDO CICLO COMPLETO DE SINCRONIZAÇÃO ===")
    
    # 1. Sincroniza atividades concluídas recentes para o TrainingPeaks
    try:
        logging.info("1/2: Verificando treinos concluídos (Intervals -> TP)...")
        sync_recent_runs()
    except Exception as e:
        logging.error("Erro ao sincronizar treinos concluídos: %s", e)

    # 2. Sincroniza treinos planejados da assessoria para o Huawei Watch
    try:
        logging.info("2/2: Verificando treinos planejados (TP -> Intervals -> Huawei)...")
        sync_planned_workouts()
    except Exception as e:
        logging.error("Erro ao sincronizar treinos planejados: %s", e)

    logging.info("=== CICLO FINALIZADO COM SUCESSO ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Executar continuamente a cada 15 minutos")
    args = parser.parse_args()

    if args.loop:
        logging.info("Iniciando modo contínuo (loop a cada 15 minutos)...")
        while True:
            run_full_sync()
            time.sleep(900)
    else:
        run_full_sync()
