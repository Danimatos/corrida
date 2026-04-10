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
        self.processed_files = set() # Evita processar o mesmo arquivo várias vezes

    def on_any_event(self, event):
        # Ignora diretórios e eventos de deleção
        if event.is_directory or event.event_type == 'deleted':
            return
            
        filename = os.path.basename(event.src_path)
        
        # Filtro: Contém "-RUNNING.fit" (case insensitive) e não foi processado
        if "-running.fit" in filename.lower() and filename not in self.processed_files:
            logging.info(f"⚡ Evento '{event.event_type}' detectado para: {filename}")
            
            # Adiciona ao set para não repetir o upload no mesmo ciclo
            self.processed_files.add(filename)
            
            # Aguarda o arquivo terminar de ser escrito/sincronizado
            time.sleep(15) 
            self.upload_to_tp(event.src_path)

    def upload_to_tp(self, file_path):
        logging.info("🚀 Iniciando processo de upload...")
        driver = None
        
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
            
            # Força o Selenium a usar o Chrome oficial que testamos no terminal
            chrome_options.binary_location = "/usr/bin/google-chrome"

            logging.info("🔧 Gerenciando ChromeDriver automaticamente...")
            
            # Voltamos ao Manager, que é mais inteligente para resolver caminhos
            service = Service(ChromeDriverManager().install())
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logging.info("🌍 Navegador aberto com sucesso!")
            
            driver.get("https://app.trainingpeaks.com/login")
            wait = WebDriverWait(driver, 60)

            logging.info("⏳ Aguardando campos de login...")
            username_field = wait.until(EC.element_to_be_clickable((By.ID, "username")))
            
            logging.info("✍️ Preenchendo credenciais...")
            username_field.send_keys(self.username)
            driver.find_element(By.ID, "password").send_keys(self.password)
            
            submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            driver.execute_script("arguments[0].click();", submit_button)
            
            logging.info("⏳ Aguardando Dashboard (pode demorar na VM)...")
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "calendar-container")))
            
            logging.info("📤 Dashboard carregado! Enviando arquivo...")
            upload_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            upload_input.send_keys(os.path.abspath(file_path))
            
            time.sleep(20) 
            logging.info(f"✅ SUCESSO: {os.path.basename(file_path)} enviado.")
            
        except Exception as e:
            logging.error(f"❌ Erro detectado: {e}")
            if driver:
                try:
                    driver.save_screenshot(os.path.expanduser("~/tp_sync/erro_debug.png"))
                    logging.info("📸 Screenshot salva em ~/tp_sync/erro_debug.png")
                except: pass
        finally:
            if driver:
                driver.quit()

if __name__ == "__main__":
    # Carrega caminho do .env
    watch_path = os.getenv("DRIVE_PATH")
    
    if not watch_path:
        logging.error("🛑 Erro: Variável DRIVE_PATH não encontrada no .env")
    elif not os.path.exists(watch_path):
        logging.error(f"🛑 Erro: O caminho {watch_path} não existe. Verifique o Rclone.")
    else:
        event_handler = TPHandler()
        observer = Observer()
        observer.schedule(event_handler, watch_path, recursive=False)
        
        print("\n" + "="*40)
        print("🖥️  SERVIDOR DE SINCRONIZAÇÃO ATIVO")
        print(f"📂 Monitorando: {watch_path}")
        print("="*40 + "\n")
        
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            logging.info("🛑 Servidor parado pelo usuário.")
        observer.join()