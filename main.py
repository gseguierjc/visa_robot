# ais_login_force_chrome.py
# Reqs (mínimo): pip install selenium requests
import os, socket, time, subprocess, sys, shutil, json, mimetypes
from pathlib import Path
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL_SIGNIN    = "https://ais.usvisa-info.com/es-pe/niv/users/sign_in"
USER_DATA_DIR = r"C:\Users\JEAN\AppData\Local\Google\Chrome\User Data"  # (no usado en esta variante)
PROFILE_DIR   = "Default"               # (no usado en esta variante)
DEBUG_PORT    = 9229                    # (no usado en esta variante)
EMAIL         = "gseguierjc@gmail.com"

TOPIC = "jcgs-ntfy-notify"  # topic por defecto si no pasas NTFY_TOPIC
img_path = "screenshot_pago.png"

# Flag para activar envío de email en producción (lo mantengo por si luego lo vuelves a usar)
env_enable = os.environ.get("VISA_ENABLE_EMAIL", "1").lower()
ENABLE_EMAIL = env_enable in ("1", "true", "yes", "on")

# Binario de Chrome (si tienes varias ediciones; en esta variante no es imprescindible)
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def notify_toast(title, msg):
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, msg, duration=7)
    except Exception:
        pass

# ==========================
#   NTFY: ENVÍO RAW (sin multipart)
#   Usa headers Title / Content-Type / Filename, y el body binario del archivo.
#   Así evitamos que llegue como "attachment.bin".
# ==========================
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

def main():
    """
    Flujo principal: abre Chrome "limpio" (perfil temporal interno de Selenium),
    intenta loguear (correo auto; contraseña/captcha idealmente manual),
    navega y, si corresponde, toma screenshot y envía a ntfy con nombre correcto.
    """
    # Recomendación: usa variables de entorno para la contraseña
    # PASSWORD = os.environ["AIS_PASSWORD"]
    PASSWORD = "hqx-fjx3pwe6kva3RXT"  # <-- Reemplaza por método seguro (env vars)

    print("Abriendo Chrome limpio (sin perfil)…")
    opts = Options()
    # Si quieres forzar binario:
    # opts.binary_location = CHROME_EXE
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, 60)

    try:
        driver.get(URL_SIGNIN)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "form")))

        # Correo
        email_input = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[type='email'], #user_email")
        ))
        email_input.clear()
        email_input.send_keys(EMAIL)

        # Contraseña (nota: este sitio puede requerir captcha/2FA; lo manual suele ser más fiable)
        try:
            password_input = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[type='password'], #user_password")
            ))
            password_input.clear()
            password_input.send_keys(PASSWORD)
        except Exception:
            print("No se localizó el campo contraseña de inmediato (puede requerir interacción manual).")

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

        # Enviar login
        try:
            submit_btn = wait.until(EC.element_to_be_clickable((By.NAME, "commit")))
            submit_btn.click()
            print("Login enviado automáticamente.")
        except Exception as e:
            print(f"No se pudo hacer clic en el botón de login: {e}")

        # Verificación post-login
        try:
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//*[contains(., 'Programar cita') or contains(., 'Pago') or contains(., 'Continuar')]")
            ))
            print("✅ Sesión detectada.")
            notify_toast("Visa AIS", "Login OK / Panel visible")

            # Botón "Continuar"
            try:
                continuar_btn = wait.until(EC.element_to_be_clickable((
                    By.XPATH, "//a[contains(@class, 'button') and contains(@class, 'primary') and contains(@class, 'small') and contains(text(), 'Continuar')]"
                )))
                continuar_btn.click()
                print("Botón 'Continuar' clickeado correctamente.")
            except Exception:
                print("No se encontró el botón 'Continuar' o no fue posible hacer clic.")

            # Sección "Pago de arancel de visa"
            try:
                pago_accordion = wait.until(EC.element_to_be_clickable((
                    By.XPATH, "//a[contains(@class, 'accordion-title') and contains(., 'Pago de arancel de visa')]"
                )))
                pago_accordion.click()
                print("Sección 'Pago de arancel de visa' expandida.")
                time.sleep(1)
                pago_btn = wait.until(EC.element_to_be_clickable((
                    By.XPATH, "//a[contains(@class, 'button') and contains(text(), 'Pago de arancel de visa')]"
                )))
                pago_btn.click()
                print("Botón 'Pago de arancel de visa' clickeado correctamente.")
            except Exception:
                print("No se pudo expandir la sección o hacer clic en el botón de pago de arancel de visa.")

            # Intento final de clic en "Pago de arancel de visa"
            try:
                pago_btn_final = wait.until(EC.element_to_be_clickable((
                    By.XPATH, "//a[contains(@class, 'button') and contains(@class, 'primary') and contains(text(), 'Pago de arancel de visa')]"
                )))
                pago_btn_final.click()
                print("Botón final 'Pago de arancel de visa' clickeado correctamente.")
            except Exception:
                print("No se pudo hacer clic en el botón final 'Pago de arancel de visa'.")

            # Verifica mensaje y envía screenshot a ntfy
            try:
                msg_elem = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "noPaymentAcceptedMessage")))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", msg_elem)
                time.sleep(0.5)
                msg_text = msg_elem.text.strip()
                print(f"Mensaje detectado: {msg_text}")

                # Screenshot
                screenshot_path = "visa_status.png"
                driver.save_screenshot(screenshot_path)
                print(f"Screenshot guardado en {screenshot_path}")

                # ===== Envío a ntfy (RAW) =====
                ntfy_disabled = os.environ.get("NTFY_DISABLED", "0").lower() in ("1", "true", "yes", "on")
                if ntfy_disabled:
                    print("NTFY_DISABLED activo; no se envía notificación (modo desarrollo).")
                else:
                    ntfy_base  = os.environ.get("NTFY_URL", "https://ntfy.sh").rstrip('/')
                    ntfy_topic = os.environ.get("NTFY_TOPIC", TOPIC)
                    ntfy_title = os.environ.get("NTFY_TITLE", "Aviso: Cambio en disponibilidad de citas VISA")
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

        except Exception:
            print("⚠️ No pude confirmar el panel post-login (revisa captcha/clave/textos).")

    except Exception as e:
        print("⚠️ Error durante el flujo:", e)
        notify_toast("Visa AIS", "Error al confirmar el login")
        raise

    print("Listo. Dejo Chrome abierto con tu sesión.")

if __name__ == '__main__':
    main()
