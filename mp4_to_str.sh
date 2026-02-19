#!/bin/bash

extraer_subs() {
    input="$1"
    base="${input%.*}"

    # Obtener índices e idiomas (sin ruido)
    ffprobe -v error -select_streams s \
    -show_entries stream=index:stream_tags=language \
    -of csv=p=0 "$input" | grep -E "spa|eng" | while IFS=',' read -r index lang
    do
        echo "index: $index, lang: $lang"
        [ -z "$lang" ] && lang="und"
        output="${base}.${lang}.srt"
        while [ -f "$output" ]; do
            output="${output}.srt"
        done
        ffmpeg -loglevel error -nostats -y \
        -i "$input" -map 0:$index -c:s srt \
        "$output"
    done
}

if [ -f "$1" ]; then
    extraer_subs "$1"

elif [ -d "$1" ]; then
    for file in "$1"/*.mp4; do
        [ -e "$file" ] && extraer_subs "$file"
    done
else
    echo "Uso: $0 <archivo.mp4 | carpeta>" >&2
    exit 1
fi
