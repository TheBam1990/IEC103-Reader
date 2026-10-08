# IEC103 Reader für Windows

Portable grafische Anwendung zum Lesen und Analysieren von IEC 60870-5-103 über eine serielle RS-485-Verbindung.

## Funktionen

- läuft als einzelne `IEC103-Reader.exe` ohne Installation
- COM-Port, Baudrate, Datenbits, Parität und Stoppbits einstellbar
- Linkadresse und IEC103 Common Address einstellbar
- passives Mithören oder aktiver Masterbetrieb
- Link-Reset, Klasse-1-/Klasse-2-Abfrage und Generalabfrage
- laufende RX-/TX-Telegrammanzeige mit Prüfsummenfehlern
- Sitzungslog `IEC103-Telegrammverkehr.txt` neben der EXE; wird bei jedem Programmstart neu begonnen
- begrenztes Trafficfenster, damit der Speicher nicht unbegrenzt wächst
- Wertetabelle mit CA, FUN, INF, ASDU-Typ, Empfangswert, Faktor, berechnetem Wert, Qualität und Zeitstempel
- frei einstellbarer und dauerhaft gespeicherter Faktor pro gelesenem Zahlenwert
- pro logischer Adresse/Datenelement nur eine Tabellenzeile; neue Werte aktualisieren die vorhandene Zeile
- CSV-Export der aktuellen Wertetabelle
- Speicherung der seriellen Einstellungen im Benutzerprofil
- bekannte IEC103-ASDUs 1–11 und 20–31
- unbekannte sowie herstellerspezifische ASDUs bleiben als Rohdaten sichtbar

## Anschluss

Ein USB-RS485-Adapter muss unter Windows als COM-Port vorhanden sein. Die Polarität der A/B-Leitungen sowie Abschluss- und Bias-Widerstände müssen zur Anlage passen. Das Programm installiert keinen Hardwaretreiber.

Typische IEC103-Startwerte:

| Einstellung | Typischer Wert |
|---|---:|
| Baudrate | 9600 |
| Datenbits | 8 |
| Parität | gerade (`E`) |
| Stoppbits | 1 |
| Linkadresse | 1 |
| Common Address | 1 |

Die tatsächlich benötigten Adressen stehen in der Parametrierung des Schutzgeräts.

## Bedienung

1. RS485-Adapter anschließen und **Ports neu laden** drücken.
2. COM-Port und Übertragungsparameter einstellen.
3. Für reine Diagnose **Aktiver Master** abwählen; zum aktiven Lesen eingeschaltet lassen.
4. **Verbinden** drücken.
5. Im Masterbetrieb sendet das Programm einen Link-Reset, optional eine Generalabfrage und danach zyklische Klasse-1-/Klasse-2-Abfragen.
6. Links erscheinen die vollständigen Telegramme. Rechts werden dekodierte Werte aktualisiert.

Alle Zeilen aus dem Telegrammfenster werden gleichzeitig in
`IEC103-Telegrammverkehr.txt` im Ordner der EXE geschrieben. Die Datei wird bei
jedem Programmstart geleert und neu angelegt; ältere Sitzungen werden nicht
angehängt.

Die Spalte **Anzahl** zeigt, wie oft das jeweilige Element empfangen wurde. Ein neuer Empfang legt daher keine doppelte Tabellenzeile an.

### Messwerte umrechnen

Einen Zahlenwert in der rechten Tabelle markieren und **Faktor für Wert setzen**
anklicken oder die Tabellenzeile doppelt anklicken. Das Programm speichert den
Faktor getrennt für die genaue Kombination aus CA, FUN, INF, ASDU-Typ und
Messwertnummer. Die Spalte **Empfangen** bleibt unverändert; **Berechnet** zeigt
`Empfangen × Faktor`. Mit Faktor `1` sind beide Werte identisch.

Bei ASDU/TK 3 und 9 trennt der Decoder den vorzeichenbehafteten 13-Bit-MVAL
korrekt von den drei Statusbits und zeigt den normierten Empfangswert an.

## Datentypen

Der Decoder kennt die standardisierten ASDU-Typkennungen 1–11 und 20–31. Messwerte I/II, Ereignisse, Zeitinformationen, Identifikation, Befehle, generische Daten sowie Störschriebdaten werden jeweils soweit sicher möglich aufgeteilt. Bei generischen, herstellerspezifischen oder unbekannten Strukturen zeigt die Anwendung zusätzlich immer die vollständigen Rohbytes. Dadurch werden auch nicht bekannte Datentypen sichtbar, ohne sie fälschlich als einen Standardwert zu interpretieren.

Normalisierte IEC103-Messwerte werden zunächst als Wert zwischen ungefähr `-1` und `+1` dargestellt. Für die Umrechnung in Volt, Ampere oder Watt werden die gerätespezifischen Nennwerte und Faktoren aus der Herstellerdokumentation benötigt.

## EXE selbst bauen

Auf einem Windows-Rechner `build-windows.bat` starten. Das Skript erzeugt:

```text
dist\IEC103-Reader.exe
```

Alternativ baut der GitHub-Workflow die EXE reproduzierbar auf einem aktuellen Windows-Runner.

## Sicherheit

Die Anwendung führt keine Shellbefehle aus und benötigt keine Administratorrechte. Im aktiven Masterbetrieb werden Abfragen auf den IEC103-Bus gesendet. Für vollständig passives Beobachten muss **Aktiver Master** deaktiviert sein.

## Lizenz

MIT
