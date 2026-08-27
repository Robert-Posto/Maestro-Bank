"""Descrieri în limbaj simplu, românesc, pentru fiecare din cele 26 de
reguli SCORATE implementate în app/fraud/catalogue.py, PLUS BEN-04
(blocklist — nu e scorată, dar tot descrisă aici pentru completitudine,
vezi app/blocklist.py) — singura sursă de "ce înseamnă regula X",
refolosită atât de prompt.py (pentru LLM), cât și de templates.py
(fallback fără LLM). NU acoperă toate ID-urile din catalogul complet al
spec-ului (guardian-claude-code-prompt.md) — doar cele chiar construite
(vezi app/fraud/rules_*.py pentru care lipsesc și de ce)."""

RULE_DESCRIPTIONS: dict[str, str] = {
    "AMT-01": "Suma e de peste 2 ori mai mare decât percentila 95 a sumelor obișnuite ale userului.",
    "VEL-04": "Cel puțin 3 încercări de login eșuate, imediat urmate de una reușită.",
    "DEV-01": "Autentificare reușită de pe un dispozitiv (aproximat prin IP + browser) niciodată văzut la acest cont.",
    "DEV-02": "Parola sau o cheie de acces (passkey) a fost schimbată/înrolată/revocată în ultimele 24 de ore.",
    "DEV-04": "Două autentificări reușite, la o distanță geografică ce ar necesita o viteză de deplasare imposibilă.",
    "DEV-05": "Autentificare reușită dintr-o țară nemaivăzută la acest cont în ultimele 30 de zile.",
    "DEV-06": "Combinație: dispozitiv nou + beneficiar nou + sumă peste percentila obișnuită a userului.",
    "BEN-04": "Beneficiarul se află pe lista de blocare a băncii — transferul e refuzat direct, fără scor.",
    "VEL-03": "Cel puțin 3 beneficiari noi (niciodată plătiți înainte) în ultimele 60 de minute.",
    "STR-01": "Cel puțin 3 tranzacții în 24 de ore, fiecare între 90% și 99% dintr-un prag de raportare configurabil (50.000 RON implicit).",
    "AMT-02": "Suma e de peste 4 ori mai mare decât suma tipică a userului pentru această categorie.",
    "AMT-03": "Suma depășește 70% din soldul disponibil al contului.",
    "AMT-04": "Suma reprezintă aproape întregul sold disponibil al contului — golire de cont.",
    "AMT-05": "Primul transfer mare al unui user cu istoric puțin — suma e de peste 5 ori media obișnuită.",
    "VEL-01": "Mai mult de 5 tranzacții în ultimele 10 minute.",
    "VEL-02": "Suma cumulată din ultima oră depășește de 3 ori media zilnică a userului.",
    "VEL-05": "Sume tot mai mari trimise către același beneficiar, în pași succesivi, în doar 30 de minute.",
    "BEN-01": "Este prima plată către acest beneficiar.",
    "BEN-03": "Țara IBAN-ului beneficiarului nu apare în istoricul de plăți al userului.",
    "BEN-05": "Acest beneficiar a primit bani de la cel puțin 5 useri diferiți în ultimele 24 de ore.",
    "TIME-01": "Ora tranzacției e în afara intervalului obișnuit de activitate al userului.",
    "TIME-02": "Prima activitate după peste 90 de zile de inactivitate.",
    "DEV-03": "A fost înrolată o cheie de acces (passkey) nouă cu puțin timp înainte de această tranzacție.",
    "BEH-01": "Categoria acestei tranzacții nu a mai fost folosită niciodată de acest user.",
    "BEH-02": "Categoria reprezintă mai puțin de 5% din istoricul de cheltuieli al userului.",
    "BEH-03": "Un credit a intrat în cont și a fost urmat rapid de un debit aproape egal.",
    "STR-02": "Aceeași sumă exactă a fost trimisă către cel puțin 3 beneficiari diferiți în 60 de minute.",
}
