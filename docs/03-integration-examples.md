# Part 3: Integration Examples - Making It Work for Your Home

*Part 3 of 3: Configuration & Real-World Results*

> **This document shows how to integrate the cutoff optimizer with YOUR specific loads.**  
> **→ [Discuss on Home Assistant Community](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741/3)**

---

## Introduction

In [Part 1](./01-theory.md) we covered the theory, and [Part 2](./02-cutoff-optimizer.md) provided the Python implementation. Now it's time to **integrate the optimizer with YOUR system**.

This part covers:
- ✅ Quick installation checklist
- ✅ Parameter calibration for YOUR building
- ✅ HVAC integration example (complete working system)
- ✅ Water heater integration example
- ✅ Creating automations for your loads
- ✅ Dashboard examples
- ✅ Troubleshooting and optimization

---

## Installation Checklist

Follow these steps in order:

### ☑️ Phase 1: Prerequisites

- [ ] Home Assistant 2024.10+ installed
- [ ] [Nordpool HACS integration](https://github.com/custom-components/nordpool) installed
- [ ] 15-minute data enabled in Nordpool integration settings
- [ ] Verify `sensor.nordpool_kwh_fi_eur_3_10_0` exists and shows `raw_today` with 96 slots (or 24 if 1h data)
- [ ] Python Scripts integration enabled in `configuration.yaml`:
```

python_script:

```

### ☑️ Phase 2: Install Optimizer

- [ ] Download `nordpool_cutoff_optimizer.py` from [GitHub repo](https://github.com/nikopaulanne/nordpool-spot-cutoff-optimizer)
- [ ] Copy to `/config/python_scripts/nordpool_cutoff_optimizer.py`
- [ ] Add `input_number` entities (see Part 2)
- [ ] Restart Home Assistant
- [ ] Verify script runs: Check Developer Tools → Services → `python_script.nordpool_cutoff_optimizer`

### ☑️ Phase 3: Add Template Sensors

- [ ] Add `sensor.cutoff_current_phase` template (see Part 2)
- [ ] Restart Home Assistant
- [ ] Verify sensor exists in Developer Tools → States

### ☑️ Phase 4: Create Automation

- [ ] Add automation to run optimizer every 15 minutes (see Part 2)
- [ ] Verify automation triggers
- [ ] Check `sensor.nordpool_cutoff_periods_python` has data

### ☑️ Phase 5: Test Without Load Control

- [ ] Monitor `sensor.cutoff_current_phase` throughout the day
- [ ] Verify cutoffs occur during expensive hours
- [ ] Check logs for errors

**Only proceed to Phase 6 after verifying the optimizer works correctly!**

### ☑️ Phase 6: Implement Load Control

- [ ] Create automations for YOUR specific loads (see examples below)
- [ ] Test in dry-run mode first (log actions, don't control loads)
- [ ] Monitor for 24-48 hours
- [ ] Enable full control when confident

---

## Parameter Calibration

The optimizer needs parameters calibrated for YOUR specific building and system.

### Key Parameters to Calibrate

| Parameter | Purpose | How to Calibrate |
|-----------|---------|------------------|
| `base_price_diff` | Minimum price difference to trigger cutoff | Start with 3.5 c/kWh, adjust based on results |
| `max_cutoff_duration` | Maximum cutoff length | Start with 4h, reduce if temperature drops too much |
| `preheat_multiplier` | Cost of preheating | 1.5 for poor insulation, 1.3 for well-insulated |
| `recovery_multiplier` | Cost of recovery | 1.2 typical, 1.1 for good thermal mass |
| `residual_load` | Load during cutoff | 0.1 for fan-only, 0.05 for complete off |

### Calibration Method 1: Historical Data Analysis

**If you have 1-2 months of data:**

1. Note your average heating consumption during different outdoor temperatures
2. Identify expensive price days where cutoff would have occurred
3. Estimate savings based on actual consumption patterns
4. Adjust `base_price_diff` so optimizer finds 2-3 cutoffs per week

**Example:**
- Your heating: 5 kWh/hour at 0°C outdoor temp
- Average price: 5 c/kWh
- Peak price: 15 c/kWh
- Price difference: 10 c/kWh → Should trigger cutoff
- If no cutoff → Lower `base_price_diff` to 2.5 c/kWh

### Calibration Method 2: A/B Testing

**Start conservative, iterate:**

1. **Week 1:** Set `base_price_diff` = 5.0 c/kWh (few cutoffs)
 - Monitor temperature impact
 - Check savings
 
2. **Week 2:** Lower to 3.5 c/kWh (more cutoffs)
 - Compare comfort vs Week 1
 - Check savings increase
 
3. **Week 3:** Lower to 2.5 c/kWh (many cutoffs)
 - If temperature drops >1°C → Too aggressive
 - If comfort OK → Keep this setting

**Rule of thumb:** If cutoffs cause >1°C temperature drop, increase `base_price_diff` or reduce `max_cutoff_duration`.

---

## Example 1: HVAC System Integration

This example shows a **real working system** with:
- 2× air-source heat pumps (primary heating)
- Hydronic radiator heating (backup)
- Weather-adaptive control

### Architecture

```

sensor.cutoff_current_phase
↓
┌────┴────┐
│         │
preheat   shutdown   recovery
│         │         │
↓         ↓         ↓
[Heat]   [Fan Only]  [Heat]
+Rads     +Rads Min   +Rads

```

### Template Sensors for HVAC

```

template:

- sensor:

# Current cutoff phase

    - name: "Cutoff Current Phase"
unique_id: cutoff_current_phase
state: >
{% set periods = state_attr('sensor.nordpool_cutoff_periods_python', 'periods') %}
{% if not periods %}
normal
{% else %}
{% set now_ts = now().timestamp() %}
{% set ns = namespace(phase='normal') %}
{% for period in periods %}
{% set preheat_ts = as_timestamp(period.preheat_start) %}
{% set shutdown_ts = as_timestamp(period.shutdown_start) %}
{% set shutdown_end_ts = as_timestamp(period.shutdown_end) %}
{% set recovery_end_ts = as_timestamp(period.recovery_end) %}

      {% if now_ts >= preheat_ts and now_ts < shutdown_ts %}
        {% set ns.phase = 'preheat' %}
      {% elif now_ts >= shutdown_ts and now_ts < shutdown_end_ts %}
        {% set ns.phase = 'shutdown' %}
      {% elif now_ts >= shutdown_end_ts and now_ts < recovery_end_ts %}
        {% set ns.phase = 'recovery' %}
      {% endif %}
    {% endfor %}
    {{ ns.phase }}
    {% endif %}


# Next cutoff info (for dashboard)

    - name: "Next Cutoff Time"
unique_id: next_cutoff_time
state: >
{% set periods = state_attr('sensor.nordpool_cutoff_periods_python', 'periods') %}
{% if periods %}
{% set now_ts = now().timestamp() %}
{% set future = periods | selectattr('shutdown_start', '>', now().isoformat()) | list %}
{% if future %}
{{ as_timestamp(future.shutdown_start) | timestamp_custom('%H:%M') }}
{% else %}
No cutoff scheduled
{% endif %}
{% else %}
No data
{% endif %}
attributes:
duration: >
{% set periods = state_attr('sensor.nordpool_cutoff_periods_python', 'periods') %}
{% if periods %}
{% set future = periods | selectattr('shutdown_start', '>', now().isoformat()) | list %}
{% if future %}
{{ future.cutoff_duration_hours }} hours
{% endif %}
{% endif %}
estimated_savings: >
{% set periods = state_attr('sensor.nordpool_cutoff_periods_python', 'periods') %}
{% if periods %}
{% set future = periods | selectattr('shutdown_start', '>', now().isoformat()) | list %}
{% if future %}
{{ future.savings_pct }}%
{% endif %}
{% endif %}

```

### Automations for HVAC Control

**Automation 1: Preheat Phase**

```

automation:

- alias: "Cutoff - HVAC Preheat"
description: "Increase heating 1°C before cutoff period"
trigger:
    - platform: state
entity_id: sensor.cutoff_current_phase
to: "preheat"
action:


# Heat pumps: Increase target temperature

    - service: climate.set_temperature
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
temperature: >
{{ state_attr('climate.heat_pump_1', 'temperature') | float(21) + 1 }}


# Radiators: Increase target temperature

    - service: number.set_value
target:
entity_id: number.radiator_target_temp
data:
value: >
{{ states('number.radiator_target_temp') | float(20) + 2 }}


# Optional: Increase fan speed

    - service: climate.set_fan_mode
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
fan_mode: "high"

```

**Automation 2: Shutdown Phase**

```

- alias: "Cutoff - HVAC Shutdown"
description: "Reduce heating during expensive period"
trigger:
    - platform: state
entity_id: sensor.cutoff_current_phase
to: "shutdown"
action:


# Heat pumps: Switch to fan-only mode

    - service: climate.set_hvac_mode
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
hvac_mode: "fan_only"


# Keep fan running for air circulation

    - service: climate.set_fan_mode
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
fan_mode: "high"


# Radiators: Set to minimum

    - service: number.set_value
target:
entity_id: number.radiator_target_temp
data:
value: 15  \# Minimum safe temperature

```

**Automation 3: Recovery Phase**

```

- alias: "Cutoff - HVAC Recovery"
description: "Return to normal heating after cutoff"
trigger:
    - platform: state
entity_id: sensor.cutoff_current_phase
to: "recovery"
action:


# Heat pumps: Return to heating mode

    - service: climate.set_hvac_mode
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
hvac_mode: "heat"


# Heat pumps: Normal target temperature

    - service: climate.set_temperature
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
temperature: 21  \# Your normal setpoint


# Radiators: Return to normal

    - service: number.set_value
target:
entity_id: number.radiator_target_temp
data:
value: 20  \# Your normal radiator temp


# Fan: Return to normal speed

    - service: climate.set_fan_mode
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
fan_mode: "auto"

```

**Automation 4: Return to Normal**

```

- alias: "Cutoff - HVAC Normal"
description: "Ensure normal operation after recovery"
trigger:
    - platform: state
entity_id: sensor.cutoff_current_phase
to: "normal"
action:


# Same as recovery, but ensures everything is reset

    - service: climate.set_hvac_mode
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
hvac_mode: "heat"
    - service: climate.set_temperature
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
temperature: 21

```

### Safety Overrides

**Important:** Always include safety overrides!

```

automation:

- alias: "Cutoff - Safety Override Cold"
description: "Cancel cutoff if too cold"
trigger:
    - platform: numeric_state
entity_id: sensor.indoor_temperature
below: 19  \# Your minimum comfort threshold
condition:
    - condition: state
entity_id: sensor.cutoff_current_phase
state: "shutdown"
action:


# Force return to heating

    - service: climate.set_hvac_mode
target:
entity_id:
- climate.heat_pump_1
- climate.heat_pump_2
data:
hvac_mode: "heat"


# Send notification

    - service: notify.mobile_app
data:
title: "Cutoff Override"
message: "Indoor temp too low, heating restored"

```

---

## Example 2: Water Heater Integration

**Simpler system:** Water tank acts as thermal storage.

### Template Sensors

```

template:

- sensor:
    - name: "Water Heater Cutoff Phase"
unique_id: water_heater_cutoff_phase
state: >
{% set periods = state_attr('sensor.nordpool_cutoff_periods_python', 'periods') %}
{% if not periods %}
normal
{% else %}
{% set now_ts = now().timestamp() %}
{% set ns = namespace(phase='normal') %}
{% for period in periods %}
{% set preheat_ts = as_timestamp(period.preheat_start) %}
{% set shutdown_ts = as_timestamp(period.shutdown_start) %}
{% set shutdown_end_ts = as_timestamp(period.shutdown_end) %}

      {% if now_ts >= preheat_ts and now_ts < shutdown_ts %}
        {% set ns.phase = 'preheat' %}
      {% elif now_ts >= shutdown_ts and now_ts < shutdown_end_ts %}
        {% set ns.phase = 'shutdown' %}
      {% endif %}
    {% endfor %}
    {{ ns.phase }}
    {% endif %}

```

### Automations

```

automation:

- alias: "Water Heater - Preheat"
trigger:
    - platform: state
entity_id: sensor.water_heater_cutoff_phase
to: "preheat"
action:


# Increase water temp by 5°C

    - service: water_heater.set_temperature
target:
entity_id: water_heater.main
data:
temperature: >
{{ state_attr('water_heater.main', 'temperature') | float(60) + 5 }}
- alias: "Water Heater - Shutdown"
trigger:
    - platform: state
entity_id: sensor.water_heater_cutoff_phase
to: "shutdown"
action:


# Turn off water heater

    - service: water_heater.turn_off
target:
entity_id: water_heater.main
- alias: "Water Heater - Return to Normal"
trigger:
    - platform: state
entity_id: sensor.water_heater_cutoff_phase
to: "normal"
action:


# Return to normal temperature

    - service: water_heater.set_temperature
target:
entity_id: water_heater.main
data:
temperature: 60  \# Normal setpoint

```

---

## Dashboard Example

Create a cutoff monitoring dashboard:

```

type: vertical-stack
cards:

- type: markdown
content: |

# Nordpool Cutoff Optimizer

**Current Phase:** {{ states('sensor.cutoff_current_phase') | title }}

**Next Cutoff:** {{ states('sensor.next_cutoff_time') }}
**Duration:** {{ state_attr('sensor.next_cutoff_time', 'duration') }}
**Est. Savings:** {{ state_attr('sensor.next_cutoff_time', 'estimated_savings') }}
- type: entities
title: Optimizer Parameters
entities:
    - entity: input_number.cutoff_base_price_diff
    - entity: input_number.cutoff_max_duration
    - entity: input_number.cutoff_min_savings_pct
- type: history-graph
title: Temperature During Cutoffs
entities:
    - entity: sensor.indoor_temperature
    - entity: sensor.cutoff_current_phase
hours_to_show: 24
- type: custom:apexcharts-card
title: Nordpool Prices with Cutoffs
graph_span: 48h
header:
show: true
series:
    - entity: sensor.nordpool_kwh_fi_eur_3_10_0
name: Electricity Price
type: line
color: blue
    - entity: sensor.cutoff_current_phase
name: Cutoff Phase
type: column
transform: |
return x === 'shutdown' ? 1 : 0;
color: red

```

---

## Troubleshooting

### Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| No cutoffs detected | Price threshold too high | Lower `base_price_diff` to 2.5 c/kWh |
| Too many cutoffs | Threshold too low | Increase `base_price_diff` to 4.0 c/kWh |
| Temperature drops >1°C | Cutoff too long | Reduce `max_cutoff_duration` to 3h |
| Recovery takes too long | Poor thermal mass | Increase `recovery_multiplier` to 1.3 |
| Script errors | Missing sensor | Check Nordpool sensor exists |

### Debug Mode

Enable detailed logging:

```

logger:
default: info
logs:
homeassistant.components.python_script: debug
homeassistant.components.automation: debug

```

---

## Expected Results

Results vary significantly based on your specific setup:

### Factors Affecting Performance

| Factor | Impact on Results |
|--------|-------------------|
| **Building insulation** | Better insulation = longer cutoffs possible |
| **Thermal mass** | High mass (concrete) = better energy storage |
| **Heat pump efficiency** | Higher SCOP = more cost-effective |
| **Outdoor temperature** | Extreme temps require shorter cutoffs |
| **Price volatility** | Higher peaks = better savings potential |
| **Backup heating** | Multiple heat sources = more flexibility |

### What to Monitor

Track these metrics during your testing period:

**Temperature metrics:**
- Indoor temperature during cutoffs (target: < 1°C drop)
- Recovery time to normal temperature
- Temperature variation between rooms

**Energy metrics:**
- Total electricity consumption before/after
- Peak hour consumption reduction
- Actual savings vs estimated savings

**Comfort metrics:**
- Perceived comfort level (subjective)
- Cold spot occurrence
- Recovery comfort (overheating?)

### Typical Results Range

Based on system design theory and building thermodynamics:

- **Savings on cutoff days:** 10-35% of peak hour costs
- **Temperature impact:** 0.3-1.0°C drop during cutoff
- **Optimal cutoff duration:** 2-4 hours depending on weather
- **Recovery time:** Equal to cutoff duration

**Your mileage WILL vary!** Start conservative and iterate based on real data.

### Community Results

*We encourage users to share their results in the [Home Assistant Community forum](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741/3).*

**Consider sharing:**
- Building type and insulation level
- Heat pump model and SCOP
- Outdoor temperature range
- Cutoff duration and frequency
- Actual savings percentage
- Temperature impact

**Future enhancement:** We may create a collaborative data analysis project to build calibration guidelines based on community-submitted data including weather forecast integration.

---

## Next Steps

1. ✅ Complete installation checklist
2. ✅ Calibrate parameters for YOUR building
3. ✅ Test for 1 week in monitoring mode
4. ✅ Enable full automation
5. ✅ Fine-tune based on results
6. ✅ Share your results in the community!

---

## Contributing Your Example

If you've successfully integrated this with a different system, please share!

**Submit to GitHub:**
- Fork the repository
- Create `examples/your_system/`
- Include README, configuration, and results
- Submit Pull Request

**Discuss in Community:**
- Share your setup in the [forum thread](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741/3)
- Help others with questions
- Improve the documentation

---

## Summary

- The optimizer is **generic** - you adapt it to YOUR loads
- Start with **conservative parameters** and iterate
- **Monitor temperature** during cutoffs
- Always include **safety overrides**
- **Test thoroughly** before full automation
- **Share your results** to help others

---

*Questions? Discuss in the [Home Assistant Community thread](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741/3)*


