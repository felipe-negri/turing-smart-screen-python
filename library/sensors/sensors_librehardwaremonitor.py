# turing-smart-screen-python - a Python system monitor and library for USB-C displays like Turing Smart Screen or XuanFang
# https://github.com/mathoudebine/turing-smart-screen-python/

# Copyright (C) 2021-2023  Matthieu Houdebine (mathoudebine)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This file will use LibreHardwareMonitor.dll library to get hardware sensors
# Some metrics are still fetched by psutil when not available on LibreHardwareMonitor
# For Windows platforms only

import ctypes
import math
import os
import sys
from statistics import mean
from typing import Tuple

import clr  # Clr is from pythonnet package. Do not install clr package
import psutil
from win32api import *
import requests  # Certifique-se de que o módulo requests está instalado

import library.sensors.sensors as sensors
from library.log import logger

# Import LibreHardwareMonitor dll to Python
lhm_dll = os.getcwd() + '\\external\\LibreHardwareMonitor\\LibreHardwareMonitorLib.dll'
# noinspection PyUnresolvedReferences
clr.AddReference(lhm_dll)
# noinspection PyUnresolvedReferences
clr.AddReference(os.getcwd() + '\\external\\LibreHardwareMonitor\\HidSharp.dll')
# noinspection PyUnresolvedReferences
from LibreHardwareMonitor import Hardware

File_information = GetFileVersionInfo(lhm_dll, "\\")

ms_file_version = File_information['FileVersionMS']
ls_file_version = File_information['FileVersionLS']

logger.debug("Found LibreHardwareMonitorLib %s" % ".".join([str(HIWORD(ms_file_version)), str(LOWORD(ms_file_version)),
                                                            str(HIWORD(ls_file_version)),
                                                            str(LOWORD(ls_file_version))]))

if ctypes.windll.shell32.IsUserAnAdmin() == 0:
    logger.error(
        "Program is not running as administrator. Please run with admin rights or choose another HW_SENSORS option in "
        "config.yaml")
    try:
        sys.exit(0)
    except:
        os._exit(0)

handle = Hardware.Computer()
handle.IsCpuEnabled = True
handle.IsGpuEnabled = True
handle.IsMemoryEnabled = True
handle.IsMotherboardEnabled = True  # For CPU Fan Speed
handle.IsControllerEnabled = True  # For CPU Fan Speed
handle.IsNetworkEnabled = True
handle.IsStorageEnabled = True
handle.IsPsuEnabled = False
handle.Open()
for hardware in handle.Hardware:
    if hardware.HardwareType == Hardware.HardwareType.Cpu:
        logger.info("Found CPU: %s" % hardware.Name)
    elif hardware.HardwareType == Hardware.HardwareType.Memory:
        logger.info("Found Memory: %s" % hardware.Name)
    elif hardware.HardwareType == Hardware.HardwareType.GpuNvidia:
        logger.info("Found Nvidia GPU: %s" % hardware.Name)
    elif hardware.HardwareType == Hardware.HardwareType.GpuAmd:
        logger.info("Found AMD GPU: %s" % hardware.Name)
    elif hardware.HardwareType == Hardware.HardwareType.GpuIntel:
        logger.info("Found Intel GPU: %s" % hardware.Name)
    elif hardware.HardwareType == Hardware.HardwareType.Storage:
        logger.info("Found Storage: %s" % hardware.Name)
    elif hardware.HardwareType == Hardware.HardwareType.Network:
        logger.info("Found Network interface: %s" % hardware.Name)


def get_hw_and_update(hwtype: Hardware.HardwareType, name: str = None) -> Hardware.Hardware:
    for hardware in handle.Hardware:
        if hardware.HardwareType == hwtype:
            if (name and hardware.Name == name) or name is None:
                hardware.Update()
                return hardware
    return None


def get_gpu_name() -> str:
    endpoint_url = "http://192.168.50.80:5050/gpu-stats"  # URL do endpoint
    try:
        response = requests.get(endpoint_url)
        response.raise_for_status()
        data = response.json()
        gpu_name = data.get("gpu_name", "")
        if gpu_name:
            logger.debug(f"GPU encontrada no endpoint: {gpu_name}")
            return gpu_name
        else:
            logger.warning("Nenhum nome de GPU encontrado no endpoint.")
            return ""
    except requests.RequestException as e:
        logger.error(f"Erro ao buscar o nome da GPU do endpoint: {e}")
        return ""

def get_net_interface_and_update(if_name: str) -> Hardware.Hardware:
    for hardware in handle.Hardware:
        if hardware.HardwareType == Hardware.HardwareType.Network and hardware.Name == if_name:
            hardware.Update()
            return hardware

    logger.warning("Network interface '%s' not found. Check names in config.yaml." % if_name)
    return None


