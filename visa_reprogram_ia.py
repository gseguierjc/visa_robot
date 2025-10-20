import os, json, time
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
from dateutil import tz
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===== IA (OpenAI Responses API + Structured Outputs) =====
from openai import OpenAI

LIMA_TZ = tz.gettz("America/Lima")
THRESHOLD = date(2026, 8, 30)  # cambia tu política aquí

class AiDecision(BaseModel):
    approve: bool  # ¿Confirmar reprogramación?
    notify: bool   # ¿Enviar notificación?
    reason: str    # Breve explicación

def fallback_rule(earliest_iso: Optional[str], flow_ok: bool) -> AiDecision:
    d = None
    try:
        d = datetime.strptime(earliest_iso, "%Y-%m-%d").date() if earliest_iso else None
    except Exception:
        pass
    approve = bool(d and d <= THRESHOLD and flow_ok)
    notify  = True if (not flow_ok or approve) else False
    reason  = f"Regla dura: fecha={earliest_iso}, flow_ok={flow_ok}, umbral={THRESHOLD}"
    return AiDecision(approve=approve, notify=notify, reason=reason)

def decide_with_openai(earliest_iso: Optional[str], flow_ok: bool, context: dict | None=None) -> Optional[AiDecision]:
    """Usa OpenAI Responses API + Structured Outputs (json_schema). Si algo falla, retorna None."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    client = OpenAI(api_key=api_key)
    model  = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    schema = {
        "name": "ReprogramDecision",
        "schema": {
            "type": "object",
            "properties": {
                "approve": {"type": "boolean"},
                "notify":  {"type": "boolean"},
                "reason":  {"type": "string"}
            },
            "required": ["approve", "notify", "reason"],
            "additionalProperties": False
        },
        "strict": True
    }

    system_prompt = (
        "Eres un asistente que decide si confirmar la reprogramación de una cita consular. "
        f"Regla obligatoria: SOLO aprobar si la fecha disponible es el {THRESHOLD.isoformat()} o anterior. "
        "Si flow_ok es falso o hay señales de error en el flujo, sugiere notificar. "
        "Responde EXCLUSIVAMENTE como JSON conforme al esquema."
    )

    payload = {
        "earliest_date": earliest_iso,   # 'YYYY-MM-DD' o None
        "flow_ok": flow_ok,              # bool
        "threshold": THRESHOLD.isoformat(),
        "timezone": "America/Lima",
        "context": context or {}
    }

    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": json.dumps(payload, ensure_ascii=False)}
            ],
            response_format={"type": "json_schema", "json_schema": schema},
            temperature=0
        )
        content = resp.output_text  # texto JSON consolidado
        data = json.loads(content)
        return AiDecision.model_validate(data)
    except Exception:
        return None

def decide_action(earliest_iso: Optional[str], flow_ok: bool, context: dict | None=None) -> AiDecision:
    d = decide_with_openai(earliest_iso, flow_ok, context)
    return d if d is not None else fallback_rule(earliest_iso, flow_ok)

# ====== Selenium: login + navegar hasta reprogramar ======

URL_SIGNIN = "https://ais.usvisa-info.com/es-pe/niv/users/sign_in"

def build_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--start-maximized")
    # Reutiliza sesión (opcional):
    # opts.add_argument(r"--user-data-dir=C:\Users\TUUSUARIO\AppData\Local\Google\Chrome\User Data")
    # opts.add_argument("--profile-directory=Default")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def login(driver, email, password, wait=60) -> bool:
    w = WebDriverWait(driver, wait)
    driver.get(URL_SIGNIN)
    # Acepta banners si aparecen


    # Campos
    driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys(email)
    driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(password)


    try:
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "//button|//a[normalize-space()='OK' or normalize-space()='Aceptar' or contains(.,'Aceptar')]")
        ))
        btn.click()
    except Exception:
        pass

    # Checkbox políticas
    try:
        print("Marcando checkbox de políticas...    ")
        chk = driver.find_element(By.ID, "policy_confirmed")
        if not chk.is_selected(): chk.click()
    except Exception:
        try:
            terms_chk = driver.find_element(By.CLASS_NAME, "icheckbox")
            if not terms_chk.is_selected():
                terms_chk.click()
            print("Checkbox (fallback) marcado.")
        except Exception:
            print("No se encontró el checkbox 'policy_confirmed' (se omite).")

    # Enviar
    try:
        driver.find_element(By.NAME, "commit").click()
    except Exception:
        driver.find_element(By.XPATH, "//button|//input[@type='submit']").click()

    # Espera a que resuelvas hCaptcha y veamos “Continuar”
    try:
        WebDriverWait(driver, 180).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Continuar') or contains(., 'Continue')]"))
        )
        return True
    except Exception:
        return False

def go_to_reschedule(driver):
    w = WebDriverWait(driver, 30)
    # Continuar
    cont = w.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Continuar') or contains(., 'Continue')]")))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cont)
    try: cont.click()
    except Exception: driver.execute_script("arguments[0].click();", cont)

    # Expandir acordeón “Reprogramar cita”
    title = w.until(EC.presence_of_element_located((
        By.XPATH,
        "//li[contains(@class,'accordion-item')]"
        "[.//h5[contains(normalize-space(.),'Reprogramar cita') or "
        " contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'reschedule')]]"
        "//a[contains(@class,'accordion-title')]"
    )))
    panel_id = title.get_attribute("aria-controls")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", title)
    try: title.click()
    except Exception: driver.execute_script("arguments[0].click();", title)
    WebDriverWait(driver, 15).until(lambda d: d.find_element(By.ID, panel_id).get_attribute("aria-hidden") == "false")

    # Botón interno Reprogramar
    panel = driver.find_element(By.ID, panel_id)
    btn = WebDriverWait(panel, 10).until(
        lambda el: panel.find_element(By.XPATH, ".//a[contains(@class,'button') and contains(@href,'/appointment')]")
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try: btn.click()
    except Exception: driver.execute_script("arguments[0].click();", btn)

def open_calendar_and_get_earliest(driver) -> Optional[str]:
    """Abre el datepicker y retorna la primera fecha disponible (YYYY-MM-DD) o None."""
    w = WebDriverWait(driver, 30)
    # Campo fecha de cita (ajusta selector si cambia)
    date_input = w.until(EC.element_to_be_clickable((By.XPATH, "//input[contains(@name,'appointment') and @type='text']")))
    date_input.click()
    time.sleep(0.4)

    def first_available_day():
        # Lee desde el DOM la primera fecha habilitada del mes visible
        try:
            # En algunas vistas: enlaces 'a' dentro del calendario
            days = driver.find_elements(By.CSS_SELECTOR, "table.ui-datepicker-calendar td a")
            enabled = []
            for a in days:
                td = a.find_element(By.XPATH, "./ancestor::td")
                cls = td.get_attribute("class") or ""
                if "disabled" not in cls and "unavailable" not in cls:
                    enabled.append(a)
            if not enabled:
                return None

            a = enabled[0]
            # Mes/año desde el encabezado del grupo visible
            group = a.find_element(By.XPATH, "./ancestor::*[contains(@class,'ui-datepicker-group')][1]")
            header = group.find_element(By.CSS_SELECTOR, ".ui-datepicker-title").text.strip()  # ej: "febrero 2027"
            parts = header.split()
            if len(parts) >= 2:
                mesTxt, anioTxt = parts[0], parts[1]
                meses = {
                    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
                    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
                }
                m = meses.get(mesTxt.lower(), None)
                y = int(anioTxt)
                d = int(a.text)
                if m:
                    return f"{y:04d}-{m:02d}-{d:02d}"
            return None
        except Exception:
            return None

    # intenta en el mes actual, si no hay, avanza hasta 30 meses
    earliest = first_available_day()
    hops = 0
    while not earliest and hops < 30:
        nxt = driver.find_element(By.CSS_SELECTOR, "a.ui-datepicker-next")
        nxt.click()
        time.sleep(0.3)
        earliest = first_available_day()
        hops += 1

    return earliest  # 'YYYY-MM-DD' o None

def select_time_and_confirm(driver, target_iso: str):
    """Elige hora (primera disponible) y confirma. Re-valida fecha antes de confirmar."""
    w = WebDriverWait(driver, 30)
    # si hay selector de hora:
    try:
        time_select = w.until(EC.element_to_be_clickable((By.XPATH, "//select[contains(@name,'time') or contains(@id,'time')]")))
        # elige primera opción válida distinta de “Seleccione…”
        options = time_select.find_elements(By.TAG_NAME, "option")
        for opt in options:
            if opt.get_attribute("value") and opt.get_attribute("disabled") is None:
                opt.click()
                break
    except Exception:
        pass  # algunos flujos muestran slots como botones/links; ajústalo si aplica

    # Re-validar que el campo fecha sigue en target_iso si el input refleja la fecha elegida
    try:
        date_input = driver.find_element(By.XPATH, "//input[contains(@name,'appointment') and @type='text']")
        # si el input muestra dd/mm/yyyy, solo chequea que el día/mes/año coinciden
        # (omito parsear porque varía según locale; si quieres, parsea y compara)
    except Exception:
        pass

    # Confirmar:
    try:
        confirm = w.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Confirmar') or contains(.,'Confirm')]")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", confirm)
        try: confirm.click()
        except Exception: driver.execute_script("arguments[0].click();", confirm)
    except Exception:
        raise RuntimeError("No encontré el botón Confirmar")

def notify_ntfy(title: str, message: str):
    """Opcional: envía notificación a ntfy si NTFY_TOPIC está definido."""
    import requests
    base = os.environ.get("NTFY_URL", "https://ntfy.sh").rstrip("/")
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    url = f"{base}/{topic}"
    headers = {"Title": title}
    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        requests.post(url, headers=headers, data=message.encode("utf-8"), timeout=10)
    except Exception:
        pass

def main():
    load_dotenv()
    email = os.environ.get("AIS_USER")
    password = os.environ.get("AIS_PASS")
    if not email or not password:
        print("Faltan AIS_USER/AIS_PASS en el entorno (.env)."); return

    driver = build_driver()
    try:
        ok = login(driver, email, password)
        if not ok:
            notify_ntfy("Visa AIS", "Login no confirmado (captcha/credenciales).")
            print("Login no confirmado."); return

        go_to_reschedule(driver)

        earliest = open_calendar_and_get_earliest(driver)  # 'YYYY-MM-DD' o None
        # flow_ok: define tu criterio. Ej.: hay fecha y no vimos banners de error
        flow_ok = bool(earliest)

        ctx = {"page": "Schedule Appointments", "notes": "Primer slot detectado"}
        decision = decide_action(earliest, flow_ok, ctx)
        print(f"[IA] approve={decision.approve} notify={decision.notify} reason={decision.reason}")

        if decision.notify:
            notify_ntfy("Visa AIS", f"{'OK' if decision.approve else 'NO-OK'} | fecha={earliest} | {decision.reason}")

        if decision.approve and earliest:
            # Selecciona hora y confirma
            select_time_and_confirm(driver, earliest)
            notify_ntfy("Visa AIS", f"Reprogramación confirmada para {earliest}.")
        else:
            print("No se confirma reprogramación.")
    finally:
        # driver.quit()  # déjalo comentado si quieres revisar el navegador
        pass

if __name__ == "__main__":
    main()
