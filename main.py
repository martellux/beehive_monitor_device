import sys
sys.path.append("")
from micropython import const
import uasyncio as asyncio
import bluetooth
import time
import random
import struct
import os
from machine import Pin
import dht
import esp

# IRQ events code
from micropython import const
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_GATTS_READ_REQUEST = const(4)
_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_IRQ_GATTC_SERVICE_RESULT = const(9)
_IRQ_GATTC_SERVICE_DONE = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
_IRQ_GATTC_DESCRIPTOR_RESULT = const(13)
_IRQ_GATTC_DESCRIPTOR_DONE = const(14)
_IRQ_GATTC_READ_RESULT = const(15)
_IRQ_GATTC_READ_DONE = const(16)
_IRQ_GATTC_WRITE_DONE = const(17)
_IRQ_GATTC_NOTIFY = const(18)
_IRQ_GATTC_INDICATE = const(19)
_IRQ_GATTS_INDICATE_DONE = const(20)
_IRQ_MTU_EXCHANGED = const(21)
_IRQ_L2CAP_ACCEPT = const(22)
_IRQ_L2CAP_CONNECT = const(23)
_IRQ_L2CAP_DISCONNECT = const(24)
_IRQ_L2CAP_RECV = const(25)
_IRQ_L2CAP_SEND_READY = const(26)
_IRQ_CONNECTION_UPDATE = const(27)
_IRQ_ENCRYPTION_UPDATE = const(28)
_IRQ_GET_SECRET = const(29)
_IRQ_SET_SECRET = const(30)

# For the _IRQ_GATTS_READ_REQUEST event, the available return codes are: 
_GATTS_NO_ERROR = const(0x00)
_GATTS_ERROR_READ_NOT_PERMITTED = const(0x02)
_GATTS_ERROR_WRITE_NOT_PERMITTED = const(0x03)
_GATTS_ERROR_INSUFFICIENT_AUTHENTICATION = const(0x05)
_GATTS_ERROR_INSUFFICIENT_AUTHORIZATION = const(0x08)
_GATTS_ERROR_INSUFFICIENT_ENCRYPTION = const(0x0f)

#For the _IRQ_PASSKEY_ACTION event, the available actions are: 
_PASSKEY_ACTION_NONE = const(0)
_PASSKEY_ACTION_INPUT = const(2)
_PASSKEY_ACTION_DISPLAY = const(3)
_PASSKEY_ACTION_NUMERIC_COMPARISON = const(4)

# ADV PACKET
_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID32_COMPLETE = const(0x5)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_UUID16_MORE = const(0x2)
_ADV_TYPE_UUID32_MORE = const(0x4)
_ADV_TYPE_UUID128_MORE = const(0x6)
_ADV_TYPE_APPEARANCE = const(0x19)
_ADV_TYPE_MANUFACTURER = const(0xFF)
_ADV_PAYLOAD_MAX_LEN = const(31)

# org.bluetooth.service.environmental_sensing
ENV_SENSE_UUID = bluetooth.UUID(0x181A)
# org.bluetooth.characteristic.digitalinput
OP_INPUT_UUID = bluetooth.UUID(0x2A56)
# org.bluetooth.characteristic.digitaloutput
OP_OUTPUT_UUID = bluetooth.UUID(0x2A57)
# org.bluetooth.characteristic.gap.appearance.xml
ADV_APPEARANCE_GENERIC_THERMOMETER = const(768)

# How frequently to send advertising beacons.
ADV_INTERVAL_MS = 250_000

# operational reference
OP_INPUT = (OP_INPUT_UUID, bluetooth.FLAG_WRITE,)
OP_OUTPUT = (OP_OUTPUT_UUID, bluetooth.FLAG_NOTIFY,)

SENSE_SERVICE = (ENV_SENSE_UUID, (OP_INPUT,OP_OUTPUT,),)
BLE_SERVICES = (SENSE_SERVICE,)


