# -*- coding: utf-8 -*-
"""
QGIS 3.40+
DIVA-GIS East Africa Land-Cover Downloader + Merger

Countries:
    Tanzania, Uganda, Rwanda, Burundi, Kenya

Source pattern:
    https://geodata.ucdavis.edu/diva/cov/TZA_cov_tif.zip

The script downloads with Windows curl.exe, validates and extracts each archive,
checks the GeoTIFFs, mosaics them with nearest-neighbour resampling, writes a
compressed GeoTIFF, preserves the source palette where possible, builds MODE
overviews, and loads the result into QGIS.
"""

import os
import shutil
import subprocess
import time
import winreg
import zipfile

from osgeo import gdal, osr
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer, QgsTask
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox


gdal.UseExceptions()

BASE_URL = "https://geodata.ucdavis.edu/diva/cov"
COUNTRIES = {
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "RWA": "Rwanda",
    "BDI": "Burundi",
    "KEN": "Kenya",
}
FINAL_NAME = "East_Africa_LandCover_TZA_UGA_RWA_BDI_KEN.tif"
VRT_NAME = "East_Africa_LandCover_TZA_UGA_RWA_BDI_KEN.vrt"


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

    raise RuntimeError(f"{country} land-cover download failed.\n\n" + "\n\n".join(errors))


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


def find_tiffs(folder):
    rasters = []
    for root, _, files in os.walk(folder):
        for filename in files:
            if filename.lower().endswith((".tif", ".tiff")):
                rasters.append(os.path.abspath(os.path.join(root, filename)))
    return sorted(rasters)


def same_crs(wkt1, wkt2):
    if not wkt1 or not wkt2:
        return False
    a = osr.SpatialReference()
    b = osr.SpatialReference()
    a.ImportFromWkt(wkt1)
    b.ImportFromWkt(wkt2)
    return bool(a.IsSame(b))


def inspect_raster(path):
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"GDAL cannot open raster: {path}")
    if ds.RasterCount < 1 or ds.RasterXSize <= 0 or ds.RasterYSize <= 0:
        ds = None
        raise RuntimeError(f"Invalid raster: {path}")

    gt = ds.GetGeoTransform(can_return_null=True)
    projection = ds.GetProjection()
    if gt is None:
        ds = None
        raise RuntimeError(f"Raster has no georeferencing: {path}")
    if not projection:
        ds = None
        raise RuntimeError(f"Raster has no CRS: {path}")

    band = ds.GetRasterBand(1)
    color_table = band.GetRasterColorTable()
    info = {
        "path": path,
        "width": ds.RasterXSize,
        "height": ds.RasterYSize,
        "bands": ds.RasterCount,
        "datatype": band.DataType,
        "datatype_name": gdal.GetDataTypeName(band.DataType),
        "nodata": band.GetNoDataValue(),
        "color_count": color_table.GetCount() if color_table else 0,
        "projection": projection,
        "geotransform": gt,
    }
    ds = None
    return info


def preserve_color_table(source_path, destination_path):
    src = gdal.Open(source_path, gdal.GA_ReadOnly)
    dst = gdal.Open(destination_path, gdal.GA_Update)
    if not src or not dst:
        src = None
        dst = None
        return

    src_band = src.GetRasterBand(1)
    dst_band = dst.GetRasterBand(1)
    table = src_band.GetRasterColorTable()
    if table:
        dst_band.SetRasterColorTable(table)
        dst_band.SetRasterColorInterpretation(src_band.GetRasterColorInterpretation())
    nodata = src_band.GetNoDataValue()
    if nodata is not None:
        dst_band.SetNoDataValue(nodata)
    dst.FlushCache()
    src = None
    dst = None


