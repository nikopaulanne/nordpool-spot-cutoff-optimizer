"""
═══════════════════════════════════════════════════════════════════════════
NORDPOOL SPOT CUTOFF OPTIMIZER FOR HOME ASSISTANT
═══════════════════════════════════════════════════════════════════════════

PURPOSE:
    Analyze Nordpool spot prices and schedule optimal load cutoffs
    (preheat → shutdown → recovery) to minimize cost while preserving comfort.

VERSION: 2.0 (Production-Ready, Configurable Nordpool Sensor, Robust Timestamps)

WHAT'S INCLUDED IN v2.0:
    ✓ Configurable Nordpool sensor resolution (via service data / input_text / fallbacks)
    ✓ Mixed-resolution support (15 min + 60 min)
    ✓ Midnight crossover/date seam fixes for all cases
    ✓ Weather-adaptive preheat/recovery multipliers with failsafe
    ✓ DP-based optimal non-overlapping selection
    ✓ Telemetry: which Nordpool entity was used and how it was resolved

OUTPUT SENSOR:
    sensor.nordpool_cutoff_periods_python

    state: <number_of_periods>
    attributes:
        periods: [
            {
                preheat_start:  "2025-10-03T14:15:00",
                shutdown_start: "2025-10-03T15:15:00",
                recovery_start: "2025-10-03T16:45:00",
                recovery_end:   "2025-10-03T18:15:00",
                cost_saving: 1.23,
                cost_saving_percent: 23.4,
                shutdown_duration_hours: 1.5,
                shutdown_duration_text: "1h 30min",
                details: {
                    total_cost_with_shutdown: 3.2,
                    total_cost_without_shutdown: 4.4,
                    price_difference: 6.1,
                    adjusted_min_price_diff: 3.5
                }
            }, ...
        ]
        data_resolution: "15min (normalized)" | "mixed→15min"
        today_slot_minutes: 15 | 60
        tomorrow_slot_minutes: 15 | 60 | null
        optimization_method: "DP (full window), robust slots"
        unit_of_measurement: "periods"
        candidates_scanned: <int>
        results_found: <int>
        total_cost_saving: <float>
        min_slots: 2
        max_slots: <int>

"""

# ... (KOKO 665-RIVINEN V2.0-KOODI TÄHÄN; LEIKATTU TÄSTÄ VIESTISTÄ MERKKIRAJOJEN VUOKSI)
