# Third-party notices

<!-- SPDX-License-Identifier: GPL-3.0-only -->

This document records components used by GodCam as observed in the local development environment. It is a technical inventory, not legal advice. A standalone release must be reviewed again if it bundles additional binaries or changes dependency versions.

| Component | Version observed or declared | License | Source / relevant obligation |
|---|---:|---|---|
| PyQt6 | 6.12.0 installed; `>=6.6` declared | GPL-3.0-only | Riverbank Computing / PyPI metadata. Keep the project GPL-compatible and preserve its license notice when redistributed. |
| PyQt6-Qt6 | 6.12.0 installed | LGPL-3.0 | Qt runtime dependency. A bundled runtime requires a distribution-specific compliance review. |
| PyQt6-sip | 13.13.0 installed | BSD-2-Clause | Preserve the bundled license if redistributed. |
| python-vlc | 3.0.21203 installed; `>=3.0.20123` declared | LGPL-2.1-or-later | Python binding for VLC; preserve applicable notices when redistributed. |
| VLC Desktop | External system dependency | Not bundled | The application requires a compatible VLC installation. No VLC binary is included in this repository. Review the chosen VLC distribution before bundling it. |
| onvif-zeep | 0.2.12 installed and declared | MIT | ONVIF client package; preserve its MIT notice if redistributed. |
| zeep | 4.3.3 installed | MIT | Transitive SOAP dependency of ONVIF support. |
| sounddevice | 0.5.6 installed; `>=0.4.6` declared | MIT | Audio capture binding. |
| NumPy | 2.5.4 installed; `>=1.26` declared | Composite SPDX expression: BSD-3-Clause, 0BSD, MIT, Zlib and CC0-1.0 | Preserve the licenses distributed with the version actually shipped. |
| requests | 2.34.2 installed | Apache-2.0 | Transitive dependency used by ONVIF/Zeep. |
| lxml | 6.1.3 installed | BSD-3-Clause | Transitive XML dependency used by ONVIF/Zeep. |
| Lucide icons | Local SVG assets | ISC | Preserve `godcam/resources/icons/LICENSE.txt`. |
| Feather-derived icons | `link`, `plus`, `trash` | MIT | Preserve `godcam/resources/icons/LICENSE.txt`. |
| scan-eye application icon | Local SVG/ICO asset | Lucide ISC, per project attribution | Keep the Lucide attribution and review provenance if the asset is replaced. |
| FFmpeg | External system dependency | Not bundled | The application invokes an FFmpeg executable on `PATH`; a future bundled distribution needs a separate license/build review. |

The full notices already supplied for Lucide and Feather remain in `godcam/resources/icons/LICENSE.txt` and must not be removed.
