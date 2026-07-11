jlog-system() {
	if [[ "$1" == "-h" || "$1" == "--help" ]]; then
		cmdhelp "${funcstack[1]}"
		return $?
	fi

	local svc="$1"
	if [ -z "$svc" ]
	then
		echo "Użycie: jlog-system NAZWA_USLUGI (bez .service albo z)"
		return 1
	fi
	if [[ "$svc" != *.service ]]
	then
		svc="${svc}.service"
	fi
	if [[ "$svc" == -* ]]
	then
		echo "Nazwa usługi nie może zaczynać się od '-'"
		return 1
	fi
	journalctl -u "$svc" -f
}