def worker(task, output_root):
    curl_path = find_curl()
    work = os.path.join(output_root, "DIVA_East_Africa_LandCover")
    downloads = os.path.join(work, "01_downloads")
    extracted = os.path.join(work, "02_extracted")
    merged = os.path.join(work, "03_merged")
    for folder in (downloads, extracted, merged):
        os.makedirs(folder, exist_ok=True)

    raster_info = []
    total = len(COUNTRIES)

    for index, (code, country) in enumerate(COUNTRIES.items()):
        if task.isCanceled():
            return None
        task.setDescription(f"East Africa Land Cover - downloading {country}")
        task.setProgress(index / total * 60)

        zip_name = f"{code}_cov_tif.zip"
        url = f"{BASE_URL}/{zip_name}"
        zip_path = os.path.join(downloads, zip_name)
        download_country(task, curl_path, url, zip_path, country)

        task.setDescription(f"East Africa Land Cover - extracting {country}")
        country_folder = os.path.join(extracted, code)
        safe_extract(zip_path, country_folder)

        tiffs = find_tiffs(country_folder)
        if not tiffs:
            raise RuntimeError(f"No GeoTIFF found after extracting {country}.")
        for tif in tiffs:
            info = inspect_raster(tif)
            info["country_code"] = code
            info["country"] = country
            raster_info.append(info)

    found = {item["country_code"] for item in raster_info}
    missing = [COUNTRIES[code] for code in COUNTRIES if code not in found]
    if missing:
        raise RuntimeError("Cannot merge land cover. Missing: " + ", ".join(missing))

    reference = raster_info[0]
    for info in raster_info[1:]:
        if not same_crs(reference["projection"], info["projection"]):
            raise RuntimeError(f"CRS mismatch: {info['path']}")
        if info["bands"] != reference["bands"]:
            raise RuntimeError(f"Band-count mismatch: {info['path']}")
        if info["datatype"] != reference["datatype"]:
            raise RuntimeError(f"Data-type mismatch: {info['path']}")

    raster_paths = [item["path"] for item in raster_info]
    vrt_path = os.path.join(merged, VRT_NAME)
    final_path = os.path.join(merged, FINAL_NAME)
    for path in (vrt_path, final_path, final_path + ".ovr"):
        if os.path.exists(path):
            os.remove(path)

    vrt_kwargs = {"resolution": "highest", "resampleAlg": "nearest"}
    if reference["nodata"] is not None:
        vrt_kwargs["srcNodata"] = reference["nodata"]
        vrt_kwargs["VRTNodata"] = reference["nodata"]

    task.setDescription("East Africa Land Cover - building categorical VRT")
    task.setProgress(70)
    vrt = gdal.BuildVRT(
        vrt_path,
        raster_paths,
        options=gdal.BuildVRTOptions(**vrt_kwargs),
    )
    if vrt is None:
        raise RuntimeError("GDAL BuildVRT failed.")
    vrt.FlushCache()
    vrt = None
    inspect_raster(vrt_path)

    task.setDescription("East Africa Land Cover - writing GeoTIFF")
    task.setProgress(84)
    out = gdal.Translate(
        final_path,
        vrt_path,
        options=gdal.TranslateOptions(
            format="GTiff",
            creationOptions=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"],
        ),
    )
    if out is None:
        raise RuntimeError("GDAL Translate failed.")
    out.FlushCache()
    out = None

    preserve_color_table(reference["path"], final_path)
    final = inspect_raster(final_path)

    task.setDescription("East Africa Land Cover - building MODE overviews")
    task.setProgress(94)
    try:
        ds = gdal.Open(final_path, gdal.GA_Update)
        if ds:
            ds.BuildOverviews("MODE", [2, 4, 8, 16, 32])
            ds = None
    except Exception:
        pass

    task.setProgress(100)
    return {
        "final_path": final_path,
        "width": final["width"],
        "height": final["height"],
        "datatype": final["datatype_name"],
        "palette": final["color_count"],
        "inputs": len(raster_paths),
    }


def finished(exception, result=None):
    if exception:
        QMessageBox.critical(None, "East Africa Land Cover failed", str(exception))
        return
    if not result:
        QMessageBox.warning(None, "East Africa Land Cover", "Task cancelled.")
        return

    layer = QgsRasterLayer(result["final_path"], "East Africa Land Cover")
    if not layer.isValid():
        QMessageBox.warning(None, "East Africa Land Cover", f"Raster created but could not be loaded:\n{result['final_path']}")
        return

    QgsProject.instance().addMapLayer(layer)
    try:
        iface.setActiveLayer(layer)
        iface.zoomToActiveLayer()
    except Exception:
        pass

    QMessageBox.information(
        None,
        "East Africa Land Cover complete",
        "SUCCESS\n\nTanzania ✓\nUganda ✓\nRwanda ✓\nBurundi ✓\nKenya ✓\n\n"
        f"Input rasters: {result['inputs']}\n"
        f"Dimensions: {result['width']} x {result['height']}\n"
        f"Data type: {result['datatype']}\n"
        f"Palette entries: {result['palette']}\n\n"
        f"Final raster:\n{result['final_path']}",
    )


output_root = QFileDialog.getExistingDirectory(None, "Choose output folder for East Africa Land Cover")
if output_root:
    task = QgsTask.fromFunction(
        "East Africa DIVA Land Cover",
        worker,
        on_finished=finished,
        output_root=output_root,
    )
    QgsApplication.taskManager().addTask(task)
