# Benford-sjekk

Web-app som tester om første siffer i de *naturlige* tallene i en PDF eller på et nettsted følger Benfords lov.

**Bruk den her: https://drmorry.github.io/benford-sjekk/**

All analyse skjer i nettleseren din. PDF-er lastes ikke opp noe sted.

## Slik virker det

1. **Tekst hentes ut**: PDF-er leses med [pdf.js](https://mozilla.github.io/pdf.js/). Nettsider hentes med `fetch` og
   tolkes med BeautifulSoup. Crawleren går bredde-først ut til valgt antall nivåer og stopper ved maks antall sider.
   Den følger lenker i hovedinnholdet før menylenker, kan holde seg på samme nettsted, leser lenkede PDF-er og respekterer robots.txt.
2. **Tall klassifiseres** av Python-koden i [`benford_app/extract.py`](benford_app/extract.py), som kjører i nettleseren via
   [Pyodide](https://pyodide.org/) i en Web Worker. Hvert tall får én kategori:
   naturlig, prosent, enkeltsiffer, eller en av de «kunstige» kategoriene (årstall, dato, klokkeslett,
   telefonnummer, ID, kode, referanse som «side 12»/«§ 4», nummerering, versjon/IP, kildehenvisning,
   sidetall, ordenstall, ISBN/DOI, tall i URL-er). Gjentatte linjer (topp-/bunntekst) fjernes først.
3. **Statistikk**: MAD med Nigrinis grenser, kjikvadrat (8 fg) med p-verdi og z-verdi per siffer.
   Du kan slå kategorier av og på og se effekten med en gang. Hver klassifisering kan kontrolleres med kontekst.

## Skanning av nettsteder: proxy

Nettlesere lar ikke en side på `github.io` hente innhold fra andre nettsteder (CORS). For URL-skanning
på GitHub Pages trengs derfor en proxy. Den legges inn under *Avanserte innstillinger* og lagres bare i din nettleser.

Gratis oppsett med Cloudflare Workers (100 000 forespørsler per dag gratis):

1. Lag en gratis konto på https://dash.cloudflare.com og velg *Workers & Pages → Create → Hello World*.
2. Erstatt koden med innholdet i [`worker/proxy.js`](worker/proxy.js), og trykk *Deploy*.
   Proxyen svarer bare til origin-ene i `ALLOWED_ORIGINS`, så andre nettsteder kan ikke misbruke den.
3. Lim inn `https://<navn>.<konto>.workers.dev/?url={url}` som proxy i appen.

Når appen kjøres lokalt, brukes den innebygde proxyen i `app.py` automatisk.

## Kjøre lokalt

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Åpne http://127.0.0.1:5000.

## Tester

```bash
.venv\Scripts\python -m pytest
```

## Publisering

Hver push til `main` publiseres til GitHub Pages av [`.github/workflows/pages.yml`](.github/workflows/pages.yml).

## Begrensninger

- Klassifiseringen bygger på heuristikker. Postnumre («3724 Skien») og klokkeslett som står alene
  (uten «kl» og uten andre klokkeslett i nærheten) kan for eksempel slippe gjennom som naturlige tall.
- Skannede PDF-er uten tekstlag gir ingen tall (ingen OCR).
- Nettsider som bygges med JavaScript, viser bare innholdet som finnes i rå HTML.
- Første besøk laster ned Python-motoren (Pyodide, ca. 10 MB). Etterpå ligger den i nettleserens hurtigbuffer.
