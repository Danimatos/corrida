import os
import time
import logging
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

class TPHandler(FileSystemEventHandler):
    def __init__(self):
        self.username = os.getenv("TP_USERNAME")
        self.password = os.getenv("TP_PASS")
        self.processed_files = set()

    def on_any_event(self, event):
        if event.is_directory or event.event_type == 'deleted':
            return
        
        filename = os.path.basename(event.src_path)
        
        # Filtro rígido para evitar duplicidade e arquivos temporários
        if "-running.fit" in filename.lower() and filename not in self.processed_files:
            logging.info(f"🏃 NOVO TREINO DETECTADO: {filename}")
            self.processed_files.add(filename)
            
            # Espera o arquivo ser totalmente escrito no disco (evita erro de arquivo aberto)
            time.sleep(10) 
            self.upload_to_tp(event.src_path)

    def upload_to_tp(self, file_path):
        logging.info(f"🚀 Iniciando sincronização: {os.path.basename(file_path)}")
        driver = None
        try:
            options = uc.ChromeOptions()
            script_dir = os.path.dirname(os.path.abspath(__file__))
            perfil_dir = os.path.join(script_dir, "perfil_robo")
            
            options.add_argument(f"--user-data-dir={perfil_dir}")
            options.add_argument("--window-size=1280,720")
            
            # Inicia o Chrome (pode ser headless=True agora se quiser que seja 100% invisível)
            driver = uc.Chrome(options=options, headless=True) 
            wait = WebDriverWait(driver, 40)

            driver.get("https://app.trainingpeaks.com/")
            
            # Pequena pausa para garantir carregamento dos cookies
            time.sleep(7)

            # Caso a sessão expire, ele faz o login novamente
            if "login" in driver.current_url.lower():
                logging.info("🔐 Sessão expirada. Refazendo login...")
                user_field = wait.until(EC.element_to_be_clickable((By.ID, "username")))
                user_field.send_keys(self.username)
                driver.find_element(By.ID, "password").send_keys(self.password)
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                time.sleep(5)

            # Upload direto
            logging.info("📤 Dashboard pronto. Injetando arquivo FIT...")
            upload_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
            upload_input.send_keys(os.path.abspath(file_path))
            
            # Aguarda o progresso do upload (aquele círculo que você viu)
            time.sleep(20) 
            logging.info(f"✅ SUCESSO: {os.path.basename(file_path)} enviado ao TrainingPeaks.")
            
        except Exception as e:
            logging.error(f"❌ Falha no upload: {e}")
        finally:
            if driver:
                driver.quit()
                logging.info("🔒 Navegador fechado e pronto para a próxima.")

if __name__ == "__main__":
    watch_path = os.getenv("DRIVE_PATH")
    if not watch_path or not os.path.exists(watch_path):
        logging.error(f"🛑 Caminho da pasta inválido: {watch_path}")
    else:
        event_handler = TPHandler()
        observer = Observer()
        observer.schedule(event_handler, watch_path, recursive=False)
        
        print("\n" + "═"*45)
        print("    🏃 SERVIDOR DE SINCRONIZAÇÃO ATIVO 🏃")
        print(f"    📂 MONITORANDO: {watch_path}")
        print("    🤖 MODO: PERFIL ISOLADO (INVISIBLE)")
        print("    (Pressione Ctrl+C para parar)")
        print("═"*45 + "\n")
        
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("🛑 Servidor parado pelo usuário.")
            observer.stop()
        observer.join()