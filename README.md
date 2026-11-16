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

Cíl je vyšší závěrečná cena první dostupné seance v den D+7 nebo později. Stejná cena se počítá do třídy bez růstu. Historický trénink vynechává cíle posunuté o více než tři dodatečné dny. Historické zdroje mohou dodatečně opravovat data. Model používá gradient boosting s histogramy, vlastní cenové indikátory a podle dostupnosti DXY, výnos 10letých amerických dluhopisů, BTC a S&P 500 s časovým posunem.

Walk-forward má rozšiřující se trénink, testovací bloky a používá pouze výsledky známé před každým blokem. Sigmoidová kalibrace používá starší out-of-sample odhady ukončené před koncovým testem. Závěrečné metriky jsou na časově nepřekrývajících se výhledech. Porovnání používá 50% odhad a historickou četnost růstu v kalibrační sadě. Pokud je méně než 50 pozorování nebo model nezlepší Brier skóre obou baseline alespoň o 0,005, rozhraní zobrazuje upozornění. Výsledky neměří ziskovost ani obchodní náklady.

## Produkce

Vytvořte samostatný GitHub repozitář a importujte jej do samostatného Vercel projektu s frameworkem Other. Nastavení build výstupu je ve vercel.json. Ve Vercelu založte Deploy Hook pro hlavní větev a jeho URL uložte jako GitHub Actions secret VERCEL_DEPLOY_HOOK. Workflow potřebuje oprávnění zapsat snapshot do hlavní větve. Spustí se denně v 06:26 UTC nebo ručně. Git ukládá první výhled pro instrument, závěr a verzi modelu, opakovaný běh jej nepřepisuje. Po dosažení cíle se doplní výsledek. Částečný výpadek zachová poslední úspěšný odhad pro postižené trhy a workflow označí výpadek jako chybu. Při úplném výpadku zůstává dostupný poslední snapshot a GitHub Actions zaznamená chybu.

Order flow, funding, likvidace, open interest a sentiment nejsou použity.
