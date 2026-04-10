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
        logging.info("🚀 Iniciando processo de upload para o TrainingPeaks...")
        driver = None # Inicializa como None para evitar erro de escopo no 'finally'
        
        try:
            # Configurações do Chrome para rodar em servidor de 1GB RAM
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Inicialização do Driver
            logging.info("🔧 Preparando o WebDriver...")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            wait = WebDriverWait(driver, 45)

            # Login
            logging.info("🔑 Acessando TrainingPeaks e realizando login...")
            driver.get("https://app.trainingpeaks.com/login")
            
            wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(self.username)
            driver.find_element(By.ID, "password").send_keys(self.password)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            
            # Espera o Dashboard carregar (calendário)
            logging.info("⏳ Aguardando carregamento do Dashboard...")
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "calendar-container")))
            
            # Upload do arquivo
            logging.info("📤 Enviando arquivo FIT...")
            upload_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            upload_input.send_keys(os.path.abspath(file_path))
            
            # Tempo para o TP processar o arquivo antes de fechar o navegador
            time.sleep(15) 
            logging.info(f"✅ SUCESSO: {os.path.basename(file_path)} enviado com sucesso!")
            
        except Exception as e:
            logging.error(f"❌ FALHA no processo: {e}")
        finally:
            if driver:
                driver.quit()
                logging.info("🔒 Sessão do navegador encerrada.")

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