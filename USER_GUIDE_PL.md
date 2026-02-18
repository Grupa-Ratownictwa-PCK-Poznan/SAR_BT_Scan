# SAR BT+WiFi Scanner - Podręcznik Użytkownika

## Co to jest?

SAR BT Scanner to przenośny system wykrywania urządzeń zaprojektowany dla **operacji poszukiwawczo-ratowniczych (SAR)**. Wykrywa sygnały bezprzewodowe z telefonów, smartwatchy, opasek fitness i innych urządzeń Bluetooth/WiFi, które może mieć przy sobie osoba zaginiona.

**Główne możliwości:**
- Wykrywa urządzenia Bluetooth w zasięgu ~50-100 metrów
- Przechwytuje żądania WiFi probe z telefonów szukających znanych sieci
- Oznacza wszystkie wykrycia współrzędnymi GPS i znacznikami czasu
- Pomaga odróżnić sprzęt zespołu SAR od potencjalnych urządzeń celu

---

## Rozpoczęcie pracy

### 1. Włączenie zasilania

Podłącz skaner do zasilania. System automatycznie:
- Zainicjuje GPS i poczeka na fix satelitarny
- Rozpocznie skanowanie urządzeń Bluetooth i WiFi
- Uruchomi panel webowy

### 2. Oczekiwanie na fix GPS

Przed wejściem w obszar poszukiwań upewnij się, że wskaźnik GPS pokazuje fix:
- **3D Fix** (zielony) - Optymalny, pełne współrzędne z wysokością
- **2D Fix** (żółty) - Akceptowalny, brak danych o wysokości
- **NO FIX** (czerwony) - Czekaj na satelity, dane GPS będą brakować

### 3. Dostęp do panelu

Na dowolnym urządzeniu podłączonym do tej samej sieci otwórz przeglądarkę i przejdź do:

```
http://<adres-ip-skanera>:8000
```

Adres IP jest zazwyczaj wyświetlany na ekranie skanera lub można go znaleźć w routerze.

---

## Przegląd panelu webowego

### Panel statusu (góra)

| Wskaźnik | Znaczenie |
|----------|-----------|
| **GPS** | Status fixu satelitarnego i liczba satelitów |
| **Mode** | Aktualny tryb skanowania (BT/WiFi/Both) |
| **WiFi Mon** | Tryb monitorowania WiFi aktywny (ON/OFF) |
| **Time** | Aktualny czas UTC |

### Zakładki danych

| Zakładka | Zawartość |
|----------|-----------|
| **BT Devices** | Unikalne wykryte urządzenia Bluetooth |
| **BT Sightings** | Pojedyncze zdarzenia wykrycia z RSSI |
| **WiFi Devices** | Unikalne adresy MAC WiFi |
| **WiFi Assoc** | Żądania WiFi probe z nazwami SSID |

### Widok mapy

Mapa pokazuje mapę cieplną lokalizacji wykryć:
- **Obszary czerwone/pomarańczowe** = Wiele wykryć (prawdopodobnie pozycje zespołu SAR)
- **Obszary niebieskie/zielone** = Mniej wykryć (potencjalnie interesujące)

Użyj przełącznika warstw, aby przełączać między widokiem tylko BT, tylko WiFi lub łączonym.

---

## Zrozumienie wyników pewności (Confidence)

Każde urządzenie otrzymuje **wynik pewności od 0-100** wskazujący, jak prawdopodobne jest, że należy do osoby zaginionej w porównaniu ze sprzętem zespołu SAR.

### Zakresy wyników

| Wynik | Interpretacja | Działanie |
|-------|---------------|-----------|
| **70-100** | Możliwe urządzenie osoby zaginionej | Zbadaj natychmiast |
| **31-69** | Niepewne pochodzenie | Przejrzyj szczegóły |
| **0-30** | Prawdopodobnie sprzęt zespołu SAR | Niższy priorytet |

### Co wpływa na wynik?

**Niższe wyniki (prawdopodobnie zespół SAR):**
- Urządzenie obecne przez całą sesję
- Silny sygnał na początku i końcu sesji
- Zawsze wykrywane w pobliżu HQ/miejsca zbiórki
- Widziane w wielu sesjach poszukiwawczych

**Wyższe wyniki (możliwy cel):**
- Urządzenie pojawiło się tylko w środku sesji
- Krótkie okno wykrycia
- Wykryte daleko od lokalizacji HQ
- Nigdy wcześniej nie widziane

### Uruchamianie analizy

1. Kliknij przycisk **"Analyze Confidence"** na pasku bocznym
2. Przejrzyj podgląd pokazujący proponowane zmiany wyników
3. Kliknij **"Apply Changes"** aby zaktualizować wyniki
4. Filtruj listę urządzeń według pewności, aby skupić się na celach o wysokim priorytecie

---

## Zarządzanie urządzeniami zespołu (Whitelist)

Aby wykluczyć znane urządzenia zespołu z analizy:

### Dodawanie urządzeń do whitelisty

