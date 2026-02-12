# Webasto Unite Setup List Integration - Summary

## Problem Statement
The Webasto Unite charger needs to appear in the EVSE Load Balancer setup device selector list, using the matkvaid/webasto_unite_modbus integration as the source of truth for device identification.

## Root Cause Analysis
The webasto_unite_modbus integration (v0.1.0) does not define `device_info` on its entities. Without `device_info`, Home Assistant does not register a device in the device registry. Without a registered device, there is nothing to select in the EVSE Load Balancer setup flow.

## Solution
Add `device_info` to all entity types in the webasto_unite_modbus integration, using the Modbus-exposed device identification registers as the source of truth.

## Implementation Status

### hass-evse-load-balancer Repository ✅ COMPLETE
The hass-evse-load-balancer repository already has everything needed:

1. **Charger Implementation** ✅
   - File: `custom_components/evse_load_balancer/chargers/webasto_unite_charger.py`
   - Fully implements the Charger interface
   - Correctly maps to Webasto Unite Modbus entities

2. **Detection Logic** ✅
   - Method: `WebastoUniteCharger.is_charger_device()`
   - Checks for identifier domain `"webasto_unite_modbus"`
   - Will work correctly once webasto_unite_modbus registers devices

3. **Config Flow Filter** ✅
   - File: `custom_components/evse_load_balancer/config_flow.py`
   - Device filter includes: `{"integration": "webasto_unite_modbus"}`
   - Will show Webasto Unite devices once they are registered

4. **Registration** ✅
   - File: `custom_components/evse_load_balancer/chargers/__init__.py`
   - WebastoUniteCharger is in the charger factory list
   - Properly imported and exported

5. **Documentation** ✅
   - README.md lists Webasto Unite with link to matkvaid/webasto_unite_modbus
   - Version requirement specified as v0.1.0+

### webasto_unite_modbus Repository ⚠️ NEEDS UPDATE
The webasto_unite_modbus integration needs `device_info` added to entities:

**Required Changes:**
1. Add `DeviceInfo` import to sensor.py, number.py, switch.py
2. Add device_info initialization in each entity's `__init__` method
3. Use Modbus register data as source of truth:
   - Serial Number (register 100) → identifier
   - Brand (register 190) → manufacturer
   - Model (register 210) → model
   - Firmware Version (register 230) → sw_version

**Files to Modify:**
- `custom_components/webasto_unite_modbus/sensor.py`
- `custom_components/webasto_unite_modbus/number.py`
- `custom_components/webasto_unite_modbus/switch.py`

**Patch File:** `patches/webasto_unite_modbus_device_info.patch`

## Device Identification (Source of Truth)

Based on the Webasto Unite Modbus specification in matkvaid/webasto_unite_modbus:

| Register | Data Type | Key | Description | Usage |
|----------|-----------|-----|-------------|-------|
| 100 | string(25) | serial_number | Unique serial number | Device identifier |
| 190 | string(10) | brand | Manufacturer name | Device manufacturer |
| 210 | string(5) | model | Model designation | Device model |
| 230 | string(50) | firmware_version | Firmware version | Software version |

The device_info structure:
```python
DeviceInfo(
    identifiers={(DOMAIN, serial_number)},
    name=f"{brand} {model}",
    manufacturer=brand,
    model=model,
    sw_version=firmware_version,
)
```

Where `DOMAIN = "webasto_unite_modbus"`

## Testing Plan

Once webasto_unite_modbus is updated:

1. **Install webasto_unite_modbus** (updated version)
   - Set up the integration with a Webasto Unite charger
   - Verify device appears in Settings > Devices & Services > Devices

2. **Install EVSE Load Balancer**
   - Navigate to Settings > Devices & Services > Add Integration
   - Search for "EVSE Load Balancer"
   - Click "Add"

3. **Verify Device Selection**
   - In the setup flow, click the charger device selector
   - Verify "Webasto Unite" (or actual brand/model) appears in the list
   - Select the device

4. **Complete Setup**
   - Configure fuse size and phase count
   - Complete the setup
   - Verify the integration loads correctly

5. **Verify Operation**
   - Check that current limits can be set
   - Verify charger status is detected correctly
   - Test load balancing functionality

## Next Steps

1. **Create PR for webasto_unite_modbus**
   - Branch: `feature/add-device-registration` (already prepared in /tmp/webasto_unite_modbus)
   - Apply patch: `patches/webasto_unite_modbus_device_info.patch`
   - Submit PR to matkvaid/webasto_unite_modbus

2. **Wait for Merge and Release**
   - Once merged, wait for new version release (e.g., v0.2.0)

3. **Update Documentation** (if needed)
   - Update minimum version in README.md if changed

4. **Test Integration**
   - Perform full integration testing as described above

## Files in This Repository

- **WEBASTO_UNITE_DEVICE_REGISTRATION.md** - Detailed technical documentation
- **PR_FOR_WEBASTO_UNITE_MODBUS.md** - PR description for webasto_unite_modbus
- **patches/webasto_unite_modbus_device_info.patch** - Ready-to-apply patch file
- **IMPLEMENTATION_SUMMARY.md** - This file

## Conclusion

The hass-evse-load-balancer repository is fully ready for Webasto Unite integration. The only missing piece is device registration in the webasto_unite_modbus integration. Once that PR is merged and released, Webasto Unite will automatically appear in the EVSE Load Balancer setup list without any changes needed to hass-evse-load-balancer.
