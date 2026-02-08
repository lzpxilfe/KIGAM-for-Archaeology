# KIGAM for Archaeology (QGIS Plugin)

**KIGAM for Archaeology** is a QGIS plugin designed to automate the processing of 1:50,000 geological maps provided by KIGAM (Korea Institute of Geoscience and Mineral Resources) for archaeological research.

## Features

-   **Automated ZIP Loading**: Directly load KIGAM provided ZIP files without manual extraction.
-   **Auto-Encoding**: Automatically handles `cp949` encoding for Korean attribute text.
-   **Dynamic Styling**: Applies symbols automatically by matching shapefile attributes with the `sym` folder contents.
-   **Smart Labeling**: Automatically labels geological layers (Litho) with optimal placement settings.
-   **Layer Organization**: Auto-sorts layers (Points > Lines > Polygons) and hides reference frames by default.

## Installation

1.  Download the latest release ZIP file.
2.  Open QGIS and go to **Plugins > Manage and Install Plugins...**.
3.  Select **Install from ZIP**.
4.  Choose the downloaded file and click **Install Plugin**.

## Usage

1.  Click the **"Load KIGAM ZIP"** icon in the "KIGAM for Archaeology" toolbar.
2.  Select a KIGAM Geological Map ZIP file (e.g., `수치지질도_5만축척_GF03_광정.zip`).
3.  In the settings dialog, choose your preferred **Font Family** and **Size** for labels.
4.  The plugin will process the file, load layers, apply styles, and organize the Table of Contents.

## 🌟 Citation & Star

이 플러그인이 유용했다면 **GitHub Star** ⭐를 눌러주세요! 개발자에게 큰 힘이 됩니다.
If you find this repository useful, please consider giving it a star ⭐ and citing it in your work:

```bibtex
@software{KIGAMForArchaeology2026,
  author = {lzpxilfe},
  title = {KIGAM for Archaeology: Automated QGIS plugin for archaeological distribution maps},
  year = {2026},
  url = {https://github.com/lzpxilfe/KIGAM-for-Archaeology},
  version = {0.1.0}
}
```

## License

This project is licensed under the MIT License.
