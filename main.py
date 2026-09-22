import os
import sys
import time
import json
import re
import base64
from typing import Tuple, Dict, Any

# ==============================================================================
# CARREGAMENTO DO .ENV
# ==============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")

try:
    from dotenv import load_dotenv

    if os.path.exists(ENV_PATH):
        load_dotenv(ENV_PATH)
        print(f"[ENV] .env carregado: {ENV_PATH}")
    else:
        print(f"[ENV] AVISO: .env não encontrado em: {ENV_PATH}")

except ImportError:
    print("[ENV] ERRO: python-dotenv não está instalado.")
    print("[ENV] Execute: pip install python-dotenv")
    sys.exit(1)


from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
import requests


# ==============================================================================
# CONFIGURAÇÕES E VARIÁVEIS DE AMBIENTE
# ==============================================================================

# Navegador
BROWSER_NAME = os.getenv("BROWSER", "firefox").lower()

# Chave da API
API_KEY = (
    os.getenv("DEEPSEEK_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ""
).strip()

# Fallback opcional para api_key.txt
if not API_KEY:
    api_key_file = os.path.join(SCRIPT_DIR, "api_key.txt")

    if os.path.exists(api_key_file):
        try:
            with open(api_key_file, "r", encoding="utf-8") as f:
                API_KEY = f.read().strip()

            if API_KEY:
                print("[API] Chave carregada de api_key.txt")

        except Exception as e:
            print(f"[API] Erro ao ler api_key.txt: {e}")


# Base URL
API_BASE_URL = (
    os.getenv("DEEPSEEK_BASE_URL")
    or "https://openrouter.ai/api/v1"
).strip()


# Modelo
MODEL_NAME = (
    os.getenv("DEEPSEEK_MODEL")
    or "deepseek/deepseek-r1"
).strip()


# URL padrão da plataforma
DEFAULT_LIVE_URL = (
    "https://label-exhed4afhtahh0b7.eastus2-01.azurewebsites.net/?"
    "projectId=sbs_general_pr_metareranker_v1&"
    "workerId=d94d4b737515d9d354ade51500541d12&"
    "hitId=reindeer.01a0ae60-8865-7bc2-9062-d117b8d7cf22&"
    "assignmentId=reindeer.01a0ae60-8865-7bc2-9062-d117b8d7cf22&"
    "source=toloka"
)

SITE_URL = os.getenv("TARGET_URL") or DEFAULT_LIVE_URL


# ==============================================================================
# VERIFICAÇÃO DA CONFIGURAÇÃO
# ==============================================================================

print()
print("=" * 70)
print(" CONFIGURAÇÃO")
print("=" * 70)
print(f"[ENV] Arquivo: {ENV_PATH}")
print(f"[ENV] Existe: {'SIM' if os.path.exists(ENV_PATH) else 'NÃO'}")
print(f"[API] Chave: {'CARREGADA' if API_KEY else 'NÃO ENCONTRADA'}")
print(f"[API] Base URL: {API_BASE_URL}")
print(f"[API] Modelo: {MODEL_NAME}")
print(f"[BROWSER] Navegador: {BROWSER_NAME}")
print("=" * 70)
print()


# ==============================================================================
# REGRAS DO GUIA DE AVALIAÇÃO
# ==============================================================================

SYSTEM_PROMPT = """
Você é um Diretor de Arte e Editor Profissional avaliando duas imagens
geradas por Inteligência Artificial (Imagem 1 e Imagem 2).

Sua missão é escolher a melhor imagem com base rigorosa no Guia de
Comparação Estética.

Você DEVE aplicar o Triple Balance (Triplo Equilíbrio):

1. VALOR ESTÉTICO E ARTÍSTICO (Peso Elevado):
   - Composição profissional, enquadramento sem cortes estranhos.
   - Iluminação expressiva e cores harmoniosas.
   - Evitar aspecto plástico-neon ou cores mortas.
   - Fator Uau e apelo visual geral.

2. INTEGRIDADE TÉCNICA E ESTRUTURAL (Peso Elevado):
   - Anatomia correta.
   - Mãos, dedos, rostos, olhos e articulações corretos.
   - Sem membros extras, partes derretidas ou rostos deformados.
   - Lógica física.
   - Sem objetos flutuantes, recortados ou fusões bizarras.
   - Ausência de artefatos.
   - Sem ruído, desfoque não intencional, assinaturas ou bordas indesejadas.

3. INTENÇÃO E RELEVÂNCIA DO PROMPT (Soft Gate):
   - A imagem deve capturar a ideia central e o tema principal do prompt.

   REGRA DE TRADE-OFF:
   Se a Imagem 1 cumpre 100% das palavras do prompt mas tem anatomia
   quebrada/glitches, e a Imagem 2 cumpre 90% mas é deslumbrante e
   biologicamente perfeita, a Imagem 2 DEVE VENCER.

4. SEGURANÇA E NSFW (Hard Gate):
   - Rejeitar conteúdo explícito ou NSFW.

RESPOSTA OBRIGATÓRIA:

Responda EXCLUSIVAMENTE um objeto JSON neste formato:

{
    "escolha": 1,
    "justificativa": "Explicação em português da razão técnica/estética da escolha entre 1 ou 2."
}

O campo "escolha" deve obrigatoriamente ser o número 1 ou o número 2.
"""


# ==============================================================================
# FUNÇÃO DE AVALIAÇÃO DA API
# ==============================================================================

def avaliar_imagens_com_deepseek(
    prompt_text: str,
    img1_b64: str,
    img2_b64: str
) -> Dict[str, Any]:

    """
    Envia o prompt e as duas imagens para a API compatível com OpenAI.

    NÃO existe mais fallback aleatório.
    Se a API não estiver configurada ou falhar, retorna erro explícito.
    """

    # --------------------------------------------------------------------------
    # VERIFICAR API KEY
    # --------------------------------------------------------------------------

    if not API_KEY or API_KEY in (
        "SUA_CHAVE_API_AQUI",
        "SUA_CHAVE_API"
    ):
        raise RuntimeError(
            "DEEPSEEK_API_KEY não encontrada.\n"
            f"Verifique o arquivo .env em:\n{ENV_PATH}\n\n"
            "Exemplo:\n"
            "DEEPSEEK_API_KEY=sk-or-v1-xxxxxxxx"
        )


    # --------------------------------------------------------------------------
    # HEADERS
    # --------------------------------------------------------------------------

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }


    # --------------------------------------------------------------------------
    # IMAGENS BASE64
    # --------------------------------------------------------------------------

    data_url_1 = (
        img1_b64
        if img1_b64.startswith("data:")
        else f"data:image/png;base64,{img1_b64}"
    )

    data_url_2 = (
        img2_b64
        if img2_b64.startswith("data:")
        else f"data:image/png;base64,{img2_b64}"
    )


    # --------------------------------------------------------------------------
    # MENSAGENS
    # --------------------------------------------------------------------------

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"PROMPT DA TAREFA:\n{prompt_text}\n\n"
                        "Analise detalhadamente a Imagem 1 e a Imagem 2 "
                        "com base nas regras do Guia de Comparação Estética.\n\n"
                        "Qual é a melhor?\n"
                        "Responda exclusivamente em JSON no formato:\n"
                        '{"escolha": 1, "justificativa": "..."}'
                    )
                },

                {
                    "type": "text",
                    "text": "=== IMAGEM 1 ==="
                },

                {
                    "type": "image_url",
                    "image_url": {
                        "url": data_url_1
                    }
                },

                {
                    "type": "text",
                    "text": "=== IMAGEM 2 ==="
                },

                {
                    "type": "image_url",
                    "image_url": {
                        "url": data_url_2
                    }
                }
            ]
        }
    ]


    # --------------------------------------------------------------------------
    # PAYLOAD
    # --------------------------------------------------------------------------

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.1
    }


    # --------------------------------------------------------------------------
    # REQUEST
    # --------------------------------------------------------------------------

    url = f"{API_BASE_URL.rstrip('/')}/chat/completions"

    print(
        f"[API] Enviando imagens para "
        f"{MODEL_NAME}..."
    )

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90
        )

        # Mostrar erro detalhado da API
        if not response.ok:

            try:
                error_data = response.json()
                error_message = json.dumps(
                    error_data,
                    ensure_ascii=False,
                    indent=2
                )
            except Exception:
                error_message = response.text

            raise RuntimeError(
                f"API retornou HTTP {response.status_code}:\n"
                f"{error_message}"
            )


        res_data = response.json()

        content = (
            res_data["choices"][0]["message"]["content"]
            .strip()
        )


        print(f"[API] Resposta recebida: {content[:300]}")


        # ----------------------------------------------------------------------
        # REMOVER MARKDOWN
        # ----------------------------------------------------------------------

        if "```" in content:

            content = re.sub(
                r"^```(?:json)?\s*",
                "",
                content,
                flags=re.MULTILINE | re.IGNORECASE
            )

            content = re.sub(
                r"```\s*$",
                "",
                content,
                flags=re.MULTILINE
            ).strip()


        # ----------------------------------------------------------------------
        # PARSE JSON
        # ----------------------------------------------------------------------

        try:

            parsed = json.loads(content)

            choice = (
                parsed.get("escolha")
                or parsed.get("choice")
                or parsed.get("selected_image")
            )


            if isinstance(choice, str):

                choice_lower = choice.lower()

                if (
                    choice_lower == "1"
                    or "image_1" in choice_lower
                    or "imagem 1" in choice_lower
                ):
                    choice = 1

                elif (
                    choice_lower == "2"
                    or "image_2" in choice_lower
                    or "imagem 2" in choice_lower
                ):
                    choice = 2


            if choice in (1, 2):

                return {
                    "escolha": int(choice),
                    "justificativa": parsed.get(
                        "justificativa",
                        content
                    )
                }

            raise ValueError(
                f"JSON recebido, mas escolha inválida: {choice}"
            )


        except json.JSONDecodeError as e:

            raise RuntimeError(
                "A API respondeu, mas não retornou JSON válido.\n"
                f"Resposta recebida:\n{content}"
            ) from e


    except requests.exceptions.Timeout as e:

        raise RuntimeError(
            "Timeout ao aguardar resposta da API."
        ) from e


    except requests.exceptions.RequestException as e:

        raise RuntimeError(
            f"Erro de conexão com a API: {e}"
        ) from e


