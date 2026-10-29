"""Every platform-exempt AppleScript driver is named in the exemption inventory.

rules/deck-editing-rules.md lists each exempt driver with its manual
validation procedure; a driver added without an entry would be exempt from
CI without any procedure.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/presentation-creator/scripts"
RULE = ROOT / "rules/deck-editing-rules.md"


def test_every_applescript_driver_is_listed_in_the_exemption_inventory():
    rule = RULE.read_text(encoding="utf-8")
    drivers = sorted(p.name for p in SCRIPTS.glob("*.applescript"))
    assert drivers, "no AppleScript drivers found"
    missing = [name for name in drivers if f"`{name}`" not in rule]
    assert missing == []
