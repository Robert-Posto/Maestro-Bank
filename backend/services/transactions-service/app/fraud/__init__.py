"""Motorul de scoring fraud — Faza 1 (shadow mode).

Deterministic, sincron, în-proces (rulează în transactions-service, NU ca
serviciu separat — vezi planul de implementare). Scorează 0-100 pe baza a
20 de reguli, scrie un jurnal de audit complet la fiecare evaluare, dar NU
blochează/reține NICIODATĂ o tranzacție — vezi fraud/service.py pentru
garanția structurală a acestui lucru.

Separat total de Guardian (explicația LLM, care nu există încă în acest
proiect) — acest pachet NU apelează niciun model de limbaj.
"""