_incoming_connection = None
_connect_event = None



class DeviceConnection:
    # Global map of connection handle to active devices (for IRQ mapping).
    _connected = {}
    
    def __init__(self):
        self._conn_handle = None
        self._disconnection_event = None
        self._task = None
    
    
    async def device_connection_task(self):
        # task to launch during device connection
        assert self._conn_handle is not None
        # wait for client to disconnect
        await self._disconnection_event.wait()
        
        # client disconnected, then clean up
        del DeviceConnection._connected[self._conn_handle]
        self._conn_handle = None
        self._task = None
        # device task will finish itself


    def run_connection(self):
        # Event will be already created this if we initiated connection.
        self._disconnection_event = self._disconnection_event or asyncio.ThreadSafeFlag()
        self._task = asyncio.create_task(self.device_connection_task())
        
        
    def is_connected(self):
        return self._conn_handle is not None
    
    
    async def disconnect(self):
        await self.disconnected()
    
    
    async def disconnected(self):
        if not self.is_connected():
            return

        # The task must have been created after successful connection.
        assert self._task
        await self._task
    
    
    # Context manager -- automatically disconnect.
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_traceback):
        await self.disconnect()





class Swarm:
    def __init__(self, ble, sensor):
        self._ble = ble
        self._sensor = sensor
    
    
    def ensure_active(self):
        if not self._ble.active():
            self._ble.active(True)
    
    
    def init_ble(self):
        self._handles = self._ble.gatts_register_services(BLE_SERVICES)
        # handles[0] is the first registered service, then it's OP_SERVICE
        self._handle_input = self._handles[0][0]
        self._handle_output = self._handles[0][1]
        # register BLE event handler
        self._ble.irq(self.bt_irq_handler)


    def read_sensor(self):
        try:
            self._sensor.measure()
            temp = self._sensor.temperature()
            hum = self._sensor.humidity()
            return (temp, hum)
        except OSError as e:
            print("Swarm: Failed to read sensor.")


    def bt_irq_handler(self, event, data):
        global _incoming_connection, _connect_event
        
        if event == _IRQ_CENTRAL_CONNECT:
            # A central has connected to this peripheral.
            print("Swarm: BLE event: _IRQ_CENTRAL_CONNECT")
            conn_handle, addr_type, addr = data

            # Setup device connection for current client
            _incoming_connection = DeviceConnection()
            _incoming_connection._conn_handle = conn_handle
            DeviceConnection._connected[conn_handle] = _incoming_connection
            
            # Signal connection event
            _connect_event.set()
            
        elif event == _IRQ_CENTRAL_DISCONNECT:
            # A central has disconnected from this peripheral.
            print("Swarm: BLE event: _IRQ_CENTRAL_DISCONNECT")
            conn_handle, addr_type, addr = data
            
            if connection := DeviceConnection._connected.get(conn_handle, None):
            # Tell the device_task that it should terminate.
                connection._disconnection_event.set()

        elif event == _IRQ_GATTS_WRITE:
            # A client has written to this characteristic or descriptor.
            print("Swarm: BLE event: _IRQ_GATTS_WRITE")
            conn_handle, attr_handle = data

            input_data = self._ble.gatts_read(self._handle_input)
            if input_data == b'RN':
                print("Swarm: Read environment now...")
                (temp, hum) = self.read_sensor()
                output_data = str(temp) + str("_") + str(hum)
                self._ble.gatts_notify(conn_handle, self._handle_output, output_data)
            
            if input_data == b'RH':
                print("Swarm: Read historical now...")
                output_data = ""
                self._ble.gatts_notify(conn_handle, self._handle_output, output_data)
                
            
        elif event == _IRQ_GATTS_READ_REQUEST:
            # A client has issued a read. Note: this is only supported on STM32.
            # Return a non-zero integer to deny the read (see below), or zero (or None)
            # to accept the read.
            print("Swarm: BLE event: _IRQ_GATTS_READ_REQUEST")
            conn_handle, attr_handle = data
        elif event == _IRQ_SCAN_RESULT:
            # A single scan result.
            print("Swarm: BLE event: _IRQ_SCAN_RESULT")
            addr_type, addr, adv_type, rssi, adv_data = data
        elif event == _IRQ_SCAN_DONE:
            # Scan duration finished or manually stopped.
            print("Swarm: BLE event: _IRQ_SCAN_DONE")
            pass
        elif event == _IRQ_PERIPHERAL_CONNECT:
            # A successful gap_connect().
            print("Swarm: BLE event: _IRQ_PERIPHERAL_CONNECT")
            conn_handle, addr_type, addr = data
        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            # Connected peripheral has disconnected.
            print("Swarm: BLE event: _IRQ_PERIPHERAL_DISCONNECT")
            conn_handle, addr_type, addr = data
        elif event == _IRQ_GATTC_SERVICE_RESULT:
            # Called for each service found by gattc_discover_services().
            print("Swarm: BLE event: _IRQ_GATTC_SERVICE_RESULT")
            conn_handle, start_handle, end_handle, uuid = data
        elif event == _IRQ_GATTC_SERVICE_DONE:
            # Called once service discovery is complete.
            # Note: Status will be zero on success, implementation-specific value otherwise.
            print("Swarm: BLE event: _IRQ_GATTC_SERVICE_DONE")
            conn_handle, status = data
        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            # Called for each characteristic found by gattc_discover_services().
            print("Swarm: BLE event: _IRQ_GATTC_CHARACTERISTIC_RESULT")
            conn_handle, end_handle, value_handle, properties, uuid = data
        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            # Called once service discovery is complete.
            # Note: Status will be zero on success, implementation-specific value otherwise.
            print("Swarm: BLE event: _IRQ_GATTC_CHARACTERISTIC_DONE")
            conn_handle, status = data
        elif event == _IRQ_GATTC_DESCRIPTOR_RESULT:
            # Called for each descriptor found by gattc_discover_descriptors().
            print("Swarm: BLE event: _IRQ_GATTC_DESCRIPTOR_RESULT")
            conn_handle, dsc_handle, uuid = data
        elif event == _IRQ_GATTC_DESCRIPTOR_DONE:
            # Called once service discovery is complete.
            # Note: Status will be zero on success, implementation-specific value otherwise.
            print("Swarm: BLE event: _IRQ_GATTC_DESCRIPTOR_DONE")
            conn_handle, status = data
        elif event == _IRQ_GATTC_READ_RESULT:
            # A gattc_read() has completed.
            print("Swarm: BLE event: _IRQ_GATTC_READ_RESULT")
            conn_handle, value_handle, char_data = data
        elif event == _IRQ_GATTC_READ_DONE:
            # A gattc_read() has completed.
            # Note: The value_handle will be zero on btstack (but present on NimBLE).
            # Note: Status will be zero on success, implementation-specific value otherwise.
            print("Swarm: BLE event: _IRQ_GATTC_READ_DONE")
            conn_handle, value_handle, status = data
        elif event == _IRQ_GATTC_WRITE_DONE:
            # A gattc_write() has completed.
            # Note: The value_handle will be zero on btstack (but present on NimBLE).
            # Note: Status will be zero on success, implementation-specific value otherwise.
            print("Swarm: BLE event: _IRQ_GATTC_WRITE_DONE")
            conn_handle, value_handle, status = data
        elif event == _IRQ_GATTC_NOTIFY:
            # A server has sent a notify request.
            print("Swarm: BLE event: _IRQ_GATTC_NOTIFY")
            conn_handle, value_handle, notify_data = data
        elif event == _IRQ_GATTC_INDICATE:
            # A server has sent an indicate request.
            print("Swarm: BLE event: _IRQ_GATTC_INDICATE")
            conn_handle, value_handle, notify_data = data
        elif event == _IRQ_GATTS_INDICATE_DONE:
            # A client has acknowledged the indication.
            # Note: Status will be zero on successful acknowledgment, implementation-specific value otherwise.
            print("Swarm: BLE event: _IRQ_GATTS_INDICATE_DONE")
            conn_handle, value_handle, status = data
        elif event == _IRQ_MTU_EXCHANGED:
            # ATT MTU exchange complete (either initiated by us or the remote device).
            print("Swarm: BLE event: _IRQ_MTU_EXCHANGED")
            conn_handle, mtu = data
        elif event == _IRQ_L2CAP_ACCEPT:
            # A new channel has been accepted.
            # Return a non-zero integer to reject the connection, or zero (or None) to accept.
            print("Swarm: BLE event: _IRQ_L2CAP_ACCEPT")
            conn_handle, cid, psm, our_mtu, peer_mtu = data
        elif event == _IRQ_L2CAP_CONNECT:
            # A new channel is now connected (either as a result of connecting or accepting).
            print("Swarm: BLE event: _IRQ_L2CAP_CONNECT")
            conn_handle, cid, psm, our_mtu, peer_mtu = data
        elif event == _IRQ_L2CAP_DISCONNECT:
            # Existing channel has disconnected (status is zero), or a connection attempt failed (non-zero status).
            print("Swarm: BLE event: _IRQ_L2CAP_DISCONNECT")
            conn_handle, cid, psm, status = data
        elif event == _IRQ_L2CAP_RECV:
            # New data is available on the channel. Use l2cap_recvinto to read.
            print("Swarm: BLE event: _IRQ_L2CAP_RECV")
            conn_handle, cid = data
        elif event == _IRQ_L2CAP_SEND_READY:
            # A previous l2cap_send that returned False has now completed and the channel is ready to send again.
            # If status is non-zero, then the transmit buffer overflowed and the application should re-send the data.
            print("Swarm: BLE event: _IRQ_L2CAP_SEND_READY")
            conn_handle, cid, status = data
        elif event == _IRQ_CONNECTION_UPDATE:
            # The remote device has updated connection parameters.
            print("Swarm: BLE event: _IRQ_CONNECTION_UPDATE")
            conn_handle, conn_interval, conn_latency, supervision_timeout, status = data
        elif event == _IRQ_ENCRYPTION_UPDATE:
            # The encryption state has changed (likely as a result of pairing or bonding).
            print("Swarm: BLE event: _IRQ_ENCRYPTION_UPDATE")
            conn_handle, encrypted, authenticated, bonded, key_size = data
        elif event == _IRQ_GET_SECRET:
            # Return a stored secret.
            # If key is None, return the index'th value of this sec_type.
            # Otherwise return the corresponding value for this sec_type and key.
            print("Swarm: BLE event: _IRQ_GET_SECRET")
            sec_type, index, key = data
            return value
        elif event == _IRQ_SET_SECRET:
            # Save a secret to the store for this sec_type and key.
            print("Swarm: BLE event: _IRQ_SET_SECRET")
            sec_type, key, value = data
            return True
        elif event == _IRQ_PASSKEY_ACTION:
            # Respond to a passkey request during pairing.
            # See gap_passkey() for details.
            # action will be an action that is compatible with the configured "io" config.
            # passkey will be non-zero if action is "numeric comparison".
            print("Swarm: BLE event: _IRQ_PASSKEY_ACTION")
            conn_handle, action, passkey = data


    # Advertising payloads are repeated packets of the following form:
    #   1 byte data length (N + 1)
    #   1 byte type (see constants below)
    #   N bytes type-specific data
    def _append(self, adv_data, resp_data, adv_type, value):
        data = struct.pack("BB", len(value) + 1, adv_type) + value
        
        if len(data) + len(adv_data) < _ADV_PAYLOAD_MAX_LEN:
            adv_data += data
            return resp_data
        
        if len(data) + (len(resp_data) if resp_data else 0) < _ADV_PAYLOAD_MAX_LEN:
            if not resp_data:
                # Overflow into resp_data for the first time.
                resp_data = bytearray()
            resp_data += data
            return resp_data
        raise ValueError("Advertising payload too long")


    def advertise(
        self,
        interval_us,
        adv_data=None,
        resp_data=None,
        connectable=True,
        limited_disc=False,
        br_edr=False,
        name=None,
        services=None,
        appearance=0,
        manufacturer=None,
        timeout_ms=None,
    ):
        if not adv_data and not resp_data:
            # If the user didn't manually specify adv_data / resp_data then
            # construct them from the kwargs. Keep adding fields to adv_data,
            # overflowing to resp_data if necessary.
            # TODO: Try and do better bin-packing than just concatenating in
            # order?

            adv_data = bytearray()
            resp_data = self._append(
                adv_data,
                resp_data,
                _ADV_TYPE_FLAGS,
                struct.pack("B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)),
            )
            
            # Services are prioritised to go in the advertising data because iOS supports
            # filtering scan results by service only, so services must come first.
            if services:
                for uuid in services:
                    b = bytes(uuid)
                    if len(b) == 2:
                        resp_data = self._append(adv_data, resp_data, _ADV_TYPE_UUID16_COMPLETE, b)
                    elif len(b) == 4:
                        resp_data = self._append(adv_data, resp_data, _ADV_TYPE_UUID32_COMPLETE, b)
                    elif len(b) == 16:
                        resp_data = self._append(adv_data, resp_data, _ADV_TYPE_UUID128_COMPLETE, b)

            if name:
                resp_data = self._append(adv_data, resp_data, _ADV_TYPE_NAME, name)

            if appearance:
                # See org.bluetooth.characteristic.gap.appearance.xml
                resp_data = self._append(
                    adv_data, resp_data, _ADV_TYPE_APPEARANCE, struct.pack("<H", appearance)
                )

            if manufacturer:
                resp_data = self._append(
                    adv_data,
                    resp_data,
                    _ADV_TYPE_MANUFACTURER,
                    struct.pack("<H", manufacturer[0]) + manufacturer[1],
                )

        self._ble.gap_advertise(interval_us, adv_data=adv_data, resp_data=resp_data, connectable=connectable)
        print("Swarm: Advertising...")


    async def wait_for_device(self):
        global _incoming_connection, _connect_event
        
        print("Swarm: Waiting for connection...")
        _connect_event = _connect_event or asyncio.ThreadSafeFlag()
        await _connect_event.wait()

        deviceConnection = _incoming_connection
        _incoming_connection = None
        # Run a task during cliet connection
        deviceConnection.run_connection()
        return deviceConnection



async def peripheral_task():
    sensor = dht.DHT22(Pin(14))
    ble = bluetooth.BLE()
    
    swarm = Swarm(ble, sensor)
    # turn on BLE
    swarm.ensure_active()
    swarm.init_ble()
    while (True):
        swarm.advertise(
            ADV_INTERVAL_MS,
            name="swarm-env-sensor",
            services=[ENV_SENSE_UUID],
            appearance=ADV_APPEARANCE_GENERIC_THERMOMETER,
        )
        async with await swarm.wait_for_device() as deviceConnection:
            await deviceConnection.disconnected()


async def real_sensor_task():
    try:
        sensor = dht.DHT22(Pin(14))
        while True:
            sensor.measure()
            temp = sensor.temperature()
            hum = sensor.humidity()
            print('Temperature: %3.1f C' %temp)
            print('Humidity: %3.1f %%' %hum)
            await asyncio.sleep_ms(10000)
    except OSError as e:
        print("Swarm: Failed to read sensor.")


# Run both tasks.
async def main():
    t1 = asyncio.create_task(peripheral_task())
    #t2 = asyncio.create_task(real_sensor_task())
    await asyncio.gather(t1)

asyncio.run(main())