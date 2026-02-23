"""Lightweight i18n support for RNMR GUI.

Phase 1:
- Persist app language in settings.
- Provide immediate EN/ES fallback translations for key UI strings.
- Keep compatibility with future Qt .qm translations.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTranslator

from renamer.runtime import resource_path


SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "es": "Espanol",
}


_ES_FALLBACK: dict[str, str] = {
    "RNMR - Media File Renamer": "RNMR - Renombrador Multimedia",
    "Renamer": "Renombrador",
    "File": "Archivo",
    "Edit": "Editar",
    "Help": "Ayuda",
    "Exit": "Salir",
    "Settings...": "Configuracion...",
    "About RNMR": "Acerca de RNMR",
    "Support RNMR...": "Apoyar RNMR...",
    "Settings updated. Rescan to apply new naming format.": "Configuracion actualizada. Reescanea para aplicar el formato.",
    "Settings": "Configuracion",
    "Browse...": "Examinar...",
    "Select a folder to scan...": "Selecciona una carpeta para escanear...",
    "Recursive": "Recursivo",
    "Scan subdirectories": "Escanear subcarpetas",
    "Use TMDB": "Usar TMDB",
    "Fetch metadata from TMDB API": "Obtener metadatos desde TMDB API",
    "Include Episode Titles": "Incluir Titulos de Episodio",
    "Include episode names in series filenames": "Incluir nombres de episodios en series",
    "Dry Run": "Simulacion",
    "Preview only, don't rename files": "Solo vista previa, no renombra archivos",
    "Scan": "Escanear",
    "Clear": "Limpiar",
    "Stop": "Detener",
    "API Key Required  --  Set one in Edit > Settings": "API Key requerida  --  Configurala en Editar > Configuracion",
    "File Details": "Detalles del Archivo",
    "Original:": "Original:",
    "New Name:": "Nombre Nuevo:",
    "N/A": "N/D",
    "Status:": "Estado:",
    "Error:": "Error:",
    "Source:": "Fuente:",
    "Parsed Title:": "Titulo Detectado:",
    "Media Type:": "Tipo de Medio:",
    "Season:": "Temporada:",
    "Episode(s):": "Episodio(s):",
    "Year:": "Anio:",
    "TMDB ID:": "TMDB ID:",
    "TMDB Title:": "Titulo TMDB:",
    "Episode Title:": "Titulo de Episodio:",
    "Close": "Cerrar",
    "Ready": "Listo",
    "Undo Last Rename": "Deshacer Ultimo Renombrado",
    "Revert the most recent rename batch": "Revertir el lote de renombrado mas reciente",
    "Rename Selected": "Renombrar Seleccionados",
    "Log": "Registro",
    "Select Media Folder": "Seleccionar Carpeta Multimedia",
    "Select Folder to Scan for Duplicates": "Seleccionar Carpeta para Buscar Duplicados",
    "Nothing to Undo": "Nada para Deshacer",
    "No transactions to undo.": "No hay transacciones para deshacer.",
    "Cannot Undo": "No se Puede Deshacer",
    "Confirm Undo": "Confirmar Deshacer",
    "Stopping scan...": "Deteniendo escaneo...",
    "Stopping...": "Deteniendo...",
    "Scanning...": "Escaneando...",
    "Scanning: {current}/{total}": "Escaneando: {current}/{total}",
    "Found {total} files ({pending} to rename)": "Encontrados {total} archivos ({pending} por renombrar)",
    "Scan complete: {total} files, {pending} pending": "Escaneo completo: {total} archivos, {pending} pendientes",
    "Error": "Error",
    "Scan Error": "Error de Escaneo",
    "Duplicate Finder": "Buscador de Duplicados",
    "Select a folder to scan for duplicates...": "Selecciona una carpeta para buscar duplicados...",
    "Scan Duplicates": "Escanear Duplicados",
    "Path": "Ruta",
    "Size": "Tamano",
    "Modified": "Modificado",
    "Hash (MD5)": "Hash (MD5)",
    "Keep Newest": "Conservar Mas Nuevo",
    "Keep Largest": "Conservar Mas Grande",
    "Manual Pick": "Seleccion Manual",
    "No duplicates found.": "No se encontraron duplicados.",
    "Duplicate Scan Error": "Error de Escaneo de Duplicados",
    "No Selection": "Sin Seleccion",
    "No files selected for deletion.": "No hay archivos seleccionados para eliminar.",
    "Delete Complete": "Eliminacion Completa",
    "Trash Empty": "Papelera Vacia",
    "Trash folder does not exist.": "La carpeta de papelera no existe.",
    "Empty Trash Failed": "Error al Vaciar Papelera",
    "Confirm Permanent Delete": "Confirmar Eliminacion Permanente",
    "Export Error": "Error de Exportacion",
    "Export Duplicate Report (CSV)": "Exportar Reporte de Duplicados (CSV)",
    "Export Duplicate Report (JSON)": "Exportar Reporte de Duplicados (JSON)",
    "Stopping duplicate scan...": "Deteniendo escaneo de duplicados...",
    "Found {groups} group(s), {files} file(s)": "Encontrados {groups} grupo(s), {files} archivo(s)",
    "Trash emptied.": "Papelera vaciada.",
    "Include all files": "Incluir todos los archivos",
    "Scan all files, not just media": "Escanear todos los archivos, no solo multimedia",
    "Safe delete moves files to .rnmr_trash (undoable). Use the Trash menu to open or empty it.": (
        "Eliminacion segura mueve archivos a .rnmr_trash (deshacer disponible). "
        "Usa el menu Papelera para abrirla o vaciarla."
    ),
    "Export": "Exportar",
    "Export CSV": "Exportar CSV",
    "Export JSON": "Exportar JSON",
    "Trash": "Papelera",
    "Open Trash": "Abrir Papelera",
    "Empty Trash": "Vaciar Papelera",
    "SAFE DELETE (Move to Trash)": "ELIMINACION SEGURA (Mover a Papelera)",
    "Safe Delete": "Eliminar Seguro",
    "Delete Permanently": "Eliminar Permanentemente",
    "Permanent Delete": "Eliminar Permanente",
    "Confirm Safe Delete": "Confirmar Eliminacion Segura",
    "Safe delete will move files to trash, not permanently delete them.": (
        "La eliminacion segura movera archivos a la papelera, no los borrara permanentemente."
    ),
    "You can recover them using 'Undo Last Rename' or from the Trash menu.": (
        "Puedes recuperarlos con 'Undo Last Rename' o desde el menu Papelera."
    ),
    "General": "General",
    "TMDB": "TMDB",
    "Behavior": "Comportamiento",
    "App Language": "Idioma de la App",
    "Language": "Idioma",
    "Restart the app to apply language changes everywhere.": (
        "Reinicia la app para aplicar el cambio de idioma en toda la interfaz."
    ),
    "Reset to Defaults": "Restablecer por Defecto",
    "Cancel": "Cancelar",
    "Save": "Guardar",
    "Series Naming": "Nomenclatura Series",
    "Movie Naming": "Nomenclatura Peliculas",
    "Preset:": "Preajuste:",
    "Enter custom template...": "Ingresa plantilla personalizada...",
    "Available Variables": "Variables Disponibles",
    "TMDB Configuration": "Configuracion TMDB",
    "Enter your TMDB API key...": "Ingresa tu TMDB API key...",
    "API Key:": "API Key:",
    "Show": "Mostrar",
    "Hide": "Ocultar",
    "Remove API Key": "Quitar API Key",
    "Clear the stored API key": "Limpiar la API key guardada",
    "Open TMDB Dashboard": "Abrir Panel TMDB",
    "Open your TMDB API settings in a browser": "Abrir ajustes de TMDB API en navegador",
    "Language:": "Idioma:",
    "Rename Behavior": "Comportamiento de Renombrado",
    "Ask before overwriting files": "Preguntar antes de sobrescribir",
    "Enable manual search fallback": "Habilitar fallback de busqueda manual",
    "Always confirm TMDB match": "Siempre confirmar coincidencia TMDB",
    "Always ask media type before search": "Siempre preguntar tipo de medio antes de buscar",
    "Episode Title Language": "Idioma de Titulos de Episodio",
    "Same as metadata language": "Igual que idioma de metadatos",
    "Original language": "Idioma original",
    "English (forced)": "Ingles (forzado)",
    "Mode:": "Modo:",
    "Force episode titles to English": "Forzar titulos de episodio en Ingles",
    "RNMR Setup": "Configuracion RNMR",
    "TMDB API Key Required": "TMDB API Key Requerida",
    "Get API Key": "Obtener API Key",
    "I Already Have One": "Ya Tengo Una",
    "Enter Your API Key": "Ingresa Tu API Key",
    "Paste your TMDB API key here...": "Pega tu TMDB API key aqui...",
    "Back": "Atras",
    "Validate && Save": "Validar y Guardar",
    "Setup Complete": "Configuracion Completa",
    "Continue": "Continuar",
    "Please enter an API key.": "Ingresa una API key.",
    "Validating...": "Validando...",
    "Support RNMR": "Apoyar RNMR",
    "If you find RNMR useful, consider supporting its development.": (
        "Si RNMR te es util, considera apoyar su desarrollo."
    ),
    "BUY ME A COFFEE": "INVITAME UN CAFE",
    "USDT (TRC20 Network)": "USDT (Red TRC20)",
    "Copy": "Copiar",
    "Copied": "Copiado",
    "TMDB Lookup Failed": "Fallo de Busqueda TMDB",
    "TMDB lookup returned no results": "La busqueda TMDB no devolvio resultados",
    "Search Manually": "Buscar Manualmente",
    "Enter TMDB ID": "Ingresar TMDB ID",
    "Skip": "Saltar",
    "Skip All": "Saltar Todo",
    "Select Media Type": "Seleccionar Tipo de Medio",
    "What type of media is this?": "Que tipo de medio es?",
    "TV Series": "Serie TV",
    "Movie": "Pelicula",
    "Select TMDB Match": "Seleccionar Coincidencia TMDB",
    "Film": "Pelicula",
    "Unknown": "Desconocido",
    "Search TMDB...": "Buscar en TMDB...",
    "Search TMDB": "Buscar TMDB",
    "Search title...": "Buscar titulo...",
    "Search": "Buscar",
    "Searching...": "Buscando...",
    "No matches found.": "No se encontraron coincidencias.",
    "No results found.": "No se encontraron resultados.",
    "Found {n} result(s)": "Encontrado(s) {n} resultado(s)",
    "Error: {msg}": "Error: {msg}",
    "Title": "Titulo",
    "Original Title": "Titulo Original",
    "TMDB ID": "TMDB ID",
    "Select": "Seleccionar",
    "Confirm Selection": "Confirmar Seleccion",
    "Set TMDB ID": "Establecer TMDB ID",
    "TMDB Identifier": "Identificador TMDB",
    "Enter TMDB ID, URL, or tv:12345 / movie:12345": "Ingresa TMDB ID, URL, o tv:12345 / movie:12345",
    "ID / URL:": "ID / URL:",
    "Type:": "Tipo:",
    "Lookup Result": "Resultado de Verificacion",
    "Enter an ID to verify...": "Ingresa un ID para verificar...",
    "Verify ID": "Verificar ID",
    "Invalid ID format": "Formato de ID invalido",
    "Looking up...": "Consultando...",
}


class I18NManager:
    """App-level translator and fallback translation helper."""

    def __init__(self):
        self._language = "en"
        self._qt_translator: QTranslator | None = None

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, app, language: str) -> None:
        """Apply language to QApplication, using Qt .qm if available."""
        lang = (language or "en").split("-")[0].lower()
        if lang not in SUPPORTED_LANGUAGES:
            lang = "en"

        if self._qt_translator is not None:
            app.removeTranslator(self._qt_translator)
            self._qt_translator = None

        self._language = lang

        if lang == "en":
            return

        # Optional Qt translator path for future lupdate/lrelease integration.
        qm_path: Path = resource_path(f"resources/i18n/rnmr_{lang}.qm")
        if qm_path.is_file():
            tr = QTranslator()
            if tr.load(str(qm_path)):
                app.installTranslator(tr)
                self._qt_translator = tr

    def t(self, text: str) -> str:
        """Translate using Qt first, then fallback dictionary."""
        qt_text = QCoreApplication.translate("MainWindow", text)
        if qt_text and qt_text != text:
            return qt_text

        if self._language == "es":
            return _ES_FALLBACK.get(text, text)
        return text


i18n = I18NManager()


def t(text: str) -> str:
    """Shorthand translate helper."""
    return i18n.t(text)
