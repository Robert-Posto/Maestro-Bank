"""Bonusul de bun-venit — politică PROPRIE MaestroBank, ca la ratele de
câștig/catalogul de recompense/segmentele roții. Un singur bonus per user,
revendicat manual (nu se acordă automat la înregistrare — userul apasă un
buton, ca să și observe că a primit ceva, nu doar să apară tăcut într-un
sold).

500 de puncte = exact costul celei mai ieftine recompense din catalog
(`cashback_10`, vezi app/rewards_catalog.py) — deliberat, ca userul să poată
răscumpăra imediat ceva și să vadă tot fluxul funcționând din prima
vizită, nu doar să acumuleze un număr abstract.
"""

WELCOME_BONUS_POINTS = 500
