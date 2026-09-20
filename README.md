# Wakeboard

Jednostronicowy panel do wykrywania urządzeń w sieci lokalnej i wysyłania pakietów Wake-on-LAN. Interfejs jest po polsku. Zapisane urządzenia są przechowywane tylko na komputerze uruchamiającym serwer.

## Uruchomienie

Wymagane: Linux, Python 3.10+ oraz polecenia `ip` i `ping`.

```bash
python3 app.py
```

Otwórz `http://127.0.0.1:8000` w przeglądarce. Możesz ustawić ten adres jako stronę startową.

Żeby serwer uruchamiał się automatycznie po zalogowaniu w systemie Linux z systemd, wykonaj jednorazowo:

```bash
bash scripts/install-autostart.sh
```

Potem ustaw `http://127.0.0.1:8000` jako stronę startową przeglądarki. Usługę można zatrzymać poleceniem `systemctl --user stop wakeboard.service`.

Jeśli chcesz otwierać panel z innych urządzeń w tej samej sieci, uruchom `python3 app.py --host 0.0.0.0`, a następnie użyj adresu IP komputera serwera i portu `8000`. Taki panel będzie dostępny dla innych użytkowników sieci, więc uruchamiaj go tylko w zaufanej sieci.

## Jak działa

- **Skanuj sieć** wysyła krótkie zapytania `ping` do adresów w lokalnej podsieci i odczytuje adresy MAC z tablicy sąsiadów systemu. Dla dużych podsieci skanuje bieżący zakres `/24`.
- **Dodaj ręcznie** zapisuje nazwę, opcjonalny IPv4 i adres MAC. Gdy podasz tylko IP urządzenia, które jest aktualnie online, panel spróbuje sam odczytać MAC.
- **Wybudź** wysyła pakiet magiczny UDP na port 9 pod adres rozgłoszeniowy lokalnej sieci.

Wake-on-LAN musi być włączone na urządzeniu docelowym w BIOS/UEFI oraz w ustawieniach karty sieciowej. Nie każde urządzenie odpowiada na skanowanie, dlatego ręczne dodawanie MAC jest przydatne także dla sprzętu wyłączonego. Zapisane urządzenia znajdują się w `data/devices.json`; ten katalog oraz `.env` są ignorowane przez Git.
