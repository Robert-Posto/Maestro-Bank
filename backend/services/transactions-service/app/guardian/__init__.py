"""Guardian — componenta LLM de explicații pentru motorul de fraudă
(app/fraud/). NU decide NICIODATĂ nimic — rulează STRICT după ce decizia
motorului determinist e deja scrisă, și scrie DOAR proză explicativă pe o
înregistrare deja finală (vezi guardian-claude-code-prompt.md, secțiunea
"Guardian")."""
