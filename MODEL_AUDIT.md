# Market Signal Lab – audit a experiment v2

## Stav před úpravami (18. 11. 2026)

- Sedmidenní cíl, jeden histogramový gradient boosting a sigmoidová kalibrace.
- Expanding walk-forward s purgem dosud nedokončených výsledků.
- Závěrečný test s nepřekrývajícími se sedmidenními výhledy.
- Srovnání jen s odhadem 50 % a četností růstu.
- Ze snapshotu na main: sedm trhů mělo 65–72 vyhodnocených výhledů; žádný nesplnil prahové zlepšení Brier score.
- Data Yahoo Finance; GC=F a SI=F proxy futures, CL=F kontinuální front-month. Chyběly automatické kvalitativní kontroly.

## Implementováno na samostatné větvi

1. Kontrola stáří, úplnosti a konzistence OHLC a označení zdrojových rizik.
2. Tržně odlišné kontextové vstupy, se zpožděním kvůli časovému souladu trhů.
3. Dva modely + předem určená kombinace, s chronologicky oddělenou kalibrací, výběrem a závěrečným testem.
4. Silnější referenční model (včetně momenta), zlepšení Brier score a 95% párový bootstrap interval.
5. Konzervativní zákaz kvalifikovaného signálu při neověřeném zlepšení, malém vzorku nebo chybějícím kontextu.
6. Režim trhu a původ/kvalita dat ve veřejném dashboardu.
7. Offline regresní testy a samostatný CI workflow pro PR, bez dotyku produkčního refresh workflow.
8. Izolovaný `?research=1` náhled nových metrik z jednorázového datového snapshotu; nejde o živé výsledky.
9. Nové scénářové rozhraní s dvoutřídními skutečně kalibrovanými pravděpodobnostmi a otevřeně nemodelovanou neutrální třídou. Orientační 80% historické 7denní pásmo je pouze popis minulých pohybů, nikoli predikční interval.

## Otevřené limity a další výzkum

- Přepínání futures kontraktů může vytvářet cenové skoky; pro spot CFD je třeba kompatibilní spotový feed a historická reconciliace.
- Yahoo historické revize nejsou point-in-time archiv. Makroekonomické vintage (ALFRED), přístupné v okamžiku rozhodnutí, jsou další fáze.
- Historické testovací metriky nejsou obchodní výkonnost; je nutné modelovat spread, slippage, swap a pravidla vstupu/výstupu.
- Je třeba dlouhodobě ukládat skutečně zveřejněné predikce a později provést forward test; backtest může podléhat overfittingu.
- Bootstrap je pouze orientační interval na neprolínajících se horizontech, nezachycuje změny režimů a modelové nejistoty.
- Nové specializované tržní feedy (COT, funding, open interest, CPI/FOMC reakce) by se měly přidávat po jednom a ověřit ablačním testem.

## Kritérium pro nasazení na main

Nejdříve projít syntaxi a offline testy, reálný refresh všech sedmi trhů a vizuální kontrolu preview. Prohlásit v2 za přesnější lze až po srovnání na zcela oddělených datech a následném forward testu; bez toho jde o **výzkumnou verzi**, nikoli prokázanou lepší předpověď.
