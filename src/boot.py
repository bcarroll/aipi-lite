"""Safe boot defaults for the AIPI-Lite MicroPython skeleton."""

import gc

from pins import BOARD_POWER_CONTROL

BOOT_LINES = (
    "boot: AIPI-Lite safe startup",
    "boot: collecting garbage before application start",
    "boot: GPIO{} board power left unchanged".format(BOARD_POWER_CONTROL),
)


def safe_boot_startup(print_func=print):
    """Run boot-time defaults without changing hardware power-control pins."""
    gc.collect()
    for line in BOOT_LINES:
        print_func(line)


safe_boot_startup()
