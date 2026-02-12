# Webasto Unite Device Registration

## Issue

For Webasto Unite chargers to appear in the EVSE Load Balancer setup device selector, the `webasto_unite_modbus` integration must properly register devices in Home Assistant's device registry.

## Root Cause

Currently, the `webasto_unite_modbus` integration (v0.1.0) does not define `device_info` on its entities, which means no device is registered in Home Assistant's device registry. Without a registered device, the charger cannot be selected during EVSE Load Balancer setup.

## Required Changes in webasto_unite_modbus

The following changes are required in the `matkvaid/webasto_unite_modbus` repository:

### 1. Add device_info to sensor.py

Add the `DeviceInfo` import and update the `WebastoUniteSensor.__init__` method:

```python
from homeassistant.helpers.entity import DeviceInfo

# In WebastoUniteSensor.__init__:
serial = coordinator.data.get("serial_number", coordinator.entry.entry_id)
brand = coordinator.data.get("brand", "Webasto")
model = coordinator.data.get("model", "Unite")

self._attr_device_info = DeviceInfo(
    identifiers={(DOMAIN, serial)},
    name=f"{brand} {model}",
    manufacturer=brand,
    model=model,
    sw_version=coordinator.data.get("firmware_version"),
)
```

### 2. Add device_info to number.py

Same pattern as sensor.py - add `DeviceInfo` import and update `WebastoUniteNumber.__init__`.

### 3. Add device_info to switch.py

Same pattern - add `DeviceInfo` import and update `WebastoUniteAliveSwitch.__init__`.

## Device Identification

Based on the Webasto Unite Modbus specification, the device exposes the following identification registers:

- **Register 100**: Serial Number (string, 25 chars)
- **Register 130**: Charge Point ID (string, 50 chars)
- **Register 190**: Brand/Manufacturer (string, 10 chars)
- **Register 210**: Model (string, 5 chars)
- **Register 230**: Firmware Version (string, 50 chars)

The device_info uses:
- **Identifiers**: `(DOMAIN, serial_number)` - where DOMAIN is `"webasto_unite_modbus"`
- **Manufacturer**: Value from register 190 (typically "Webasto")
- **Model**: Value from register 210 (typically "Unite")
- **Name**: `"{brand} {model}"` (e.g., "Webasto Unite")
- **Software Version**: Value from register 230

## Verification

Once these changes are implemented in webasto_unite_modbus:

1. The integration will register a device with identifier domain `"webasto_unite_modbus"`
2. The EVSE Load Balancer's detection logic in `webasto_unite_charger.py` will correctly identify the device
3. The device will appear in the charger selection dropdown during setup

## Current Status

The EVSE Load Balancer integration already has:
- ✅ Webasto Unite charger implementation (`webasto_unite_charger.py`)
- ✅ Detection logic that checks for `CHARGER_DOMAIN_WEBASTO_UNITE` ("webasto_unite_modbus")
- ✅ Device filter in config_flow.py (`{"integration": "webasto_unite_modbus"}`)
- ✅ Full charger control implementation with Modbus entities
- ✅ Documentation in README.md

What's needed:
- ⚠️ The webasto_unite_modbus integration needs device_info implementation (see above)

## Implementation Plan

1. Open a PR in the `matkvaid/webasto_unite_modbus` repository with the device_info changes
2. Once merged and released, update the minimum version requirement in the README
3. Test the full flow: Install webasto_unite_modbus → Set up device → Select in EVSE Load Balancer setup
