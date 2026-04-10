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
        logging.info("🚀 Iniciando processo de upload para o TrainingPeaks...")
        driver = None
        
        try:
            chrome_options = Options()
            # Camuflagem: Sem modo headless explícito para o Cloudflare não bloquear
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Remove a flag de automação que os sites detectam
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # User-Agent de alta fidelidade
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
            
            chrome_options.binary_location = "/usr/bin/google-chrome"

            logging.info("🔧 Iniciando navegador via Monitor Virtual...")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Script extra para esconder o webdriver no navegador
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            wait = WebDriverWait(driver, 60)

            logging.info("🔑 Acessando TrainingPeaks...")
            driver.get("https://app.trainingpeaks.com/login")
            
            # Pausa para o site carregar sem pressa (bypass block)
            time.sleep(8)

            logging.info("⏳ Localizando campos de login...")
            username_field = wait.until(EC.element_to_be_clickable((By.ID, "username")))
            
            logging.info("✍️ Preenchendo credenciais...")
            username_field.send_keys(self.username)
            driver.find_element(By.ID, "password").send_keys(self.password)
            
            submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            driver.execute_script("arguments[0].click();", submit_button)
            
            logging.info("⏳ Aguardando Dashboard...")
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "calendar-container")))
            
            logging.info("📤 Dashboard OK! Enviando arquivo...")
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
                    logging.info(f"📸 Screenshot salva em {path}")
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
        print("🖥️  SERVIDOR SYNC ATIVO (Modo Camuflado)")
        print(f"📂 Monitorando: {watch_path}")
        print("="*40 + "\n")
        
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()