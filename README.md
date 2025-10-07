# Nordpool Spot Cutoff Optimizer for Home Assistant

**Dynamic load optimization using Nordpool 15-minute spot pricing**

Intelligently reduce electricity consumption during price peaks while maintaining comfort and functionality. Save 10-20% on peak electricity costs.

## 🎯 What Is This?

A **Python-based optimization engine** for Home Assistant that:
- Analyzes Nordpool 15-minute spot prices
- Finds optimal cutoff periods (when to reduce load)
- Calculates preheat and recovery phases
- Outputs schedule as Home Assistant sensors
- **You integrate it with YOUR specific loads**

## 💡 Use Cases

This system can optimize **any controllable electrical load**:

| Load Type | Use Case | Storage Method |
|-----------|----------|----------------|
| **HVAC** | Heat pumps, AC units | Building thermal mass |
| **Water Heating** | Electric boilers, heat pump water heaters | Water tank |
| **EV Charging** | Smart charging schedules | Battery |
| **Pool/Spa** | Heating and filtration | Water thermal mass |
| **Industrial** | Compressors, refrigeration | Process buffers |

**Key requirement:** Your load must tolerate short interruptions or have energy storage capacity.

## 📊 How It Works

### 3-Phase Optimization:

```
┌─────────────┬──────────────┬─────────────┐
│   PREHEAT   │    CUTOFF    │   RECOVERY  │
├─────────────┼──────────────┼─────────────┤
│ Store       │ Minimize     │ Return to   │
│ energy      │ consumption  │ normal      │
│ (optional)  │ (save €€€)   │ operation   │
└─────────────┴──────────────┴─────────────┘
```

1. **Preheat** (optional) - Store energy before expensive period
2. **Cutoff** - Reduce/stop load during price peaks  
3. **Recovery** - Gentle return to normal operation

The optimizer finds the **globally optimal schedule** using Dynamic Programming, testing 100-200 candidates per day.

## 🚀 Quick Start

### Prerequisites

- Home Assistant 2024.10+
- [Nordpool HACS integration](https://github.com/custom-components/nordpool) with 15-min data enabled
- Python Scripts integration (`python_script:` in configuration.yaml)
- Controllable load (climate entities, switches, etc.)

### Installation

1. **Clone this repository**
   ```bash
   cd /config/
   git clone https://github.com/YOUR-USERNAME/nordpool-spot-cutoff-optimizer.git
   ```

2. **Copy Python script**
   ```bash
   cp nordpool-spot-cutoff-optimizer/python_scripts/nordpool_cutoff_optimizer.py /config/python_scripts/
   ```

3. **Choose your integration example**
   - HVAC: See [`examples/hvac/`](./examples/hvac/)
   - Water heater: See [`examples/water_heater/`](./examples/water_heater/)

4. **Restart Home Assistant**

5. **Calibrate parameters** (see [documentation](./docs/03-integration-examples.md#calibration))

## 📚 Documentation

**3-part series on Home Assistant Community:**

1. **[Part 1: Theory](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741)** - Understanding the concept (using HVAC as example)
2. **[Part 2: Cutoff Optimizer](LINK-WHEN-PUBLISHED)** - Python implementation details
3. **[Part 3: Integration Examples](LINK-WHEN-PUBLISHED)** - How to integrate with YOUR system

**Full documentation also available in [`docs/`](./docs/) folder.**

## 📈 Real-World Results

**HVAC Heating Example (Finland, October 2025):**

| Date | Peak Price | Savings | Temperature Impact |
|------|------------|---------|-------------------|
| Oct 1 | 36.6 c/kWh | 35.9% | < 0.3°C drop |
| Oct 3 | 7.66 c/kWh | 18.2% | < 0.5°C drop |
| **Average** | - | **10-20%** | Minimal |

## 🎛️ Key Configuration Parameters

The optimizer is **load-agnostic**. Core parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_price_diff` | 3.5 c/kWh | Minimum price difference for 1h cutoff |
| `max_cutoff_duration` | 4 hours | Maximum cutoff length |
| `preheat_temp_offset` | +1°C | Preheat amount (HVAC example) |
| `min_savings_threshold` | 10% | Minimum savings to activate |

**You calibrate these for YOUR specific system.** See [calibration guide](./docs/03-integration-examples.md#calibration).

## 📂 Repository Structure

```
nordpool-spot-cutoff-optimizer/
├── README.md                    # This file
├── docs/                        # Full documentation
│   ├── 01-theory.md            # Conceptual background
│   ├── 02-cutoff-optimizer.md  # Python implementation
│   └── 03-integration-examples.md  # Setup guides
├── python_scripts/
│   └── nordpool_cutoff_optimizer.py  # Core optimizer
├── examples/
│   ├── hvac/                   # HVAC integration example
│   ├── water_heater/           # Water heater example
│   └── ...                     # More examples welcome!
└── tools/                      # Calibration & analysis tools
```

## 🖼️ Screenshots

_Coming soon: Dashboard examples, results visualization_

## 🤝 Contributing

**We need YOUR integration examples!**

If you've successfully implemented this for:
- Different heating/cooling systems
- Industrial equipment  
- Smart home devices
- Other creative uses

Please share! Submit a PR with:
1. Your configuration files
2. A README explaining your setup
3. (Optional) Results/screenshots

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## 📝 License

MIT License - see [LICENSE](./LICENSE) file

## ⚠️ Disclaimer

This is a **scheduling optimizer only**. YOU are responsible for:
- ✅ Safe implementation for your equipment
- ✅ Respecting manufacturer guidelines  
- ✅ Testing thoroughly before production use
- ✅ Monitoring system behavior
- ✅ Ensuring comfort and safety

**The authors assume no liability for equipment damage or comfort issues.**

## 🙏 Acknowledgments

- Home Assistant community for feedback and testing
- Nordpool integration developers
- All contributors sharing integration examples

## 📞 Support & Discussion

- **Issues:** [GitHub Issues](https://github.com/YOUR-USERNAME/nordpool-spot-cutoff-optimizer/issues)
- **Discussion:** [Home Assistant Community Forum](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741)
- **Documentation:** See [`docs/`](./docs/) folder

---

**⭐ If this project helps you save energy, please star the repository!**

**💬 Share your results and setup in the discussions!**