class Cpu(sensors.Cpu):
    @staticmethod
    def percentage(interval: float) -> float:
        cpu = get_hw_and_update(Hardware.HardwareType.Cpu)
        for sensor in cpu.Sensors:
            if sensor.SensorType == Hardware.SensorType.Load and str(sensor.Name).startswith(
                    "CPU Total") and sensor.Value is not None:
                return float(sensor.Value)

        logger.error("CPU load cannot be read")
        return math.nan

    @staticmethod
    def frequency() -> float:
        frequencies = []
        cpu = get_hw_and_update(Hardware.HardwareType.Cpu)
        try:
            for sensor in cpu.Sensors:
                if sensor.SensorType == Hardware.SensorType.Clock:
                    # Keep only real core clocks, ignore effective core clocks
                    if "Core #" in str(sensor.Name) and "Effective" not in str(
                            sensor.Name) and sensor.Value is not None:
                        frequencies.append(float(sensor.Value))

            if frequencies:
                # Take mean of all core clock as "CPU clock" (as it is done in Windows Task Manager Performance tab)
                return mean(frequencies)
        except:
            pass

        # Frequencies reading is not supported on this CPU
        return math.nan

    @staticmethod
    def load() -> Tuple[float, float, float]:  # 1 / 5 / 15min avg (%):
        # Get this data from psutil because it is not available from LibreHardwareMonitor
        return psutil.getloadavg()

    @staticmethod
    def temperature() -> float:
        cpu = get_hw_and_update(Hardware.HardwareType.Cpu)
        try:
            # By default, the average temperature of all CPU cores will be used
            for sensor in cpu.Sensors:
                if sensor.SensorType == Hardware.SensorType.Temperature and str(sensor.Name).startswith(
                        "Core Average") and sensor.Value is not None:
                    return float(sensor.Value)
            # If not available, the max core temperature will be used
            for sensor in cpu.Sensors:
                if sensor.SensorType == Hardware.SensorType.Temperature and str(sensor.Name).startswith(
                        "Core Max") and sensor.Value is not None:
                    return float(sensor.Value)
            # If not available, the CPU Package temperature (usually same as max core temperature) will be used
            for sensor in cpu.Sensors:
                if sensor.SensorType == Hardware.SensorType.Temperature and str(sensor.Name).startswith(
                        "CPU Package") and sensor.Value is not None:
                    return float(sensor.Value)
            # Otherwise any sensor named "Core..." will be used
            for sensor in cpu.Sensors:
                if sensor.SensorType == Hardware.SensorType.Temperature and str(sensor.Name).startswith(
                        "Core") and sensor.Value is not None:
                    return float(sensor.Value)
        except:
            pass

        return math.nan

    @staticmethod
    def fan_percent(fan_name: str = None) -> float:
        mb = get_hw_and_update(Hardware.HardwareType.Motherboard)
        try:
            for sh in mb.SubHardware:
                sh.Update()
                for sensor in sh.Sensors:
                    if sensor.SensorType == Hardware.SensorType.Control and "#2" in str(
                            sensor.Name) and sensor.Value is not None:  # Is Motherboard #2 Fan always the CPU Fan ?
                        return float(sensor.Value)
        except:
            pass

        # No Fan Speed sensor for this CPU model
        return math.nan


