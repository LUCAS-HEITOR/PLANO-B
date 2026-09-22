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
Você é um Diretor de Arte e Editor Profissional avaliando tarefas de comparação de imagens geradas por Inteligência Artificial exibidas na tela do navegador.

Sua missão é analisar a captura de tela inteira do navegador e escolher a melhor opção (A ou B) com base no Guia de Comparação Estética.

Você DEVE aplicar o Triple Balance (Triplo Equilíbrio):

1. VALOR ESTÉTICO E ARTÍSTICO (Peso Elevado):
   - Composição profissional, enquadramento sem cortes estranhos.
   - Iluminação expressiva e cores harmoniosas.
   - Evitar aspecto plástico-neon ou cores mortas.
   - Fator Uau e apelo visual geral.

2. INTEGRIDADE TÉCNICA E ESTRUTURAL (Peso Elevado):
   - Anatomia correta (mãos, dedos, rostos, olhos, articulações).
   - Sem membros extras, partes derretidas ou rostos deformados.
   - Lógica física (sem objetos flutuantes, recortados ou fusões bizarras).
   - Ausência de artefatos, ruído, desfoque não intencional ou bordas indesejadas.

3. INTENÇÃO E RELEVÂNCIA DO PROMPT (Soft Gate):
   - A imagem deve capturar a ideia central do prompt.
   - REGRA DE TRADE-OFF: Se a Opção A cumpre 100% do prompt mas tem anatomia quebrada/glitches, e a Opção B cumpre 90% mas é deslumbrante e tecnicamente perfeita, a Opção B DEVE VENCER.

4. SEGURANÇA E NSFW (Hard Gate):
   - Rejeitar conteúdo explícito ou NSFW.

RESPOSTA OBRIGATÓRIA:

Responda EXCLUSIVAMENTE um objeto JSON neste formato:

{
    "escolha": "A",
    "justificativa": "Explicação em português da razão técnica/estética da escolha entre A e B."
}

