# unmount_partition

wrapper na: udisksctl unmount -b <device>

## Użycie

```bash
unmount_partition <sciezka do partycji>
unmount_partition [-h|--help]
```

## Opcje

- `-h`, `--help` — pokaż pomoc

## Efekt końcowy

Partycja zostaje odmontowana (udisks).

## Przykłady

```bash
unmount_partition /dev/sdb1
unmount_partition /dev/sdXN
```
