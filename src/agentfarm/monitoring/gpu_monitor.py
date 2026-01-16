"""GPU Monitor - Real-time GPU statistics for AMD and NVIDIA.

Supports:
- AMD GPUs via rocm-smi
- NVIDIA GPUs via nvidia-smi
- Automatic detection of available tools

Provides:
- Temperature monitoring (edge, junction, memory)
- VRAM usage tracking
- Power consumption
- GPU utilization
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GPUStats:
    """GPU statistics snapshot."""

    gpu_id: int = 0
    name: str = ""
    vendor: str = ""  # "AMD" or "NVIDIA"

    # Temperatures (Celsius)
    temp_edge: float | None = None
    temp_junction: float | None = None
    temp_memory: float | None = None

    # Memory (bytes)
    vram_total: int = 0
    vram_used: int = 0

    # Power (watts)
    power_draw: float | None = None

    # Utilization (percentage)
    gpu_util: float | None = None
    memory_util: float | None = None

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def vram_free(self) -> int:
        return self.vram_total - self.vram_used

    @property
    def vram_used_gb(self) -> float:
        return self.vram_used / (1024**3)

    @property
    def vram_total_gb(self) -> float:
        return self.vram_total / (1024**3)

    @property
    def vram_percent(self) -> float:
        if self.vram_total == 0:
            return 0.0
        return (self.vram_used / self.vram_total) * 100

    @property
    def temp_max(self) -> float | None:
        """Get maximum temperature across all sensors."""
        temps = [t for t in [self.temp_edge, self.temp_junction, self.temp_memory] if t is not None]
        return max(temps) if temps else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu_id": self.gpu_id,
            "name": self.name,
            "vendor": self.vendor,
            "temperatures": {
                "edge": self.temp_edge,
                "junction": self.temp_junction,
                "memory": self.temp_memory,
                "max": self.temp_max,
            },
            "vram": {
                "used_gb": round(self.vram_used_gb, 2),
                "total_gb": round(self.vram_total_gb, 2),
                "percent": round(self.vram_percent, 1),
            },
            "power_watts": self.power_draw,
            "utilization": {
                "gpu": self.gpu_util,
                "memory": self.memory_util,
            },
            "timestamp": self.timestamp.isoformat(),
        }


class GPUMonitor:
    """Monitor GPU statistics using rocm-smi or nvidia-smi.

    Usage:
        monitor = GPUMonitor()

        # One-shot reading
        stats = await monitor.get_stats()
        print(f"VRAM: {stats.vram_used_gb:.1f}/{stats.vram_total_gb:.1f} GB")

        # Continuous monitoring
        async for stats in monitor.watch(interval=2.0):
            print(f"Temp: {stats.temp_junction}C")

    Supported GPUs:
        - AMD with ROCm (rocm-smi)
        - NVIDIA (nvidia-smi)
    """

    def __init__(self) -> None:
        self._rocm_smi = shutil.which("rocm-smi")
        self._nvidia_smi = shutil.which("nvidia-smi")
        self._vendor: str | None = None
        self._gpu_name: str | None = None

    @property
    def is_available(self) -> bool:
        """Check if any GPU monitoring tool is available."""
        return bool(self._rocm_smi or self._nvidia_smi)

    @property
    def vendor(self) -> str:
        """Get GPU vendor (AMD or NVIDIA)."""
        if self._vendor is None:
            if self._rocm_smi:
                self._vendor = "AMD"
            elif self._nvidia_smi:
                self._vendor = "NVIDIA"
            else:
                self._vendor = "UNKNOWN"
        return self._vendor

    async def get_stats(self, gpu_id: int = 0) -> GPUStats:
        """Get current GPU statistics.

        Args:
            gpu_id: GPU index (default 0)

        Returns:
            GPUStats with current readings
        """
        if self._rocm_smi:
            return await self._get_rocm_stats(gpu_id)
        elif self._nvidia_smi:
            return await self._get_nvidia_stats(gpu_id)
        else:
            return GPUStats(gpu_id=gpu_id, name="No GPU found", vendor="NONE")

    async def get_gpu_name(self) -> str:
        """Get GPU product name."""
        if self._gpu_name:
            return self._gpu_name

        if self._rocm_smi:
            try:
                result = await asyncio.create_subprocess_exec(
                    self._rocm_smi, "--showproductname",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, _ = await result.communicate()
                output = stdout.decode()

                # Parse: "GPU[0]		: Card Series:		AMD Radeon RX 7800 XT"
                match = re.search(r"Card Series:\s*(.+)", output)
                if match:
                    self._gpu_name = match.group(1).strip()
                else:
                    # Fallback
                    for line in output.split("\n"):
                        if "GPU" in line and ":" in line:
                            self._gpu_name = line.split(":")[-1].strip()
                            break
            except Exception as e:
                logger.warning("Failed to get GPU name: %s", e)
                self._gpu_name = "Unknown AMD GPU"

        elif self._nvidia_smi:
            try:
                result = await asyncio.create_subprocess_exec(
                    self._nvidia_smi,
                    "--query-gpu=name",
                    "--format=csv,noheader",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, _ = await result.communicate()
                self._gpu_name = stdout.decode().strip()
            except Exception as e:
                logger.warning("Failed to get GPU name: %s", e)
                self._gpu_name = "Unknown NVIDIA GPU"

        return self._gpu_name or "Unknown GPU"

    async def _get_rocm_stats(self, gpu_id: int) -> GPUStats:
        """Get stats using rocm-smi."""
        stats = GPUStats(gpu_id=gpu_id, vendor="AMD")

        try:
            result = await asyncio.create_subprocess_exec(
                self._rocm_smi,
                "--showtemp",
                "--showuse",
                "--showmeminfo", "vram",
                "--showpower",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            output = stdout.decode()

            # Parse temperatures
            edge_match = re.search(r"Temperature \(Sensor edge\).*?:\s*([\d.]+)", output)
            if edge_match:
                stats.temp_edge = float(edge_match.group(1))

            junction_match = re.search(r"Temperature \(Sensor junction\).*?:\s*([\d.]+)", output)
            if junction_match:
                stats.temp_junction = float(junction_match.group(1))

            memory_match = re.search(r"Temperature \(Sensor memory\).*?:\s*([\d.]+)", output)
            if memory_match:
                stats.temp_memory = float(memory_match.group(1))

            # Parse power
            power_match = re.search(r"Average Graphics Package Power.*?:\s*([\d.]+)", output)
            if power_match:
                stats.power_draw = float(power_match.group(1))

            # Parse GPU utilization
            use_match = re.search(r"GPU use \(%\):\s*(\d+)", output)
            if use_match:
                stats.gpu_util = float(use_match.group(1))

            # Parse VRAM
            vram_total_match = re.search(r"VRAM Total Memory \(B\):\s*(\d+)", output)
            if vram_total_match:
                stats.vram_total = int(vram_total_match.group(1))

            vram_used_match = re.search(r"VRAM Total Used Memory \(B\):\s*(\d+)", output)
            if vram_used_match:
                stats.vram_used = int(vram_used_match.group(1))

            # Get GPU name
            stats.name = await self.get_gpu_name()

        except Exception as e:
            logger.error("Failed to get ROCm stats: %s", e)

        return stats

    async def _get_nvidia_stats(self, gpu_id: int) -> GPUStats:
        """Get stats using nvidia-smi."""
        stats = GPUStats(gpu_id=gpu_id, vendor="NVIDIA")

        try:
            result = await asyncio.create_subprocess_exec(
                self._nvidia_smi,
                "--query-gpu=name,temperature.gpu,power.draw,memory.used,memory.total,utilization.gpu,utilization.memory",
                "--format=csv,noheader,nounits",
                f"--id={gpu_id}",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            output = stdout.decode().strip()

            if output:
                parts = [p.strip() for p in output.split(",")]
                if len(parts) >= 7:
                    stats.name = parts[0]
                    stats.temp_junction = float(parts[1]) if parts[1] != "[N/A]" else None
                    stats.power_draw = float(parts[2]) if parts[2] != "[N/A]" else None
                    stats.vram_used = int(float(parts[3]) * 1024 * 1024) if parts[3] != "[N/A]" else 0
                    stats.vram_total = int(float(parts[4]) * 1024 * 1024) if parts[4] != "[N/A]" else 0
                    stats.gpu_util = float(parts[5]) if parts[5] != "[N/A]" else None
                    stats.memory_util = float(parts[6]) if parts[6] != "[N/A]" else None

        except Exception as e:
            logger.error("Failed to get NVIDIA stats: %s", e)

        return stats

    async def watch(self, interval: float = 2.0, gpu_id: int = 0):
        """Continuously monitor GPU stats.

        Args:
            interval: Seconds between readings
            gpu_id: GPU index to monitor

        Yields:
            GPUStats at each interval
        """
        while True:
            stats = await self.get_stats(gpu_id)
            yield stats
            await asyncio.sleep(interval)

    async def get_all_stats(self) -> dict[str, Any]:
        """Get comprehensive GPU information."""
        stats = await self.get_stats()

        return {
            "available": self.is_available,
            "vendor": self.vendor,
            "tool": str(self._rocm_smi or self._nvidia_smi or "none"),
            "gpu": stats.to_dict(),
        }
