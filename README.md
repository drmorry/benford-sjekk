# Benford-sjekk

Lokal web-app som tester om første siffer i de *naturlige* tallene i en PDF eller på et nettsted følger Benfords lov.

## Kjøre

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Åpne http://127.0.0.1:5000.

## Slik virker det

1. **Tekst hentes ut**: PDF via `pypdf` (side for side), nettsider via `requests` + BeautifulSoup.
   Crawleren går bredde-først ut til valgt antall nivåer og stopper ved maks antall sider. Den følger
   lenker i hovedinnholdet før menylenker, kan holde seg på samme nettsted, leser lenkede PDF-er og respekterer robots.txt.
2. **Tall klassifiseres** (`benford_app/extract.py`). Hvert tall får én kategori:
   naturlig, prosent, enkeltsiffer, eller en av de «kunstige» kategoriene (årstall, dato, klokkeslett,
   telefonnummer, ID, kode, referanse som «side 12»/«§ 4», nummerering, versjon/IP, kildehenvisning,
   sidetall, ordenstall, ISBN/DOI, tall i URL-er). Gjentatte linjer (topp-/bunntekst) fjernes først.
3. **Statistikken beregnes i nettleseren**, så du kan slå kategorier av og på og se effekten med en gang:
   MAD med Nigrinis grenser, kjikvadrat (8 fg) med p-verdi og z-verdi per siffer.

Under «Tall som er funnet» kan du kontrollere hver klassifisering med kontekst.

## Tester

```bash
.venv\Scripts\python -m pytest
```

## Begrensninger

- Klassifiseringen bygger på heuristikker. Postnumre («3724 Skien») og klokkeslett som står alene
  («kl» mangler og det er ingen andre klokkeslett i nærheten) kan for eksempel slippe gjennom som naturlige tall.
- Skannede PDF-er uten tekstlag gir ingen tall (ingen OCR).
- Nettsider som bygges med JavaScript, viser bare innholdet som finnes i rå HTML.
- Appen er laget for lokal bruk. URL-skanneren henter alle adresser du oppgir, også interne,
  så den bør ikke eksponeres på et åpent nett uten SSRF-beskyttelse.
