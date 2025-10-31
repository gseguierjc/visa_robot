"""
Automatiza el flujo de reprogramación de cita en el portal AIS (visado EE.UU.)
para Perú usando Selenium. El script recorre el calendario hasta encontrar
la fecha disponible más próxima. Solo reprogramará si la cita encontrada
es anterior al 1 de junio de 2026; en caso contrario, mostrará el valor
detecto y no hará cambios.

Uso:
  - Instala Selenium (`pip install selenium`) y descarga el controlador
    correspondiente a tu navegador (ChromeDriver, EdgeDriver, etc.).
  - Ajusta las constantes `USERNAME` y `PASSWORD` con tus credenciales.
  - Ejecuta el script en un entorno donde puedas interactuar manualmente
    para resolver el hCaptcha y cualquier 2FA. El script se detendrá y
    esperará a que pulses ENTER después de completar el captcha.
  - Si encuentra una cita antes de junio de 2026, seleccionará la fecha
    y la primera hora disponible. Antes de confirmar el cambio, el script
    solicitará tu confirmación manual.
  - Si la primera cita libre es posterior al 1 de junio de 2026, imprimirá
    la fecha detectada y terminará sin modificar la cita.

Nota de responsabilidad: Programar o reprogramar citas de visa es un
proceso delicado. Asegúrate de revisar cuidadosamente la información en
pantalla antes de confirmar la reprogramación. Este script no elude el
hCaptcha ni la autenticación en dos pasos; estas tareas deben ser
realizadas manualmente.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional
from pathlib import Path
import requests
import os, socket, time, subprocess, sys, shutil, json, mimetypes
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
# === Configuración del usuario ===
# Cambia estos valores por tus credenciales reales. Para mayor seguridad,
# considera obtenerlos de variables de entorno o de un gestor seguro.
USERNAME: str = "gseguierjc@gmail.com"
PASSWORD: str = "hqx-fjx3pwe6kva3RXT" 
TOPIC = "jcgs-ntfy-notify"  # topic por defecto si no pasas NTFY_TOPIC
# URL base para iniciar sesión
LOGIN_URL: str = "https://ais.usvisa-info.com/es-pe/niv/users/sign_in"
RETRY_DELAY_SEC = 60 
# Límite para considerar la fecha como válida.
# Se reprogramará solo si la primera fecha disponible es igual o anterior a
# agosto de 2026. Para ello se establece el umbral al 31 de agosto de 2026.
DATE_THRESHOLD: datetime = datetime(2026, 6, 30)
##fecha nueva##

def find_next_available_date(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    date_input_selector: str = "appointments_consulate_appointment_date",



) -> Optional[str]:
    """Busca la primera fecha disponible en el calendario.

    Abre el selector de fecha, avanza mes a mes hasta encontrar la primera
    celda no deshabilitada y selecciona esa fecha. Devuelve el valor de
    fecha en formato ISO (AAAA-MM-DD) que queda en el campo de entrada.
    Si no se encuentran fechas disponibles en un número razonable de meses,
    devuelve None.

    Args:
        driver: instancia de WebDriver.
        wait: instancia de WebDriverWait para esperar elementos.
        date_input_selector: selector CSS del campo de fecha de la cita.

    Returns:
        La cadena de fecha seleccionada ("YYYY-MM-DD") o None si no se
        encuentra ninguna.
    """
    # Abre el calendario haciendo clic en el campo
    date_input = wait.until(
        EC.element_to_be_clickable((By.ID, date_input_selector))
    )
    date_input.click()
    print("buscando fecha en el calendario...")
    # Iterar hasta encontrar un día disponible o hasta un límite de meses
    max_months_to_scan = 24  # evita bucles infinitos; 2 años de búsqueda
    for _ in range(max_months_to_scan):
        # Busca celdas disponibles (td sin clase 'disabled' ni 'unavailable' con enlace)
        available_days = driver.find_elements(
            By.XPATH,
            (
                "//table[contains(@class,'ui-datepicker-calendar')]"
                "//td[not(contains(@class,'disabled'))"
                " and not(contains(@class,'unavailable'))]"
                "/a"
            ),
        )
        if available_days:
            # Selecciona la primera fecha disponible
            available_days[0].click()
            # Lee el valor del campo de fecha después de seleccionar
            selected_value = date_input.get_attribute("value")
            return selected_value
        # Si no hay días, pasa al siguiente mes
        try:
            next_button = driver.find_element(By.CSS_SELECTOR, "a.ui-datepicker-next")
            next_button.click()
            # Espera un breve momento para que el calendario se actualice
            time.sleep(0.5)
        except NoSuchElementException:
            # No hay botón para avanzar; salir
            break
    return None

def reprogram_appointment():
    """Automatiza el flujo de reprogramación respetando la fecha límite.

    El script inicia sesión, navega hasta la pantalla de reprogramación,
    busca la primera fecha disponible y reprograma solo si es anterior a
    DATE_THRESHOLD. Si la fecha encontrada es posterior, notifica al
    usuario y no realiza cambios.
    """
    # Inicializa el navegador (usa Chrome por defecto)
    fecha_disponible = ""
    opts = Options()
    chrome_bin = os.environ.get("CHROME_BIN") or os.environ.get("GOOGLE_CHROME_SHIM")
    if chrome_bin:
        opts.binary_location = chrome_bin
    opts.add_argument("--headless=new")    
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1200")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    # service = Service(ChromeDriverManager().install())
    service =Service("/usr/local/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1920, 1200)
    wait = WebDriverWait(driver, 60)
    try:
        # Paso 1: abrir la página de inicio de sesión
        driver.get(LOGIN_URL)
        time.sleep(8)  # espera breve para carga inicial
        print("URL actual:",driver.current_url)
        # print("Html parcial:",driver.page_source[:2000])  # depuración
        # Paso 2: introducir credenciales
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "form")))
        driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys(USERNAME)
        driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(PASSWORD)
        # Acepta la política de privacidad si aparece una casilla
        # Checkbox de términos (varían selectores)
        try:
            terms_chk = driver.find_element(By.ID, "policy_confirmed")
            if not terms_chk.is_selected():
                terms_chk.click()
            print("Checkbox de términos y condiciones marcado.")
        except Exception:
            try:
                terms_chk = driver.find_element(By.CLASS_NAME, "icheckbox")
                if not terms_chk.is_selected():
                    terms_chk.click()
                print("Checkbox (fallback) marcado.")
            except Exception:
                print("No se encontró el checkbox 'policy_confirmed' (se omite).")

        # Intento de cerrar diálogo previo (heurístico)
        try:
            dialog_ok_btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button, input[type='button'], .btn")
            ))
            if dialog_ok_btn.is_displayed():
                dialog_ok_btn.click()
                print("Botón OK del diálogo aceptado.")
                time.sleep(1)
        except Exception:
            pass

                # Enviar login
        try:
            submit_btn = wait.until(EC.element_to_be_clickable((By.NAME, "commit")))
            submit_btn.click()
            print("Login enviado automáticamente.")
        except Exception as e:
            print(f"No se pudo hacer clic en el botón de login: {e}")
        # Esperar a que el usuario resuelva hCaptcha/2FA y pulse "Iniciar sesión"
        # input(
        #     "Por favor, resuelve el hCaptcha y cualquier verificación adicional en el navegador, "
        #     "haz clic en 'Iniciar sesión' y luego pulsa ENTER aquí para continuar..."
        # )

        # Paso 3: esperar y pulsar el botón "Continuar"
        continuar_button = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//a[contains(., 'Continuar')] | //button[contains(., 'Continuar')]")
            )
        )
        continuar_button.click()

        title = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//li[contains(@class,'accordion-item')]"
            "[.//h5[contains(normalize-space(.),'Reprogramar cita')] "
            "or .//h5[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reschedule appointment')]]"
            "//a[contains(@class,'accordion-title')]"
        )))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", title)

        # 2) Toma el panel asociado por aria-controls
        panel_id = title.get_attribute("aria-controls")

        # 3) Click para expandir (con fallback a JS)
        try:
            wait.until(EC.element_to_be_clickable((By.ID, title.get_attribute("id") or "")))
            title.click()
        except Exception:
            driver.execute_script("arguments[0].click();", title)

        # 4) Espera a que el panel esté expandido (aria-hidden="false")
        wait.until(lambda d: d.find_element(By.ID, panel_id).get_attribute("aria-hidden") == "false")

        # 5) Devuelve el panel expandido
        driver.find_element(By.ID, panel_id)
        
        print("Sección 'Reprogramar cita' expandida.")
        print("Esperando 5 segundos...")
        # y ahora sí, clic al botón:
        time.sleep(5)  # espera breve para evitar problemas de sincronización

       
        panel = driver.find_element(By.ID, panel_id) 

        xpaths = [
        ".//a[contains(@class,'button') and contains(@href,'/appointment')]",  # la más común
        ".//a[contains(@class,'button') and contains(@href,'/reschedule')]",   # por si cambia el path
        ".//a[contains(@class,'button') and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reprogramar')]",  # por texto
        ".//a[contains(@class,'button') and contains(., 'Reprogramar')]",
        ".//a[contains(@class,'button') and contains(., 'Reschedule')]",
        ]

        btn = None
        last_exc = None
        for xp in xpaths:
            try:
                btn = WebDriverWait(panel, 3).until(
                    lambda _p: panel.find_element(By.XPATH, xp)
                )
                if btn:
                    break
            except Exception as e:
                last_exc = e
                continue

        if not btn:
            # Depuración: listar lo que sí hay
            links = panel.find_elements(By.CSS_SELECTOR, "a.button")
            found = [ (a.get_attribute("href") or "", a.text.strip()) for a in links ]
            raise TimeoutException(f"No encontré el botón dentro del panel. Disponibles: {found}. Último error: {last_exc}")

        # 2) Asegurar visibilidad/viewport
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)

        # 3) Intentar click normal; si falla por overlay, hacer click JS
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(btn))
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        print("Clic en 'Reprogramar cita' realizado.")

         # 1) Inicio de la busqueda de una fecha disponible #################################################
        intento = 0
        max_retries = 15
        while intento <= max_retries:
            print(f"Intento {intento} de {max_retries}...")
            if intento == 0:
                buscar_fecha_disponible(driver, wait)
                intento += 1
            else :
            # refrescar, esperar y reintentar
                try:
                        time.sleep(RETRY_DELAY_SEC)
                        driver.refresh()
                        # Espera a que el documento esté en 'complete'
                        WebDriverWait(driver,5).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                        buscar_fecha_disponible(driver, wait)
                        intento += 1
                        if intento == max_retries:
                            take_screenshot(driver, TOPIC, "","Ultima intento de reprogramación en busqueda")    
                        continue
                except Exception:
                        pass
                        print(f"↻ Página refrescada. Esperando {RETRY_DELAY_SEC } segundos antes de reintentar…")
                        time.sleep(RETRY_DELAY_SEC )
                return False
            continue
        

    finally:
        # Deja el navegador abierto para revisar o cierra según necesidad
        pass


def ntfy_send_image_raw(topic: str, screenshot_path: str,
                        title: str = "Aviso", ntfy_base: str = "https://ntfy.sh",
                        token: str | None = None, content_type: str | None = None):
    url = f"{ntfy_base.rstrip('/')}/{topic}"
    filename = os.path.basename(screenshot_path)

    # Determina content-type si no lo mandas fijo
    if not content_type:
        guess = mimetypes.guess_type(screenshot_path)[0]
        content_type = guess or ("image/png" if Path(screenshot_path).suffix.lower() == ".png" else "application/octet-stream")

    headers = {
        "Title": title,
        "Content-Type": content_type,
        "Filename": filename,   # clave para evitar "attachment.bin"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with open(screenshot_path, "rb") as f:
        r = requests.post(url, data=f, headers=headers, timeout=30)
    r.raise_for_status()
    return r
def take_screenshot(driver: webdriver.Chrome, topic: str, fecha_disponible: str = "",message: str = ""):
     driver.execute_script("window.scrollTo(0, 220);")
      # Screenshot
     screenshot_path = "visa_status_repro.png"
     driver.save_screenshot(screenshot_path)
     print(f"Screenshot guardado en {screenshot_path}")
     try:
         ntfy_disabled = False
         if ntfy_disabled:
             print("NTFY_DISABLED activo; no se envía notificación (modo desarrollo).")
         else:
             ntfy_base  = os.environ.get("NTFY_URL", "https://ntfy.sh").rstrip('/')
             ntfy_topic = os.environ.get("NTFY_TOPIC", topic)
             ntfy_title = os.environ.get("NTFY_TITLE", message + fecha_disponible)
             # ntfy_token = os.environ.get("NTFY_TOKEN")  # opcional
          # Fuerza content-type por extensión para evitar ambigüedades
             content_type = "image/png" if Path(screenshot_path).suffix.lower() == ".png" else "image/jpeg"
             ntfy_send_image_raw(
                 topic=ntfy_topic,
                 screenshot_path=screenshot_path,
                 title=ntfy_title,
                 ntfy_base=ntfy_base,
                 # token=ntfy_token,
                 content_type=content_type
             )
             print(f"Notificación enviada a ntfy: {ntfy_base}/{ntfy_topic}")
     except Exception as e:
             print(f"No se pudo verificar/enviar notificación: {e}")
def buscar_fecha_disponible(driver: webdriver.Chrome, wait: WebDriverWait,topic: str = TOPIC):
    print("Iniciando búsqueda de fecha disponible...")
    try:
    # Paso 5: buscar la fecha disponible más próxima
        selected_date_str = find_next_available_date(driver, wait)
        fecha_disponible = selected_date_str
        print(selected_date_str)
        if not selected_date_str:
            print("No se encontró ninguna fecha disponible en el rango evaluado.")

        selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d")

        print(f"Primera cita disponible encontrada: {selected_date_str}")
        # Compara con el umbral definido
        if selected_date >= DATE_THRESHOLD:
            print(
                f"La fecha disponible {selected_date_str} es posterior al límite "
                f"{DATE_THRESHOLD.date()} – no se reprogramará."
            )
            # Screenshot
            
            return False
        # Paso 6: seleccionar la primera hora disponible
        try:
            import re
            def looks_like_time(txt: str) -> bool:
                if not txt:
                    return False
                s = txt.strip()
                patterns = [
                    r"^\d{1,2}:\d{2}(\s?[AaPp][Mm])?$",
                    r"^\d{1,2}\s?[AaPp][Mm]$",
                ]
                return any(re.match(p, s) for p in patterns)
            # Localiza el control (container o <select>) y haz click para desplegar si aplica
            time_widget = wait.until(
                EC.element_to_be_clickable((By.ID, "appointments_consulate_appointment_time"))
            )
            try:
                time_widget.click()
            except Exception:
                driver.execute_script("arguments[0].click();", time_widget)
            time.sleep(0.3)  # breve espera para que el dropdown/DOM se actualice
            selected_time = ""
            # Intento 1: si existe un <select> real dentro del widget, recorrer sus <option>
            try:
                select_el = time_widget if time_widget.tag_name.lower() == "select" else time_widget.find_element(By.TAG_NAME, "select")
                sel = Select(select_el)
                WebDriverWait(driver, 5).until(lambda d: len(sel.options) > 0)
                chosen_idx = None
                for i, opt in enumerate(sel.options):
                    # saltar opciones deshabilitadas
                    disabled = (opt.get_attribute("disabled") or "").lower() in ("true", "disabled")
                    aria_disabled = (opt.get_attribute("aria-disabled") or "").lower() in ("true", "disabled")
                    if disabled or aria_disabled:
                        continue
                    text = (opt.text or "").strip()
                    val = (opt.get_attribute("value") or "").strip()
                    if i == 0 and (text == "" or text.lower().startswith("seleccione") or text.lower().startswith("select")):
                        continue
                    if looks_like_time(text) or looks_like_time(val):
                        chosen_idx = i
                        break
                    if chosen_idx is None and text:
                        chosen_idx = i
                if chosen_idx is None:
                    raise Exception("No hay opciones válidas en el <select> de horas.")
                sel.select_by_index(chosen_idx)
                # disparar change por si la página necesita reaccionar
                try:
                    driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles:true}));", select_el)
                except Exception:
                    pass
                selected_time = (sel.first_selected_option.text or sel.first_selected_option.get_attribute("value") or "").strip()
            except Exception:
                # Intento 2: dropdown/lista personalizada -> buscar opciones visibles dentro del widget
                option_xpath_candidates = [
                    ".//option",
                    ".//ul//li",
                    ".//div[contains(@class,'dropdown') or contains(@class,'time')]//a",
                    ".//div[@role='listbox']//div[@role='option']",
                    ".//li[contains(@class,'time-option')]",
                    ".//a[contains(@class,'time')]",
                    "//ul[contains(@class,'ui-datepicker-time-list')]/li"
                ]
                option_el = None
                option_text = ""
                for xp in option_xpath_candidates:
                    try:
                        opts = time_widget.find_elements(By.XPATH, xp)
                        # si no hay dentro del widget, buscar globalmente (algún dropdown se añade en otro nodo)
                        if not opts:
                            opts = driver.find_elements(By.XPATH, xp)
                        if not opts:
                            continue
                        # escoger la primera opción que parezca hora y no esté deshabilitada
                        for cand in opts:
                            # comprobar visibilidad y estado
                            try:
                                if not cand.is_displayed():
                                    continue
                            except Exception:
                                pass
                            cls = (cand.get_attribute("class") or "").lower()
                            aria_disabled = (cand.get_attribute("aria-disabled") or "").lower()
                            disabled = (cand.get_attribute("disabled") or "").lower()
                            if "disabled" in cls or aria_disabled in ("true","disabled") or disabled in ("true","disabled"):
                                continue
                            txt = (cand.text or "").strip() or (cand.get_attribute("data-value") or "").strip()
                            if looks_like_time(txt):
                                option_el = cand
                                option_text = txt
                                break
                        if option_el:
                            break
                        # fallback: pick first visible non-empty
                        for cand in opts:
                            try:
                                if not cand.is_displayed():
                                    continue
                            except Exception:
                                pass
                            txt = (cand.text or "").strip()
                            if txt:
                                option_el = cand
                                option_text = txt
                                break
                        if option_el:
                            break
                    except Exception:
                        continue
                if not option_el:
                    raise Exception("No se encontraron opciones en el dropdown/lista de horas.")
                # Asegurar que la opción esté en viewport y clicar
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", option_el)
                    option_el.click()
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", option_el)
                    except Exception as e:
                        raise Exception(f"No se pudo clicar la opción encontrada: {e}")
                selected_time = option_text or (option_el.text or option_el.get_attribute("data-value") or "").strip()
            # Validar que el texto obtenido parezca una hora válida
            if not looks_like_time(selected_time):
                raise Exception(f"Hora seleccionada no válida o vacía: '{selected_time}'")
            print(f"Hora seleccionada (validada): {selected_time}")
        except Exception as e:
            print(f"No se pudo localizar/validar el selector de horas: {e}")
            take_screenshot(driver, topic, fecha_disponible,"No se pudo localizar/validar el selector de horas")
        confirm_button = wait.until(
            EC.element_to_be_clickable(
                (By.ID, "appointments_submit")
            )
        )
        
        confirm_button.click()
        print("La cita se ha reprogramado exitosamente.")
        take_screenshot(driver, topic, fecha_disponible,"Reprogramación exitosa a ")  
    except Exception as e:
        print(f"No se pudo seleccionar fecha/hora: {e}")
        take_screenshot(driver, topic, fecha_disponible,"Error durante selección de fecha/hora")



if __name__ == "__main__":
    reprogram_appointment()
