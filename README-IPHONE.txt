VILO NA IPHONE — ROZSZERZENIE ISTNIEJĄCEGO PROJEKTU (0.5)

Co dodano:
- manifest PWA: instalowanie ikonki na ekranie początkowym iPhone'a
- iPhone touch icon i ikony 192/512
- ustawienia Safari i pełnoekranowy widok aplikacji
- poprawki mobilne (safe area, klawiatura, przyciski)
- service worker: buforuje WYŁĄCZNIE publiczny kod i ikony interfejsu, NIGDY konta, wiadomości ani załączniki

WAZNE: to nie jest plik .ipa ani aplikacja App Store.
Wersja NIE ma hostingu HTTPS i NIE jest jeszcze usługą internetową.

Aby używać na iPhone poza komputerem:
1. Najpierw trzeba wdrożyć backend na zaufanym hostingu HTTPS z trwałą bazą danych.
2. Backend w tym projekcie opisany jest jako local-first / nieaudytowany do publicznej sieci.
   Nie wystawiaj go bezpośrednio do internetu, nie przekierowuj portu 8765 na routerze.
   Przed publicznym uruchomieniem potrzebny jest przegląd bezpieczeństwa, konfiguracji,
   sesji, limitów, przechowywania danych, kopii zapasowych i ochrony prywatności.
3. Dopiero pod adresem HTTPS otwórz Safari na iPhonie: Udostępnij -> Dodaj do ekranu początkowego.
4. Po dodaniu aplikacja VILO będzie miała ikonę i własny widok, jednak do czatu nadal potrzebne jest połączenie z serwerem.

Na Windows projekt nadal można uruchamiać przez Electron. Jeśli lokalnie zgłasza
ModuleNotFoundError: No module named 'PIL', zainstaluj Pillow i pozostałe pakiety:
  py -3 -m pip install -r backend/requirements.txt

Ten pakiet zawiera pełny projekt 0.5 plus przygotowanie PWA; nie zawiera instalatora iOS.