# ==============================================================================
# CLASSE DE AUTOMAÇÃO SELENIUM
# ==============================================================================

class EvaluatorAutomation:

    def __init__(self, url: str):

        self.url = url
        self.driver = self._init_driver()


    # --------------------------------------------------------------------------
    # INICIALIZAR NAVEGADOR
    # --------------------------------------------------------------------------

    def _init_driver(self):

        browser = BROWSER_NAME

        print(
            f"[SELENIUM] Inicializando "
            f"{browser.upper()}..."
        )

        if browser == "firefox":

            firefox_options = FirefoxOptions()

            try:

                service = FirefoxService(
                    GeckoDriverManager().install()
                )

                driver = webdriver.Firefox(
                    service=service,
                    options=firefox_options
                )

            except Exception as e:

                print(
                    "[SELENIUM] GeckoDriverManager falhou."
                )

                print(
                    "[SELENIUM] Tentando Firefox padrão..."
                )

                driver = webdriver.Firefox(
                    options=firefox_options
                )


            try:
                driver.maximize_window()
            except Exception:
                pass

            return driver


        else:

            chrome_options = ChromeOptions()
            chrome_options.add_argument("--start-maximized")

            service = ChromeService(
                ChromeDriverManager().install()
            )

            return webdriver.Chrome(
                service=service,
                options=chrome_options
            )


    # --------------------------------------------------------------------------
    # CONECTAR À PÁGINA
    # --------------------------------------------------------------------------

    def conectar_ou_navegar(self):

        print(
            "[SELENIUM] Escaneando abas abertas..."
        )

        try:

            handles = self.driver.window_handles

            for handle in handles:

                self.driver.switch_to.window(handle)

                current_url = (
                    self.driver.current_url.lower()
                )

                current_title = (
                    self.driver.title.lower()
                )

                is_live_site = (

                    "azurewebsites.net" in current_url

                    or "toloka" in current_url

                    or "projectid=" in current_url

                    or "workerid=" in current_url

                    or "hitid=" in current_url

                    or "ferramenta de anotação" in current_title

                    or "qualidade visual" in current_title

                    or len(
                        self.driver.find_elements(
                            By.CSS_SELECTOR,
                            "input[name='selected_image'], .panel-radio"
                        )
                    ) > 0
                )


                if (
                    is_live_site
                    and "site.html" not in current_url
                ):

                    print(
                        "[SELENIUM] Conectado com sucesso:"
                    )

                    print(
                        f"URL: {self.driver.current_url}"
                    )

                    return


        except Exception as e:

            print(
                f"[AVISO TAB SCAN] {e}"
            )


        # ----------------------------------------------------------------------
        # NENHUMA ABA ENCONTRADA
        # ----------------------------------------------------------------------

        print(
            "[SELENIUM] Nenhuma aba compatível encontrada."
        )

        print(
            f"[SELENIUM] Navegando para:\n{self.url}"
        )

        self.driver.get(self.url)

        time.sleep(3)


    # --------------------------------------------------------------------------
    # EXTRAIR PROMPT
    # --------------------------------------------------------------------------

    def extrair_prompt(self) -> str:

        selectors = [

            "#prompt-text",
            ".prompt-box",
            ".prompt-text",
            "[data-testid='prompt']",
            ".prompt-container",
            "div.prompt-content",
            "div[class*='prompt']"
        ]


        for sel in selectors:

            try:

                elem = self.driver.find_element(
                    By.CSS_SELECTOR,
                    sel
                )

                text = elem.text.strip()

                if (
                    text
                    and "FONTE CONTEXTO" not in text
                ):

                    print(
                        f"[SELENIUM] Prompt detectado: "
                        f"{text[:100]}..."
                    )

                    return text


            except Exception:

                continue


        # ----------------------------------------------------------------------
        # FALLBACK XPATH
        # ----------------------------------------------------------------------

        try:

            elems = self.driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'criar') "
                "or contains(text(), 'Mockup') "
                "or contains(text(), 'foto') "
                "or contains(text(), 'retrato') "
                "or contains(text(), 'estilo')]"
            )


            for el in elems:

                t = el.text.strip()

                if (
                    len(t) > 10
                    and "FONTE CONTEXTO" not in t
                    and "Ferramenta" not in t
                ):

                    print(
                        f"[SELENIUM] Prompt detectado via XPath: "
                        f"{t[:100]}..."
                    )

                    return t


        except Exception:
            pass


        return "Prompt de anotação."


    # --------------------------------------------------------------------------
    # CAPTURAR IMAGEM
    # --------------------------------------------------------------------------

    def capturar_imagem_b64(self, element) -> str:

        try:

            screenshot_png = (
                element.screenshot_as_png
            )

            return base64.b64encode(
                screenshot_png
            ).decode("utf-8")


        except Exception as e:

            print(
                f"[ERRO SCREENSHOT] "
                f"Falha ao capturar imagem: {e}"
            )

            return ""


    # --------------------------------------------------------------------------
    # LOCALIZAR IMAGENS E RADIOS
    # --------------------------------------------------------------------------

    def obter_elementos_imagem_e_radios(
        self
    ) -> Tuple[Any, Any, Any, Any]:

        # ----------------------------------------------------------------------
        # RADIO 1
        # ----------------------------------------------------------------------

        radio1 = None

        for sel in [

            "input[name='selected_image'][value='image_1']",
            "input.panel-radio[value='image_1']",
            "input[value='image_1']"

        ]:

            try:

                elems = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    sel
                )

                if elems:

                    radio1 = elems[0]
                    break


            except Exception:
                pass


        # ----------------------------------------------------------------------
        # RADIO 2
        # ----------------------------------------------------------------------

        radio2 = None

        for sel in [

            "input[name='selected_image'][value='image_2']",
            "input.panel-radio[value='image_2']",
            "input[value='image_2']"

        ]:

            try:

                elems = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    sel
                )

                if elems:

                    radio2 = elems[0]
                    break


            except Exception:
                pass


        # ----------------------------------------------------------------------
        # IMAGENS
        # ----------------------------------------------------------------------

        img1 = None
        img2 = None


        if radio1:

            try:

                container1 = radio1.find_element(
                    By.XPATH,
                    "./ancestor::*["
                    "contains(@class, 'card') "
                    "or contains(@class, 'panel') "
                    "or contains(@class, 'box') "
                    "or contains(@class, 'grid') "
                    "or position()=last()"
                    "]"
                )

                imgs1 = container1.find_elements(
                    By.TAG_NAME,
                    "img"
                )

                if imgs1:
                    img1 = imgs1[0]


            except Exception:
                pass


        if radio2:

            try:

                container2 = radio2.find_element(
                    By.XPATH,
                    "./ancestor::*["
                    "contains(@class, 'card') "
                    "or contains(@class, 'panel') "
                    "or contains(@class, 'box') "
                    "or contains(@class, 'grid') "
                    "or position()=last()"
                    "]"
                )

                imgs2 = container2.find_elements(
                    By.TAG_NAME,
                    "img"
                )

                if imgs2:
                    img2 = imgs2[0]


            except Exception:
                pass


        # ----------------------------------------------------------------------
        # FALLBACK
        # ----------------------------------------------------------------------

        if not img1 or not img2:

            imgs_page = self.driver.find_elements(
                By.CSS_SELECTOR,
                "img.task-image, "
                "#img1, "
                "#img2, "
                ".comparison-grid img, "
                "img"
            )


            valid_imgs = [

                i for i in imgs_page

                if (
                    i.size.get("width", 0) > 80
                    or i.size.get("height", 0) > 80
                )

            ]


            if len(valid_imgs) >= 2:

                img1 = valid_imgs[0]
                img2 = valid_imgs[1]

            elif len(imgs_page) >= 2:

                img1 = imgs_page[0]
                img2 = imgs_page[1]


        if not img1 or not img2:

            raise Exception(
                "Não foi possível localizar "
                "as Imagens 1 e 2."
            )


        return radio1, radio2, img1, img2


    # --------------------------------------------------------------------------
    # SELECIONAR E SUBMETER
    # --------------------------------------------------------------------------

    def selecionar_e_submeter(
        self,
        escolha: int,
        radio1,
        radio2
    ):

        if escolha not in (1, 2):

            raise ValueError(
                f"Escolha inválida recebida da IA: {escolha}"
            )


        val_target = f"image_{escolha}"

        print(
            f"[SELENIUM] Selecionando "
            f"Imagem {escolha}..."
        )


        target_radio = (
            radio1
            if escolha == 1
            else radio2
        )

        radio_clicado = False


        # ----------------------------------------------------------------------
        # CLIQUE DIRETO
        # ----------------------------------------------------------------------

        if target_radio:

            try:

                self.driver.execute_script(
                    """
                    arguments[0].checked = true;
                    arguments[0].dispatchEvent(
                        new Event('change', {bubbles: true})
                    );
                    arguments[0].click();
                    """,
                    target_radio
                )

                radio_clicado = True

                print(
                    f"[SELENIUM] Radio "
                    f"{val_target} marcado."
                )


            except Exception as e:

                print(
                    f"[AVISO CLIQUE RADIO] {e}"
                )


        # ----------------------------------------------------------------------
        # FALLBACK POR SELETOR
        # ----------------------------------------------------------------------

        if not radio_clicado:

            radio_selectors = [

                f"input[name='selected_image'][value='{val_target}']",

                f"input.panel-radio[value='{val_target}']",

                f"input[value='{val_target}']",

                f"#radio-{escolha}"

            ]


            for r_sel in radio_selectors:

                try:

                    radios = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        r_sel
                    )

                    if radios:

                        self.driver.execute_script(
                            """
                            arguments[0].checked = true;
                            arguments[0].click();
                            """,
                            radios[0]
                        )

                        print(
                            f"[SELENIUM] Radio marcado "
                            f"via seletor: {r_sel}"
                        )

                        radio_clicado = True
                        break


                except Exception:

                    continue


        if not radio_clicado:

            raise RuntimeError(
                f"Não foi possível selecionar "
                f"Imagem {escolha}."
            )


        # ----------------------------------------------------------------------
        # TECLA 1 OU 2
        # ----------------------------------------------------------------------

        try:

            body = self.driver.find_element(
                By.TAG_NAME,
                "body"
            )

            body.send_keys(str(escolha))

        except Exception:
            pass


        time.sleep(0.5)


        # ----------------------------------------------------------------------
        # ENTER
        # ----------------------------------------------------------------------

        print(
            "[SELENIUM] Pressionando ENTER..."
        )

        try:

            body = self.driver.find_element(
                By.TAG_NAME,
                "body"
            )

            body.send_keys(Keys.ENTER)

        except Exception as e:

            print(
                f"[AVISO ENTER] {e}"
            )


        # ----------------------------------------------------------------------
        # BOTÃO SUBMIT
        # ----------------------------------------------------------------------

        try:

            submits = self.driver.find_elements(
                By.CSS_SELECTOR,
                "#submit-btn, "
                ".submit-btn, "
                "button[type='submit']"
            )


            for btn in submits:

                if btn.is_enabled():

                    btn.click()
                    break


        except Exception:
            pass


    # --------------------------------------------------------------------------
    # LOOP PRINCIPAL
    # --------------------------------------------------------------------------

    def executar_loop(
        self,
        max_tarefas: int = 100
    ):

        self.conectar_ou_navegar()

        tarefas_executadas = 0
        prompt_anterior = ""


        while tarefas_executadas < max_tarefas:

            print()
            print("=" * 60)
            print(
                f"PROCESSANDO TAREFA "
                f"#{tarefas_executadas + 1}"
            )
            print("=" * 60)


            try:

                # --------------------------------------------------------------
                # 1. PROMPT
                # --------------------------------------------------------------

                prompt_text = (
                    self.extrair_prompt()
                )


                # --------------------------------------------------------------
                # ESPERAR NOVA TAREFA
                # --------------------------------------------------------------

                if (
                    prompt_text == prompt_anterior
                    and tarefas_executadas > 0
                ):

                    print(
                        "[SELENIUM] Aguardando "
                        "nova tarefa..."
                    )

                    time.sleep(2.5)

                    prompt_text = (
                        self.extrair_prompt()
                    )


                prompt_anterior = prompt_text


                # --------------------------------------------------------------
                # 2. IMAGENS E RADIOS
                # --------------------------------------------------------------

                (
                    radio1,
                    radio2,
                    img1_elem,
                    img2_elem
                ) = self.obter_elementos_imagem_e_radios()


                # --------------------------------------------------------------
                # 3. SCREENSHOTS
                # --------------------------------------------------------------

                img1_b64 = (
                    self.capturar_imagem_b64(
                        img1_elem
                    )
                )

                img2_b64 = (
                    self.capturar_imagem_b64(
                        img2_elem
                    )
                )


                if not img1_b64 or not img2_b64:

                    print(
                        "[ERRO] Não foi possível "
                        "capturar as imagens."
                    )

                    time.sleep(3)
                    continue


                # --------------------------------------------------------------
                # 4. IA
                # --------------------------------------------------------------

                print(
                    "[AI] Enviando imagens "
                    "para análise..."
                )


                try:

                    decisao = (
                        avaliar_imagens_com_deepseek(
                            prompt_text,
                            img1_b64,
                            img2_b64
                        )
                    )


                except Exception as e:

                    print()
                    print("!" * 70)
                    print("[ERRO CRÍTICO DA IA]")
                    print(str(e))
                    print("!" * 70)
                    print()

                    print(
                        "[SEGURANÇA] Nenhuma escolha "
                        "será feita automaticamente."
                    )

                    # NÃO escolhe aleatoriamente.
                    # NÃO envia a tarefa.
                    time.sleep(5)

                    continue


                # --------------------------------------------------------------
                # 5. DECISÃO
                # --------------------------------------------------------------

                escolha = decisao.get(
                    "escolha"
                )

                justificativa = decisao.get(
                    "justificativa",
                    "Sem justificativa."
                )


                if escolha not in (1, 2):

                    print(
                        "[ERRO] A IA retornou "
                        f"uma escolha inválida: {escolha}"
                    )

                    time.sleep(3)
                    continue


                print()
                print("=" * 60)
                print(
                    f"[DECISÃO DA IA] "
                    f"IMAGEM {escolha}"
                )
                print(
                    f"[JUSTIFICATIVA] "
                    f"{justificativa}"
                )
                print("=" * 60)
                print()


                # --------------------------------------------------------------
                # 6. SELECIONAR E ENVIAR
                # --------------------------------------------------------------

                self.selecionar_e_submeter(
                    escolha,
                    radio1,
                    radio2
                )


                tarefas_executadas += 1

                time.sleep(2.5)


            except KeyboardInterrupt:

                print(
                    "\n[AUTOMAÇÃO] "
                    "Interrompida pelo usuário."
                )

                break


            except Exception as e:

                print(
                    f"[ERRO NO LOOP] {e}"
                )

                time.sleep(3)


        print()
        print("=" * 60)
        print(
            f"[FIM] Total de tarefas processadas: "
            f"{tarefas_executadas}"
        )
        print("=" * 60)


    # --------------------------------------------------------------------------
    # FECHAR
    # --------------------------------------------------------------------------

    def fechar(self):

        print(
            "[SELENIUM] Encerrando navegador..."
        )

        try:

            self.driver.quit()

        except Exception:

            pass


