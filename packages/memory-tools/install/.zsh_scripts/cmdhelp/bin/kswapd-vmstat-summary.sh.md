# kswapd-vmstat-summary.sh

Krótka komenda do jednorazowego profilu aktywności reclaimu `kswapd` na podstawie liczników z `/proc/vmstat`.

## Co mierzy

Śledzi różnice liczników:

- `pgscan_kswapd*` — ile stron/s przeskanował `kswapd`
- `pgsteal_kswapd*` — ile stron/s realnie odzyskano

Na końcu pokazuje:

- `min / avg / max` dla `scan` i `steal`
- przeliczenie `pages/s -> MiB/s`
- `Time ≥ thresholds`
- `Reclaim efficiency (steal/scan)`

## Użycie

```bash
kswapd-vmstat-summary.sh [interval_s=1] [duration_s=300] [scan_thr_pages_s=256] [steal_thr_pages_s=50]
```

## Argumenty

- `interval_s` — odstęp próbkowania w sekundach; obsługuje też ułamki, np. `0.5`
- `duration_s` — łączny czas pomiaru
- `scan_thr_pages_s` — próg dla `scan` w pages/s
- `steal_thr_pages_s` — próg dla `steal` w pages/s

Przy rozmiarze strony 4 KiB:

- `256 pages/s ≈ 1 MiB/s`

## Przykłady

```bash
kswapd-vmstat-summary.sh 1 600 256 50
kswapd-vmstat-summary.sh 0.5 120 512 100
```

## Interpretacja

- same zera zwykle znaczą brak aktywności `kswapd` w oknie pomiarowym
- reclaim mógł też iść ścieżką `direct reclaim`, której ten skrypt nie liczy
- wysoki `scan` przy słabym `steal` oznacza mało efektywny reclaim

## Szybki podgląd direct reclaim

```bash
watch -n1 'grep -E "pg(scan|steal)_(kswapd|direct)" /proc/vmstat'
```
