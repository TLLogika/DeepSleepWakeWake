# Wakeboard

Jednostronicowy panel do wykrywania urządzeń w sieci lokalnej i wysyłania pakietów Wake-on-LAN. Interfejs jest po polsku. Zapisane urządzenia są przechowywane tylko na komputerze uruchamiającym serwer.

## Uruchomienie

Wymagane: Linux, Python 3.10+ oraz polecenie `ip`. Zalecane jest `arp-scan` z uprawnieniem `CAP_NET_RAW`; bez niego aplikacja używa `ping` i tablicy sąsiadów, co może pominąć część urządzeń.

```bash
python3 app.py
```

Otwórz `http://127.0.0.1:8000` w przeglądarce. Możesz ustawić ten adres jako stronę startową.

### Docker (Linux)

Docker Compose uruchamia aplikację w sieci hosta, dzięki czemu skanowanie i pakiety Wake-on-LAN korzystają z lokalnej karty sieciowej. Obraz zawiera `arp-scan` z uprawnieniem `CAP_NET_RAW`. Przy starcie kontener nadaje użytkownikowi aplikacji dostęp do katalogu `data/`, a potem uruchamia ją bez uprawnień roota. Zapisane urządzenia pozostają w katalogu `data/` na hoście.

```bash
mkdir -p data
WAKEBOARD_UID=$(id -u) WAKEBOARD_GID=$(id -g) docker compose up -d --build
```

Jeśli pojawi się błąd dostępu do `/var/run/docker.sock`, użyj `sudo WAKEBOARD_UID=$(id -u) WAKEBOARD_GID=$(id -g) docker compose up -d --build` (oraz `sudo docker compose down` przy zatrzymywaniu).

Kontener nasłuchuje na `0.0.0.0:9000`. Panel otworzysz na tym komputerze pod `http://127.0.0.1:9000`, a z innego urządzenia w LAN pod `http://ADRES_IP_KOMPUTERA:9000`. Panel jest dostępny dla innych użytkowników tej sieci, więc uruchamiaj go w zaufanej sieci. Do zatrzymania kontenera użyj `docker compose down`. Zmienne `WAKEBOARD_UID` i `WAKEBOARD_GID` pozwalają kontenerowi odczytać i zapisać `data/devices.json` z uprawnieniami bieżącego użytkownika.

### Wersja

Numer wydania i data z godziną oraz minutą są zapisane w `version.json` i widoczne na dole panelu. Czas jest podawany dla strefy `Europe/Warsaw`. Przed każdym następnym wydaniem uruchom `python3 scripts/bump-version.py`; skrypt zwiększy numer, np. z `1.0v` na `1.1v`, i zapisze aktualny czas wydania.

Żeby serwer uruchamiał się automatycznie po zalogowaniu w systemie Linux z systemd, wykonaj jednorazowo:

```bash
bash scripts/install-autostart.sh
```

Potem ustaw `http://127.0.0.1:8000` jako stronę startową przeglądarki. Usługę można zatrzymać poleceniem `systemctl --user stop wakeboard.service`.

Jeśli chcesz otwierać panel z innych urządzeń w tej samej sieci, uruchom `python3 app.py --host 0.0.0.0`, a następnie użyj adresu IP komputera serwera i portu `8000`. Taki panel będzie dostępny dla innych użytkowników sieci, więc uruchamiaj go tylko w zaufanej sieci.

## Jak działa

- **Skanuj sieć** używa `arp-scan` do wykrywania urządzeń odpowiadających na ARP, także gdy blokują ping. Jeśli `arp-scan` nie jest zainstalowany, używa `ping` i tablicy sąsiadów systemu. Próbuje pobrać nazwy urządzeń przez reverse DNS lub mDNS. Adresy MAC nie są wyświetlane w wynikach skanowania. Dla dużych podsieci skanuje bieżący zakres `/24`.
- **Podsieć do skanowania** pozwala wybrać interfejs i wpisać własny zakres IPv4 w formacie CIDR, np. `192.168.0.0/25`. Zakres musi należeć do sieci podłączonej do wybranego interfejsu i może obejmować najwyżej 256 adresów (`/24`). Puste pole przywraca automatyczny zakres. Wybrany interfejs jest używany także do wysłania Wake-on-LAN.
- **Dodaj ręcznie** zapisuje nazwę, opcjonalny IPv4 i adres MAC wpisany w sześciu polach po dwa znaki. Urządzenie może być wyłączone. Gdy podasz tylko IP urządzenia, które jest aktualnie online, panel spróbuje sam odczytać MAC.
- **Wybudź** wysyła pakiet magiczny UDP na port 9 pod adres rozgłoszeniowy lokalnej sieci.

Wake-on-LAN musi być włączone na urządzeniu docelowym w BIOS/UEFI oraz w ustawieniach karty sieciowej. Skan wykrywa urządzenia osiągalne z komputera z serwerem; sieć gościnna, izolacja klientów Wi-Fi i wyłączony sprzęt mogą ukryć inne urządzenia. Nie każde urządzenie udostępnia nazwę hosta, dlatego ręczne dodawanie MAC jest przydatne. Zapisane urządzenia znajdują się w `data/devices.json`; ten katalog oraz `.env` są ignorowane przez Git.
