jlogpretty() {
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
		cmdhelp "${funcstack[1]}"
		return $?
  	fi

  	local svc="$1"
  	if [ -z "$svc" ]
  	then
  		echo "Użycie: jlog NAZWA_USLUGI (bez .service albo z)"
  		return 1
  	fi
  	if [[ "$svc" != *.service ]]
  	then
  		svc="${svc}.service"
  	fi
  	journalctl --user -u "$svc" -n 50 -f -o cat
}
