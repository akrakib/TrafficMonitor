"""Backward-compatible import shim for the renamed TrafficMonitor module."""

from .traffic_monitor import TrafficMonitor

Application = TrafficMonitor
