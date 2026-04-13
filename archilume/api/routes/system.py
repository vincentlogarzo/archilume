"""GET /system — machine health metrics (CPU, memory, load)."""

import psutil
from fastapi import APIRouter

router = APIRouter()


@router.get("/system")
def system_stats():
    """Snapshot of host CPU, memory, and load — htop-like data for the UI."""
    vm = psutil.virtual_memory()
    try:
        load_avg = psutil.getloadavg()  # not available on Windows < py3.13
    except (AttributeError, OSError):
        load_avg = None

    return {
        "cpu_percent_total": psutil.cpu_percent(interval=0.2),
        "cpu_percent_per_core": psutil.cpu_percent(interval=0.2, percpu=True),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "memory_percent": vm.percent,
        "memory_used_gb": round(vm.used / 1e9, 2),
        "memory_total_gb": round(vm.total / 1e9, 2),
        "load_avg_1_5_15": load_avg,
    }
