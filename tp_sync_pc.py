import os
import time
import logging
import requests
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
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

load_dotenv()

def send_telegram_msg(message):
    """Envia notificação para o bot do Telegram"""
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
        self.processed_files = set()

    def on_created(self, event):
        if not event.is_directory:
            self.process(event.src_path)

    def process(self, file_path):
        filename = os.path.basename(file_path)
        # Filtro para arquivos de corrida que ainda não foram processados nesta sessão
        if "-running.fit" in filename.lower() and filename not in self.processed_files:
            logging.info(f"🏃 NOVO TREINO DETECTADO: {filename}")
            self.processed_files.add(filename)
            # Aguarda o Google Drive terminar de escrever o arquivo
            time.sleep(10) 
            self.upload_to_tp(file_path)

    def upload_to_tp(self, file_path):
        filename = os.path.basename(file_path)
        logging.info(f"🚀 Iniciando sincronização: {filename}")
        driver = None
        
        try:
            options = uc.ChromeOptions()
            script_dir = os.path.dirname(os.path.abspath(__file__))
            perfil_dir = os.path.join(script_dir, "perfil_robo")
            
            options.add_argument(f"--user-data-dir={perfil_dir}")
            options.add_argument("--window-size=1280,720")
            options.add_argument('--log-level=3') 
            
            # headless=True para rodar sem abrir janela
            driver = uc.Chrome(options=options, headless=True, use_subprocess=True) 
            wait = WebDriverWait(driver, 45)

            driver.get("https://app.trainingpeaks.com/")
            time.sleep(8)

            # Se o perfil deslogar, ele refaz o login
            if "login" in driver.current_url.lower():
                logging.info("🔐 Sessão expirada, refazendo login...")
                wait.until(EC.element_to_be_clickable((By.ID, "username"))).send_keys(self.username)
                driver.find_element(By.ID, "password").send_keys(self.password)
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                time.sleep(5)

            # Localiza o input de arquivo e envia
            logging.info("📤 Enviando para o Dashboard...")
            upload_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
            upload_input.send_keys(os.path.abspath(file_path))
            
            # Aguarda o processamento do site
            time.sleep(20) 
            
            msg = f"✅ *Treino Sincronizado!*\n🚀 Arquivo: `{filename}` já está no TrainingPeaks."
            logging.info(f"✅ SUCESSO: {filename}")
            send_telegram_msg(msg)
            
        except Exception as e:
            err_msg = f"❌ Erro ao sincronizar `{filename}`: {str(e)}"
            logging.error(err_msg)
            send_telegram_msg(err_msg)
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                logging.info("🔒 Sessão encerrada.")

if __name__ == "__main__":
    watch_path = os.getenv("DRIVE_PATH")
    
    if not watch_path or not os.path.exists(watch_path):
        logging.error(f"🛑 Caminho da pasta inválido: {watch_path}")
        sys.exit(1)

    event_handler = TPHandler()
    
    # --- MODO DE RECUPERAÇÃO ---
    # Verifica se já existem arquivos na pasta ao iniciar o script
    logging.info("🔍 Verificando arquivos pendentes na pasta...")
    for f in os.listdir(watch_path):
        if "-running.fit" in f.lower():
            event_handler.process(os.path.join(watch_path, f))

    observer = Observer()
    observer.schedule(event_handler, watch_path, recursive=False)
    
    print("\n" + "═"*45)
    print("    🏃 SERVIDOR DE SINCRONIZAÇÃO ATIVO 🏃")
    print(f"    📂 MONITORANDO: {watch_path}")
    print("    🤖 MODO: INVISÍVEL + NOTIFICAÇÃO TELEGRAM")
    print("═"*45 + "\n")
    
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()