# kswapd-summary.sh

Krótka komenda do jednorazowego profilu **CPU wątków `kswapd*`** na podstawie `pidstat`.

## Co mierzy

W każdej próbce zbiera sumę **%CPU wszystkich wątków `kswapd*`**.
Na końcu pokazuje:

- `min`
- `avg`
- `max`
- `Time ≥ threshold` — procent próbek powyżej zadanego progu

Wynik jest podany jako **% jednego rdzenia CPU**.

## Użycie

```bash
kswapd-summary.sh [interval_s=1] [duration_s=300] [threshold_pct=1]
```

## Argumenty

- `interval_s` — odstęp próbkowania w sekundach; praktycznie trzymaj się `>= 1`, bo `pidstat` działa sensownie per-sekundowo
- `duration_s` — łączny czas testu w sekundach
- `threshold_pct` — próg procentowy dla metryki `Time ≥ threshold`

## Wymagania

- `pidstat` z pakietu `sysstat`
- najlepiej uruchamiać przez `sudo`, żeby widzieć wątki jądra

## Przykłady

```bash
sudo kswapd-summary.sh 1 600 1
sudo kswapd-summary.sh 2 300 5
```

## Interpretacja

- stale `>5–10%` przez dłuższy czas zwykle oznacza wyraźną presję pamięci / kosztowny reclaim
- krótkie piki `1–2%` są zwykle normalnym tłem
- jeśli wynik daje `Brak próbek`, najpierw sprawdź `sysstat` i uruchomienie przez `sudo`
