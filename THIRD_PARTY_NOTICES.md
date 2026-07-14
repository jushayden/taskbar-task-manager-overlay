# Third-Party Notices

This project bundles the following pre-built components under `lib/`. They are
redistributed unmodified under their respective licenses.

## LibreHardwareMonitor
- Files: `lib/LibreHardwareMonitorLib.dll`
- Version: 0.9.4 (net472 build)
- License: Mozilla Public License 2.0 (MPL-2.0)
- Source: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor
- License text: https://www.mozilla.org/en-US/MPL/2.0/

Used to read CPU package temperature sensors.

## HidSharp
- Files: `lib/HidSharp.dll`
- License: Apache License 2.0
- Source: https://github.com/IntergatedCircuits/HidSharp
- License text: https://www.apache.org/licenses/LICENSE-2.0

Bundled as a runtime dependency of LibreHardwareMonitor.

---

The Python dependencies (PySide6, psutil, nvidia-ml-py, pythonnet) are installed
from PyPI via `requirements.txt` and are not redistributed in this repository.