Edytuj plik `device_whitelist.txt` na skanerze:

```text
# Sprzęt zespołu SAR
# Dodaj jeden adres MAC na linię

# Telefon kierownika zespołu
AA:BB:CC:DD:EE:FF

# Tracker pojazdu SAR
11:22:33:44:55:66

# Kontroler drona
AA:BB:CC:11:22:33
```

Urządzenia na whiteliście automatycznie otrzymują wynik pewności = 0.

### Znajdowanie adresu MAC urządzenia

- **iPhone**: Ustawienia → Ogólne → To urządzenie → Adres Wi-Fi
- **Android**: Ustawienia → Informacje o telefonie → Status → Adres MAC Wi-Fi
- **Urządzenia Bluetooth**: Sprawdź opakowanie urządzenia lub aplikację towarzyszącą

---

## Operacje terenowe

### Przed wyjazdem

1. **Naładuj w pełni** - Skaner działa ~8 godzin na powerbanku 10 000 mAh
2. **Przetestuj fix GPS** - Upewnij się, że satelity się połączą przed opuszczeniem miejsca zbiórki
3. **Zaktualizuj whitelistę** - Dodaj wszystkie adresy MAC urządzeń zespołu
4. **Ustaw współrzędne HQ** - Skonfiguruj lokalizację miejsca zbiórki w ustawieniach (opcjonalnie)
5. **Zweryfikuj dostęp do panelu** - Potwierdź, że panel ładuje się na telefonie/tablecie

### Podczas poszukiwań

1. **Poruszaj się równomiernie** - Idź normalnym tempem, zatrzymując się na chwilę w kluczowych miejscach
2. **Zwracaj uwagę na siłę sygnału** - Silne sygnały (> -60 dBm) wskazują na pobliskie urządzenia
3. **Obserwuj pojawienia się w środku sesji** - Nowe urządzenia pojawiające się podczas poszukiwań są interesujące
4. **Zaznaczaj lokalizacje** - Notuj współrzędne GPS znaczących wykryć

### Typowe scenariusze wykrycia

| Scenariusz | Co może oznaczać |
|------------|------------------|
| Silny sygnał, nieruchomy | Urządzenie jest w pobliżu, możliwe że osoba nieruchoma |
| Słaby sygnał, ruchomy | Urządzenie w oddali lub osoba się przemieszcza |
| Urządzenie pojawia się i znika | Osoba przeszła przez obszar |
| WiFi szuka sieci domowej | Właściciel urządzenia mieszka przy tej lokalizacji sieci |

### Po poszukiwaniach

1. **Uruchom analizę pewności** aby ocenić wszystkie urządzenia
2. **Wyeksportuj dane** do raportu z akcji
3. **Wyczyść bazę danych** przed następną akcją (opcjonalnie)
4. **Zrób kopię zapasową pliku bazy** do dokumentacji

---

## Filtrowanie i wyszukiwanie urządzeń

### Według adresu MAC

Wpisz częściowy MAC w polu filtra:
- `AA:BB` znajduje wszystkie MAC zaczynające się od AA:BB
- `EE:FF` znajduje wszystkie MAC kończące się na EE:FF

### Według siły sygnału

Użyj suwaka RSSI, aby skupić się na:
- **Silne sygnały (> -60 dBm)**: Urządzenia w zasięgu ~10 metrów
- **Średnie sygnały (-60 do -80 dBm)**: Urządzenia 10-30 metrów dalej
- **Słabe sygnały (< -80 dBm)**: Odległe urządzenia, 30+ metrów

### Według czasu

Użyj filtra czasowego, aby:
- Usunąć zaszumiony okres uruchamiania
- Skupić się na konkretnych oknach poszukiwań
- Wyizolować czasy, gdy wystąpiła interesująca aktywność

### Według pewności

Filtruj według wyniku pewności, aby:
- Pokazać tylko cele o wysokiej pewności (70+)
- Ukryć prawdopodobny sprzęt SAR (0-30)

---

## Zalecenia i przestrogi

### TAK ✅

- **TAK** dodaj wszystkie urządzenia zespołu do whitelisty przed wyjazdem
- **TAK** czekaj na fix GPS przed rozpoczęciem poszukiwań
- **TAK** uruchamiaj analizę pewności okresowo podczas długich poszukiwań
- **TAK** notuj czas i lokalizację gdy widzisz interesujące urządzenia
- **TAK** ładuj skaner w pełni przed każdą akcją
- **TAK** trzymaj skaner przy sobie (nie w pojeździe) dla lepszego zasięgu
- **TAK** sprawdzaj panel webowy okresowo w poszukiwaniu alertów o wysokiej pewności
- **TAK** dokumentuj i rób kopie zapasowe danych po każdej akcji

### NIE ❌

