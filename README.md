# OpenMooring ⚓

OpenMooring è uno strumento open-source scritto in Python per l'analisi statica del bilancio delle forze e la distribuzione del carico sulle linee di ormeggio delle navi, sviluppato come supporto operativo e ingegneristico seguendo i principi guida OCIMF MEG4.

## Caratteristiche
- Calcolo delle forze ambientali (vento e corrente) secondo le formule implementate nel motore idrodinamico del progetto.
- Risoluzione della matrice di rigidezza 2D/3D per la ripartizione dei carichi sui cavi attivi.
- Interfaccia grafica interattiva sviluppata in Streamlit.
- Gestione di certificati e componenti delle linee di ormeggio.
- Storico persistente delle linee e delle sessioni operative.
- Ispezione visiva assistita da AI, con conferma dell'operatore.
- Criterio operativo configurato per questa applicazione: **55% MBL**. Il valore è un criterio operativo del progetto e non deve essere interpretato come un limite universale imposto da MEG4.

## Principio di affidabilità dei dati
I risultati operativi devono essere basati su dati identificabili e tracciabili. L'applicazione non deve presentare valori simulati o di esempio come dati live, misure reali o risultati di calcolo.

## Interactive Mooring Station Plan
Il ramo `feature/interactive-mooring-plan` introduce una nuova architettura nella quale il database è la fonte unica per la configurazione geometrica:

`DATABASE → COMPONENTS / CONNECTIONS → 2D PLAN ↔ 3D VIEW → CALCULATION`

Il drawing tecnico resta una **reference layer**. Le coordinate e le connessioni di progetto non vengono dedotte automaticamente dal semplice aspetto grafico quando il dato non è disponibile.

La prima stazione in fase di mappatura è la **AFT / Poppa**. Il drawing `006242A2C010105_01_101832731607(1)` fornisce identificazione e descrizione di numerosi equipment (winch, bollard, Panama chock, universal fairlead, vertical guide roller ed external roller). Questi dati sono presenti nel catalogo sorgente `core/mooring_station_catalog.py`; le posizioni rimangono da calibrare sul drawing reale.

### Geometria delle linee
Il modello iniziale rappresenta il percorso operativo come:

`WINCH → FAIRLEAD / CHOCK → SHORE BOLLARD`

Il programma calcola automaticamente la **centerline direction change** quando tutte le coordinate XYZ sono disponibili. Il **fairlead contact/wrap angle** rimane volutamente non valorizzato fino a quando diametro e geometria di contatto della fairlead sono disponibili. Non vengono inventati coefficienti di attrito.

### Uso della nuova pagina
La pagina Streamlit `2_Interactive_Mooring_Plan.py` permette di:
1. caricare il pianetto reale;
2. importare il catalogo equipment AFT derivato dal drawing;
3. mappare componenti sul piano;
4. associare Winch/Fairlead/Bollard alle linee presenti nell'inventario;
5. visualizzare la configurazione nella vista 3D.

La vista 3D contiene attualmente un **ship envelope visuale** basato sulle dimensioni principali della nave. Non viene utilizzato dal solver come geometria idrodinamica o strutturale.

## Installazione e Avvio
1. Clona il repository.
2. Installa le dipendenze da `requirements.txt`.
3. Configura le credenziali/API necessarie tramite Streamlit Secrets quando richiesto.
4. Avvia l'applicazione Streamlit.
