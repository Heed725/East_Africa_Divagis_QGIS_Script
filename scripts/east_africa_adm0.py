# -*- coding: utf-8 -*-
"""
QGIS 3.40+
DIVA-GIS East Africa Administrative Level 0 Downloader + Merger

Countries:
    Tanzania, Uganda, Rwanda, Burundi, Kenya

Source pattern:
    https://geodata.ucdavis.edu/diva/adm/TZA_adm.zip

The script downloads with Windows curl.exe, extracts each archive, selects only
ADM0 shapefiles, validates them, merges them into one GeoPackage, and loads the
result into QGIS.
"""

import os
import shutil
import subprocess
import time
import winreg
import zipfile

from osgeo import gdal, ogr
from qgis.core import QgsApplication, QgsProject, QgsTask, QgsVectorLayer
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox


gdal.UseExceptions()

BASE_URL = "https://geodata.ucdavis.edu/diva/adm"
COUNTRIES = {
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "RWA": "Rwanda",
    "BDI": "Burundi",
    "KEN": "Kenya",
}
OUTPUT_FILE = "East_Africa_ADM0.gpkg"
OUTPUT_LAYER = "east_africa_adm0"


def find_curl():
    for path in (shutil.which("curl.exe"), shutil.which("curl"), r"C:\Windows\System32\curl.exe"):
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    raise RuntimeError("curl.exe was not found. Open PowerShell and run: curl.exe --version")


def get_windows_proxy():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        try:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        except FileNotFoundError:
            enabled = 0
        if not enabled:
            winreg.CloseKey(key)
            return None

        try:
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
        except FileNotFoundError:
            proxy_server = None
        winreg.CloseKey(key)
        if not proxy_server:
            return None

        if "=" in proxy_server:
            proxies = {}
            for item in proxy_server.split(";"):
                if "=" in item:
                    protocol, address = item.split("=", 1)
                    proxies[protocol.strip().lower()] = address.strip()
            proxy = proxies.get("https") or proxies.get("http")
        else:
            proxy = proxy_server

        if proxy and not proxy.startswith(("http://", "https://")):
            proxy = "http://" + proxy
        return proxy
    except Exception:
        return None


def run_curl(task, curl_path, url, destination, proxy=None):
    part = destination + ".part"
    if os.path.exists(part):
        os.remove(part)

    command = [
        curl_path,
        "-4",
        "--http1.1",
        "-L",
        "--fail",
        "--show-error",
        "--retry", "4",
        "--retry-all-errors",
        "--retry-delay", "3",
        "--connect-timeout", "40",
        "--max-time", "900",
        "--ssl-no-revoke",
        "--output", part,
    ]
    if proxy:
        command.extend(["--proxy", proxy])
    command.append(url)

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=flags,
    )

    while process.poll() is None:
        if task.isCanceled():
            process.kill()
            raise RuntimeError("Task cancelled by user.")
        time.sleep(0.25)

    _, stderr = process.communicate()
    if process.returncode != 0:
        if os.path.exists(part):
            os.remove(part)
        raise RuntimeError(f"curl failed for {url}\n\n{stderr}")

    if not os.path.isfile(part) or os.path.getsize(part) < 1000:
        raise RuntimeError(f"Downloaded file is missing or suspiciously small: {url}")
    if not zipfile.is_zipfile(part):
        raise RuntimeError(f"Downloaded file is not a valid ZIP: {url}")

    with zipfile.ZipFile(part, "r") as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Corrupt ZIP member: {bad}")

    if os.path.exists(destination):
        os.remove(destination)
    os.replace(part, destination)
    return destination


def download_country(task, curl_path, url, destination, country):
    errors = []
    proxy = get_windows_proxy()
    if proxy:
        try:
            return run_curl(task, curl_path, url, destination, proxy)
        except Exception as exc:
            errors.append(f"Windows proxy attempt failed:\n{exc}")

    try:
        return run_curl(task, curl_path, url, destination, None)
    except Exception as exc:
        errors.append(f"Direct curl attempt failed:\n{exc}")

    raise RuntimeError(f"{country} download failed.\n\n" + "\n\n".join(errors))


def safe_extract(zip_path, destination):
    if os.path.isdir(destination):
        shutil.rmtree(destination)
    os.makedirs(destination, exist_ok=True)
    base = os.path.realpath(destination)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = os.path.realpath(os.path.join(destination, member.filename))
            if os.path.commonpath([base, target]) != base:
                raise RuntimeError(f"Unsafe path in ZIP: {member.filename}")
        archive.extractall(destination)


def find_adm0(folder, code):
    expected = f"{code}_adm0.shp".lower()
    matches = []
    for root, _, files in os.walk(folder):
        for filename in files:
            if filename.lower() == expected:
                matches.append(os.path.abspath(os.path.join(root, filename)))
    if not matches:
        raise RuntimeError(f"Could not find {code}_adm0.shp")
    return matches[0]


