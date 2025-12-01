# palletPortal

Pallet Portal is a dual archway automated pallet scanning system designed to streamline outbound shipping operations by integrating barcode detection, object tracking, and manifest verification. It uses the **NVIDIA Jetson Orin Nano**, custom 3D printed hardware, and a Python graphical user interface.

## Overview
- Dual IMX219 cameras for live barcode capture and object tracking.  
- Integrated IR barcode scanner for redundancy and precision.  
- Ultrasonic ping sensors for pallet presence detection and GUI activation.  
- Custom PyQt GUI for real time feedback, mode selection, and system status.  
- Fully 3D printed button interface and display housing, mounted on a dual arch frame.

## Features
- Live dual camera video feed via GStreamer pipeline.  
- Barcode detection and comparison using Pillow/pyzbar/ZXing.  
- Ultrasonic sensor input synchronized with GUI states to prevent crosstalk.  
- Automatic USB manifest detection and reading.  
- Hardware input mapped to GUI navigation (down, cancel, select, up).  
- Custom layered button icons designed in Fusion for tactile control.  

## Hardware
- Jetson Orin Nano Developer Kit  
- Dual IMX219 Cameras  
- Ultrasonic Ping Sensors (HC-SR04)  
- IR Barcode Scanner  
- 3D Printed Components: Display enclosure, button case, dual layer buttons, scaled pallet model (203 mm width)

## Software Stack
| Component | Description |
|------------|-------------|
| Python 3 | Main control and GUI logic |
| PyQt5/Pillow | GUI display and image processing |
| GStreamer | Real time camera pipeline |
| pyzbar/ZXing | Barcode decoding (OpenCV free alternatives) |
| GPIO/Jetson.GPIO | Peripheral communication |
| Threading | Dual camera and sensor concurrency management |

## Current Focus
- Refining UI housing and crossmember mounting.  
- Fusing YOLO individuality to Pillow supportive lightweight detection.  
- Optimizing IR scanner and camera coordination to prevent redundant reads.  
- Improving print efficiency for long 3D jobs (>10 hours per iteration).  

## Known Issues
- Occasional PyQt layout and event conflicts.  
- Camera sensor ID mismatches between CAM0 and CAM1.  
- nvargus daemon instability under high load capture.  
- Jetson thermal throttling during extended use.  
- 3D print size limitations requiring segmented builds.  

## Setup Instructions
```bash
git clone https://github.com/neyoyoyminoy/PalletPortal.git
cd PalletPortal

sudo apt install python3-pyqt5 gstreamer1.0-tools
pip install pillow pyzbar jetson-gpio

python3 GUIv12.py

#this is an optional single camera test; make sure to see current header pin configuration; there can only be sensor 1 and 2 from the 22 header pins
gst-launch-1.0 nvarguscamerasrc sensor-id=0 ! 'video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1' ! nvvidconv ! videoconvert ! xvimagesink
```

## Contributors
- **Brendan Nellis** — Lead Developer, Hardware Integration, GUI and System Design
- **Simeon-Paul O'James** — Lead AI Model Developer, Hardware Integration
- **Jose Escareno II** — Physical Model Fabrication and Assembly  
- **Elliot Cid** — Power Engineer
- **Jim Yanney** — Physical Dimensions Lead

## License
This project is for academic and research purposes under UTSA Senior Design Fall 2025.  
All code and designs are open for non-commercial educational use.