class Gpu(sensors.Gpu):
    endpoint_url = "http://192.168.50.80:5050/gpu-stats"  # URL do endpoint

    @classmethod
    def fetch_data_from_endpoint(cls):
        try:
            response = requests.get(cls.endpoint_url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Erro ao buscar dados do endpoint: {e}")
            return None

    @classmethod
    def stats(cls) -> Tuple[float, float, float, float, float]:
        data = cls.fetch_data_from_endpoint()
        if data:
            load = data.get("load", math.nan)
            memory_percentage = data.get("memory_percentage", math.nan)
            memory_used_mb = data.get("memory_used_mb", math.nan)
            total_memory_mb = data.get("total_memory_mb", math.nan)
            temperature = data.get("temperature", math.nan)
            return load, memory_percentage, memory_used_mb, total_memory_mb, temperature
        return math.nan, math.nan, math.nan, math.nan, math.nan

    @classmethod
    def fps(cls) -> int:
        data = cls.fetch_data_from_endpoint()
        if data:
            return data.get("fps", -1)
        return -1

    @classmethod
    def fan_percent(cls) -> float:
        data = cls.fetch_data_from_endpoint()
        if data:
            return data.get("fan_percent", math.nan)
        return math.nan

    @classmethod
    def frequency(cls) -> float:
        data = cls.fetch_data_from_endpoint()
        if data:
            return data.get("freq_ghz", math.nan)
        return math.nan

    @classmethod
    def is_available(cls) -> bool:
        data = cls.fetch_data_from_endpoint()
        return data is not None


class Memory(sensors.Memory):
    @staticmethod
    def swap_percent() -> float:
        memory = get_hw_and_update(Hardware.HardwareType.Memory)

        virtual_mem_used = math.nan
        mem_used = math.nan
        virtual_mem_available = math.nan
        mem_available = math.nan

        # Get virtual / physical memory stats
        for sensor in memory.Sensors:
            if sensor.SensorType == Hardware.SensorType.Data and str(sensor.Name).startswith(
                    "Virtual Memory Used") and sensor.Value is not None:
                virtual_mem_used = int(sensor.Value)
            elif sensor.SensorType == Hardware.SensorType.Data and str(sensor.Name).startswith(
                    "Memory Used") and sensor.Value is not None:
                mem_used = int(sensor.Value)
            elif sensor.SensorType == Hardware.SensorType.Data and str(sensor.Name).startswith(
                    "Virtual Memory Available") and sensor.Value is not None:
                virtual_mem_available = int(sensor.Value)
            elif sensor.SensorType == Hardware.SensorType.Data and str(sensor.Name).startswith(
                    "Memory Available") and sensor.Value is not None:
                mem_available = int(sensor.Value)

        # Compute swap stats from virtual / physical memory stats
        swap_used = virtual_mem_used - mem_used
        swap_available = virtual_mem_available - mem_available
        swap_total = swap_used + swap_available
        try:
            percent_swap = swap_used / swap_total * 100.0
        except:
            # No swap / pagefile disabled
            percent_swap = 0.0

        return percent_swap

    @staticmethod
    def virtual_percent() -> float:
        memory = get_hw_and_update(Hardware.HardwareType.Memory)
        for sensor in memory.Sensors:
            if sensor.SensorType == Hardware.SensorType.Load and str(sensor.Name).startswith(
                    "Memory") and sensor.Value is not None:
                return float(sensor.Value)

        return math.nan

    @staticmethod
    def virtual_used() -> int:  # In bytes
        memory = get_hw_and_update(Hardware.HardwareType.Memory)
        for sensor in memory.Sensors:
            if sensor.SensorType == Hardware.SensorType.Data and str(sensor.Name).startswith(
                    "Memory Used") and sensor.Value is not None:
                return int(sensor.Value * 1000000000.0)

        return 0

    @staticmethod
    def virtual_free() -> int:  # In bytes
        memory = get_hw_and_update(Hardware.HardwareType.Memory)
        for sensor in memory.Sensors:
            if sensor.SensorType == Hardware.SensorType.Data and str(sensor.Name).startswith(
                    "Memory Available") and sensor.Value is not None:
                return int(sensor.Value * 1000000000.0)

        return 0


# NOTE: all disk data are fetched from psutil Python library, because LHM does not have it.
# This is because LHM is a hardware-oriented library, whereas used/free/total space is for partitions, not disks
class Disk(sensors.Disk):
    @staticmethod
    def disk_usage_percent() -> float:
        return psutil.disk_usage("/").percent

    @staticmethod
    def disk_used() -> int:  # In bytes
        return psutil.disk_usage("/").used

    @staticmethod
    def disk_free() -> int:  # In bytes
        return psutil.disk_usage("/").free


class Net(sensors.Net):
    @staticmethod
    def stats(if_name, interval) -> Tuple[
        int, int, int, int]:  # up rate (B/s), uploaded (B), dl rate (B/s), downloaded (B)

        upload_rate = 0
        uploaded = 0
        download_rate = 0
        downloaded = 0

        if if_name != "":
            net_if = get_net_interface_and_update(if_name)
            if net_if is not None:
                for sensor in net_if.Sensors:
                    if sensor.SensorType == Hardware.SensorType.Data and str(sensor.Name).startswith(
                            "Data Uploaded") and sensor.Value is not None:
                        uploaded = int(sensor.Value * 1000000000.0)
                    elif sensor.SensorType == Hardware.SensorType.Data and str(sensor.Name).startswith(
                            "Data Downloaded") and sensor.Value is not None:
                        downloaded = int(sensor.Value * 1000000000.0)
                    elif sensor.SensorType == Hardware.SensorType.Throughput and str(sensor.Name).startswith(
                            "Upload Speed") and sensor.Value is not None:
                        upload_rate = int(sensor.Value)
                    elif sensor.SensorType == Hardware.SensorType.Throughput and str(sensor.Name).startswith(
                            "Download Speed") and sensor.Value is not None:
                        download_rate = int(sensor.Value)

        return upload_rate, uploaded, download_rate, downloaded
