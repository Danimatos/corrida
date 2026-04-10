import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tp_sync.log"),
        logging.StreamHandler()
    ]
)

load_dotenv()

class TPHandler(FileSystemEventHandler):
    def __init__(self):
        self.username = os.getenv("TP_USERNAME")
        self.password = os.getenv("TP_PASS")
        self.processed_files = set()

    def on_any_event(self, event):
        if event.is_directory or event.event_type == 'deleted':
            return
            
        filename = os.path.basename(event.src_path)
        
        if "-running.fit" in filename.lower() and filename not in self.processed_files:
            logging.info(f"⚡ Evento '{event.event_type}' detectado para: {filename}")
            self.processed_files.add(filename)
            time.sleep(15) 
            self.upload_to_tp(event.src_path)

    def upload_to_tp(self, file_path):
        logging.info("🚀 Iniciando processo de upload (Modo Camuflagem iPhone)...")
        driver = None
        
        try:
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            
            # --- CONFIGURAÇÃO DE EMULAÇÃO MOBILE (iPhone) ---
            mobile_emulation = {
                "deviceMetrics": { "width": 390, "height": 844, "pixelRatio": 3.0 },
                "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            }
            chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
            
            # Esconde rastros de automação
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            chrome_options.binary_location = "/usr/bin/google-chrome"

            logging.info("🔧 Inicializando driver com perfil Mobile...")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Script extra para remover o objeto navigator.webdriver
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            wait = WebDriverWait(driver, 60)

            # 1. Primeiro vai ao Google para criar um histórico/referer
            logging.info("🌍 Passando pelo Google para 'aquecer' o IP...")
            driver.get("https://www.google.com")
            time.sleep(3)

            # 2. Tenta o acesso ao TrainingPeaks
            logging.info("🔑 Acessando TrainingPeaks...")
            driver.get("https://app.trainingpeaks.com/login")
            
            # Pausa para o firewall analisar o "iPhone"
            time.sleep(10)

            logging.info("⏳ Localizando campos de login...")
            username_field = wait.until(EC.element_to_be_clickable((By.ID, "username")))
            
            logging.info("✍️ Preenchendo credenciais...")
            username_field.send_keys(self.username)
            driver.find_element(By.ID, "password").send_keys(self.password)
            
            submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            driver.execute_script("arguments[0].click();", submit_button)
            
            logging.info("⏳ Aguardando Dashboard...")
            # Em mobile, o seletor pode ser ligeiramente diferente, mas mantemos o padrão por enquanto
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "calendar-container")))
            
            logging.info("📤 Enviando arquivo FIT...")
            upload_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            upload_input.send_keys(os.path.abspath(file_path))
            
            time.sleep(20) 
            logging.info(f"✅ SUCESSO: {os.path.basename(file_path)} sincronizado.")
            
        except Exception as e:
            logging.error(f"❌ Erro detectado: {e}")
            if driver:
                try:
                    path = os.path.expanduser("~/tp_sync/erro_debug.png")
                    driver.save_screenshot(path)
                    logging.info(f"📸 Screenshot de erro salva em {path}")
                except: pass
        finally:
            if driver:
                driver.quit()
                logging.info("🔒 Sessão encerrada.")

if __name__ == "__main__":
    watch_path = os.getenv("DRIVE_PATH")
    
    if not watch_path or not os.path.exists(watch_path):
        logging.error(f"🛑 Erro: Pasta {watch_path} não encontrada.")
    else:
        event_handler = TPHandler()
        observer = Observer()
        observer.schedule(event_handler, watch_path, recursive=False)
        
        print("\n" + "="*40)
        print("🖥️  SERVIDOR SYNC (ESTRATÉGIA IPHONE)")
        print(f"📂 Monitorando: {watch_path}")
        print("="*40 + "\n")
        
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()