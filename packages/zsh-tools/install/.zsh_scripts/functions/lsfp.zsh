lsfp() {
	if [[ "$1" == "-h" || "$1" == "--help" ]]; then
		cmdhelp "${funcstack[1]}"
		return $?
	fi

  	emulate -L zsh
  	setopt nullglob extendedglob
  	local -a opts operands files dirs abs
  	local inopts=1 a
  	for a in "$@"
  	do
  		if (( inopts )) && [[ "$a" == -- ]]
  		then
  			inopts=0
  		elif (( inopts )) && [[ "$a" == -* && "$a" != "-" ]]
  		then
  			opts+=("$a")
  		else
  			operands+=("$a")
  			inopts=0
  		fi
  	done
  	local flag_a=0 flag_A=0 flag_d=0
  	for a in "${opts[@]}"
  	do
  		if [[ "$a" == --* ]]
  		then
  			[[ "$a" == "--all" ]] && flag_a=1
  			[[ "$a" == "--almost-all" ]] && flag_A=1
  			[[ "$a" == "--directory" ]] && flag_d=1
  		else
  			[[ "$a" == -*a* ]] && flag_a=1
  			[[ "$a" == -*A* ]] && flag_A=1
  			[[ "$a" == -*d* ]] && flag_d=1
  		fi
  	done
  	if (( ! flag_a && ! flag_A ))
  	then
  		opts=("-A" "${opts[@]}")
  		flag_A=1
  	fi
  	(( ${#operands} == 0 )) && operands=(.)
  	for a in "${operands[@]}"
  	do
  		a="${~a}"
  		a="${a:a}"
  		abs+=("$a")
  	done
  	if (( flag_d ))
  	then
  		command ls "${opts[@]}" -- "${abs[@]}"
  		return $?
  	fi
  	for a in "${abs[@]}"
  	do
  		if [[ -d "$a" ]]
  		then
  			dirs+=("$a")
  		else
  			files+=("$a")
  		fi
  	done
  	local rc=0
  	if (( ${#files} ))
  	then
  		command ls "${opts[@]}" -- "${files[@]}" || rc=$?
  	fi
  	if (( ${#dirs} ))
  	then
  		(( ${#files} && ${#dirs} )) && print
  		local i d ndirs=${#dirs}
  		for i in {1..$ndirs}
  		do
  			d="${dirs[i]}"
  			if (( ndirs > 1 || ${#files} > 0 ))
  			then
  				print -r -- "${d}:"
  			fi
  			local -a entries=()
  			if (( flag_a ))
  			then
  				entries+=("$d/." "$d/..")
  				entries+=("$d"/*(N) "$d"/.[!.]*(N) "$d"/..?*(N))
  			else
  				entries+=("$d"/*(N) "$d"/.[!.]*(N) "$d"/..?*(N))
  			fi
  			if (( ${#entries} ))
  			then
  				command ls -d "${opts[@]}" -- "${entries[@]}" || rc=$?
  			fi
  			if (( (ndirs > 1 || ${#files} > 0) && i < ndirs ))
  			then
  				print
  			fi
  		done
  	fi
  	return $rc
}
