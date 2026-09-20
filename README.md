# Wakeboard

Jednostronicowy panel do wykrywania urządzeń w sieci lokalnej i wysyłania pakietów Wake-on-LAN. Interfejs jest po polsku. Zapisane urządzenia są przechowywane tylko na komputerze uruchamiającym serwer.

## Uruchomienie

Wymagane: Linux, Python 3.10+ oraz polecenia `ip` i `ping`.

```bash
python3 app.py
```

Otwórz `http://127.0.0.1:8000` w przeglądarce. Możesz ustawić ten adres jako stronę startową.

### Docker (Linux)

Docker Compose uruchamia aplikację w sieci hosta, dzięki czemu skanowanie i pakiety Wake-on-LAN korzystają z lokalnej karty sieciowej. Zapisane urządzenia pozostają w katalogu `data/` na hoście.

```bash
mkdir -p data
WAKEBOARD_UID=$(id -u) WAKEBOARD_GID=$(id -g) docker compose up -d --build
```

Panel będzie dostępny pod `http://127.0.0.1:8000`. Jeśli aplikacja uruchomiona bez Dockera zajmuje już port 8000, zatrzymaj ją albo wybierz inny port, np. `WAKEBOARD_PORT=8001 WAKEBOARD_UID=$(id -u) WAKEBOARD_GID=$(id -g) docker compose up -d --build`. Do zatrzymania kontenera użyj `docker compose down`. Zmienne `WAKEBOARD_UID` i `WAKEBOARD_GID` pozwalają kontenerowi odczytać i zapisać `data/devices.json` z uprawnieniami bieżącego użytkownika.

Żeby serwer uruchamiał się automatycznie po zalogowaniu w systemie Linux z systemd, wykonaj jednorazowo:

```bash
bash scripts/install-autostart.sh
```

Potem ustaw `http://127.0.0.1:8000` jako stronę startową przeglądarki. Usługę można zatrzymać poleceniem `systemctl --user stop wakeboard.service`.

Jeśli chcesz otwierać panel z innych urządzeń w tej samej sieci, uruchom `python3 app.py --host 0.0.0.0`, a następnie użyj adresu IP komputera serwera i portu `8000`. Taki panel będzie dostępny dla innych użytkowników sieci, więc uruchamiaj go tylko w zaufanej sieci.

## Jak działa

- **Skanuj sieć** wysyła krótkie zapytania `ping` do adresów w lokalnej podsieci, odczytuje adresy MAC z tablicy sąsiadów systemu i próbuje pobrać nazwy hostów przez reverse DNS lub mDNS. Dla dużych podsieci skanuje bieżący zakres `/24`.
- **Dodaj ręcznie** zapisuje nazwę, opcjonalny IPv4 i adres MAC. Gdy podasz tylko IP urządzenia, które jest aktualnie online, panel spróbuje sam odczytać MAC.
- **Wybudź** wysyła pakiet magiczny UDP na port 9 pod adres rozgłoszeniowy lokalnej sieci.

Wake-on-LAN musi być włączone na urządzeniu docelowym w BIOS/UEFI oraz w ustawieniach karty sieciowej. Nie każde urządzenie odpowiada na skanowanie lub udostępnia nazwę hosta, dlatego ręczne dodawanie MAC jest przydatne także dla sprzętu wyłączonego. Zapisane urządzenia znajdują się w `data/devices.json`; ten katalog oraz `.env` są ignorowane przez Git.
