---
name: cfd-units
description: Quantity units and reference conventions
trigger: always
---

Default units: SI (m, kg, s, K, Pa).

When reporting forces, always state the reference area used. If the user
hasn't given one, ask for it before calling `calculate(method='force')`.

Mach and Reynolds numbers are dimensionless — don't append units.
