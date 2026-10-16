# 🏃‍♂️ Huawei Watch ⇄ TrainingPeaks: Sincronizador Bidirecional Automático

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Huawei Health](https://img.shields.io/badge/Huawei-Health%20Kit-red.svg)](https://consumer.huawei.com/)
[![TrainingPeaks](https://img.shields.io/badge/TrainingPeaks-Compatible-blue.svg)](https://www.trainingpeaks.com/)
[![Intervals.icu](https://img.shields.io/badge/Intervals.icu-Integrated-orange.svg)](https://intervals.icu/)

Solução 100% automatizada e independente para quem treina com relógios **Huawei (Watch GT4, GT3, Runner, Watch 4, Watch 5, etc.)** e tem treinos prescritos por assessoria de corrida no **TrainingPeaks**.

---

## 🎯 O Problema
Devido a restrições comerciais e embargos geopolíticos entre EUA e China, **não existe integração direta oficial entre a Huawei e o TrainingPeaks**:
1. Quem tem relógio Huawei precisa recriar os treinos estruturados da assessoria manualmente no app Huawei Health (bloco por bloco, tiro por tiro).
2. Após o treino, a atividade concluída não sobe diretamente para o TrainingPeaks sem gambiarras manuais de exportação de arquivos FIT.

## 💡 A Solução
Usamos o **Intervals.icu** (plataforma neutra sediada na África do Sul/Europa com parceria oficial do *Huawei Health Service Kit*) como uma **engrenagem invisível na nuvem**, combinada com um bot leve em Python:

* 📤 **Treinos Concluídos:** O relógio finaliza a corrida ➔ Huawei Health envia pra nuvem ➔ Intervals.icu recebe ➔ O bot faz upload automático para o **TrainingPeaks**.
* 📥 **Treinos Planejados (Assessoria):** O treinador monta a planilha no TrainingPeaks ➔ O bot lê via API e converte os tiros e zonas de batimento ➔ Publica no Intervals.icu ➔ Cai automaticamente no seu **Huawei Watch** como **Percurso Personalizado** (com avisos sonoros e vibrações de zona no pulso)!

---

## 🏗️ Arquitetura

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        1. TREINOS CONCLUÍDOS                           │
│  [ Huawei Watch GT4 ] ──(BT)──► [ Huawei Health ]                      │
│                                        │ (Health Service Kit - Nuvem)  │
│                                        ▼                               │
│  [ TrainingPeaks ] ◄──(API REST)── [ Intervals.icu ]                   │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                   2. TREINOS PLANEJADOS (ASSESSORIA)                   │
│  [ TrainingPeaks ] (Seu treinador prescreve os tiros/zonas)            │
│         │ (Extrator via Chrome CDP / Sessão REST)                      │
│         ▼                                                              │
│  [ Bot Sincronizador ] ──(Converte estrutura & FC)──► [ Intervals.icu ] │
│                                                              │         │
│                                           (Upload automático)│         │
│                                                              ▼         │
│  [ Huawei Watch GT4 ] ◄────────(Bluetooth)──────── [ Huawei Health ]   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📋 Receita de Bolo: Passo a Passo Completo

### Passo 1: Conectar o Huawei Health ao Intervals.icu
O Intervals.icu é gratuito e será a sua ponte oficial com a Huawei.

1. Crie uma conta gratuita em [intervals.icu](https://intervals.icu).
2. No seu celular com o aplicativo **Huawei Health**:
   * Vá em **Eu** ➔ **Gerenciamento de privacidade** (ou **Configurações**).
   * Toque em **Compartilhamento de dados e autorizações** ➔ **Kit de Serviços de Saúde (Health Service Kit)**.
   * Certifique-se de que a sincronização na nuvem está ativada.
3. No site do **Intervals.icu**:
   * Vá em **Settings (Configurações)** ➔ role até a seção **Connections (Conexões)**.
   * Ao lado de **HUAWEI Health**, clique em **Connect (Conectar)**.
   * Faça login com a sua conta Huawei ID e autorize o acesso.
   * **Importante:** Marque as caixas:
     - `Activities` (Sincronizar atividades concluídas)
     - `Upload planned workouts` (Enviar treinos planejados para o relógio).

---

### Passo 2: Configurar sua Frequência Limiar (LTHR) no Intervals.icu
Para que os tiros prescritos pela sua assessoria caiam com os batimentos cardíacos exatos no relógio:
1. No **Intervals.icu**, vá em **Settings (Configurações)** ➔ role até **Heart Rate (Frequência Cardíaca)**.
2. No campo **LTHR (Frequência Cardíaca Limiar)**, coloque o mesmo valor que sua assessoria usa no TrainingPeaks (por exemplo, `179` bpm).

---

### Passo 3: Obter as Chaves de API do Intervals.icu
1. Ainda na página de **Settings** do Intervals.icu:
   * No topo, anote o seu **Athlete ID** (formato: `iXXXXXX`).
2. Role até o final da página na seção **Developer Settings**:
   * Clique em **Generate API Key**.
   * Copie a chave gerada.

---

### Passo 4: Clonar o Repositório e Instalar Dependências
Você pode rodar este projeto em qualquer máquina com Python 3.10+ (Windows, Linux, macOS ou até mesmo direto em um celular Android antigo via **Termux**).

```bash
git clone https://github.com/Danimatos/corrida.git
cd corrida
pip install -r requirements.txt
```

---

### Passo 5: Configurar o Arquivo `.env`
Duplique o arquivo `.env.example` para `.env`:
```bash
cp .env.example .env
```

Abra o arquivo `.env` e preencha com seus dados:
```env
# Configurações do Intervals.icu
INTERVALS_ATHLETE_ID=iXXXXXX
INTERVALS_API_KEY=sua_chave_api_aqui

# TrainingPeaks
TP_ATHLETE_ID=seu_athlete_id_tp

# Conexão com o Chrome autenticado (ADB / CDP)
# Se rodar no próprio celular (Termux), use 127.0.0.1:5555
# Se rodar do computador conectando no celular via Wi-Fi, use o IP do celular:
ANDROID_ADB_TARGET=127.0.0.1:5555
ANDROID_CDP_PORT=9222

# Notificações no Telegram (Opcional)
TELEGRAM_TOKEN=seu_token_de_bot_do_telegram
TELEGRAM_CHAT_ID=seu_chat_id
```

---

### Passo 6: Autenticação com o TrainingPeaks (via Chrome DevTools)
Para não precisar salvar sua senha do TrainingPeaks em texto puro e contornar captchas:
1. Abra o navegador Chrome no dispositivo conectado ao ADB (computador ou celular Android).
2. Faça login normalmente na sua conta do [app.trainingpeaks.com](https://app.trainingpeaks.com).
3. O bot utiliza o protocolo **Chrome DevTools Protocol (CDP)** na porta `9222` para ler o cookie de autenticação ativo de forma segura.

---

## 🏃 Como Executar

### 1. Execução Única (Teste imediato):
Executa uma rodada completa de sincronização em ambos os sentidos e encerra:
```bash
python run_sync.py
```

### 2. Modo Contínuo (24/7 em segundo plano):
Fica rodando continuamente, realizando uma checagem leve a cada 15 minutos:
```bash
python run_sync.py --loop
```

### 3. Execução Isolada (se desejar rodar apenas um dos sentidos):
* **Apenas subir treinos feitos para o TrainingPeaks:**
  ```bash
  python sync_intervals_tp.py
  ```
* **Apenas baixar treinos da assessoria para o Huawei Watch:**
  ```bash
  python sync_planned_workouts.py
  ```

---

## ❓ Perguntas Frequentes (FAQ & Dicas)

#### 1. "Por que só o treino do próximo dia apareceu no meu relógio e não o mês inteiro?"
> **Esta é uma regra oficial do ecossistema Huawei Health.** A API da Huawei funciona com um sistema de **fila rotativa de 1 treino ativo por vez** (*"Only a single planned workout can be uploaded at a time"*).
> 
> O relógio sempre mantém na memória **o próximo treino da sua planilha** (ex: o treino de domingo). Assim que você correr no domingo e o relógio sincronizar, o sistema descarta o de domingo e **empurra automaticamente o treino de terça-feira**, mantendo seu relógio sempre limpo e organizado!

#### 2. "Onde eu acho o treino no relógio Huawei GT4?"
> No seu relógio:
> 1. Pressione o botão superior e selecione **Exercício**.
> 2. Vá em **Corrida ao ar livre**.
> 3. Desça a tela até **Percursos (ou Cursos)** ➔ **Percursos personalizados**.
> 4. O treino estará lá, pronto para iniciar com todas as metas de tempo, distância e batimento cardíaco!

#### 3. "Como rodar 24/7 sem deixar o PC ligado?"
> Você pode usar um celular Android antigo (como um servidor doméstico):
> 1. Instale o **Termux** no celular.
> 2. Ative a **Depuração sem Fio** nas Opções de Desenvolvedor.
> 3. Instale o Python e rode o script via `tmux` ou `nohup`.
> Toda vez que seu treinador colocar um treino novo na planilha, o relógio receberá o treino e seu bot do Telegram te avisará!

---

## 📄 Licença
Distribuído sob a licença **MIT**. Veja `LICENSE` para mais detalhes.