O campo "escolha" deve obrigatoriamente ser a letra "A" ou a letra "B" (ou 1 ou 2).
"""


# ==============================================================================
# FUNÇÃO DE AVALIAÇÃO DA API
# ==============================================================================

def avaliar_tela_com_deepseek(
    prompt_text: str,
    screenshot_b64: str
) -> Dict[str, Any]:
    """
    Envia a captura de tela inteira do navegador para a API de visão.
    """

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

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data_url = (
        screenshot_b64
        if screenshot_b64.startswith("data:")
        else f"data:image/png;base64,{screenshot_b64}"
    )

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
                        "Analise a captura de tela inteira do navegador exibindo as opções A e B.\n"
                        "Escolha a melhor opção (A ou B) aplicando o Guia de Comparação Estética.\n\n"
                        "Responda exclusivamente em JSON no formato:\n"
                        '{"escolha": "A", "justificativa": "..."}'
                    )
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": data_url
                    }
                }
            ]
        }
    ]

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.1
    }

    url = f"{API_BASE_URL.rstrip('/')}/chat/completions"

    print(
        f"[API] Enviando captura de tela inteira para "
        f"{MODEL_NAME}..."
    )

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90
        )

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

        try:
            parsed = json.loads(content)

            raw_choice = (
                parsed.get("escolha")
                or parsed.get("choice")
                or parsed.get("opcao")
                or parsed.get("selected_image")
            )

            choice_norm = None
            if raw_choice is not None:
                c_str = str(raw_choice).strip().upper()
                if c_str in ("A", "1", "IMAGE_1", "IMAGEM 1", "IMAGEM_1"):
                    choice_norm = "A"
                elif c_str in ("B", "2", "IMAGE_2", "IMAGEM 2", "IMAGEM_2"):
                    choice_norm = "B"

            if choice_norm in ("A", "B"):
                return {
                    "escolha": choice_norm,
                    "justificativa": parsed.get(
                        "justificativa",
                        content
                    )
                }

            raise ValueError(
                f"JSON recebido, mas escolha inválida: {raw_choice}"
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
    # CAPTURAR TELA CHEIA
    # --------------------------------------------------------------------------

    def capturar_tela_cheia_b64(self) -> str:
        """
        Captura um screenshot da tela inteira do navegador em base64.
        """
        try:
            screenshot_png = self.driver.get_screenshot_as_png()
            return base64.b64encode(screenshot_png).decode("utf-8")
        except Exception as e:
            print(f"[ERRO SCREENSHOT] Falha ao capturar tela cheia: {e}")
            return ""

    # --------------------------------------------------------------------------
    # SELECIONAR INPUT (value="a", value="b", etc.)
    # --------------------------------------------------------------------------

    def clicar_input_opcao(self, opcao: str) -> bool:
        """
        Marca o input correspondente no HTML:
        value="a" -> A
        value="b" -> B
        """
        opcao_str = str(opcao).upper()

        if opcao_str in ("A", "1"):
            target_vals = ["a", "A", "image_1", "1"]
            key_to_send = "a"
            alt_key = "1"
        else:
            target_vals = ["b", "B", "image_2", "2"]
            key_to_send = "b"
            alt_key = "2"

        clicado = False

        # 1. Tentar encontrar e marcar input no HTML
        for val in target_vals:
            selectors = [
                f"input[value='{val}']",
                f"input[name='selected_image'][value='{val}']",
                f"input.panel-radio[value='{val}']",
                f"input[type='radio'][value='{val}']",
                f"#radio-{val}",
                f"#radio-{val.lower()}"
            ]
            for sel in selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elems:
                        self.driver.execute_script(
                            """
                            arguments[0].checked = true;
                            arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                            arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                            arguments[0].click();
                            """,
                            elem
                        )
                        print(f"[SELENIUM] Input marcado: {sel} (value='{val}')")
                        clicado = True
                        break
                    if clicado:
                        break
                except Exception as e:
                    print(f"[AVISO CLIQUE INPUT {val}] {e}")
            if clicado:
                break

        # 2. Tentar clicar em label associado se houver
        if not clicado:
            for val in target_vals:
                try:
                    labels = self.driver.find_elements(
                        By.XPATH,
                        f"//label[contains(@for, '{val}') or .//input[@value='{val}']]"
                    )
                    if labels:
                        self.driver.execute_script("arguments[0].click();", labels[0])
                        print(f"[SELENIUM] Label clicado para valor '{val}'")
                        clicado = True
                        break
                except Exception:
                    pass

        # 3. Enviar tecla no teclado (a/1 ou b/2)
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(key_to_send)
            body.send_keys(alt_key)
        except Exception:
            pass

        return clicado

    # --------------------------------------------------------------------------
    # SUBMETER RESPOSTA (ENTER / BUTTON)
    # --------------------------------------------------------------------------

    def submeter_resposta(self):
        print("[SELENIUM] Pressionando ENTER...")
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ENTER)
        except Exception as e:
            print(f"[AVISO ENTER] {e}")

        try:
            submits = self.driver.find_elements(
                By.CSS_SELECTOR,
                "#submit-btn, .submit-btn, button[type='submit'], input[type='submit'], .btn-submit, button.submit"
            )
            for btn in submits:
                if btn.is_displayed() and btn.is_enabled():
                    self.driver.execute_script("arguments[0].click();", btn)
                    break
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # VERIFICAR ERRO NA PÁGINA
    # --------------------------------------------------------------------------

    def verificar_erro_ou_resposta_incorreta(self) -> bool:
        """
        Verifica se a página exibe algum aviso ou mensagem de erro após submeter.
        """
        error_selectors = [
            ".error-message", ".alert-danger", ".has-error", "#error-msg",
            ".feedback-error", ".error", ".incorrect", "[data-testid='error']"
        ]
        for sel in error_selectors:
            try:
                elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elems:
                    if el.is_displayed() and el.text.strip():
                        print(f"[VERIFICAÇÃO] Mensagem de erro detectada ({sel}): {el.text.strip()}")
                        return True
            except Exception:
                pass

        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            textos_erro = [
                "resposta incorreta",
                "tente novamente",
                "escolha incorreta",
                "wrong answer",
                "incorrect",
                "tente a outra opção",
                "opção incorreta"
            ]
            for msg in textos_erro:
                if msg in body_text:
                    print(f"[VERIFICAÇÃO] Texto de erro detectado no HTML: '{msg}'")
                    return True
        except Exception:
            pass

        return False

    # --------------------------------------------------------------------------
    # SELECIONAR E SUBMETER COM FALLBACK DE ERRO
    # --------------------------------------------------------------------------

    def selecionar_e_submeter_com_fallback(self, escolha_ia: str) -> str:
        """
        Marca a opção da IA (A ou B) e envia. Se a página indicar erro/resposta incorreta,
        marca automaticamente a outra opção e envia.
        """
        opcao_principal = "A" if str(escolha_ia).upper() in ("A", "1", "IMAGE_1") else "B"
        opcao_oposta = "B" if opcao_principal == "A" else "A"

        print(f"[AUTOMAÇÃO] Selecionando Opção {opcao_principal}...")
        self.clicar_input_opcao(opcao_principal)
        self.submeter_resposta()

        time.sleep(1.5)

        if self.verificar_erro_ou_resposta_incorreta():
            print()
            print("!" * 70)
            print(f"[FALLBACK] A opção {opcao_principal} resultou em ERRO / RESPOSTA INCORRETA.")
            print(f"[FALLBACK] Trocando para a outra opção ({opcao_oposta}) e enviando...")
            print("!" * 70)
            print()

            self.clicar_input_opcao(opcao_oposta)
            self.submeter_resposta()
            time.sleep(1.5)

            return opcao_oposta

        print(f"[AUTOMAÇÃO] Opção {opcao_principal} submetida com sucesso!")
        return opcao_principal

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
            print(f"PROCESSANDO TAREFA #{tarefas_executadas + 1}")
            print("=" * 60)

            try:
                # 1. Prompt
                prompt_text = self.extrair_prompt()

                if prompt_text == prompt_anterior and tarefas_executadas > 0:
                    print("[SELENIUM] Aguardando nova tarefa...")
                    time.sleep(2.5)
                    prompt_text = self.extrair_prompt()

                prompt_anterior = prompt_text

                # 2. Screenshot Tela Inteira
                screenshot_b64 = self.capturar_tela_cheia_b64()

                if not screenshot_b64:
                    print("[ERRO] Não foi possível capturar a tela cheia do navegador.")
                    time.sleep(3)
                    continue

                # 3. Análise IA
                print("[AI] Enviando captura de tela inteira do navegador para análise...")

                try:
                    decisao = avaliar_tela_com_deepseek(prompt_text, screenshot_b64)
                except Exception as e:
                    print()
                    print("!" * 70)
                    print("[ERRO CRÍTICO DA IA]")
                    print(str(e))
                    print("!" * 70)
                    print()
                    print("[SEGURANÇA] Nenhuma escolha será feita automaticamente.")
                    time.sleep(5)
                    continue

                escolha_ia = decisao.get("escolha")
                justificativa = decisao.get("justificativa", "Sem justificativa.")

                if escolha_ia not in ("A", "B"):
                    print(f"[ERRO] Escolha inválida retornada pela IA: {escolha_ia}")
                    time.sleep(3)
                    continue

                print()
                print("=" * 60)
                print(f"[DECISÃO DA IA] OPÇÃO {escolha_ia}")
                print(f"[JUSTIFICATIVA] {justificativa}")
                print("=" * 60)
                print()

                # 4. Marcar Input e Submeter (com Fallback automático se errou)
                opcao_final = self.selecionar_e_submeter_com_fallback(escolha_ia)

                tarefas_executadas += 1
                time.sleep(2.5)

            except KeyboardInterrupt:
                print("\n[AUTOMAÇÃO] Interrompida pelo usuário.")
                break

            except Exception as e:
                print(f"[ERRO NO LOOP] {e}")
                time.sleep(3)

        print()
        print("=" * 60)
        print(f"[FIM] Total de tarefas processadas: {tarefas_executadas}")
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