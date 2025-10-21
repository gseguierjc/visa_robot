automation visa

Variables de entorno útiles
---------------------------

- CHROME_BIN: ruta al binario de Chrome/Chromium (si no está en PATH). Ej: /usr/bin/google-chrome-stable
- HEADLESS: 1 o true para ejecutar en modo headless (por defecto el script no fuerza headless)
- USER_AGENT: user-agent personalizado para el navegador
- NTFY_URL, NTFY_TOPIC, NTFY_TITLE: para el envío de notificaciones vía ntfy

- CHROME_KILL_CONFLICTS: si se establece a 1/true el script listará procesos
	relacionados con Chrome/Chromedriver antes de crear el WebDriver y
	los intentará terminar (útil para depuración en contenedores donde queden
	procesos huérfanos que bloqueen el perfil de usuario).

Ejecución en Ubuntu
-------------------

1. Instala dependencias: python3 -m pip install -r requirements.txt
2. Asegúrate de tener Chrome/Chromium instalado y el chromedriver compatible, o deja que webdriver-manager lo descargue automáticamente.
3. Ejecuta: python visa_reprogram.py

Notas sobre "sigilo" (bot evasion)
---------------------------------
El script intenta mitigar detecciones básicas (navigator.webdriver, flags de Chrome).
Si necesitas mayor evasión, instala `undetected-chromedriver` y establece la variable HEADLESS si corresponde.
