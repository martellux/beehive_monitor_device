# beehive_monitor_device
A rudimentary device for the environmental monitoring of beehives based on ESP32 board.

## Some details

### 1. The Board
The board used for this project is a standard ESP32-DevKitC [ESPRESSIF Website](https://www.espressif.com/en/products/devkits/esp32-devkitc).
The board has been flashed with MicroPython firmware v1.19.1 [MicroPython](https://micropython.org/download/esp32/)

### 2. The Sensor
The sensor used for this project is a standard DHT22 [Specifications](https://components101.com/sensors/dht22-pinout-specs-datasheet)

### 3. The Software
The software for the measurement and for the BLE connections has been developed using MicroPython for ESP32 [Docs](https://docs.micropython.org/en/latest/esp32/quickref.html)

### 4. The Box
A tailored Lego-based box has been designed for containing the ESP32 board and a PowerBank as power supplier. Further, some peculiarities have been provided for cables and sensor.
![Screenshot](BoxSmall.png)

The design hass been realized with with Studio by bricklink [Download](https://www.bricklink.com/v3/studio/download.page) and can be downloaded here [Source file](https://github.com/martellux/beehive_monitor_device/blob/develop/box/BoxSmall.io?raw=true)

### 5. Flash and Run
The file main.py contains the code for the management of BLE communication and sensor scanning. With a simple tool, like [Thonny](https://thonny.org), you can open it and execute the loading into the ESP32 board. By default, the code in the main.py file is executed automatically at every boot of the board.
Once powered, the board starts emitting the BLE advertising packet (peripheral mode) and it becomes discoverable and connectable from a BLE client. The discoverable name is "swarm-env-sensor". If you need a BLE client you can use a free Mobile App from Play Store or App Store (i.e [nRF Connect for Mobile](https://play.google.com/store/apps/details?id=no.nordicsemi.android.mcp))

After the connection, the board shows up the following configuration:

Service | Name
--- | ---
PRIMARY SERVICE | "Environmental Sensing" service with UUID 181A

Characteristic | Properties
--- | ---
"Digital" characteristic with UUID 2A56 | Write
"Digital Output" characteristic with UUID 2A57 | Notify


### 6. Available Commands

Command | Type | Description
--- | --- | ---
"RN" | UTF-8 | Send this command to get current temperature and humidity


License
-------

    Copyright 2023 Alessandro Martellucci

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

[1]: https://search.maven.org/remote_content?g=com.martellux&a=lifecycle&v=LATEST
