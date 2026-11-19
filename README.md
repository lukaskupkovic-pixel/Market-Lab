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

Experimentální větev v2 používá podle trhu různé zpožděné kontextové řady (BTC/ETH, zlato/stříbro, Nasdaq/S&P 500, USD index a výnos 10letého dluhopisu), rozšířené technické indikátory a dva rozdílné modely: regularizovanou logistickou regresi a omezený histogramový gradient boosting. Třetí kandidát je fixní průměr jejich pravděpodobností. Vedle modelu se zobrazuje jednoduchá diagnostika tržního režimu; režim není samostatný predikční model.

Walk-forward má rozšiřující se trénink a testovací bloky. Obsahuje tři **chronologicky oddělené** části mimovzorkových predikcí:

1. Starší 40% část – sigmoidová kalibrace jednotlivých kandidátů.
2. Dalších 20% – výběr kandidáta podle Brier score na nepřekrývajících se horizontech.
3. Posledních 40% – závěrečné, během výběru neviděné hodnocení na nepřekrývajících se horizontech.

Pro trénování a výběr se používají jen výsledky známé v příslušném čase. Reference: konstantní historická četnost růstu, odhad 50 % a pevně daný momentum odhad 55/45 %. Model není kvalifikován, pokud má méně než 50 nezávislých testovacích výhledů, nezlepší Brier score nejlepší reference alespoň o 0,005, nebo spodní hranice párového 95% bootstrap intervalu zlepšení není kladná. Výsledky **neprokazují** ziskovost CFD ani výhodu po spreadu, skluzu a financování.

Při novém výpočtu se předem kontroluje čerstvost, historie a konzistence OHLC dat. Kontinuální futures mohou mít při přechodu kontraktů cenové skoky; tato verze je ještě neopravuje. Při chybějící kontextové řadě nevzniká kvalifikovaný signál. Nová verze modelu má vlastní identifikátor historie, takže nepřepisuje původní zveřejněné výhledy.

## Testování v2

```sh
python -m unittest discover -s tests -v
python -m py_compile engine.py refresh.py
node --check public/app.js
```

Testovací GitHub Action běží na feature větvích a v PR, nespouští produkční aktualizaci ani Deploy Hook. Bez ověřeného zlepšení metrik nelze tvrdit, že v2 předpovídá trhy přesněji než původní verze. Podrobnosti auditu jsou v [MODEL_AUDIT.md](MODEL_AUDIT.md).

Na náhledovém nasazení lze otevřít `?research=1`: stránka načte zvláštní statický soubor `research-v2.json` vzniklý při testovacím přepočtu. Je viditelně označen jako **neživý výzkumný snapshot** a neobsahuje produkční historii zveřejněných odhadů. Standardní URL dál načítá `data.json` a nic v produkci nemění.

## Produkce

Vytvořte samostatný GitHub repozitář a importujte jej do samostatného Vercel projektu s frameworkem Other. Nastavení build výstupu je ve vercel.json. Ve Vercelu založte Deploy Hook pro hlavní větev a jeho URL uložte jako GitHub Actions secret VERCEL_DEPLOY_HOOK. Workflow potřebuje oprávnění zapsat snapshot do hlavní větve. Spustí se denně v 06:26 UTC nebo ručně. Git ukládá první výhled pro instrument, závěr a verzi modelu, opakovaný běh jej nepřepisuje. Po dosažení cíle se doplní výsledek. Částečný výpadek zachová poslední úspěšný odhad pro postižené trhy a workflow označí výpadek jako chybu. Při úplném výpadku zůstává dostupný poslední snapshot a GitHub Actions zaznamená chybu.

Order flow, funding, likvidace, open interest, ekonomický kalendář a COT zatím nejsou použity. Pro jejich zavedení je nutné získat časově věrná, licenčně vhodná data a prokázat přínos nezávislým testem.
