import sys

sys.path.append("")

from micropython import const

import uasyncio as asyncio
import aioble
import bluetooth
import time

import random
import struct

import os

from machine import Pin
import dht

from aioble.core import (
    register_irq_handler,
)

import esp

sensor = dht.DHT22(Pin(14))

# org.bluetooth.service.environmental_sensing
_ENV_SENSE_UUID = bluetooth.UUID(0x181A)
# org.bluetooth.service.generic_access
_ENV_GENERIC_ACCESS_UUID = bluetooth.UUID(0x1800)
# org.bluetooth.characteristic.temperature
_ENV_SENSE_TEMP_UUID = bluetooth.UUID(0x2A6E)
# org.bluetooth.characteristic.humidity
_ENV_SENSE_HUMIDITY_UUID = bluetooth.UUID(0x2A6F)
# org.bluetooth.characteristic.scan_refresh
_ENV_SCAN_REFRESH_UUID = bluetooth.UUID(0x2A31)
# org.bluetooth.characteristic.aggregate
_ENV_AGGREGATE_UUID = bluetooth.UUID(0x2A5A)
# org.bluetooth.characteristic.gap.appearance.xml
_ADV_APPEARANCE_GENERIC_THERMOMETER = const(768)

# How frequently to send advertising beacons.
_ADV_INTERVAL_MS = 250_000


# Register GATT server.
sense_service = aioble.Service(_ENV_SENSE_UUID)
temp_characteristic = aioble.Characteristic(
    sense_service, _ENV_SENSE_TEMP_UUID, read=True, notify=True
)
humidity_characteristic = aioble.Characteristic(
    sense_service, _ENV_SENSE_HUMIDITY_UUID, read=True, notify=True
)

generic_service = aioble.Service(_ENV_GENERIC_ACCESS_UUID)
input_characteristic = aioble.Characteristic(
    generic_service, _ENV_SCAN_REFRESH_UUID, write=True
)
output_characteristic = aioble.Characteristic(
    generic_service, _ENV_AGGREGATE_UUID, notify=True
)
aioble.register_services(sense_service, generic_service)





def _peripheral_irq(event, data):
    print("My Event:", event)
    print("My Data: ", data)


def _peripheral_shutdown():
    print("Peripheral shutdown")


register_irq_handler(_peripheral_irq, _peripheral_shutdown)






# Helper to encode the temperature characteristic encoding (sint16, hundredths of a degree).
def _encode_temperature(temp_deg_c):
    return struct.pack("<h", int(temp_deg_c * 100))

#Helper to encode the humidity characteristic
def _encode_humidity(humidity_perc):
    return struct.pack("<h", int(humidity_perc * 100))    


async def disk_task():
    print('Flash size: ', esp.flash_size())
    print('User offset: ', esp.flash_user_start())
    starting_offset_for_counter = esp.flash_user_start() + 1
    starting_offset_for_reads = esp.flash_user_start() + 2
    
    buf_counter = bytearray(1)
    esp.flash_read(starting_offset_for_counter, buf_counter)
    saved_sensors_reads = buf_counter[0]
    print('Saved sensors reads: ', saved_sensors_reads)
    
    

    my_str = "hello world"
    my_str_as_bytes = str.encode(my_str, 'utf-8')
    print(type(my_str_as_bytes))
    print(len(my_str_as_bytes))
    print(my_str_as_bytes[0])
    
    
    esp.flash_write(starting_offset_for_reads, my_str_as_bytes)
    
    buf_reads = bytearray(11)
    esp.flash_read(starting_offset_for_reads, buf_reads)
    
    print(len(buf_reads))
    print(buf_reads[0])
    my_decoded_str = buf_reads.decode('utf-8')
    print(my_decoded_str)
    
    try:
        # list root directory
        print(os.listdir('/'))
        # print current director
        print(os.getcwd())
        print(os.stat('/'))
    except IOError as e:
        print('IOError: ', e)
    
    
    
    
    
    
    
    


# This would be periodically polling a hardware sensor.
async def sensor_task():
    os.remove('data.txt')
    t = 0.0
    h = 0.0
    
    await asyncio.sleep_ms(2000)
    while True:
        try:
            sensor.measure()
            t = sensor.temperature()
            h = sensor.humidity()
            print('Temperature: %3.1f C' %t)
            print('Humidity: %3.1f %%' %h)
        except OSError as e:
            print('Error reading sensor: ', e)
            
        try:
            # Encode data from sensor and write to characteristics
            temp_characteristic.write(_encode_temperature(t))
            humidity_characteristic.write(_encode_humidity(h))
        except OSError as e:
            print('Error writing characteristics: ', e)

        
#        try:
            
#            # Append time and sensor data to file
#            data = str(time.localtime()) + "_" + str(t) + "_" + str(h) + "\n"
#            with open('data.txt', 'a') as f:
#                b = f.write(data)
#                f.flush()
#                f.close()
#                
#            # Read and print data from file
#            with open('data.txt', 'r') as f:
#                    lines = f.readlines()
#                    print("Lines ", lines)
#                    f.close()
#        except IOError as e:
#            print('IOError: ', e)

        # wait for next scan
        await asyncio.sleep_ms(10000)
        #3600000 1h


# Serially wait for connections. Don't advertise while a central is
# connected.
async def peripheral_task():
    while True:
        print("Start while")
        async with await aioble.advertise(
            _ADV_INTERVAL_MS,
            name="swarm-env-sensor",
            services=[_ENV_SENSE_UUID],
            appearance=_ADV_APPEARANCE_GENERIC_THERMOMETER,
        ) as connection:
#            print("Connection from", connection.device)
            await connection.disconnected()
            print("Disconnected")
        print("End while")
        
        

async def timer_task():
    while True:
        print("Local time：%s" %str(time.localtime()))
        await asyncio.sleep_ms(60000)

async def only_sensor_task():
    try:
        while True:
            sensor.measure()
            temp = sensor.temperature()
            hum = sensor.humidity()
            print('Temperature: %3.1f C' %temp)
            print('Humidity: %3.1f %%' %hum)
            await asyncio.sleep_ms(10000)
    except OSError as e:
        print('Failed to read sensor.')


# Run both tasks.
async def main():
    t1 = asyncio.create_task(peripheral_task())
#    t2 = asyncio.create_task(only_sensor_task())
#    t2 = asyncio.create_task(sensor_task())
#    t3 = asyncio.create_task(timer_task())
#    t4 = asyncio.create_task(disk_task())
    await asyncio.gather(t1)


asyncio.run(main())