# ==============================================================================
# PONTO DE ENTRADA
# ==============================================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        " AUTOMAÇÃO DE ANOTAÇÃO VISUAL "
        "COM IA"
    )
    print("=" * 70)


    url_alvo = SITE_URL


    # URL passada pela linha de comando
    if (
        len(sys.argv) > 1
        and sys.argv[1].strip()
    ):

        url_alvo = sys.argv[1].strip()


    print(
        f"URL Alvo: {url_alvo}"
    )

    print(
        f"Navegador: {BROWSER_NAME.upper()}"
    )

    print(
        f"Modelo API: {MODEL_NAME}"
    )

    print(
        f"Base URL API: {API_BASE_URL}"
    )


    # --------------------------------------------------------------------------
    # NÃO INICIAR SE NÃO HOUVER API KEY
    # --------------------------------------------------------------------------

    if not API_KEY:

        print()
        print("!" * 70)
        print(
            " ERRO: API KEY NÃO ENCONTRADA"
        )
        print("!" * 70)
        print()
        print(
            "Crie um arquivo .env na mesma pasta "
            "deste script."
        )
        print()
        print(
            "Exemplo:"
        )
        print(
            "DEEPSEEK_API_KEY=sk-or-v1-xxxxxxxx"
        )
        print(
            "DEEPSEEK_BASE_URL=https://openrouter.ai/api/v1"
        )
        print(
            "DEEPSEEK_MODEL=seu-modelo-de-visao"
        )
        print()
        print(
            "O programa foi encerrado para evitar "
            "escolhas aleatórias."
        )
        print()

        sys.exit(1)


    # --------------------------------------------------------------------------
    # INICIAR AUTOMAÇÃO
    # --------------------------------------------------------------------------

    automation = EvaluatorAutomation(
        url=url_alvo
    )


    try:

        max_t = int(
            os.getenv(
                "MAX_TASKS",
                "100"
            )
        )


        automation.executar_loop(
            max_tarefas=max_t
        )


    finally:

        automation.fechar()