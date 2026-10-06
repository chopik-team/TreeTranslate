"""Offline, explicitly curated translation memory. No automatic learning."""
from .engine import TranslationMemoryEngine
from .models import MemoryMatch, TranslationUnit, Status

__all__ = ['TranslationMemoryEngine', 'MemoryMatch', 'TranslationUnit', 'Status']
