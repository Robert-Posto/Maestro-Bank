"""Sugestii în limbaj natural, per regulă, DOAR pentru fallback-ul fără LLM
al raportului pentru analiștii de fraudă (vezi templates.py). Diferite de
RULE_DESCRIPTIONS (rule_descriptions.py) — acelea sunt descrieri tehnice,
scurte, care hrănesc promptul LLM-ului; astea sunt gata scrise ca proză,
orientate spre ce ar trebui să verifice/întrebe un analist, exact stilul pe
care i-l cerem și LLM-ului să-l producă dinamic (vezi prompt.py). NU conțin
NICIODATĂ ID-uri de regulă — analistul le vede deja separat, pe pagină."""

RULE_ANALYST_HINTS: dict[str, str] = {
    "AMT-01": "Suma e mult peste ce cheltuiește de obicei clientul — merită să confirmi cu el scopul sumei; poate fi o achiziție mare planificată (electronice, o mașină) sau ceva ce nu-i aparține.",
    "VEL-03": "Clientul a plătit mai mulți beneficiari noi, pe care nu i-a mai plătit niciodată, într-un timp foarte scurt — verifică dacă îi recunoaște pe toți sau dacă cineva îi controlează contul și îl golește către conturi diferite.",
    "STR-01": "Mai multe transferuri, la scurt timp unul de altul, se opresc mereu chiar sub aceeași valoare rotundă — un tipar tipic pentru cineva care încearcă deliberat să evite o limită de raportare; tratează cu prioritate și întreabă clientul de ce sumele sunt mereu atât de apropiate.",
    "AMT-02": "Suma e neobișnuit de mare pentru genul ăsta de cheltuială la acest client — întreabă-l ce a cumpărat, ca să te asiguri că achiziția are sens pentru el.",
    "AMT-03": "Transferul folosește o parte foarte mare din soldul disponibil al contului — verifică dacă clientul știe cât de mult îi afectează asta restul fondurilor.",
    "AMT-04": "Practic golește contul clientului — fie e o mutare planificată (ex. își mută banii în alt cont al lui), fie altcineva controlează contul; confirmă direct cu el.",
    "AMT-05": "E un cont relativ nou, iar prima sumă mare trimisă e departe de ce a făcut până acum — merită mai multă atenție la identitatea și intenția clientului, ca la orice cont proaspăt.",
    "VEL-01": "Au fost multe tranzacții într-un timp foarte scurt — întreabă clientul dacă le-a inițiat el pe toate sau dacă a observat activitate pe cont pe care nu și-o amintește.",
    "VEL-02": "Clientul a cheltuit brusc mult mai mult decât suma lui obișnuită pe zi — merită aflat dacă a avut o cheltuială neplanificată sau dacă altcineva are acces la cont.",
    "VEL-05": "Sumele trimise către același beneficiar cresc rapid, una după alta — un tipar tipic pentru cineva care „testează” un cont înainte de a-l goli; verifică relația clientului cu acest beneficiar.",
    "BEN-01": "E prima dată când clientul trimite bani către acest beneficiar — nimic alarmant de unul singur, dar merită o întrebare rapidă despre cine e, mai ales combinat cu celelalte semnale.",
    "BEN-03": "Clientul trimite bani către o țară către care n-a mai trimis niciodată — dacă nu are o legătură cunoscută cu acea țară, merită clarificat de ce.",
    "BEN-05": "Acest beneficiar a primit recent bani de la mai mulți clienți diferiți, necorelați — un tipar specific conturilor folosite ca „mulă” pentru spălare de bani; tratează cu prioritate.",
    "TIME-01": "Tranzacția are loc la o oră neobișnuită pentru acest client — nu e neapărat suspect de unul singur (program de noapte etc.), dar contează combinat cu restul semnalelor.",
    "TIME-02": "Clientul a fost inactiv o vreme lungă și reapare brusc cu tranzacția asta — merită verificat dacă chiar el a revenit sau dacă altcineva a preluat contul.",
    "BEH-01": "Clientul nu a mai cheltuit niciodată în categoria asta — poate fi complet normal, dar merită menționat clientului ca reper de context.",
    "BEH-02": "Categoria asta e foarte rar folosită de client — un detaliu de context, nu neapărat un semnal suficient de unul singur.",
    "BEH-03": "Banii au intrat în cont și au ieșit aproape imediat, în sumă aproape identică — tiparul unui cont folosit ca releu pentru bani din altă parte; verifică sursa creditului inițial.",
    "STR-02": "Aceeași sumă exactă a fost trimisă către mai mulți beneficiari diferiți, la scurt timp una de alta — tipar tipic de împărțire a unei sume mari în bucăți mai mici, ca să treacă neobservată; tratează cu prioritate.",
}
