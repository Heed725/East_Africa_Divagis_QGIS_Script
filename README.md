# East Africa DIVA-GIS QGIS Scripts

![QGIS](https://img.shields.io/badge/QGIS-3.40%2B-589632?logo=qgis&logoColor=white)
![Python](https://img.shields.io/badge/Python-QGIS%20Python-3776AB?logo=python&logoColor=white)
![GDAL](https://img.shields.io/badge/GDAL-Raster%20%26%20Vector-5CAE58)
![DIVA-GIS](https://img.shields.io/badge/Data-DIVA--GIS-0A7BBC)
![East Africa](https://img.shields.io/badge/Region-East%20Africa-F4B400)
![curl](https://img.shields.io/badge/Downloader-curl.exe-073551?logo=curl&logoColor=white)
![License](https://img.shields.io/badge/License-Data%20source%20terms%20apply-lightgrey)

A small collection of **QGIS Python scripts** for downloading, validating, extracting, and merging selected **DIVA-GIS** datasets for five East African countries:

- 🇹🇿 Tanzania
- 🇺🇬 Uganda
- 🇷🇼 Rwanda
- 🇧🇮 Burundi
- 🇰🇪 Kenya

The scripts are intended to be pasted into the **QGIS Python Console Editor** and run directly from QGIS. Heavy work is placed in a `QgsTask` background task so the QGIS interface can remain responsive while processing.

---

## Included scripts

| Script | Dataset | DIVA-GIS source | Final output |
|---|---|---|---|
| `scripts/east_africa_dem.py` | Elevation / DEM | `diva/alt/*_alt_tif.zip` | Merged GeoTIFF DEM |
| `scripts/east_africa_adm0.py` | Administrative Level 0 | `diva/adm/*_adm.zip` | Merged GeoPackage |
| `scripts/east_africa_landcover.py` | Land cover | `diva/cov/*_cov_tif.zip` | Merged categorical GeoTIFF |

---

## Repository structure

```text
East_Africa_Divagis_QGIS_Script/
│
├── README.md
│
└── scripts/
    ├── east_africa_dem.py
    ├── east_africa_adm0.py
    └── east_africa_landcover.py
```

---

## Requirements

- **QGIS 3.40 or newer** recommended
- QGIS Python environment with bundled **GDAL/OGR**
- **Windows 10/11** for the current `curl.exe` download implementation
- `curl.exe` available in `PATH` or at:

```text
C:\Windows\System32\curl.exe
```

Check curl from PowerShell:

```powershell
curl.exe --version
```

No extra `pip install` is required when running the scripts from a normal QGIS installation.

---

# 1. East Africa DEM

Script:

```text
scripts/east_africa_dem.py
```

Downloads:

```text
https://geodata.ucdavis.edu/diva/alt/TZA_alt_tif.zip
https://geodata.ucdavis.edu/diva/alt/UGA_alt_tif.zip
https://geodata.ucdavis.edu/diva/alt/RWA_alt_tif.zip
https://geodata.ucdavis.edu/diva/alt/BDI_alt_tif.zip
https://geodata.ucdavis.edu/diva/alt/KEN_alt_tif.zip
```

The workflow is:

```text
curl download
      ↓
ZIP validation
      ↓
Extract GeoTIFFs
      ↓
GDAL raster validation
      ↓
Build VRT mosaic
      ↓
Create compressed GeoTIFF
      ↓
Build overviews
      ↓
Load into QGIS
```

Output example:

```text
DIVA_East_Africa_DEM/
│
├── 01_downloads/
├── 02_extracted/
└── 03_merged/
    ├── East_Africa_DEM_TZA_UGA_RWA_BDI_KEN.vrt
    └── East_Africa_DEM_TZA_UGA_RWA_BDI_KEN.tif
```

The merged `.tif` can be used for:

- hillshade
- slope
- aspect
- contour generation
- elevation classification
- topographic mapping
- terrain analysis

---

# 2. East Africa ADM0

Script:

```text
scripts/east_africa_adm0.py
```

Downloads:

```text
https://geodata.ucdavis.edu/diva/adm/TZA_adm.zip
https://geodata.ucdavis.edu/diva/adm/UGA_adm.zip
https://geodata.ucdavis.edu/diva/adm/RWA_adm.zip
https://geodata.ucdavis.edu/diva/adm/BDI_adm.zip
https://geodata.ucdavis.edu/diva/adm/KEN_adm.zip
```

Each DIVA-GIS administrative ZIP can contain several administrative levels. This script deliberately selects **ADM0 only**:

```text
TZA_adm0.shp
UGA_adm0.shp
RWA_adm0.shp
BDI_adm0.shp
KEN_adm0.shp
```

The five country boundaries are merged into:

```text
East_Africa_ADM0.gpkg
└── east_africa_adm0
```

A GeoPackage is used instead of a merged Shapefile because it avoids several Shapefile limitations, including short field names and multi-file storage.

---

# 3. East Africa Land Cover

Script:

```text
scripts/east_africa_landcover.py
```

Downloads:

```text
https://geodata.ucdavis.edu/diva/cov/TZA_cov_tif.zip
https://geodata.ucdavis.edu/diva/cov/UGA_cov_tif.zip
https://geodata.ucdavis.edu/diva/cov/RWA_cov_tif.zip
https://geodata.ucdavis.edu/diva/cov/BDI_cov_tif.zip
https://geodata.ucdavis.edu/diva/cov/KEN_cov_tif.zip
```

Land cover is **categorical raster data**, so the script intentionally uses:

```text
Mosaic resampling: NEAREST
Overview resampling: MODE
```

It does **not** use Bilinear or Cubic resampling because those methods can create artificial class values between valid land-cover categories.

The script also attempts to preserve the original raster color table from the source dataset.

Output example:

```text
DIVA_East_Africa_LandCover/
│
├── 01_downloads/
├── 02_extracted/
└── 03_merged/
    ├── East_Africa_LandCover_TZA_UGA_RWA_BDI_KEN.vrt
    └── East_Africa_LandCover_TZA_UGA_RWA_BDI_KEN.tif
```

---

## How to run a script in QGIS

### Step 1 — Open QGIS

Launch QGIS 3.40 or newer.

### Step 2 — Open the Python Console

Go to:

```text
Plugins → Python Console
```

### Step 3 — Open the editor

Click **Show Editor** in the Python Console.

### Step 4 — Copy a script

Open one of the files from the `scripts` folder and copy the complete Python code into the QGIS Python editor.

### Step 5 — Run

Click **Run Script**.

### Step 6 — Select an output folder

The script asks where the project output should be stored.

### Step 7 — Watch QGIS Tasks

The processing work runs through a QGIS background task. Watch the **Tasks** indicator in QGIS for progress.

### Step 8 — Use the result

After a successful run, the final raster/vector layer is automatically added to the QGIS project and QGIS zooms to it.

---

## Download strategy

The scripts currently use **Windows `curl.exe`** rather than Python `urllib` or a blocking QGIS network call.

Typical curl options include:

```text
-4
--http1.1
-L
--fail
--retry
--retry-all-errors
--connect-timeout
--max-time
--ssl-no-revoke
```

The scripts also attempt to detect an explicitly configured Windows HTTPS/HTTP proxy and can fall back to a direct curl connection.

> **Note:** A browser and curl can sometimes reach the same website through different network, proxy, DNS, or TLS paths. If your browser can download from DIVA-GIS but curl cannot, that is usually a local/network routing issue rather than a GDAL or QGIS merge problem.

---

## Safety and validation checks

Before using downloaded data, the scripts perform checks such as:

- ZIP exists and is not suspiciously small
- ZIP structure is valid
- ZIP members pass integrity testing
- extracted paths are checked before extraction
- expected TIFF/Shapefile data is present
- GDAL/OGR can open the dataset
- raster dimensions are valid
- raster georeferencing exists
- raster CRS exists
- ADM0 features exist
- land-cover input CRS, band count, and data type are compatible before mosaicking

The scripts stop rather than silently creating a result when an important validation step fails.

---

## Data source

Data are downloaded from the DIVA-GIS / UC Davis geodata server:

**DIVA-GIS:** https://www.diva-gis.org/

**UC Davis geodata:** https://geodata.ucdavis.edu/diva/

This repository contains automation scripts only. The downloaded geographic datasets remain subject to the terms, attribution requirements, metadata, and licensing conditions of their original data providers.

---

## Supported countries

| ISO3 | Country |
|---|---|
| `TZA` | Tanzania |
| `UGA` | Uganda |
| `RWA` | Rwanda |
| `BDI` | Burundi |
| `KEN` | Kenya |

To extend the scripts to another country, add its DIVA-GIS ISO3 code to the `COUNTRIES` dictionary if the equivalent dataset exists on the source server.

---

## Troubleshooting

### `curl.exe was not found`

Run:

```powershell
curl.exe --version
```

If Windows cannot find curl, confirm that this file exists:

```text
C:\Windows\System32\curl.exe
```

### Connection timeout

Test one dataset manually:

```powershell
curl.exe -4 --http1.1 -L --ssl-no-revoke \
  "https://geodata.ucdavis.edu/diva/alt/TZA_alt_tif.zip" \
  -o "$env:USERPROFILE\Downloads\TZA_alt_tif.zip"
```

If the browser downloads immediately but curl times out, inspect Windows proxy/PAC/network settings. The merge portion of the QGIS script cannot begin until the ZIP files are successfully obtained.

### QGIS becomes unresponsive

Do not convert the downloads back to a blocking call on the QGIS main GUI thread. The scripts in this repository use `QgsTask` so long-running work can happen in the background.

### Land-cover colors look different

The script attempts to transfer the source color table. If QGIS still renders the output differently, open **Layer Properties → Symbology**, use **Paletted/Unique values**, and classify the raster values.

---

## Contributing

Issues, improvements, additional DIVA-GIS datasets, Linux/macOS download support, and QGIS Processing Toolbox versions are welcome.

Potential future additions:

- ADM1 / ADM2 merger scripts
- roads and rivers
- population rasters
- climate datasets
- automatic QGIS style files (`.qml`)
- Linux/macOS curl support
- QGIS Processing Toolbox algorithms
- a full QGIS plugin interface

---

## Author

Created and maintained in the **Heed725** GitHub collection for GIS/QGIS automation and East African spatial-data workflows.

⭐ If this repository is useful, consider starring it on GitHub.
