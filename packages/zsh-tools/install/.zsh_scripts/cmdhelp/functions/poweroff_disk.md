# poweroff_disk

wrapper na: udisksctl power-off -b <device>

## Użycie

```bash
poweroff_disk <device>
poweroff_disk [-h|--help]
```

## Opcje

- `-h`, `--help` — pokaż pomoc

## Efekt końcowy

Dysk zostaje "power-off" przez udisks (o ile nic go nie używa).

## Przykłady

```bash
poweroff_disk /dev/sdb
poweroff_disk /dev/sdX
```
