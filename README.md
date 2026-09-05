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

## Installazione e Avvio
1. Clona il repository.
2. Installa le dipendenze da `requirements.txt`.
3. Configura le credenziali/API necessarie tramite Streamlit Secrets quando richiesto.
4. Avvia l'applicazione Streamlit.
