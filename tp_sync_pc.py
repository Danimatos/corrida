import os
import time
import logging
import requests
import shutil
import sys
import undetected_chromedriver as uc
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

# --- CONFIGURAÇÃO DE LOGS ---
log_path = os.path.join(os.path.dirname(__file__), "debug_sync.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_path, encoding='utf-8'), logging.StreamHandler()]
)

load_dotenv()

def send_telegram_msg(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, data=payload)
        except Exception as e:
            logging.error(f"❌ Erro ao enviar Telegram: {e}")

class TPHandler(FileSystemEventHandler):
    def __init__(self):
        self.username = os.getenv("TP_USERNAME")
        self.password = os.getenv("TP_PASS")

    def on_created(self, event):
        if not event.is_directory:
            self.process(event.src_path)

    def process(self, file_path):
        filename = os.path.basename(file_path)
        if "-running.fit" in filename.lower():
            logging.info(f"🏃 NOVO TREINO DETECTADO: {filename}")
            time.sleep(10) # Aguarda o arquivo terminar de copiar
            self.upload_to_tp(file_path)

    def upload_to_tp(self, file_path):
        filename = os.path.basename(file_path)
        logging.info(f"🚀 Iniciando sincronização: {filename}")
        driver = None
        
        try:
            options = uc.ChromeOptions()
            perfil_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perfil_robo")
            options.add_argument(f"--user-data-dir={perfil_dir}")
            options.add_argument("--window-size=1280,720")
            options.add_argument('--log-level=3') 
            
            driver = uc.Chrome(options=options, headless=True, use_subprocess=True) 
            wait = WebDriverWait(driver, 45)

            driver.get("https://app.trainingpeaks.com/")
            time.sleep(10)

            if "login" in driver.current_url.lower():
                wait.until(EC.element_to_be_clickable((By.ID, "username"))).send_keys(self.username)
                driver.find_element(By.ID, "password").send_keys(self.password)
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                time.sleep(5)

            upload_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
            upload_input.send_keys(os.path.abspath(file_path))
            
            time.sleep(20) 
            
            # Sucesso! Notificar e Mover
            msg = f"✅ *Treino Sincronizado!*\n🚀 Arquivo: `{filename}` já está no TrainingPeaks."
            logging.info(f"✅ SUCESSO: {filename}")
            send_telegram_msg(msg)
            
            # --- MOVENDO ARQUIVO PARA BACKUP ---
            backup_dir = os.path.join(os.path.dirname(file_path), "Sincronizados")
            if not os.path.exists(backup_dir): os.makedirs(backup_dir)
            shutil.move(file_path, os.path.join(backup_dir, filename))
            logging.info(f"📂 Arquivo movido para backup: {backup_dir}")
            
        except Exception as e:
            err_msg = f"❌ Erro ao sincronizar `{filename}`: {str(e)}"
            logging.error(err_msg)
            send_telegram_msg(err_msg)
        finally:
            if driver: driver.quit()

if __name__ == "__main__":
    watch_path = os.getenv("DRIVE_PATH")
    
    event_handler = TPHandler()
    
    # 1. Iniciar o observador
    observer = Observer()
    observer.schedule(event_handler, watch_path, recursive=False)
    observer.start()
    
    # 2. Avisar que acordou APENAS depois de startar o observador
    send_telegram_msg("🖥️ *O Robô do TrainingPeaks acordou!* \nEstou monitorando sua pasta de treinos. 🏃‍♂️💨")
    logging.info("🚀 Sistema iniciado e monitorando...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()