def validate_adm0(path, country):
    ds = ogr.Open(path, 0)
    if ds is None:
        raise RuntimeError(f"OGR cannot open {country} ADM0: {path}")
    layer = ds.GetLayer(0)
    if layer is None:
        ds = None
        raise RuntimeError(f"{country} ADM0 has no layer.")
    count = layer.GetFeatureCount()
    if count < 1:
        ds = None
        raise RuntimeError(f"{country} ADM0 contains no features.")
    if layer.GetSpatialRef() is None:
        ds = None
        raise RuntimeError(f"{country} ADM0 has no CRS.")
    ds = None
    return count


def worker(task, output_root):
    curl_path = find_curl()
    work = os.path.join(output_root, "DIVA_East_Africa_ADM0")
    downloads = os.path.join(work, "01_downloads")
    extracted = os.path.join(work, "02_extracted")
    merged = os.path.join(work, "03_merged")
    for folder in (downloads, extracted, merged):
        os.makedirs(folder, exist_ok=True)

    adm0_files = []
    total = len(COUNTRIES)

    for index, (code, country) in enumerate(COUNTRIES.items()):
        if task.isCanceled():
            return None
        task.setDescription(f"East Africa ADM0 - downloading {country}")
        task.setProgress(index / total * 65)

        zip_name = f"{code}_adm.zip"
        url = f"{BASE_URL}/{zip_name}"
        zip_path = os.path.join(downloads, zip_name)
        download_country(task, curl_path, url, zip_path, country)

        task.setDescription(f"East Africa ADM0 - extracting {country}")
        country_folder = os.path.join(extracted, code)
        safe_extract(zip_path, country_folder)

        adm0 = find_adm0(country_folder, code)
        validate_adm0(adm0, country)
        adm0_files.append(adm0)

    if len(adm0_files) != len(COUNTRIES):
        raise RuntimeError("Expected exactly five validated ADM0 datasets.")

    final_path = os.path.join(merged, OUTPUT_FILE)
    if os.path.exists(final_path):
        os.remove(final_path)

    task.setDescription("East Africa ADM0 - creating GeoPackage")
    task.setProgress(72)

    first = gdal.VectorTranslate(
        final_path,
        adm0_files[0],
        options=gdal.VectorTranslateOptions(
            format="GPKG",
            layerName=OUTPUT_LAYER,
            accessMode="overwrite",
        ),
    )
    if first is None:
        raise RuntimeError("Failed to create initial GeoPackage.")
    first = None

    for i, shp_path in enumerate(adm0_files[1:], start=1):
        if task.isCanceled():
            return None
        task.setDescription(f"East Africa ADM0 - merging country {i + 1}/5")
        appended = gdal.VectorTranslate(
            final_path,
            shp_path,
            options=gdal.VectorTranslateOptions(
                format="GPKG",
                layerName=OUTPUT_LAYER,
                accessMode="append",
                addFields=True,
            ),
        )
        if appended is None:
            raise RuntimeError(f"Failed while appending: {shp_path}")
        appended = None
        task.setProgress(72 + (i / 4) * 23)

    ds = ogr.Open(final_path, 0)
    if ds is None:
        raise RuntimeError("Could not reopen final GeoPackage.")
    layer = ds.GetLayerByName(OUTPUT_LAYER)
    if layer is None:
        ds = None
        raise RuntimeError("Merged ADM0 layer was not found.")
    feature_count = layer.GetFeatureCount()
    ds = None
    if feature_count < 5:
        raise RuntimeError("Final ADM0 contains fewer than five country features.")

    task.setProgress(100)
    return {
        "final_path": final_path,
        "layer_name": OUTPUT_LAYER,
        "feature_count": feature_count,
    }


def finished(exception, result=None):
    if exception:
        QMessageBox.critical(None, "East Africa ADM0 failed", str(exception))
        return
    if not result:
        QMessageBox.warning(None, "East Africa ADM0", "Task cancelled.")
        return

    uri = result["final_path"] + "|layername=" + result["layer_name"]
    layer = QgsVectorLayer(uri, "East Africa ADM0", "ogr")
    if not layer.isValid():
        QMessageBox.warning(None, "East Africa ADM0", f"GeoPackage created but could not be loaded:\n{result['final_path']}")
        return

    QgsProject.instance().addMapLayer(layer)
    try:
        iface.setActiveLayer(layer)
        iface.zoomToActiveLayer()
    except Exception:
        pass

    QMessageBox.information(
        None,
        "East Africa ADM0 complete",
        "SUCCESS\n\nTanzania ✓\nUganda ✓\nRwanda ✓\nBurundi ✓\nKenya ✓\n\n"
        f"Features: {result['feature_count']}\n\n"
        f"Final GeoPackage:\n{result['final_path']}",
    )


output_root = QFileDialog.getExistingDirectory(None, "Choose output folder for East Africa ADM0")
if output_root:
    task = QgsTask.fromFunction(
        "East Africa DIVA ADM0",
        worker,
        on_finished=finished,
        output_root=output_root,
    )
    QgsApplication.taskManager().addTask(task)
