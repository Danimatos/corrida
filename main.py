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

# Configuração de Logs para você acompanhar no VS Code
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
load_dotenv()

class TrainingPeaksUploader(FileSystemEventHandler):
    def __init__(self):
        self.username = os.getenv("TP_USERNAME") 
        self.password = os.getenv("TP_PASS")

    def on_created(self, event):
        # Filtro rigoroso pelo padrão de nome enviado
        filename = os.path.basename(event.src_path)
        if not event.is_directory and "-RUNNING.fit" in filename:
            logging.info(f"🏃 Treino de corrida detectado: {filename}")
            # Aguarda 3 segundos para o Google Drive terminar de sincronizar o arquivo totalmente
            time.sleep(3)
            self.upload_process(event.src_path)

    def upload_process(self, file_path):
        chrome_options = Options()
        # Remova o '--headless' se quiser ver o robô trabalhando na primeira vez
        chrome_options.add_argument("--headless") 
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        wait = WebDriverWait(driver, 30)

    try:
            logging.info("🔑 Acessando TrainingPeaks...")
            driver.get("https://app.trainingpeaks.com/login")
            
            # Localiza o campo de username (o ID no HTML do TP ainda costuma ser 'username')
            wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(self.username)
            driver.find_element(By.ID, "password").send_keys(self.password)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            
            # Espera carregar o calendário (garante que logou)
            logging.info("⏳ Aguardando carregamento do Dashboard...")
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "calendar-container")))
            
            # Upload via input de arquivo
            logging.info("📤 Realizando upload do arquivo FIT...")
            upload_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
            upload_input.send_keys(os.path.abspath(file_path))
            
            # O TP precisa de alguns segundos para processar o arquivo após o envio
            time.sleep(10)
            logging.info(f"✅ FINALIZADO: {os.path.basename(file_path)} já está no seu TrainingPeaks.")
            
    except Exception as e:
            logging.error(f"❌ Erro durante o upload: {e}")
    finally:
            driver.quit()

if __name__ == "__main__":
    path = os.getenv("DRIVE_PATH")
    event_handler = TrainingPeaksUploader()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=False)
    
    print(f"--- MONITOR DE TREINOS ATIVO ---")
    print(f"Pasta: {path}")
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()