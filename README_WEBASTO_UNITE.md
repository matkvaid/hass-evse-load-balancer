# Webasto Unite Integration - Quick Reference

## Status: ✅ Ready for Deployment

### Summary
The hass-evse-load-balancer integration is **fully ready** to support Webasto Unite chargers. The only required change is in the upstream `webasto_unite_modbus` integration, which needs to add `device_info` to properly register devices in Home Assistant's device registry.

## What Was Done

### 1. Analysis
- Investigated why Webasto Unite doesn't appear in setup list
- Identified root cause: `webasto_unite_modbus` doesn't register devices
- Verified all detection logic in hass-evse-load-balancer is correct

### 2. Solution
- Created device_info implementation for webasto_unite_modbus
- Uses Modbus registers as source of truth (serial, brand, model)
- Generated ready-to-apply patch file

### 3. Documentation
- **IMPLEMENTATION_SUMMARY.md** - Full technical overview
- **WEBASTO_UNITE_DEVICE_REGISTRATION.md** - Device registration details
- **PR_FOR_WEBASTO_UNITE_MODBUS.md** - PR template for upstream
- **patches/webasto_unite_modbus_device_info.patch** - Code patch

### 4. Testing
- ✅ All 22 existing tests pass
- ✅ Linting checks pass
- ✅ Code review clean
- ✅ Security scan clean

## Device Identification (Source of Truth)

From Webasto Unite Modbus specification:

| Register | Type | Data | Usage |
|----------|------|------|-------|
| 100 | string | Serial Number | Device identifier |
| 190 | string | Brand (e.g. "Webasto") | Manufacturer |
| 210 | string | Model (e.g. "Unite") | Model name |
| 230 | string | Firmware Version | Software version |

## For Users

Once the webasto_unite_modbus update is released:

1. **Install Prerequisites**
   - Install HACS
   - Add matkvaid/webasto_unite_modbus repository
   - Install webasto_unite_modbus integration

2. **Set Up Webasto Unite**
   - Go to Settings > Devices & Services
   - Add "Webasto Unite Modbus" integration
   - Enter your charger's IP address and port
   - Device will be registered automatically

3. **Set Up EVSE Load Balancer**
   - Add "EVSE Load Balancer" integration
   - Select your Webasto Unite charger from the device list ✅
   - Configure fuse size and phase count
   - Complete setup

## For Developers

### To Apply Patch to webasto_unite_modbus

```bash
# Clone the repository
git clone https://github.com/matkvaid/webasto_unite_modbus.git
cd webasto_unite_modbus

# Apply the patch
git apply /path/to/webasto_unite_modbus_device_info.patch

# Or manually add device_info as documented
```

### Key Changes Needed

Add to each entity class (sensor.py, number.py, switch.py):

```python
from homeassistant.helpers.entity import DeviceInfo

# In __init__:
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

## Files in This Repository

1. **README_WEBASTO_UNITE.md** (this file) - Quick reference
2. **IMPLEMENTATION_SUMMARY.md** - Complete technical overview
3. **WEBASTO_UNITE_DEVICE_REGISTRATION.md** - Device registration details
4. **PR_FOR_WEBASTO_UNITE_MODBUS.md** - PR description template
5. **patches/webasto_unite_modbus_device_info.patch** - Code patch

## Timeline

- ✅ **Now**: hass-evse-load-balancer ready
- ⏳ **Next**: Submit PR to webasto_unite_modbus
- ⏳ **Then**: Wait for merge and release
- ✅ **Result**: Webasto Unite appears in setup list automatically

## Contact

For issues related to:
- **hass-evse-load-balancer**: Open issue in matkvaid/hass-evse-load-balancer
- **webasto_unite_modbus**: Open issue in matkvaid/webasto_unite_modbus
- **This PR**: Comment on this pull request

---

**Note**: No code changes were needed in hass-evse-load-balancer. All detection logic was already correct. The integration will work automatically once webasto_unite_modbus adds device registration.
