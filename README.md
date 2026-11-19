# Market Signal Lab

Analytický dashboard se sedmidenním horizontem. Python zpracovává data a modely dávkově, Vercel servíruje statický výstup z adresáře public. Aplikace nemá žádné spojení s brokerem.

## Lokální spuštění

Python 3.12. V kořeni projektu spusťte:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python refresh.py
python -m http.server 8000 --directory public
```

Otevřete http://localhost:8000. Tlačítko Obnovit data znovu stáhne poslední publikovaný snapshot. Ruční přepočet se spouští z GitHub Actions přes Run workflow nebo lokálním příkazem výše.

## Data a model

Yahoo Finance Chart dodává denní OHLCV a poslední dostupnou kotaci. Trénink bere ukončené lokální kalendářní dny a historické seance podle dostupných svíček. BTC a ETH běží denně. Zlato a stříbro používají výslovně označené futures GC=F a SI=F jako zástupné řady za spot, jehož symboly Yahoo v tomto prostředí nevracelo. Ropa je kontinuální front-month WTI a může zahrnovat cenové skoky při rolování. Nasdaq a S&P jsou indexy. Cena je USD nebo indexové body. Denní změna je rozdíl posledních dvou denních závěrů.

Cíl je vyšší závěrečná cena první dostupné seance v den D+7 nebo později. Stejná cena se počítá do třídy bez růstu. Historický trénink vynechává cíle posunuté o více než tři dodatečné dny. Historické zdroje mohou dodatečně opravovat data.

Experimentální větev v3 používá podle trhu různé zpožděné kontextové řady (BTC/ETH, zlato/stříbro, Nasdaq/S&P 500, USD index a výnos 10letého dluhopisu), rozšířené technické indikátory a čtyři kandidáty: regularizovanou logistickou regresi, omezený histogramový gradient boosting, jejich fixní průměr a **režimového specialistu** (logistické modely naučené na historicky podobných režimech; při nedostatku historie záložní globální model). Režim má čtyři ex ante stavy: boční trh, růst, pokles a zvýšená volatilita. Režimový kandidát musí uspět na stejné předem oddělené validační sadě; nesmí se automaticky použít pouze proto, že existuje.

Walk-forward má rozšiřující se trénink a testovací bloky. Obsahuje tři **chronologicky oddělené** části mimovzorkových predikcí:

1. Starší 40% část – sigmoidová kalibrace jednotlivých kandidátů.
2. Dalších 20% – výběr kandidáta podle Brier score na nepřekrývajících se horizontech.
3. Posledních 40% – závěrečné, během výběru neviděné hodnocení na nepřekrývajících se horizontech.

Pro trénování a výběr se používají jen výsledky známé v příslušném čase. Reference: konstantní historická četnost růstu, odhad 50 % a pevně daný momentum odhad 55/45 %. Model není kvalifikován, pokud má méně než 50 nezávislých testovacích výhledů, nezlepší Brier score nejlepší reference alespoň o 0,005, nebo spodní hranice párového 95% bootstrap intervalu zlepšení není kladná. Výsledky **neprokazují** ziskovost CFD ani výhodu po spreadu, skluzu a financování.

Při novém výpočtu se předem kontroluje čerstvost, historie a konzistence OHLC dat. Kontinuální futures mohou mít při přechodu kontraktů cenové skoky; tato verze je ještě neopravuje. Při chybějící kontextové řadě nevzniká kvalifikovaný signál. Nová verze modelu má vlastní identifikátor `daily-ensemble-v4-regime`, takže nepřepisuje původní zveřejněné výhledy.

## Osm zlepšení a jejich přesný stav

1. **Datová vrstva – částečně.** Validace OHLC, stáří dat, explicitní zdroj i chybějící kontext fungují. Doplněn volně dostupný oficiální CFTC COT (agregované pozice futures, jen GC/SI/CL), s minimálně 14denním odstupem od reportovaného úterý. COT má výslovné `used_in_model: false`; kvůli absenci autentické historické vintage není použit pro trénink. BLS kalendář je také jen kontext. Druhý licencovaný tickový/CFD feed, historické order flow ani futures term structure stále chybí.
2. **Modely – implementováno.** Logistická regrese, gradient boosting, pevná směs a specialista na tržní režim soutěží ve walk-forward validaci; výběr jen na starších datech.
3. **Market Regime Detector – implementováno jako výzkumný kandidát.** Čtyři stavy z dokončených svíček; reálnou přidanou hodnotu musí prokázat ve validaci.
4. **Makro a události – částečně.** Oficiální budoucí události BLS jsou zobrazené s časem zveřejnění. Překvapení vůči konsenzu FOMC/CPI/NFP, historické ALFRED vintages, geopolitické události a měření jejich efektu do modelu zatím nepatří. Bez zdrojů a záznamů prvního zveřejnění by hrozil únik budoucích informací.
5. **Pokročilé pravděpodobnosti – částečně.** Zůstává kalibrovaný binární směr a historické 10.–90. percentilové pásmo, jasně označené jako historické. Přibyly **historické** četnosti růstu/klidu/poklesu v podobném režimu s volatilní neutrální zónou. Nejsou prezentovány jako třícestná kalibrovaná predikce ani jako pravděpodobnost dosažení cílové ceny.
6. **Backtesting – rozšířeno.** Oddělené tréninkové, kalibrační, validační a testovací období; purge cílů známých až v budoucnu; nepřekrývající se testovací výsledky. Nový volitelný nákladový *proxy* backtest na poslední testovací sadě používá **výlučně zadané** spread, skluz a denní financování; bez jejich zadání výnos po nákladech **nevypočítáváme**. Reálný CFD P&L a exekuci netvrdíme.
7. **Degradace – implementováno s podmínkou dat.** Každá nová verze uchovává neměnné publikované předpovědi. Po 20 nepřekrývajících se dokončených výhledech monitoruje poslední Brier; zhoršenou verzi může automaticky zablokovat. Nejde o statistický důkaz degradace. Na nově zavedené verzi bude několik měsíců stav `insufficient`.
8. **Explainable AI – implementováno lokálně.** Ukazuje citlivost vybraného modelu při změně jednotlivých vstupů na historický medián (v procentních bodech). Nejde o kauzalitu a korelované ukazatele se tím mohou zkreslit. Nemění to predikční skóre.

Oficiální CFTC dataset: https://publicreporting.cftc.gov/stories/s/72hh-3qpy ; kalendář BLS: https://www.bls.gov/schedule/news_release/bls.ics. Externí zdroje se dají vypnout `MARKET_LAB_OFFICIAL_FEEDS=0`. Při výpadku doplňkového zdroje se nepřidává imaginární hodnota a trénink nezíská neověřený obsah.

Volitelný nákladový výpočet vyžaduje najednou `MARKET_LAB_ROUNDTRIP_SPREAD_BPS`, `MARKET_LAB_ROUNDTRIP_SLIPPAGE_BPS` a `MARKET_LAB_DAILY_FINANCING_BPS`. Pro produkční CFD výsledky navíc chybí specifikace kontraktů, rollover, swapová sazba podle směru, provize a kvalita exekuce; model proto neslibuje výnosnost.

## Testování v3

```sh
python -m unittest discover -s tests -v
python -m py_compile engine.py refresh.py monitor.py external_data.py
node --check public/app.js
```

Testovací GitHub Action běží na feature větvích a v PR, nespouští produkční aktualizaci ani Deploy Hook. Bez ověřeného zlepšení metrik nelze tvrdit, že v2 předpovídá trhy přesněji než původní verze. Podrobnosti auditu jsou v [MODEL_AUDIT.md](MODEL_AUDIT.md).

Na náhledovém nasazení lze otevřít `?research=1`: stránka načte zvláštní statický soubor `research-v3.json` vzniklý při testovacím přepočtu s `MARKET_LAB_OUTPUT=public/research-v3.json python refresh.py`. Je viditelně označen jako **neživý výzkumný snapshot** a neobsahuje produkční historii zveřejněných odhadů. Standardní URL dál načítá `data.json` a nic v produkci nemění.

## Produkce

Vytvořte samostatný GitHub repozitář a importujte jej do samostatného Vercel projektu s frameworkem Other. Nastavení build výstupu je ve vercel.json. Ve Vercelu založte Deploy Hook pro hlavní větev a jeho URL uložte jako GitHub Actions secret VERCEL_DEPLOY_HOOK. Workflow potřebuje oprávnění zapsat snapshot do hlavní větve. Spustí se denně v 06:26 UTC nebo ručně. Git ukládá první výhled pro instrument, závěr a verzi modelu, opakovaný běh jej nepřepisuje. Po dosažení cíle se doplní výsledek. Částečný výpadek zachová poslední úspěšný odhad pro postižené trhy a workflow označí výpadek jako chybu. Při úplném výpadku zůstává dostupný poslední snapshot a GitHub Actions zaznamená chybu.

Order flow, funding, likvidace a historicky věrné COT/makro události zatím **nejsou vstupy modelu**. Pro jejich zavedení je nutné získat časově věrná, licenčně vhodná data a prokázat přínos nezávislým testem. Historické předpovědi už obsahují starší verze; v monitoru se verze oddělují.