- **NIE** używaj tego narzędzia do celów innych niż operacje SAR
- **NIE** śledź osób, które nie są oficjalnie zaginione
- **NIE** udostępniaj danych ze skanowania nieautoryzowanym osobom
- **NIE** zakładaj, że wszystkie urządzenia o wysokiej pewności należą do osoby zaginionej
- **NIE** ignoruj słabych sygnałów - mogą wskazywać na odległe cele
- **NIE** uruchamiaj skanera bez GPS - stracisz dane lokalizacyjne
- **NIE** zapominaj o czyszczeniu bazy danych między niepowiązanymi akcjami
- **NIE** umieszczaj skanera w metalowych pojemnikach lub pojazdach (zmniejsza zasięg)

---

## Rozwiązywanie problemów

### GPS pokazuje "NO FIX"

- Przenieś się na otwartą przestrzeń (z dala od budynków/drzew)
- Poczekaj 2-3 minuty na pozyskanie satelitów
- Sprawdź, czy dongle GPS jest mocno podłączony

### Panel webowy się nie ładuje

- Sprawdź, czy skaner jest włączony
- Upewnij się, że jesteś w tej samej sieci
- Spróbuj adresu IP bezpośrednio (nie nazwy hosta)
- Sprawdź, czy `WEB_UI_ENABLED = True` w ustawieniach

### Nie pojawiają się urządzenia

- Potwierdź, że tryb skanowania obejmuje BT i/lub WiFi
- Dla WiFi: zweryfikuj, że tryb monitorowania jest włączony
- Sprawdź, czy adapter Bluetooth jest podłączony
- Przenieś się do obszaru z większą aktywnością bezprzewodową

### Wszystkie urządzenia pokazują pewność = 50

- Uruchom "Analyze Confidence" z panelu
- Upewnij się, że sesja ma wystarczająco danych (10+ minut)
- Sprawdź, czy analiza zakończyła się pomyślnie

### Bateria szybko się rozładowuje

- Normalne zużycie to ~5W
- Oczekiwany czas pracy: ~8 godzin na 10 000 mAh
- Zmniejsz jasność ekranu na podłączonych urządzeniach
- Rozważ większy powerbank do dłuższych operacji

---

## Prywatność danych i etyka

To narzędzie jest zaprojektowane **wyłącznie dla operacji poszukiwawczo-ratowniczych**.

### Dozwolone użycie
- Aktywne operacje SAR dla osób zaginionych
- Ćwiczenia szkoleniowe tylko ze sprzętem zespołu
- Testy i rozwój za zgodą

### Zabronione użycie
- Śledzenie członków rodziny, partnerów lub znajomych
- Jakikolwiek rodzaj inwigilacji
- Monitorowanie pracowników lub sąsiadów
- Jakiekolwiek użycie wymierzone w osoby niezaginione

**Etyczne uzasadnienie dla tego narzędzia istnieje tylko wtedy, gdy istnieje rzeczywiste zagrożenie dla ludzkiego życia.**

Pełne wytyczne etyczne znajdziesz w [ETHICS.md](ETHICS.md).

---

## Skrócona karta referencyjna

### Kluczowe działania

| Działanie | Jak |
|-----------|-----|
| Przeglądaj urządzenia | Otwórz panel webowy, kliknij zakładkę "BT Devices" lub "WiFi Devices" |
| Filtruj według sygnału | Dostosuj suwak RSSI w panelu filtrów |
| Analizuj wyniki | Kliknij "Analyze Confidence" → Przejrzyj → Apply |
| Dodaj urządzenie zespołu | Edytuj `device_whitelist.txt`, dodaj adres MAC |
| Znajdź silne sygnały | Filtruj RSSI > -60 dBm |
| Znajdź nowe urządzenia | Sortuj według "First Seen" malejąco |
| Skup się na celach | Filtruj pewność ≥ 70 |

### Podsumowanie wyników pewności

```
0-30   = Prawdopodobnie zespół SAR (whitelist lub zawsze obecne)
31-69  = Nieznane, wymaga zbadania
70-100 = Możliwy cel (pojawił się w środku sesji, daleko od HQ)
```

### Przewodnik po sile sygnału

```
> -50 dBm  = Bardzo blisko (< 5m)
-50 do -60 = Blisko (5-10m)
-60 do -70 = Średnio (10-20m)
-70 do -80 = Daleko (20-30m)
< -80 dBm  = Bardzo daleko (30m+)
```

---

## Uzyskiwanie pomocy

- **Problemy techniczne**: Sprawdź [README.md](README.md) i [WEB_UI_QUICKSTART.md](docs/WEB_UI_QUICKSTART.md)
- **Ocenianie pewności**: Zobacz [CONFIDENCE_ANALYZER.md](docs/CONFIDENCE_ANALYZER.md)
- **Konfiguracja WiFi**: Zobacz [WIFI_SETUP.md](docs/WIFI_SETUP.md)
- **Repozytorium projektu**: https://github.com/Grupa-Ratownictwa-PCK-Poznan/SAR_BT_Scan

---

*To narzędzie zostało opracowane przez Grupę Ratownictwa PCK Poznań w celu wspierania humanitarnych operacji poszukiwawczo-ratowniczych.*
