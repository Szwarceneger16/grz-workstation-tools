# get_app_mem

Pokazuje PID-y i parametry pamięci Node (max-old-space-size / NODE_OPTIONS) dla procesu pasującego do wzorca

## Użycie

```bash
get_app_mem <pattern>
get_app_mem [-h|--help]
```

## Opcje

- <pattern> Wzorzec dla pgrep -af (np. "node", "nx", "webpack", "code")
- `-h`, `--help` — pokaż pomoc

## Co robi

Wypisuje:

- PID
- wykryty flag: --max-old-space-size=...
- NODE_OPTIONS z /proc/<pid>/environ
- pełny cmdline z /proc/<pid>/cmdline

## Efekt końcowy

Dostajesz szybki podgląd limitów pamięci Node dla działających procesów.

## Przykłady

```bash
get_app_mem nx
get_app_mem --help
```
