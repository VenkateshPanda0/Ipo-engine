"""
src/ipo_engine/screening/rules/__init__.py

Rules package — individual regulatory rule implementations.

This package contains:
  - base_rule.py: Abstract BaseRule interface
  - registry.py: RuleRegistry with auto-discovery
  - mandatory/: SEBI ICDR mandatory eligibility rules (11 rules)
  - advisory/: Governance and risk advisory rules (5 rules)

ARCHITECTURAL CONSTRAINTS:
  - Rules may only import from: ipo_engine.screening.models
  - Rules MUST NOT import from: ipo_engine.screening.intelligence, ipo_engine.screening.api, ipo_engine.screening.services, ipo_engine.screening.engine
  - Each rule is a pure function: f(CompanyData) → RuleResult
  - No shared mutable state between rules
"""
