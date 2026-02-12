# PR for webasto_unite_modbus: Add Device Registration

## Summary
This PR adds `device_info` to all entity types (sensor, number, switch) to properly register the Webasto Unite charger as a device in Home Assistant's device registry. This is required for the charger to appear in device selectors, particularly in the EVSE Load Balancer integration setup.

## Changes
- Added `DeviceInfo` import to `sensor.py`, `number.py`, and `switch.py`
- Added `device_info` attribute initialization in all entity `__init__` methods
- Device info includes:
  - **Identifiers**: `(DOMAIN, serial_number)` using the unique serial from register 100
  - **Name**: `"{brand} {model}"` from registers 190 and 210
  - **Manufacturer**: Brand value from register 190 (typically "Webasto")
  - **Model**: Model value from register 210 (typically "Unite")
  - **Software Version**: Firmware version from register 230

## Why This Change Is Needed
Without `device_info`, the integration creates entities but no device entry in Home Assistant's device registry. This prevents:
- Device appearing in device selectors during integration setup
- Integration with other home automation integrations that expect a device (like EVSE Load Balancer)
- Proper organization of entities under a single device in the UI
- Device-level automation triggers and conditions

## Testing
After applying this change:
1. Set up the webasto_unite_modbus integration with a Webasto Unite charger
2. Navigate to Settings > Devices & Services > Devices
3. Verify that a device named "Webasto Unite" (or similar based on actual brand/model) appears
4. Verify all entities are grouped under this device
5. In EVSE Load Balancer setup, verify the charger appears in the device selector

## Compatibility
- No breaking changes to existing functionality
- All existing entity behaviors remain unchanged
- Device identifiers use serial number which is unique per physical charger

## Related Issues
- Enables Webasto Unite support in matkvaid/hass-evse-load-balancer
- Follows Home Assistant best practices for device registry integration

## Branch
`feature/add-device-registration`

## Files Changed
- `custom_components/webasto_unite_modbus/sensor.py`
- `custom_components/webasto_unite_modbus/number.py`
- `custom_components/webasto_unite_modbus/switch.py`
